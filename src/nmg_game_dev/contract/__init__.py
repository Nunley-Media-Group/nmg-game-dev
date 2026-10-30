"""Contract CLI: headless Blender runs of the contract checks, with exit codes for scripts and CI.

Run as ``python -m nmg_game_dev.contract {validate,reimport,render}``.
"""

from .blender import resolve_blender
from .cli import main

__all__ = ["main", "resolve_blender"]
