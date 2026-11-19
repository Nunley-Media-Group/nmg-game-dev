"""``CommandResult``: the outcome of one external command (onboarding and the Godot runner).

It lives in this dependency-free module so ``nmg_game_dev.godot`` and ``nmg_game_dev.onboard`` can
both import it without loading each other's package (#249).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CommandResult:
    """The outcome of one external command."""

    returncode: int
    stdout: str = ""
    stderr: str = ""
