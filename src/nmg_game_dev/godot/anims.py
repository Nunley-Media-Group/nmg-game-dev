"""Animation clips as Godot ``AnimationLibrary`` resources for ``import_anims`` (#249 FR3, AC3).

The Blender add-on exports each clip as ``Animations/A_<Name>_<Clip>.glb``. ``import_clips`` works
on the clips the caller says changed:

1. Writes ``A_<Name>_<Clip>.glb.import`` with ``importer="animation_library"`` when the file is
   missing or names another importer, so Godot imports the clip as an animation library and not
   as a scene.
2. Runs ``godot --headless --import`` once when any clip changed.
3. Runs ``probe_anims.gd`` for the changed clips and the skeleton scenes the caller names, and
   returns its ``{clips, skeletons}`` result.

``verify_clips`` and ``check_compatible`` turn that result into ``import_anims.clip_mismatch``,
``finalize.skeleton_mismatch`` and ``finalize.skeleton_not_found``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, cast

from nmg_game_dev.pipeline.errors import PipelineError

from .project import parse_config, res_path
from .runner import GodotRunner, import_project, run_probe

IMPORTER: Final = '"animation_library"'
PROBE: Final = "probe_anims.gd"
_STAGE: Final = "import_anims"
_MISMATCH_REMEDIATION: Final = (
    "Re-export the clip and rerun import_anims with force, so Godot rebuilds the animation "
    "library from the current .glb."
)


@dataclass(frozen=True)
class ClipPlan:
    """One clip to import and measure.

    Attributes:
        name: The clip (action) name.
        file: The clip ``.glb`` on disk.
        fps: The scene frame rate the clip was exported at.
        expected_frames: ``frame_end - frame_start``: Godot's animation length times fps.
    """

    name: str
    file: Path
    fps: float
    expected_frames: int


def import_settings_path(clip: Path) -> Path:
    """Return the ``.import`` file Godot keeps beside ``clip``."""
    return clip.with_name(clip.name + ".import")


def has_library_importer(clip: Path) -> bool:
    """Return ``True`` when ``clip``'s ``.import`` selects the animation-library importer."""
    settings = import_settings_path(clip)
    if not settings.is_file():
        return False
    return parse_config(settings.read_text(encoding="utf-8")).get(("remap", "importer")) == IMPORTER


def write_library_importer(clip: Path) -> bool:
    """Write the minimal ``.import`` selecting ``animation_library``. Returns whether it wrote."""
    if has_library_importer(clip):
        return False
    import_settings_path(clip).write_text(f"[remap]\n\nimporter={IMPORTER}\n", encoding="utf-8")
    return True


def import_clips(
    runner: GodotRunner,
    project: Path,
    *,
    clips: Sequence[ClipPlan],
    skeletons: Sequence[Path] = (),
    timeout: float | None = None,
) -> dict[str, Any]:
    """Import the changed ``clips`` and probe them and ``skeletons``. Returns the probe result.

    With no clips only the skeleton scenes are probed, and ``--import`` does not run.
    """
    for clip in clips:
        write_library_importer(clip.file)
    if clips:
        import_project(runner, project, error_code="import_anims.failed", timeout=timeout)
    params = {
        "clips": [
            {"name": clip.name, "path": res_path(project, clip.file), "fps": clip.fps}
            for clip in clips
        ],
        "skeletons": [res_path(project, scene) for scene in skeletons],
    }
    result = run_probe(
        runner, project, PROBE, params, error_code="import_anims.failed", timeout=timeout
    )
    measured = result.get("clips")
    found = result.get("skeletons")
    return {
        "clips": cast(dict[str, Any], measured) if isinstance(measured, dict) else {},
        "skeletons": cast(dict[str, Any], found) if isinstance(found, dict) else {},
    }


def verify_clips(clips: Sequence[ClipPlan], measured: Mapping[str, Any]) -> dict[str, list[str]]:
    """Check each clip's measured frame count. Returns each clip's bone names.

    A clip the probe could not load, or whose frame count differs, raises
    ``import_anims.clip_mismatch``.
    """
    bones: dict[str, list[str]] = {}
    for clip in clips:
        seen = measured.get(clip.name)
        if not isinstance(seen, dict):
            raise PipelineError(
                code="import_anims.clip_mismatch",
                message=f"Clip {clip.name} did not import as an animation library "
                f"({clip.file.name}).",
                remediation=_MISMATCH_REMEDIATION,
                stage=_STAGE,
            )
        entry = cast(dict[str, Any], seen)
        frames = entry.get("frame_count")
        if frames != clip.expected_frames:
            raise PipelineError(
                code="import_anims.clip_mismatch",
                message=f"Clip {clip.name} frame count: expected {clip.expected_frames}, "
                f"measured {frames}.",
                remediation=_MISMATCH_REMEDIATION,
                stage=_STAGE,
            )
        raw = entry.get("bones")
        names = cast(list[object], raw) if isinstance(raw, list) else []
        bones[clip.name] = sorted(str(bone) for bone in names)
    return bones


def check_compatible(
    project: Path,
    required: Sequence[str],
    targets: Sequence[tuple[str, Path]],
    skeletons: Mapping[str, Any],
) -> list[str]:
    """Check every required bone exists in each target's Desktop skeleton. Returns their paths.

    ``targets`` pairs each ``<Category>/<Name>`` with its Desktop ``.glb``. A target the probe could
    not load raises ``finalize.skeleton_not_found``; a missing bone raises
    ``finalize.skeleton_mismatch`` naming the bones.
    """
    registered: list[str] = []
    for label, scene in targets:
        resource = res_path(project, scene)
        entry = skeletons.get(resource)
        if not isinstance(entry, dict) or entry.get("found") is not True:
            raise skeleton_not_found(label, resource)
        listed = entry.get("bones")
        names = cast(list[object], listed) if isinstance(listed, list) else []
        have = {str(bone) for bone in names}
        missing = sorted(set(required) - have)
        if missing:
            raise PipelineError(
                code="finalize.skeleton_mismatch",
                message=f"{label} ({resource}) lacks bones the clips animate: "
                f"{', '.join(missing)}.",
                remediation="Only list characters rigged with the same bone names in "
                "compatible_with.",
                stage=_STAGE,
            )
        registered.append(resource)
    return registered


def skeleton_not_found(label: str, path: str, *, own: bool = False) -> PipelineError:
    """Return ``finalize.skeleton_not_found`` for a Desktop scene that does not exist."""
    if own:
        remediation = f"Run import_godot for {label} first, then rerun import_anims."
    else:
        remediation = (
            f"Finalize {label} first so its Desktop skeleton exists, or remove it from "
            "compatible_with, then rerun import_anims."
        )
    return PipelineError(
        code="finalize.skeleton_not_found",
        message=f"The Desktop skeleton scene {path} for {label} does not exist in the project.",
        remediation=remediation,
        stage=_STAGE,
    )


__all__ = [
    "ClipPlan",
    "check_compatible",
    "has_library_importer",
    "import_clips",
    "import_settings_path",
    "skeleton_not_found",
    "verify_clips",
    "write_library_importer",
]
