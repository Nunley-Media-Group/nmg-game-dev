"""The gitignore_env step keeps .env and Godot's import cache out of git (#98 FR10, #249)."""

from __future__ import annotations

from pathlib import Path

import pytest

from nmg_game_dev.onboard.gitignore import ensure_gitignore_env


def test_missing_gitignore_is_created_with_env_and_godot_cache(tmp_path: Path) -> None:
    target = tmp_path / ".gitignore"
    result = ensure_gitignore_env("gitignore_env", target)
    assert result.name == "gitignore_env" and result.status == "installed"
    assert target.read_text(encoding="utf-8") == ".env\ngame/.godot/\n"
    assert not (tmp_path / ".env").exists()


def test_existing_entries_are_kept_and_lines_are_appended(tmp_path: Path) -> None:
    target = tmp_path / ".gitignore"
    target.write_text("node_modules/\nbuild/\n", encoding="utf-8")
    assert ensure_gitignore_env("gitignore_env", target).status == "installed"
    assert target.read_text(encoding="utf-8") == "node_modules/\nbuild/\n.env\ngame/.godot/\n"


def test_a_missing_final_newline_is_completed_before_the_entry(tmp_path: Path) -> None:
    target = tmp_path / ".gitignore"
    target.write_text("build", encoding="utf-8")
    ensure_gitignore_env("gitignore_env", target)
    assert target.read_text(encoding="utf-8") == "build\n.env\ngame/.godot/\n"


def test_a_rerun_is_unchanged_and_adds_no_duplicate(tmp_path: Path) -> None:
    target = tmp_path / ".gitignore"
    first = ensure_gitignore_env("gitignore_env", target)
    second = ensure_gitignore_env("gitignore_env", target)
    assert (first.status, second.status) == ("installed", "unchanged")
    assert target.read_text(encoding="utf-8").splitlines() == [".env", "game/.godot/"]


@pytest.mark.parametrize("line", [".env", "/.env", "  .env  "])
def test_an_existing_env_line_counts_as_present(tmp_path: Path, line: str) -> None:
    target = tmp_path / ".gitignore"
    original = f"logs/\n{line}\ngame/.godot/\n"
    target.write_text(original, encoding="utf-8")
    assert ensure_gitignore_env("gitignore_env", target).status == "unchanged"
    assert target.read_text(encoding="utf-8") == original


@pytest.mark.parametrize("line", ["game/.godot/", "/game/.godot/", "game/.godot", "/game/.godot"])
def test_an_existing_godot_cache_line_counts_as_present(tmp_path: Path, line: str) -> None:
    target = tmp_path / ".gitignore"
    original = f".env\n{line}\n"
    target.write_text(original, encoding="utf-8")
    assert ensure_gitignore_env("gitignore_env", target).status == "unchanged"
    assert target.read_text(encoding="utf-8") == original


def test_the_cache_line_follows_the_game_dir(tmp_path: Path) -> None:
    target = tmp_path / ".gitignore"
    ensure_gitignore_env("gitignore_env", target, game_dir="client")
    assert target.read_text(encoding="utf-8") == ".env\nclient/.godot/\n"


def test_a_similar_pattern_does_not_count_as_env(tmp_path: Path) -> None:
    target = tmp_path / ".gitignore"
    target.write_text(".env.local\ngame/.godot/\n", encoding="utf-8")
    assert ensure_gitignore_env("gitignore_env", target).status == "installed"
    assert target.read_text(encoding="utf-8") == ".env.local\ngame/.godot/\n.env\n"
