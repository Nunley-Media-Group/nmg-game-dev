"""2D game art from the local texture models: icons, UI panels, and paintings (#253).

``validate_request`` checks one :class:`ArtRequest` (kind, name, prompt, seeds, aspect, backend, and
resolution). ``run`` skips every seed whose raw take already exists, and generates the rest in one
backend batch. Art is never tiled: the worker's PNGs are kept exactly as written, with no seamless
pass and no derived maps.

Raw takes are the kept source under ``SourceArt/Art/raw/<kind>/``. ``<Name>.json`` records the
prompt, the project style, the backend, and the takes, and ``<Name>_sheet.png`` shows every take
side by side. ``nmg_game_dev.texture.art_finish`` turns a picked take into game images.

The prompt is ``<prompt>, <project style>, <kind style>``, and the project style is left out when
``SourceArt/Art/style.json`` is absent (see ``nmg_game_dev.texture.style``).
"""

from __future__ import annotations

import json
import os
import random
import re
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any

from nmg_game_dev.texture import generate
from nmg_game_dev.texture.batch import Batch, ImageItem, Spawn, default_spawn, run_backend_batches
from nmg_game_dev.texture.deps import DepsProbe, require_dependencies
from nmg_game_dev.texture.errors import TextureGenError
from nmg_game_dev.texture.hardware import HardwareFacts, probe, reserve_gb
from nmg_game_dev.texture.paths import models_dir, project_root, weights_dir
from nmg_game_dev.texture.registry import REGISTRY, BackendSpec, resolve
from nmg_game_dev.texture.sheet import compare
from nmg_game_dev.texture.style import project_style

DEFAULT_BACKEND = generate.DEFAULT_BACKEND
MIN_RESOLUTION = 256
MAX_RESOLUTION = 2048
SIDE_MULTIPLE = 64
ASPECT_TOLERANCE = 0.05
NAME_PATTERN = re.compile(r"^[A-Z][A-Za-z0-9]*$")
RAW_RELATIVE = Path("SourceArt") / "Art" / "raw"
MANIFEST_SUFFIX = ".json"
SHEET_SUFFIX = "_sheet.png"


@dataclass(frozen=True)
class KindSpec:
    """What one art kind asks of the model: its framing sentence and the aspects it allows."""

    framing: str
    aspects: tuple[str, ...]
    default_aspect: str


KINDS: Mapping[str, KindSpec] = MappingProxyType(
    {
        "icon": KindSpec(
            framing=(
                "single game item icon, one object centered, whole object visible with empty "
                "space around it, flat plain solid light grey background, no shadow on the "
                "background, no text, no border"
            ),
            aspects=("1:1",),
            default_aspect="1:1",
        ),
        "ui": KindSpec(
            framing=(
                "game interface panel or frame, centered, whole element visible with empty space "
                "around it, flat plain solid light grey background, no text"
            ),
            aspects=("1:1",),
            default_aspect="1:1",
        ),
        "painting": KindSpec(
            framing=(
                "painterly illustration, full composition filling the frame, no text, no border"
            ),
            aspects=("16:9", "3:2", "1:1"),
            default_aspect="16:9",
        ),
    }
)
ASPECT_RATIOS: Mapping[str, tuple[int, int]] = MappingProxyType(
    {"1:1": (1, 1), "3:2": (3, 2), "16:9": (16, 9)}
)


def _random_seed() -> list[int]:
    return [random.randrange(2**31)]


@dataclass(frozen=True)
class ArtRequest:
    """One art request: every take of ``name`` shares its kind, prompt, backend, and size."""

    kind: str
    name: str
    prompt: str
    seeds: list[int] = field(default_factory=_random_seed)
    backend: str = DEFAULT_BACKEND
    aspect: str | None = None
    resolution: int = 1024

    def resolved_aspect(self) -> str:
        """The aspect in use: the request's, else the kind's default. Call after validation."""
        return self.aspect if self.aspect is not None else KINDS[self.kind].default_aspect


@dataclass(frozen=True)
class ArtImage:
    """One newly generated raw take and the seconds the worker spent on it."""

    seed: int
    path: Path
    seconds: float

    def as_json(self) -> dict[str, Any]:
        return {"seed": self.seed, "path": str(self.path), "seconds": self.seconds}


