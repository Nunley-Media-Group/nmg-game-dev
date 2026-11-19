"""AC3: the player changelog section a ship requires before it gates (#254 FR3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from nmg_game_dev.ship.changelog import changelog_section
from nmg_game_dev.ship.errors import ShipError


def _changelog(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "CHANGELOG.md"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "heading",
    ["## 1.3.0", "## [1.3.0]", "## [1.3.0] - 2026-11-18", "## 1.3.0 - 2026-11-18", "##  1.3.0"],
)
def test_each_heading_form_is_found(tmp_path: Path, heading: str) -> None:
    path = _changelog(tmp_path, f"# Changelog\n\n{heading}\n\n- Faster loading.\n")
    assert changelog_section(path, "1.3.0") == "- Faster loading."


def test_the_section_stops_at_the_next_level_two_heading(tmp_path: Path) -> None:
    path = _changelog(
        tmp_path,
        "## [Unreleased]\n\n## 1.3.0\n\n### Added\n\n- New map.\n\n- Faster loading.\n\n"
        "## 1.2.3\n\n- Older change.\n",
    )
    assert changelog_section(path, "1.3.0") == "### Added\n\n- New map.\n\n- Faster loading."


def test_a_longer_version_is_not_a_prefix_match(tmp_path: Path) -> None:
    path = _changelog(tmp_path, "## 1.3.10\n\n- Not this one.\n")
    with pytest.raises(ShipError) as caught:
        changelog_section(path, "1.3.1")
    assert caught.value.code == "ship.changelog_missing"


def test_a_missing_file_is_refused_with_the_remediation(tmp_path: Path) -> None:
    path = tmp_path / "CHANGELOG.md"
    with pytest.raises(ShipError) as caught:
        changelog_section(path, "1.3.0")
    error = caught.value
    assert error.code == "ship.changelog_missing"
    assert str(path) in error.message
    assert error.remediation == (
        "Add a `## 1.3.0` section with at least one line for players to CHANGELOG.md, "
        "then rerun the ship."
    )


def test_a_missing_section_is_refused(tmp_path: Path) -> None:
    path = _changelog(tmp_path, "## 1.2.3\n\n- Older change.\n")
    with pytest.raises(ShipError) as caught:
        changelog_section(path, "1.3.0")
    assert caught.value.code == "ship.changelog_missing"
    assert "has no '## 1.3.0' section" in caught.value.message


@pytest.mark.parametrize(
    "text",
    [
        "## 1.3.0\n\n\n## 1.2.3\n\n- Older change.\n",
        "## 1.3.0\n   \n## 1.2.3\n- Older change.\n",
        "## 1.3.0\n",
    ],
)
def test_a_blank_section_is_refused(tmp_path: Path, text: str) -> None:
    path = _changelog(tmp_path, text)
    with pytest.raises(ShipError) as caught:
        changelog_section(path, "1.3.0")
    assert caught.value.code == "ship.changelog_missing"
    assert "no text" in caught.value.message


def test_the_section_text_keeps_its_lines_verbatim(tmp_path: Path) -> None:
    path = _changelog(tmp_path, "## 1.3.0\n\n- Faster loading.\n  Continued line.\n\n")
    assert changelog_section(path, "1.3.0") == "- Faster loading.\n  Continued line."
