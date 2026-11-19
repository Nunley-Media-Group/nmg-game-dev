"""ship: gate, export, sign, notarize, and package an NMG Godot game per platform (#6, #249).

Public API::

    run_ship(target, project, release_dir, dry_run, env, *, godot=None) -> list[ReleaseEntry]

Failures raise ``ShipError`` with ``code``, ``message``, ``remediation``, and ``stage``.
"""

from __future__ import annotations

from nmg_game_dev.ship.errors import ShipError
from nmg_game_dev.ship.runner import run_ship
from nmg_game_dev.ship.targets import Platform, Target

__all__ = ["Platform", "ShipError", "Target", "run_ship"]
