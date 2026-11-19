"""Where the audio import writes its files (#155, #249 Data / Storage).

``SourceArt/Audio/<SFX|Music>/<Name>.wav`` holds the stored WAV. The Godot project at
``game/`` gets ``assets/Audio/<Name>.wav`` for a sound effect and ``assets/Audio/<Name>.ogg`` for
music, each beside the ``.import`` file Godot's importer reads. The project root comes from the
meshy package's ``project_root``, so ``CLAUDE_PROJECT_DIR`` wins and the working directory is the
fallback.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

from nmg_game_dev.audio.request import KINDS
from nmg_game_dev.meshy.config import project_root as _project_root

GAME_DIR: Final = "game"
AUDIO_DIR: Final = Path("assets") / "Audio"
EXTENSIONS: Final[dict[str, str]] = {"sfx": ".wav", "music": ".ogg"}
SETTINGS_FILE: Final = "audio.json"


def project_root() -> Path:
    """Return ``CLAUDE_PROJECT_DIR`` when it is set, else the working directory."""
    return _project_root(os.environ, Path.cwd())


def source_art(root: Path, kind: str, name: str) -> Path:
    return root / "SourceArt" / "Audio" / KINDS[kind] / f"{name}.wav"


def settings_file(root: Path) -> Path:
    """Return ``SourceArt/Audio/audio.json``, which keeps each sound's finishing settings (#252)."""
    return root / "SourceArt" / "Audio" / SETTINGS_FILE


def game_project(root: Path) -> Path:
    """Return the Godot project folder, ``<root>/game``."""
    return root / GAME_DIR


def game_asset(root: Path, kind: str, name: str) -> Path:
    """Return ``<root>/game/assets/Audio/<name>.wav`` (sfx) or ``.ogg`` (music)."""
    return game_project(root) / AUDIO_DIR / f"{name}{EXTENSIONS[kind]}"


def godot_asset(kind: str, name: str) -> str:
    """Return the ``res://`` path of the imported stream."""
    return f"res://{AUDIO_DIR.as_posix()}/{name}{EXTENSIONS[kind]}"
