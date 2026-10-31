"""Project root and design-file locations (#112 FR2).

The project root is ``CLAUDE_PROJECT_DIR`` when set and non-empty, otherwise the working
directory.  This matches the budget-file lookup in ``nmg_game_dev.finalize.service``.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Final

PROJECT_ENV: Final = "CLAUDE_PROJECT_DIR"
DESIGN_DIR_NAME: Final = Path("docs") / "design"
BACKLOG_NAME: Final = "backlog.json"


def project_root(env: Mapping[str, str] | None = None, cwd: Path | None = None) -> Path:
    """Return ``CLAUDE_PROJECT_DIR`` when set, otherwise ``cwd`` (default: the working dir)."""
    environment = os.environ if env is None else env
    configured = environment.get(PROJECT_ENV)
    if configured:
        return Path(configured)
    return cwd if cwd is not None else Path.cwd()


def design_dir(root: Path) -> Path:
    """Return ``<root>/docs/design``."""
    return root / DESIGN_DIR_NAME


def backlog_path(root: Path) -> Path:
    """Return ``<root>/docs/design/backlog.json``."""
    return design_dir(root) / BACKLOG_NAME
