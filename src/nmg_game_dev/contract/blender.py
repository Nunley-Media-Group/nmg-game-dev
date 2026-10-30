"""Blender resolution and headless launch for the contract CLI.

Resolution order matches ``scripts/run-blender-tests.sh``: ``BLENDER_BIN``, then
``BLENDER_APP/Contents/MacOS/Blender``, then the documented ``/Applications`` default.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Final

from nmg_game_dev.pipeline.errors import PipelineError

REPO_ROOT: Final = Path(__file__).resolve().parents[3]
ENTRY_SCRIPT: Path = REPO_ROOT / "scripts" / "blender" / "contract_entry.py"
DEFAULT_BLENDER_APP: Path = Path("/Applications/Blender.app")

_BINARY_RELATIVE: Final = Path("Contents") / "MacOS" / "Blender"
_STDERR_TAIL_LINES: Final = 12


def resolve_blender() -> Path:
    """Return the Blender executable, or raise ``contract.blender_not_found`` with the tries."""
    tried: list[str] = []

    override = os.environ.get("BLENDER_BIN", "")
    if override:
        if _is_executable(Path(override)):
            return Path(override)
        tried.append(f"BLENDER_BIN={override}")

    candidates: list[Path] = []
    app = os.environ.get("BLENDER_APP", "")
    if app:
        candidates.append(Path(app) / _BINARY_RELATIVE)
    candidates.append(DEFAULT_BLENDER_APP / _BINARY_RELATIVE)

    for candidate in candidates:
        if _is_executable(candidate):
            return candidate
        tried.append(str(candidate))

    raise PipelineError(
        code="contract.blender_not_found",
        message=f"Blender was not found. Tried: {', '.join(tried)}.",
        remediation="Set BLENDER_BIN to the Blender executable, or BLENDER_APP to the Blender.app "
        "bundle, then rerun.",
        stage="contract",
    )


def run_blender(
    blender: Path,
    subcommand: str,
    args: list[str],
    *,
    factory_startup: bool,
) -> subprocess.CompletedProcess[str]:
    """Run contract_entry.py headless with the subcommand and args; return the completed process.

    The process exit code is not interpreted here: callers decide success from the report file.
    """
    if not ENTRY_SCRIPT.is_file():
        raise PipelineError(
            code="contract.entry_missing",
            message=f"The Blender contract entry script is missing: {ENTRY_SCRIPT}",
            remediation="Run the contract CLI from a checkout of nmg-game-dev that contains "
            "scripts/blender/contract_entry.py.",
            stage="contract",
        )
    command = [str(blender), "--background"]
    if factory_startup:
        command.append("--factory-startup")
    command.extend(["--python", str(ENTRY_SCRIPT), "--", subcommand, *args])
    try:
        return subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as error:
        raise PipelineError(
            code="contract.blender_failed",
            message=f"Blender could not be started: {blender} ({error}).",
            remediation="Check that the Blender executable runs, then rerun.",
            stage="contract",
        ) from error


def stderr_tail(result: subprocess.CompletedProcess[str]) -> str:
    """Return the last lines of Blender's stderr, falling back to stdout when stderr is empty."""
    source = result.stderr or result.stdout or ""
    lines = [line for line in source.splitlines() if line.strip()]
    return "\n".join(lines[-_STDERR_TAIL_LINES:]) or "(Blender printed no output)"


def _is_executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)
