"""ship: gate, export, sign, notarize, and package an NMG Godot game per platform (#6, #249).

Public API::

    run_ship(target, project, release_dir, dry_run, env, *, godot=None, bump=None, version=None)
        -> list[ReleaseEntry]

``bump`` (``major``, ``minor``, or ``patch``) or ``version`` (``X.Y.Z``) sets the build version
before export (#254); with neither, the project's current version ships.

Failures raise ``ShipError`` with ``code``, ``message``, ``remediation``, and ``stage``.
"""

from __future__ import annotations

from nmg_game_dev.ship.errors import ShipError
from nmg_game_dev.ship.runner import run_ship
from nmg_game_dev.ship.targets import Platform, Target

__all__ = ["Platform", "ShipError", "Target", "run_ship"]
