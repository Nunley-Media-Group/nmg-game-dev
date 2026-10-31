"""The gitignore_env step keeps the consumer's project .env out of git (#98 FR10, AC14)."""

from __future__ import annotations

from pathlib import Path

import pytest

from nmg_game_dev.onboard.gitignore import ensure_gitignore_env


def test_missing_gitignore_is_created_with_env_and_no_dotenv(tmp_path: Path) -> None:
    target = tmp_path / ".gitignore"
    result = ensure_gitignore_env("gitignore_env", target)
    assert result.name == "gitignore_env" and result.status == "installed"
    assert target.read_text(encoding="utf-8") == ".env\n"
    assert not (tmp_path / ".env").exists()


def test_existing_entries_are_kept_and_env_is_appended(tmp_path: Path) -> None:
    target = tmp_path / ".gitignore"
    target.write_text("node_modules/\nBinaries/\n", encoding="utf-8")
    assert ensure_gitignore_env("gitignore_env", target).status == "installed"
    assert target.read_text(encoding="utf-8") == "node_modules/\nBinaries/\n.env\n"


def test_a_missing_final_newline_is_completed_before_the_entry(tmp_path: Path) -> None:
    target = tmp_path / ".gitignore"
    target.write_text("build", encoding="utf-8")
    ensure_gitignore_env("gitignore_env", target)
    assert target.read_text(encoding="utf-8") == "build\n.env\n"


def test_a_rerun_is_unchanged_and_adds_no_duplicate(tmp_path: Path) -> None:
    target = tmp_path / ".gitignore"
    first = ensure_gitignore_env("gitignore_env", target)
    second = ensure_gitignore_env("gitignore_env", target)
    assert (first.status, second.status) == ("installed", "unchanged")
    assert target.read_text(encoding="utf-8").splitlines() == [".env"]


@pytest.mark.parametrize("line", [".env", "/.env", "  .env  "])
def test_an_existing_env_line_counts_as_present(tmp_path: Path, line: str) -> None:
    target = tmp_path / ".gitignore"
    original = f"logs/\n{line}\n"
    target.write_text(original, encoding="utf-8")
    assert ensure_gitignore_env("gitignore_env", target).status == "unchanged"
    assert target.read_text(encoding="utf-8") == original


def test_a_similar_pattern_does_not_count_as_env(tmp_path: Path) -> None:
    target = tmp_path / ".gitignore"
    target.write_text(".env.local\n", encoding="utf-8")
    assert ensure_gitignore_env("gitignore_env", target).status == "installed"
