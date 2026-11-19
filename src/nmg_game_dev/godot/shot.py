"""The on-demand game screenshot (#251 FR4, AC5, AC6).

``take_shot`` runs the consumer game in a window with ``--nmg-shot=<path>``, which makes NmgLaunch
save the root viewport to that PNG and quit. It then reads the PNG header for the size. The
``shot`` CLI and the finalize MCP tool ``game_screenshot`` both call it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from nmg_game_dev.pipeline.errors import PipelineError

from .binary import resolve_godot
from .runner import GodotRunner, SubprocessGodotRunner

SHOT_GRACE_S: Final = 60.0
"""Seconds past ``after`` that a windowed run may take before it is stopped."""
NO_IMAGE_TAIL: Final = 20
PNG_SIGNATURE: Final = b"\x89PNG\r\n\x1a\n"
NO_IMAGE_REMEDIATION: Final = (
    "Check that the game starts in a window and that NmgLaunch is registered as an autoload, then "
    "rerun."
)

__all__ = ["SHOT_GRACE_S", "png_size", "shot_args", "take_shot"]


def shot_args(path: Path, after: float, options: Sequence[str]) -> list[str]:
    """The Godot arguments for a screenshot: the game's launch options, then the shot flags."""
    return [
        "--",
        *options,
        "--nmg-test-saves",
        f"--nmg-shot={path}",
        f"--nmg-shot-after={after:g}",
    ]


def png_size(path: Path) -> tuple[int, int] | None:
    """Return ``(width, height)`` from a PNG's IHDR chunk, or ``None`` when ``path`` is not one."""
    try:
        with path.open("rb") as handle:
            head = handle.read(24)
    except OSError:
        return None
    if len(head) < 24 or not head.startswith(PNG_SIGNATURE) or head[12:16] != b"IHDR":
        return None
    return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")


def take_shot(
    project_dir: Path,
    path: Path,
    after: float,
    options: Sequence[str],
    *,
    runner: GodotRunner | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Save a PNG of the running game after ``after`` seconds and return ``{path, width, height}``.

    ``path`` becomes absolute, its folder is created, and a stale file there is removed first. With
    no ``runner``, the windowed ``SubprocessGodotRunner`` runs the binary from ``env``, so
    ``godot.not_found`` propagates. A path that cannot be prepared (a folder, or an unwritable
    parent) raises ``shot.invalid_path``; a missing or non-PNG result raises ``shot.no_image``.
    """
    if not 0 <= after:
        raise PipelineError(
            code="shot.invalid_after",
            message=f"after must be 0 seconds or more, got {after:g}.",
            remediation="Pass a non-negative number of seconds for after.",
            stage="shot",
        )
    target = path.absolute()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.unlink(missing_ok=True)
    except OSError as exc:
        raise PipelineError(
            code="shot.invalid_path",
            message=f"Cannot write the screenshot to {target}: {exc.strerror or exc}.",
            remediation="Pass a .png file path in a folder you can write to.",
            stage="shot",
        ) from exc
    active: GodotRunner = (
        runner if runner is not None else SubprocessGodotRunner(resolve_godot(env), headless=False)
    )
    result = active.run(
        shot_args(target, after, options), project=project_dir, timeout=after + SHOT_GRACE_S
    )
    size = png_size(target)
    if size is None:
        lines = [line for line in f"{result.stdout}\n{result.stderr}".splitlines() if line.strip()]
        tail = "\n".join(lines[-NO_IMAGE_TAIL:]) or "(Godot printed no output)"
        raise PipelineError(
            code="shot.no_image",
            message=(
                f"The game did not save a PNG to {target} (Godot exited {result.returncode}). "
                f"Last output:\n{tail}"
            ),
            remediation=NO_IMAGE_REMEDIATION,
            stage="shot",
        )
    width, height = size
    return {"path": str(target), "width": width, "height": height}
