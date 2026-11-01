"""Consumer onboarding for nmg-game-dev (#7).

``run_onboard`` installs the start scripts, SessionStart hooks, asset contract, UE and Blender
plugins, VibeUE, the texture models, and the Git LFS setup (``.gitattributes`` block and LFS hooks)
into a consumer project. Each step is idempotent and reports installed, unchanged, drift, refreshed,
or skipped. ``list_volumes`` backs the skill's disk question.
"""

from __future__ import annotations

from nmg_game_dev.onboard.errors import OnboardError
from nmg_game_dev.onboard.report import StepResult
from nmg_game_dev.onboard.runner import run_onboard
from nmg_game_dev.onboard.volumes import list_volumes

__all__ = ["OnboardError", "StepResult", "list_volumes", "run_onboard"]
