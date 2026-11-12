"""Finalize step table: order, kinds, cache settings, blob layout, gates, and envelope handling.

The steps run in ``STEP_ORDER``.  ``validate``, ``bake``, ``variants``, ``export``, ``reimport``,
and ``export_anims`` run in Blender (``scripts/blender/finalize_entry.py``); ``import_ue`` and
``import_anims`` run through the Unreal MCP.  ``export_anims`` and ``import_anims`` are per-clip
steps (#138): ``pipeline/anims.py`` runs them, and each clip is cached on its own key.  Every
Blender step returns a JSON envelope that this module checks and converts into either outputs or a
``PipelineError``.  ``validate``, ``export``, and ``reimport`` also pass their contract reports
through ``quality.contract.gate``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

from nmg_game_dev.quality.contract import gate, load_report

from .errors import PipelineError
from .request import FinalizeRequest

StepName = Literal[
    "validate",
    "bake",
    "variants",
    "export",
    "export_anims",
    "reimport",
    "import_ue",
    "import_anims",
]
StepKind = Literal["blender", "unreal"]

STEP_ORDER: Final[tuple[StepName, ...]] = (
    "validate",
    "bake",
    "variants",
    "export",
    "export_anims",
    "reimport",
    "import_ue",
    "import_anims",
)
VARIANTS: Final[tuple[str, ...]] = ("Desktop", "Mobile")
ENVELOPE_SCHEMA_VERSION: Final = 1

_STEP_VERSION: Final = (
    "4"  # bumped for #148 (material-variants keys) and #138 (per-clip anim steps)
)
_REPO_ROOT: Final = Path(__file__).resolve().parents[3]
_BUDGET_TABLE: Final = (
    _REPO_ROOT / "plugins" / "nmg-game-dev-blender-addon" / "utils" / "budgets.py"
)


@dataclass(frozen=True)
class StepSpec:
    """Static description of one step.

    Attributes:
        name: Step name.
        kind: ``blender`` runs headless Blender; ``unreal`` calls the Unreal MCP.
        mutates_scene: ``True`` when the step writes a new ``.blend`` that feeds the next step.
        per_clip: ``True`` when the step is cached per clip and runs through ``pipeline/anims.py``
            instead of the whole-step cache.  Per-clip steps never change the input hash of the
            steps after them, so a clip-only change leaves the mesh steps' cache entries valid.
    """

    name: StepName
    kind: StepKind
    mutates_scene: bool
    per_clip: bool = False


STEPS: Final[dict[StepName, StepSpec]] = {
    "validate": StepSpec("validate", "blender", mutates_scene=False),
    "bake": StepSpec("bake", "blender", mutates_scene=True),
    "variants": StepSpec("variants", "blender", mutates_scene=True),
    "export": StepSpec("export", "blender", mutates_scene=False),
    "export_anims": StepSpec("export_anims", "blender", mutates_scene=False, per_clip=True),
    "reimport": StepSpec("reimport", "blender", mutates_scene=False),
    "import_ue": StepSpec("import_ue", "unreal", mutates_scene=False),
    "import_anims": StepSpec("import_anims", "unreal", mutates_scene=False, per_clip=True),
}

# The steps each step needs.  ``import_anims`` needs every other step: the sidecar it checks
# against comes from ``export_anims``, and the skeleton it imports onto comes from ``import_ue``.
DEPENDS: Final[dict[StepName, tuple[StepName, ...]]] = {
    "validate": (),
    "bake": ("validate",),
    "variants": ("validate", "bake"),
    "export": ("validate", "bake", "variants"),
    "export_anims": ("validate", "bake", "variants"),
    "reimport": ("validate", "bake", "variants", "export"),
    "import_ue": ("validate", "bake", "variants", "export", "reimport"),
    "import_anims": tuple(step for step in STEP_ORDER if step != "import_anims"),
}


def parse_step(step: str) -> StepSpec:
    """Return the spec for ``step``, or raise ``finalize.unknown_step``."""
    if step not in STEPS:
        raise PipelineError(
            code="finalize.unknown_step",
            message=f"Unknown finalize step {step!r}",
            remediation=f"Use one of: {', '.join(STEP_ORDER)}.",
            stage="finalize",
        )
    return STEPS[step]


def ordered_steps(steps: tuple[str, ...] | list[str]) -> tuple[StepName, ...]:
    """Return the dependency closure of ``steps`` in canonical execution order, de-duplicated.

    Requesting a step also runs every step it depends on (see ``DEPENDS``).  ``import_ue`` gives the
    six-step chain it has always had, and ``export_anims`` leaves out ``reimport`` and
    ``import_ue``.
    """
    pending = [parse_step(step).name for step in steps]
    needed: set[StepName] = set()
    while pending:
        name = pending.pop()
        if name in needed:
            continue
        needed.add(name)
        pending.extend(DEPENDS[name])
    return tuple(name for name in STEP_ORDER if name in needed)


def budget_fingerprint(budgets_path: Path | None) -> str:
    """Return a hash of the budget table and the override file, if any.

    A change to either changes every step key that depends on budgets, without resolving budgets in
    the host process.
    """
    digest = hashlib.sha256()
    digest.update(_BUDGET_TABLE.read_bytes() if _BUDGET_TABLE.is_file() else b"")
    if budgets_path is not None:
        digest.update(budgets_path.read_bytes())
    return digest.hexdigest()


def material_variants_fingerprint(path: Path | None) -> str:
    """Return a hash of the material-variants declaration and the texture bytes it references.

    A missing declaration hashes as absent, so adding or removing one changes the key. Each
    base_color resolves relative to the declaration, as the contract resolves it, and a missing
    texture hashes as absent too.
    """
    digest = hashlib.sha256()
    if path is None or not path.is_file():
        digest.update(b"absent")
        return digest.hexdigest()
    text = path.read_bytes()
    digest.update(b"declaration\0")
    digest.update(text)
    for texture in _declared_textures(text, path.parent):
        digest.update(b"texture\0")
        digest.update(texture.read_bytes() if texture.is_file() else b"absent")
    return digest.hexdigest()


def _declared_textures(text: bytes, base: Path) -> list[Path]:
    """The base_color files a declaration names, resolved beside it. Malformed JSON names none."""
    try:
        data: object = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return []
    entries = data.get("material_variants") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return []
    textures: list[Path] = []
    for entry in entries:
        value = entry.get("base_color") if isinstance(entry, dict) else None
        if isinstance(value, str) and value:
            candidate = Path(value)
            textures.append(candidate if candidate.is_absolute() else base / candidate)
    return textures


def settings_hash(step: StepName, request: FinalizeRequest, budgets: str) -> str:
    """Return the SHA-256 of the canonical settings that a whole-step output depends on.

    Per-clip steps have no whole-step key; see ``clip_settings_hash``.
    """
    settings: dict[str, object] = {"step": step, "version": _STEP_VERSION}
    if step == "validate":
        settings |= {"collection": request.collection, "asset_class": request.asset_class}
        settings["budgets"] = budgets
        settings["material_variants"] = material_variants_fingerprint(
            request.material_variants_path
        )
    elif step == "bake":
        settings |= {
            "collection": request.collection,
            "asset_class": request.asset_class,
            "device": request.device,
        }
        settings["budgets"] = budgets
    elif step == "variants":
        settings |= {"collection": request.collection, "asset_class": request.asset_class}
        settings["budgets"] = budgets
    elif step == "export":
        settings |= {
            "collection": request.collection,
            "category": request.category,
            "asset_class": request.asset_class,
            "export_root": str(request.export_root),
        }
        settings["material_variants"] = material_variants_fingerprint(
            request.material_variants_path
        )
    elif step == "reimport":
        settings["collection"] = request.collection
    elif step == "import_ue":
        settings |= {
            "collection": request.collection,
            "category": request.category,
            "export_root": str(request.export_root),
        }
    else:
        raise ValueError(f"{step} is a per-clip step and has no whole-step settings hash")
    return hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()


def clip_settings_hash(step: StepName, request: FinalizeRequest, *, options: str = "") -> str:
    """Return the SHA-256 of the settings a single clip's export or import depends on (#138).

    ``options`` is the fingerprint of the Blender export options that the probe reports, so the
    export cache follows ``ANIM_EXPORT_OPTIONS`` without the host importing ``bpy``.
    ``compatible_with`` is not included: registration runs on every ``import_anims``.
    """
    settings: dict[str, object] = {
        "step": step,
        "version": _STEP_VERSION,
        "collection": request.collection,
        "category": request.category,
        "export_root": str(request.export_root),
    }
    if step == "export_anims":
        settings["options"] = options
    elif step == "import_anims":
        settings["skeleton"] = desktop_skeleton_path(request)
    else:
        raise ValueError(f"{step} has no per-clip settings hash")
    return hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()


def ue_destination(request: FinalizeRequest, variant: str) -> str:
    """Return the UE folder for ``variant``: ``/Game/<Category>/<Name>/<Variant>``."""
    return f"/Game/{request.category}/{request.collection}/{variant}"


def desktop_skeleton_path(request: FinalizeRequest) -> str:
    """Return the Desktop skeleton asset: ``/Game/<Category>/<Name>/Desktop/SM_<Name>_Skeleton``."""
    return f"{ue_destination(request, 'Desktop')}/SM_{request.collection}_Skeleton"


def envelope_outputs(step: StepName, envelope: Mapping[str, Any]) -> dict[str, Any]:
    """Return a Blender envelope's outputs, or raise its error as a PipelineError."""
    if envelope.get("schemaVersion") != ENVELOPE_SCHEMA_VERSION or envelope.get("step") != step:
        raise PipelineError(
            code="finalize.bad_envelope",
            message=f"The {step} step wrote an envelope for another step or schema",
            remediation="Rerun the step. If it persists, check the Blender entry script version.",
            stage=step,
        )
    error = envelope.get("error")
    if envelope.get("ok") is not True:
        if not isinstance(error, dict):
            raise PipelineError(
                code=f"{step}.failed",
                message=f"The {step} step failed without an error description",
                remediation=f"Read the Blender log for the {step} step and rerun.",
                stage=step,
            )
        code = str(error.get("code", f"{step}.failed"))
        if not code.startswith(f"{step}."):
            # Core codes such as texture.bake_failed surface as <step>.<code>, for example
            # bake.texture.bake_failed, per the design's error list.
            code = f"{step}.{code}"
        raise PipelineError(
            code=code,
            message=str(error.get("message", f"The {step} step failed")),
            remediation=str(error.get("remediation", f"Read the {step} step log and rerun.")),
            stage=step,
        )
    outputs = envelope.get("outputs")
    if not isinstance(outputs, dict):
        raise PipelineError(
            code="finalize.bad_envelope",
            message=f"The {step} step envelope has no outputs object",
            remediation="Check the Blender entry script version.",
            stage=step,
        )
    return dict(outputs)


