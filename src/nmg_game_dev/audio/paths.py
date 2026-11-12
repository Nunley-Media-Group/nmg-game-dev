"""Where the audio import writes its files (#155 Data / Storage).

``SourceArt/Audio/<SFX|Music>/<Name>.wav`` holds the stored WAV.
``/Game/Audio/<SFX|Music>/SW_<Name>`` is the SoundWave the Unreal import creates from it. The
project root comes from the meshy package's ``project_root``, so ``CLAUDE_PROJECT_DIR`` wins and
the working directory is the fallback.
"""

from __future__ import annotations

import os
from pathlib import Path

from nmg_game_dev.audio.request import KINDS
from nmg_game_dev.meshy.config import project_root as _project_root


def project_root() -> Path:
    """Return ``CLAUDE_PROJECT_DIR`` when it is set, else the working directory."""
    return _project_root(os.environ, Path.cwd())


def source_art(root: Path, kind: str, name: str) -> Path:
    return root / "SourceArt" / "Audio" / KINDS[kind] / f"{name}.wav"


def unreal_folder(kind: str) -> str:
    return f"/Game/Audio/{KINDS[kind]}"


def asset_name(name: str) -> str:
    return f"SW_{name}"


def unreal_asset(kind: str, name: str) -> str:
    return f"{unreal_folder(kind)}/{asset_name(name)}"
