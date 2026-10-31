"""The ``gitignore_env`` onboarding step: keep the consumer's project ``.env`` out of git (#98).

Onboarding never creates or writes ``.env``; the optional Meshy key is the developer's to add. This
step appends ``.env`` to the consumer ``.gitignore``, creating that file when it is missing. An
existing ``.env`` or ``/.env`` line counts as present, so a rerun adds nothing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from nmg_game_dev.onboard.report import StepResult

ENV_LINE: Final = ".env"
_PRESENT: Final = frozenset({".env", "/.env"})


def ensure_gitignore_env(name: str, path: Path) -> StepResult:
    """Ensure the ``.gitignore`` at ``path`` ignores ``.env``.

    Return ``installed`` when the line was appended, ``unchanged`` when it was already there.
    """
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    if any(line.strip() in _PRESENT for line in text.splitlines()):
        return StepResult(name, "unchanged", f"{path.name} already ignores .env")
    separator = "" if not text or text.endswith("\n") else "\n"
    path.write_text(f"{text}{separator}{ENV_LINE}\n", encoding="utf-8")
    return StepResult(name, "installed", f"added .env to {path.name}")
