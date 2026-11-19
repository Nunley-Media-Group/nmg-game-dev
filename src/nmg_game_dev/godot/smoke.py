"""The headless autoplay smoke run (#251 FR3, AC2, AC3).

``run_smoke`` runs the consumer game for a fixed number of frames with ``--nmg-autoplay`` and
``--nmg-test-saves``, then fails on a runtime error line or a non-zero exit. ``/ship`` runs the same
command as a pre-export gate (``ship.runner``), so both report the same codes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.process import CommandResult

from .runner import TIMEOUT_EXIT, GodotRunner

DEFAULT_FRAMES: Final = 600
MAX_ERROR_LINES: Final = 20
RUNTIME_REMEDIATION: Final = (
    "Fix the first error above (run the game in Godot to reproduce it), then rerun the smoke run."
)
TIMEOUT_REMEDIATION: Final = (
    "Check that the main scene quits after its frames and does not hang in autoplay, or raise "
    "NMG_GODOT_TIMEOUT_S, then rerun the smoke run."
)
_ERROR_PREFIXES: Final = ("SCRIPT ERROR", "ERROR:")
_PARSE_ERROR: Final = "Parse Error"

__all__ = [
    "DEFAULT_FRAMES",
    "MAX_ERROR_LINES",
    "check_smoke",
    "error_lines",
    "run_smoke",
    "smoke_args",
]


def smoke_args(frames: int) -> list[str]:
    """The Godot arguments for a smoke run of ``frames`` frames; the runner adds headless flags."""
    return [
        "--fixed-fps",
        "60",
        "--quit-after",
        str(frames),
        "--",
        "--nmg-autoplay",
        "--nmg-test-saves",
    ]


def error_lines(result: CommandResult) -> list[str]:
    """Return the stripped stdout and stderr lines that are runtime errors, in order.

    A line counts when it starts with ``SCRIPT ERROR`` or ``ERROR:``, or contains ``Parse Error``.
    """
    found: list[str] = []
    for line in f"{result.stdout}\n{result.stderr}".splitlines():
        stripped = line.strip()
        if stripped.startswith(_ERROR_PREFIXES) or _PARSE_ERROR in stripped:
            found.append(stripped)
    return found


def check_smoke(result: CommandResult) -> None:
    """Raise ``smoke.timeout`` or ``smoke.runtime_error`` for a failed run; return on a clean one.

    The runtime error carries up to ``MAX_ERROR_LINES`` error lines, or ``Godot exited <n>`` when
    the run exited non-zero without printing one.
    """
    if result.returncode == TIMEOUT_EXIT:
        detail = result.stderr.strip() or f"exit {TIMEOUT_EXIT}"
        raise PipelineError(
            code="smoke.timeout",
            message=f"The smoke run did not finish within its timeout: {detail}",
            remediation=TIMEOUT_REMEDIATION,
            stage="smoke",
        )
    errors = error_lines(result)
    if errors or result.returncode != 0:
        shown = errors[:MAX_ERROR_LINES]
        detail = "\n".join(shown) if shown else f"Godot exited {result.returncode}"
        raise PipelineError(
            code="smoke.runtime_error",
            message=f"The smoke run failed:\n{detail}",
            remediation=RUNTIME_REMEDIATION,
            stage="smoke",
        )


def run_smoke(
    runner: GodotRunner, project_dir: Path, frames: int = DEFAULT_FRAMES
) -> CommandResult:
    """Run one smoke run of ``frames`` frames against ``project_dir`` and check it."""
    result = runner.run(smoke_args(frames), project=project_dir)
    check_smoke(result)
    return result
