"""The marked nmg-game-dev block in CLAUDE.md and AGENTS.md (#7 FR4, AC1, AC8; #112 FR8, AC7).

The block sits between ``<!-- nmg-game-dev:begin -->`` and ``<!-- nmg-game-dev:end -->`` and points
agents at the installed asset and design contracts and at ``docs/design/``. It is added once,
replaced in place when its text changes, and never duplicated. ``CLAUDE.md`` is created when
missing. ``AGENTS.md`` is touched only if it already exists.
"""

from __future__ import annotations

from pathlib import Path

from nmg_game_dev.onboard.report import StepResult

BEGIN = "<!-- nmg-game-dev:begin -->"
END = "<!-- nmg-game-dev:end -->"
CONTRACT_REL = "docs/nmg-game-dev/asset-contract.md"
DESIGN_CONTRACT_REL = "docs/nmg-game-dev/design-contract.md"
DESIGN_DIR_REL = "docs/design/"


def block_text() -> str:
    return (
        f"{BEGIN}\n"
        "## nmg-game-dev asset contract\n\n"
        f"Assets authored for this project follow [the asset contract]({CONTRACT_REL}). Read it "
        "before you author, finalize, or import an asset.\n"
        f"Design docs in [{DESIGN_DIR_REL}]({DESIGN_DIR_REL}) follow [the design contract]"
        f"({DESIGN_CONTRACT_REL}). Read it before you write or change a design doc.\n"
        f"{END}"
    )


def upsert_block(name: str, path: Path, *, create: bool) -> StepResult | None:
    """Add, verify, or replace the marked block in ``path``.

    Returns None when the file is missing and ``create`` is false (AGENTS.md when absent).
    """
    block = block_text()
    if not path.exists():
        if not create:
            return None
        path.write_text(block + "\n", encoding="utf-8")
        return StepResult(name, "installed", f"created {path.name} with the nmg-game-dev block")
    text = path.read_text(encoding="utf-8")
    if BEGIN in text and END in text:
        start = text.index(BEGIN)
        end = text.index(END) + len(END)
        updated = text[:start] + block + text[end:]
        if updated == text:
            return StepResult(name, "unchanged", f"{path.name} block is current")
        path.write_text(updated, encoding="utf-8")
        return StepResult(name, "refreshed", f"replaced the nmg-game-dev block in {path.name}")
    separator = "\n" if text and not text.endswith("\n") else ""
    spacer = "\n" if text.strip() else ""
    path.write_text(text + separator + spacer + block + "\n", encoding="utf-8")
    return StepResult(name, "installed", f"added the nmg-game-dev block to {path.name}")
