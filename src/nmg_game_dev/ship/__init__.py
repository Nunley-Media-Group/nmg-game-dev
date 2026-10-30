"""ship: build, gate, sign, notarize, and package an NMG game per platform (#6).

Public API::

    run_ship(target, project, release_dir, dry_run, env) -> list[ReleaseEntry]

Failures raise ``ShipError`` with ``code``, ``message``, ``remediation``, and ``stage``.
"""

from __future__ import annotations

from nmg_game_dev.ship.errors import ShipError
from nmg_game_dev.ship.runner import run_ship
from nmg_game_dev.ship.targets import Platform, Target

__all__ = ["Platform", "ShipError", "Target", "run_ship"]
