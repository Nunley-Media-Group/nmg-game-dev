"""Contract core: validation, re-import check, review renders, and the texture proof.

The operators, the agent's execute_blender_code calls, and the host CLI
(python -m nmg_game_dev.contract) all reach these functions. Every failure is raised as
ContractError with a stable code, message, and remediation, before any file is written.
"""

from __future__ import annotations

from .reimport import reimport_check, run_isolated
from .render import render_review, render_texture_proof
from .report import ContractError
from .validate import validate_asset

__all__ = [
    "ContractError",
    "reimport_check",
    "render_review",
    "render_texture_proof",
    "run_isolated",
    "validate_asset",
]
