"""Per-sound finishing settings and ``SourceArt/Audio/audio.json`` (#252 FR3, AC5, AC7).

``resolve`` picks each setting from the explicit value, else the sound's stored entry (when it was
stored as the same kind), else the default for its kind. ``save`` upserts the entry after a
successful import, so a byte-identical re-import and ``refinish`` reuse it. An out-of-range explicit
value raises ``audio.invalid_request``. An unreadable or malformed ``audio.json`` raises
``audio.settings_invalid``, and it is read before anything is written.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, TypeGuard

from nmg_game_dev.audio import paths
from nmg_game_dev.audio.convert import _write_atomic
from nmg_game_dev.audio.errors import AudioError

DEFAULT_LUFS: Final[dict[str, float]] = {"sfx": -16.0, "music": -18.0}
DEFAULT_LOOP_CROSSFADE_MS: Final = 500
LUFS_RANGE: Final = (-40.0, -5.0)
SETTINGS_VERSION: Final = 1

_INVALID_REMEDIATION: Final = (
    "Pass max_seconds above zero, loudness_lufs between -40 and -5, and loop_crossfade_ms of zero "
    "or more, then import the sound again."
)
_SETTINGS_REMEDIATION: Final = (
    "Fix or delete the entry in SourceArt/Audio/audio.json. Each sound needs kind, loop, finish, "
    "max_seconds, loudness_lufs, and loop_crossfade_ms with valid values, or delete the file to "
    "fall back to the defaults."
)


@dataclass(frozen=True)
class FinishSettings:
    """How one sound is finished before import. ``loudness_lufs`` is the integrated target."""

    loudness_lufs: float
    finish: bool = True
    max_seconds: float | None = None
    loop_crossfade_ms: int = DEFAULT_LOOP_CROSSFADE_MS

    def validate(self) -> None:
        """Raise ``audio.invalid_request`` when a value is outside the range the spec allows."""
        if self.max_seconds is not None and not (
            math.isfinite(self.max_seconds) and self.max_seconds > 0
        ):
            raise _invalid("max_seconds must be a positive number of seconds")
        low, high = LUFS_RANGE
        if not low <= self.loudness_lufs <= high:
            raise _invalid(f"loudness_lufs must be between {low:g} and {high:g}")
        if self.loop_crossfade_ms < 0:
            raise _invalid("loop_crossfade_ms must be zero or more")


@dataclass(frozen=True)
class StoredSound:
    """One ``audio.json`` entry: the sound's kind, its loop setting, and its finishing settings."""

    kind: str
    loop: bool
    settings: FinishSettings


def load(root: Path) -> dict[str, StoredSound]:
    """Return the stored entries keyed by sound name, or ``{}`` when ``audio.json`` is absent."""
    path = paths.settings_file(root)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise _settings_invalid(path, str(error)) from error
    sounds = data.get("sounds") if isinstance(data, dict) else None
    if not isinstance(data, dict) or data.get("version") != SETTINGS_VERSION:
        raise _settings_invalid(path, 'expected {"version": 1, "sounds": {...}}')
    if not isinstance(sounds, dict):
        raise _settings_invalid(path, 'expected a "sounds" object')
    return {name: _stored(path, name, entry) for name, entry in sounds.items()}


def resolve(
    root: Path,
    name: str,
    kind: str,
    *,
    finish: bool | None = None,
    max_seconds: float | None = None,
    loudness_lufs: float | None = None,
    loop_crossfade_ms: int | None = None,
) -> FinishSettings:
    """Return the settings for one import: explicit values, then the stored entry, then defaults."""
    stored = load(root).get(name)
    base = FinishSettings(loudness_lufs=DEFAULT_LUFS[kind])
    if stored is not None and stored.kind == kind:
        base = stored.settings
    settings = FinishSettings(
        loudness_lufs=base.loudness_lufs if loudness_lufs is None else float(loudness_lufs),
        finish=base.finish if finish is None else bool(finish),
        max_seconds=base.max_seconds if max_seconds is None else float(max_seconds),
        loop_crossfade_ms=(
            base.loop_crossfade_ms if loop_crossfade_ms is None else int(loop_crossfade_ms)
        ),
    )
    settings.validate()
    return settings


def save(root: Path, name: str, kind: str, loop: bool, settings: FinishSettings) -> None:
    """Upsert ``name``'s entry and rewrite ``audio.json`` as sorted, indented JSON."""
    sounds = {key: _entry(sound) for key, sound in load(root).items()}
    sounds[name] = _entry(StoredSound(kind=kind, loop=loop, settings=settings))
    payload = {"version": SETTINGS_VERSION, "sounds": dict(sorted(sounds.items()))}
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"

    def write(tmp: Path) -> None:
        tmp.write_text(text, encoding="utf-8")

    _write_atomic(paths.settings_file(root), write)


def describe(settings: FinishSettings) -> dict[str, Any]:
    """Return the resolved settings as the ``settings`` block of an import result."""
    return {
        "finish": settings.finish,
        "max_seconds": settings.max_seconds,
        "loudness_lufs": settings.loudness_lufs,
        "loop_crossfade_ms": settings.loop_crossfade_ms,
    }


def _entry(sound: StoredSound) -> dict[str, Any]:
    return {"kind": sound.kind, "loop": sound.loop, **describe(sound.settings)}


def _stored(path: Path, name: str, entry: object) -> StoredSound:
    if not isinstance(entry, dict):
        raise _settings_invalid(path, f"the entry for {name} is not an object")
    kind = entry.get("kind")
    loop = entry.get("loop")
    finish = entry.get("finish")
    max_seconds = entry.get("max_seconds")
    loudness = entry.get("loudness_lufs")
    crossfade = entry.get("loop_crossfade_ms")
    missing = f"the entry for {name} has a missing or invalid field"
    if kind not in DEFAULT_LUFS or not isinstance(loop, bool) or not isinstance(finish, bool):
        raise _settings_invalid(path, missing)
    if not _is_number(loudness) or not _is_int(crossfade):
        raise _settings_invalid(path, missing)
    if max_seconds is not None and not _is_number(max_seconds):
        raise _settings_invalid(path, missing)
    settings = FinishSettings(
        loudness_lufs=float(loudness),
        finish=finish,
        max_seconds=None if max_seconds is None else float(max_seconds),
        loop_crossfade_ms=crossfade,
    )
    try:
        settings.validate()
    except AudioError as error:
        raise _settings_invalid(path, f"the entry for {name}: {error.message}") from error
    return StoredSound(kind=str(kind), loop=loop, settings=settings)


def _is_number(value: object) -> TypeGuard[int | float]:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _is_int(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _invalid(message: str) -> AudioError:
    return AudioError(
        code="audio.invalid_request",
        message=message,
        remediation=_INVALID_REMEDIATION,
    )


def _settings_invalid(path: Path, detail: str) -> AudioError:
    return AudioError(
        code="audio.settings_invalid",
        message=f"{path} could not be read: {detail}",
        remediation=_SETTINGS_REMEDIATION,
    )