@dataclass(frozen=True)
class ArtResult:
    """What an art run wrote: the new takes, the seeds it skipped, and the manifest and sheet."""

    kind: str
    name: str
    prompt: str
    project_style: str | None
    full_prompt: str
    backend: str
    aspect: str
    width: int
    height: int
    images: tuple[ArtImage, ...]
    skipped: tuple[int, ...]
    manifest: Path
    contact_sheet: Path

    def as_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name,
            "prompt": self.prompt,
            "project_style": self.project_style,
            "full_prompt": self.full_prompt,
            "backend": self.backend,
            "aspect": self.aspect,
            "width": self.width,
            "height": self.height,
            "images": [image.as_json() for image in self.images],
            "skipped": list(self.skipped),
            "manifest": str(self.manifest),
            "contact_sheet": str(self.contact_sheet),
        }


def _invalid(message: str, remediation: str) -> TextureGenError:
    return TextureGenError("texture.invalid_request", message, remediation)


def size(aspect: str, resolution: int) -> tuple[int, int]:
    """``(width, height)``: the long side is ``resolution`` and the short side is the aspect's
    share of it, rounded to a multiple of 64 and never below 64."""
    wide, high = ASPECT_RATIOS[aspect]
    short = max(SIDE_MULTIPLE, round(resolution * high / wide / SIDE_MULTIPLE) * SIDE_MULTIPLE)
    return resolution, short


def _aspect_error(aspect: str, resolution: int) -> float:
    """How far ``size(aspect, resolution)`` is from the aspect's exact ratio, as a fraction."""
    wide, high = ASPECT_RATIOS[aspect]
    width, height = size(aspect, resolution)
    return abs((width / height) / (wide / high) - 1)


def _resolutions_for(aspect: str) -> list[int]:
    """Every allowed resolution whose size keeps ``aspect`` within ``ASPECT_TOLERANCE``."""
    return [
        resolution
        for resolution in range(MIN_RESOLUTION, MAX_RESOLUTION + 1, SIDE_MULTIPLE)
        if _aspect_error(aspect, resolution) <= ASPECT_TOLERANCE
    ]


def validate_request(
    request: ArtRequest, registry: Mapping[str, BackendSpec] = REGISTRY
) -> BackendSpec:
    """Raise ``texture.invalid_request`` for a bad kind, name, prompt, seed list, aspect, backend,
    or resolution, and return the pinned backend the request names."""
    if request.kind not in KINDS:
        raise _invalid(
            f"Unknown art kind {request.kind!r}.",
            "Use --kind icon, ui, or painting.",
        )
    if not NAME_PATTERN.match(request.name):
        raise _invalid(
            f"Art name {request.name!r} is not a PascalCase identifier.",
            "Use a name that starts with a capital letter and holds only letters and digits, "
            "such as HealthPotion.",
        )
    if not request.prompt.strip():
        raise _invalid("The art prompt is empty.", "Pass a non-empty --prompt describing the art.")
    if not request.seeds:
        raise _invalid("No seeds were given.", "Pass at least one seed, such as --seeds 1,2,3.")
    if len(set(request.seeds)) != len(request.seeds):
        raise _invalid(
            f"The seeds {request.seeds} repeat a seed.",
            "List each seed once, such as --seeds 1,2,3.",
        )
    allowed = KINDS[request.kind].aspects
    if request.aspect is not None and request.aspect not in allowed:
        raise _invalid(
            f"Aspect {request.aspect!r} is not allowed for {request.kind} art.",
            f"Use one of {', '.join(allowed)} for {request.kind}, or omit --aspect.",
        )
    if request.backend == generate.BOTH:
        raise _invalid(
            'Art is generated by one backend; "both" is not allowed.',
            "Pass --backend z-image-turbo or --backend flux2-klein-4b.",
        )
    if not (
        MIN_RESOLUTION <= request.resolution <= MAX_RESOLUTION
        and request.resolution % SIDE_MULTIPLE == 0
    ):
        raise _invalid(
            f"Resolution {request.resolution} is not a multiple of 64 from "
            f"{MIN_RESOLUTION} to {MAX_RESOLUTION}.",
            "Use a resolution such as 512, 1024, or 2048.",
        )
    aspect = request.resolved_aspect()
    if _aspect_error(aspect, request.resolution) > ASPECT_TOLERANCE:
        nearest = sorted(
            _resolutions_for(aspect), key=lambda valid: (abs(valid - request.resolution), valid)
        )[:2]
        raise _invalid(
            f"Resolution {request.resolution} cannot keep aspect {aspect} within 5 % at sides "
            "that are multiples of 64.",
            f"Use --resolution {' or '.join(str(valid) for valid in sorted(nearest))} "
            f"for aspect {aspect}.",
        )
    return resolve(request.backend, registry)


