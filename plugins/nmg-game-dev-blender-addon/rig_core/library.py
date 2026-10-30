"""Local animation library: library.json, clip validation, provenance, and bone maps.

Pure Python. Reading a clip file for its SHA-256 is the only file access here.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .outcome import STATUS_FALLBACK, RigError
from .skeleton import MANNY_BONE_NAMES

_CLIP_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_CLIP_SUFFIXES = (".fbx", ".bvh")
_SKELETONS = ("mixamo", "manny", "custom")

# Every target bone the retargeter needs before it can drive a humanoid.
REQUIRED_TARGETS: tuple[str, ...] = (
    "pelvis",
    "thigh_l",
    "thigh_r",
    "calf_l",
    "calf_r",
    "upperarm_l",
    "upperarm_r",
    "lowerarm_l",
    "lowerarm_r",
    "head",
)


def _mixamo_map() -> dict[str, str]:
    mapping = {
        "Hips": "pelvis",
        "Spine": "spine_01",
        "Spine1": "spine_03",
        "Spine2": "spine_05",
        "Neck": "neck_01",
        "Head": "head",
    }
    for source_side, side in (("Left", "l"), ("Right", "r")):
        mapping[f"{source_side}Shoulder"] = f"clavicle_{side}"
        mapping[f"{source_side}Arm"] = f"upperarm_{side}"
        mapping[f"{source_side}ForeArm"] = f"lowerarm_{side}"
        mapping[f"{source_side}Hand"] = f"hand_{side}"
        mapping[f"{source_side}UpLeg"] = f"thigh_{side}"
        mapping[f"{source_side}Leg"] = f"calf_{side}"
        mapping[f"{source_side}Foot"] = f"foot_{side}"
        mapping[f"{source_side}ToeBase"] = f"ball_{side}"
    return mapping


# Source bone name -> Manny target bone name.
BONE_MAPS: dict[str, dict[str, str]] = {
    "mixamo": _mixamo_map(),
    "manny": {name: name for name in MANNY_BONE_NAMES},
}


@dataclass(frozen=True)
class LibraryClip:
    name: str
    file: str
    path: Path
    frame_start: int | None
    frame_end: int | None
    sha256: str


@dataclass(frozen=True)
class Library:
    name: str
    skeleton: str
    bone_map: dict[str, str]
    clips: tuple[LibraryClip, ...]
    directory: Path

    def clip(self, name: str) -> LibraryClip | None:
        return next((clip for clip in self.clips if clip.name == name), None)


def load(library_dir: str | Path) -> Library:
    """Read and validate library_dir/library.json. Raises RigError on any violation."""
    directory = Path(library_dir)
    raw = _read_manifest(directory / "library.json")

    name = raw.get("name")
    if not isinstance(name, str) or not name:
        raise _invalid("library.json needs a non-empty string 'name'.")

    skeleton = raw.get("skeleton")
    if skeleton not in _SKELETONS:
        raise _invalid("library.json 'skeleton' must be mixamo, manny, or custom.")

    bone_map = _resolve_bone_map(skeleton, raw.get("bone_map"))
    missing = [target for target in REQUIRED_TARGETS if target not in set(bone_map.values())]
    if missing:
        raise RigError(
            STATUS_FALLBACK,
            "anim.bone_map_incomplete",
            f"The bone map does not reach: {', '.join(missing)}.",
            "Add the missing Manny targets to the library's bone_map, or use skeleton "
            "mixamo or manny.",
        )

    clips = _load_clips(directory, raw.get("clips"))
    return Library(
        name=name,
        skeleton=skeleton,
        bone_map=bone_map,
        clips=clips,
        directory=directory,
    )


def resolve_source_bone(name: str, bone_map: Mapping[str, str]) -> str | None:
    """Return the Manny target for a source bone, ignoring any 'prefix:' (mixamorig:)."""
    return bone_map.get(name.rsplit(":", 1)[-1])


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise _invalid(f"No library.json at {path}.") from error
    except (OSError, ValueError) as error:
        raise _invalid(f"{path} is not readable JSON: {error}.") from error
    if not isinstance(raw, dict):
        raise _invalid("library.json must contain a JSON object.")
    return raw


def _resolve_bone_map(skeleton: str, declared: Any) -> dict[str, str]:
    if skeleton != "custom":
        return dict(BONE_MAPS[skeleton])
    if not isinstance(declared, dict) or not declared:
        raise _invalid("skeleton 'custom' needs a non-empty 'bone_map' object.")
    for source, target in declared.items():
        if not isinstance(source, str) or not source:
            raise _invalid("bone_map keys must be non-empty source bone names.")
        if target not in MANNY_BONE_NAMES:
            raise _invalid(f"bone_map maps '{source}' to '{target}', which is not a Manny bone.")
    return dict(declared)


def _load_clips(directory: Path, declared: Any) -> tuple[LibraryClip, ...]:
    if not isinstance(declared, list) or not declared:
        raise _invalid("library.json needs a non-empty 'clips' list.")
    clips: list[LibraryClip] = []
    seen: set[str] = set()
    for entry in declared:
        if not isinstance(entry, dict):
            raise _invalid("Each clip must be a JSON object.")
        clip = _load_clip(directory, entry)
        if clip.name in seen:
            raise _invalid(f"Clip name '{clip.name}' appears more than once.")
        seen.add(clip.name)
        clips.append(clip)
    return tuple(clips)


def _load_clip(directory: Path, entry: dict[str, Any]) -> LibraryClip:
    name = entry.get("name")
    if not isinstance(name, str) or not _CLIP_NAME.match(name):
        raise _invalid(f"Clip name {name!r} must match ^[A-Za-z][A-Za-z0-9_]*$.")

    file_name = entry.get("file")
    if not isinstance(file_name, str) or not file_name:
        raise _invalid(f"Clip '{name}' needs a 'file' path.")
    relative = Path(file_name)
    if relative.is_absolute() or ".." in relative.parts:
        raise _invalid(f"Clip '{name}' file must be a path inside the library folder.")
    if not file_name.lower().endswith(_CLIP_SUFFIXES):
        raise _invalid(f"Clip '{name}' file must end in .fbx or .bvh.")
    path = directory / relative
    if not path.is_file():
        raise _invalid(f"Clip '{name}' file {file_name} does not exist in the library.")

    frame_start = _optional_frame(entry, "frame_start", name)
    frame_end = _optional_frame(entry, "frame_end", name)
    if frame_start is not None and frame_end is not None and frame_start > frame_end:
        raise _invalid(f"Clip '{name}' has frame_start after frame_end.")

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return LibraryClip(
        name=name,
        file=file_name,
        path=path,
        frame_start=frame_start,
        frame_end=frame_end,
        sha256=digest,
    )


def _optional_frame(entry: dict[str, Any], key: str, clip_name: str) -> int | None:
    value = entry.get(key)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise _invalid(f"Clip '{clip_name}' {key} must be an integer frame.")
    return value


def _invalid(message: str) -> RigError:
    return RigError(
        STATUS_FALLBACK,
        "anim.library_invalid",
        message,
        "Fix library.json and the clip files it lists, then rerun.",
    )