def gate_outputs(step: StepName, outputs: Mapping[str, Any]) -> None:
    """Apply the contract or re-import gate to every report a step produced.

    Raises ``quality.contract_failed`` or ``quality.reimport_mismatch`` when a report fails, and
    ``quality.report_unreadable`` when a report is missing or malformed.
    """
    if step == "validate":
        gate(load_report(Path(str(outputs["report"]))), "contract")
    elif step == "export":
        for variant in VARIANTS:
            pre_report = Path(str(_variant(outputs, variant)["pre_report"]))
            gate(load_report(pre_report), "contract")
    elif step == "reimport":
        reports = outputs.get("reports")
        if not isinstance(reports, dict):
            raise PipelineError(
                code="finalize.bad_envelope",
                message="The reimport step envelope has no reports object",
                remediation="Check the Blender entry script version.",
                stage="reimport",
            )
        for variant in VARIANTS:
            gate(load_report(Path(str(reports[variant]))), "reimport")


def _variant(outputs: Mapping[str, Any], variant: str) -> Mapping[str, Any]:
    variants = outputs.get("variants")
    if not isinstance(variants, dict) or not isinstance(variants.get(variant), dict):
        raise PipelineError(
            code="finalize.bad_envelope",
            message=f"The export step envelope has no {variant} variant",
            remediation="Check the Blender entry script version.",
            stage="export",
        )
    result: Mapping[str, Any] = variants[variant]
    return result