def raw_dir(root: Path, kind: str) -> Path:
    """Where the raw takes of ``kind`` live under the project root."""
    return root / RAW_RELATIVE / kind


def take_path(root: Path, request: ArtRequest, seed: int) -> Path:
    """The raw PNG of one take: ``SourceArt/Art/raw/<kind>/<Name>-<seed>.png``."""
    return raw_dir(root, request.kind) / f"{request.name}-{seed}.png"


def manifest_path(root: Path, request: ArtRequest) -> Path:
    return raw_dir(root, request.kind) / f"{request.name}{MANIFEST_SUFFIX}"


def sheet_path(root: Path, request: ArtRequest) -> Path:
    return raw_dir(root, request.kind) / f"{request.name}{SHEET_SUFFIX}"


def full_prompt(request: ArtRequest, style: str | None) -> str:
    """``<prompt>, <project style>, <kind style>``; the style is omitted when it is None."""
    parts = (request.prompt.strip(), style, KINDS[request.kind].framing)
    return ", ".join(part for part in parts if part)


def missing_seeds(request: ArtRequest, root: Path) -> tuple[int, ...]:
    """The seeds whose raw take does not exist yet, in request order."""
    return tuple(seed for seed in request.seeds if not take_path(root, request, seed).is_file())


def _generate_takes(
    request: ArtRequest,
    spec: BackendSpec,
    root: Path,
    seeds: Sequence[int],
    prompt: str,
    *,
    models_root: Path | None,
    spawn: Spawn,
) -> list[ArtImage]:
    """Run one worker for ``seeds`` and return the takes it wrote. Art is kept as written."""
    width, height = size(request.resolved_aspect(), request.resolution)
    items = tuple(
        ImageItem(
            index=index,
            prompt=prompt,
            seed=seed,
            resolution=request.resolution,
            path=take_path(root, request, seed),
            width=width,
            height=height,
        )
        for index, seed in enumerate(seeds)
    )
    with tempfile.TemporaryDirectory(prefix="nmg-art-batch-") as scratch:
        batch = Batch(
            spec=spec,
            weights=weights_dir(spec, models_root) if models_root is not None else Path(),
            items=items,
            batch_file=Path(scratch) / f"{spec.id}.json",
        )
        timings = run_backend_batches([batch], spawn=spawn)
    by_index = {timing.index: timing for timing in timings.get(spec.id, [])}
    takes: list[ArtImage] = []
    for item in items:
        timing = by_index.get(item.index)
        if timing is None or not item.path.is_file():
            raise TextureGenError(
                "texture.worker_failed",
                f"The {spec.id} worker exited without writing {item.path.name}.",
                "Check that the models are installed and that the Blender reserve leaves enough "
                "memory, then generate again. Takes already written are kept and skipped.",
            )
        takes.append(ArtImage(seed=item.seed, path=item.path, seconds=timing.seconds))
    return takes


def _previous_seconds(manifest: Path) -> dict[int, float | None]:
    """The seconds recorded for each take in an earlier run's manifest, keyed by seed."""
    try:
        data: object = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    entries = data.get("takes", []) if isinstance(data, dict) else []
    previous: dict[int, float | None] = {}
    for entry in entries if isinstance(entries, list) else []:
        if isinstance(entry, dict) and isinstance(entry.get("seed"), int):
            seconds = entry.get("seconds")
            previous[entry["seed"]] = float(seconds) if isinstance(seconds, int | float) else None
    return previous


