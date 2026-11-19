"""The ``gitignore_env`` onboarding step: keep ``.env`` and Godot's cache out of git (#98, #249).

Onboarding never creates or writes ``.env``; the optional Meshy key is the developer's to add. This
step appends ``.env`` and ``<game>/.godot/`` (Godot's import cache) to the consumer ``.gitignore``,
creating that file when it is missing. An existing line with or without a leading ``/`` (and, for
the cache, with or without the trailing ``/``) counts as present, so a rerun adds nothing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from nmg_game_dev.onboard.report import StepResult

ENV_LINE: Final = ".env"


def _variants(line: str) -> set[str]:
    bare = line.rstrip("/")
    return {line, f"/{line}", bare, f"/{bare}"} if line.endswith("/") else {line, f"/{line}"}


def ensure_gitignore_env(name: str, path: Path, *, game_dir: str = "game") -> StepResult:
    """Ensure the ``.gitignore`` at ``path`` ignores ``.env`` and ``<game_dir>/.godot/``.

    Return ``installed`` when a line was appended, ``unchanged`` when both were already there.
    """
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    present = {line.strip() for line in text.splitlines()}
    wanted = [ENV_LINE, f"{game_dir.rstrip('/')}/.godot/"]
    missing = [line for line in wanted if not (_variants(line) & present)]
    if not missing:
        return StepResult(name, "unchanged", f"{path.name} already ignores {', '.join(wanted)}")
    separator = "" if not text or text.endswith("\n") else "\n"
    added = "".join(line + "\n" for line in missing)
    path.write_text(f"{text}{separator}{added}", encoding="utf-8")
    return StepResult(name, "installed", f"added {', '.join(missing)} to {path.name}")
