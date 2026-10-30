"""nmg-game-dev — Blender-first, Unreal-shipped content pipeline for NMG games."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

try:
    __version__ = version("nmg-game-dev")
except PackageNotFoundError:  # running from a source tree without an installed distribution
    __version__ = (Path(__file__).parents[2] / "VERSION").read_text(encoding="utf-8").strip()