def _takes_record(
    request: ArtRequest, root: Path, manifest: Path, generated: Sequence[ArtImage]
) -> list[dict[str, Any]]:
    """Every take of ``request`` on disk, merged across runs: earlier manifests, the requested
    seeds, and this run's new takes (which win on seconds)."""
    seconds_by_seed: dict[int, float | None] = _previous_seconds(manifest)
    for seed in request.seeds:
        seconds_by_seed.setdefault(seed, None)
    for image in generated:
        seconds_by_seed[image.seed] = image.seconds
    takes: list[dict[str, Any]] = []
    for seed in sorted(seconds_by_seed):
        path = take_path(root, request, seed)
        if path.is_file():
            takes.append({"seed": seed, "path": str(path), "seconds": seconds_by_seed[seed]})
    return takes


def run(
    request: ArtRequest,
    *,
    registry: Mapping[str, BackendSpec] = REGISTRY,
    env: Mapping[str, str] | None = None,
    facts: HardwareFacts | None = None,
    spawn: Spawn | None = None,
    cwd: Path | None = None,
    project_root_override: Path | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    deps_probe: DepsProbe | None = None,
) -> ArtResult:
    """Generate the missing takes of ``request`` and write its manifest and contact sheet.

    A seed whose raw take exists is reported in ``skipped`` and not regenerated. When every seed
    exists, no backend is checked and no worker starts.
    """
    env_map = os.environ if env is None else env
    spec = validate_request(request, registry)
    root = project_root_override or project_root(env_map, cwd or Path.cwd())
    style = project_style(root)
    prompt = full_prompt(request, style)
    missing = missing_seeds(request, root)
    raw_dir(root, request.kind).mkdir(parents=True, exist_ok=True)

    generated: list[ArtImage] = []
    if missing:
        host = probe() if facts is None else facts
        models_root = models_dir(env_map)
        generate.select_backends(
            request.backend, registry, models_root, host, reserve_gb(env_map), deps_probe
        )
        require_dependencies(deps_probe)
        if on_progress is not None:
            on_progress(0, len(missing))
        generated = _generate_takes(
            request,
            spec,
            root,
            missing,
            prompt,
            models_root=models_root,
            spawn=default_spawn if spawn is None else spawn,
        )
        if on_progress is not None:
            on_progress(len(missing), len(missing))

    manifest = manifest_path(root, request)
    skipped = tuple(seed for seed in request.seeds if seed not in missing)
    takes = _takes_record(request, root, manifest, generated)
    width, height = size(request.resolved_aspect(), request.resolution)
    record = {
        "kind": request.kind,
        "name": request.name,
        "prompt": request.prompt.strip(),
        "project_style": style,
        "kind_style": KINDS[request.kind].framing,
        "full_prompt": prompt,
        "backend": spec.id,
        "repo": spec.repo,
        "revision": spec.revision,
        "aspect": request.resolved_aspect(),
        "width": width,
        "height": height,
        "takes": takes,
        "skipped": list(skipped),
    }
    manifest.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    sheet = sheet_path(root, request)
    compare(
        [Path(str(take["path"])) for take in takes],
        [f"seed {take['seed']}" for take in takes],
        sheet,
    )
    return ArtResult(
        kind=request.kind,
        name=request.name,
        prompt=request.prompt.strip(),
        project_style=style,
        full_prompt=prompt,
        backend=spec.id,
        aspect=request.resolved_aspect(),
        width=width,
        height=height,
        images=tuple(generated),
        skipped=skipped,
        manifest=manifest,
        contact_sheet=sheet,
    )


def request_as_json(request: ArtRequest) -> dict[str, Any]:
    """The request as plain JSON, for a job's ``request.json``."""
    return {
        "kind": request.kind,
        "name": request.name,
        "prompt": request.prompt,
        "seeds": list(request.seeds),
        "backend": request.backend,
        "aspect": request.aspect,
        "resolution": request.resolution,
    }


def request_from_json(data: Mapping[str, Any]) -> ArtRequest:
    """Rebuild an :class:`ArtRequest` from :func:`request_as_json` output."""
    aspect = data.get("aspect")
    return ArtRequest(
        kind=str(data["kind"]),
        name=str(data["name"]),
        prompt=str(data["prompt"]),
        seeds=[int(seed) for seed in data["seeds"]],
        backend=str(data["backend"]),
        aspect=str(aspect) if aspect is not None else None,
        resolution=int(data["resolution"]),
    )
