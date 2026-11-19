"""Resolve the Godot 4 executable (#249 FR2).

Resolution order: ``GODOT_BIN`` (must be executable), then ``godot`` on ``PATH``, then
``/Applications/Godot.app/Contents/MacOS/Godot``. Godot is never pinned; any installed 4.x works.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Final

from nmg_game_dev.pipeline.errors import PipelineError

DEFAULT_GODOT_APP_BINARY: Final = Path("/Applications/Godot.app/Contents/MacOS/Godot")
NOT_FOUND_REMEDIATION: Final = "Install Godot 4 (latest stable) or set GODOT_BIN to its executable."

Which = Callable[[str], str | None]


def _is_executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def resolve_godot(
    env: Mapping[str, str] | None = None,
    which: Which = shutil.which,
    *,
    default_app: Path = DEFAULT_GODOT_APP_BINARY,
) -> Path:
    """Return the Godot executable, or raise ``godot.not_found`` with a remediation."""
    environ = os.environ if env is None else env
    tried: list[str] = []
    override = environ.get("GODOT_BIN", "")
    if override:
        if _is_executable(Path(override)):
            return Path(override)
        tried.append(f"GODOT_BIN={override}")
    on_path = which("godot")
    if on_path:
        return Path(on_path)
    tried.append("godot on PATH")
    if _is_executable(default_app):
        return default_app
    tried.append(str(default_app))
    raise PipelineError(
        code="godot.not_found",
        message=f"Godot was not found. Tried: {', '.join(tried)}.",
        remediation=NOT_FOUND_REMEDIATION,
        stage="godot",
    )
