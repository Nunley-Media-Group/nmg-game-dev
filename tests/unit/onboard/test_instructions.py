"""The marked CLAUDE.md / AGENTS.md block is added once and replaced in place (#7 FR4, AC1, AC8)."""

from __future__ import annotations

from pathlib import Path

from nmg_game_dev.onboard.instructions import BEGIN, END, upsert_block


def test_claude_md_is_created_when_missing(tmp_path: Path) -> None:
    target = tmp_path / "CLAUDE.md"
    result = upsert_block("agent_instructions:CLAUDE.md", target, create=True)
    assert result is not None and result.status == "installed"
    text = target.read_text()
    assert text.count(BEGIN) == 1 and text.count(END) == 1
    assert "docs/nmg-game-dev/asset-contract.md" in text


def test_block_is_appended_once_and_keeps_existing_text(tmp_path: Path) -> None:
    target = tmp_path / "CLAUDE.md"
    target.write_text("# Game\n\nNotes.")
    upsert_block("agent_instructions:CLAUDE.md", target, create=True)
    once = target.read_text()

    again = upsert_block("agent_instructions:CLAUDE.md", target, create=True)

    assert again is not None and again.status == "unchanged"
    assert target.read_text() == once
    assert once.startswith("# Game\n\nNotes.")
    assert once.count(BEGIN) == 1


def test_stale_block_is_replaced_in_place(tmp_path: Path) -> None:
    target = tmp_path / "CLAUDE.md"
    target.write_text(f"Top\n{BEGIN}\nold text\n{END}\nBottom\n")
    result = upsert_block("agent_instructions:CLAUDE.md", target, create=True)
    assert result is not None and result.status == "refreshed"
    text = target.read_text()
    assert text.startswith("Top\n") and text.endswith("Bottom\n")
    assert "old text" not in text and text.count(BEGIN) == 1


def test_agents_md_is_touched_only_when_present(tmp_path: Path) -> None:
    missing = tmp_path / "AGENTS.md"
    assert upsert_block("agent_instructions:AGENTS.md", missing, create=False) is None
    assert not missing.exists()

    present = tmp_path / "AGENTS.md"
    present.write_text("Agents\n")
    result = upsert_block("agent_instructions:AGENTS.md", present, create=False)
    assert result is not None and result.status == "installed"
    assert present.read_text().count(BEGIN) == 1