def blobs_for(step: StepName, outputs: Mapping[str, Any]) -> dict[str, Path]:
    """Return the named files and folders a step's outputs point at, for the cache.

    Restoring a cache hit writes each blob back to the path its outputs name, so these paths are the
    restore targets too.
    """
    if step == "validate":
        return {"validate.report.json": Path(str(outputs["report"]))}
    if step in ("bake", "variants"):
        return {f"{step}.blend": Path(str(outputs["blend"]))}
    if step == "export":
        blobs: dict[str, Path] = {"nmg-variants.json": Path(str(outputs["sidecar"]))}
        for variant in VARIANTS:
            entry = _variant(outputs, variant)
            blobs[variant] = Path(str(entry["dir"]))
            blobs[f"export.pre-report-{variant}.json"] = Path(str(entry["pre_report"]))
        return blobs
    if step == "reimport":
        reports = outputs.get("reports")
        if not isinstance(reports, dict):
            return {}
        return {f"reimport.{variant}.json": Path(str(reports[variant])) for variant in VARIANTS}
    return {}


def chain_input(asset_hash: str, previous_output_hash: str) -> str:
    """Return the input hash for the step after one whose output hashed to ``previous_output_hash``.

    The asset hash is always included.  Blender steps read the checkpoint .blend, not only the
    previous step's output, so a changed material must miss even when an earlier step's output is
    byte-identical.  Hashing the previous output alone would let a stale bake hit.
    """
    return hashlib.sha256(f"{asset_hash}:{previous_output_hash}".encode()).hexdigest()


def output_hash(
    step: StepName,
    outputs: Mapping[str, Any],
    blobs: Mapping[str, Path],
    *,
    job_dir: Path,
) -> str:
    """Return the hash that becomes the next step's input.

    The hash covers the outputs with the job directory replaced by ``$JOB``, so the same content in
    another job hashes the same, plus the bytes of each blob.  A changed mesh, material, or image
    therefore changes every later key.
    """
    digest = hashlib.sha256()
    digest.update(step.encode())
    relocated = json.dumps(outputs, sort_keys=True, default=str).replace(str(job_dir), "$JOB")
    digest.update(relocated.encode())
    for name in sorted(blobs):
        digest.update(name.encode())
        digest.update(_tree_hash(blobs[name]).encode())
    return digest.hexdigest()


def _tree_hash(path: Path) -> str:
    digest = hashlib.sha256()
    if path.is_dir():
        for child in sorted(p for p in path.rglob("*") if p.is_file()):
            digest.update(child.relative_to(path).as_posix().encode())
            digest.update(child.read_bytes())
    elif path.is_file():
        digest.update(path.read_bytes())
    return digest.hexdigest()
