"""AC1-AC4: CHANGELOG release sections are unique, strictly descending, non-empty and match VERSION.

The checker reads CHANGELOG.md as it is checked in. It fails when a release repeats, when releases
are not strictly descending, when a release section has no bullet, when the newest release differs
from VERSION, or when a reconciled issue reference is missing or appears in more than one bullet.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_UNRELEASED = "## [Unreleased]"
_RELEASE_HEADING = re.compile(r"^## \[(\d+)\.(\d+)\.(\d+)\] - \d{4}-\d{2}-\d{2}$")
_RECONCILED_REFERENCES = (*range(133, 156), 189, 193, 202, 203, 204, 211, 215)


def _sections(text: str) -> list[tuple[str, list[str]]]:
    """Return each level-two heading with the lines that follow it, in file order."""
    sections: list[tuple[str, list[str]]] = []
    for line in text.split("\n"):
        if line.startswith("## "):
            sections.append((line, []))
        elif sections:
            sections[-1][1].append(line)
    return sections


def changelog_problems(text: str, version: str) -> list[str]:
    """Return one message per broken rule; an empty list means the changelog passes."""
    sections = _sections(text)
    problems: list[str] = []
    if not sections or sections[0][0] != _UNRELEASED:
        problems.append(f"the first '## ' heading must be '{_UNRELEASED}'")
    releases = sections[1:]
    if not releases:
        problems.append(f"no release section follows '{_UNRELEASED}'")

    numbers: set[tuple[int, int, int]] = set()
    previous: tuple[int, int, int] | None = None
    previous_label = ""
    for index, (heading, body) in enumerate(releases):
        match = _RELEASE_HEADING.match(heading)
        if match is None:
            problems.append(f"'{heading}' is not a '## [x.y.z] - YYYY-MM-DD' release heading")
            continue
        number = (int(match[1]), int(match[2]), int(match[3]))
        label = ".".join(str(part) for part in number)
        if number in numbers:
            problems.append(f"release {label} appears more than once")
        elif previous is not None and number >= previous:
            problems.append(
                f"release {label} is not lower than the release above it ({previous_label})"
            )
        numbers.add(number)
        previous, previous_label = number, label
        if not any(line.startswith("- ") for line in body):
            problems.append(f"release {label} has no '- ' bullet")
        if index == 0 and label != version:
            problems.append(f"newest release {label} does not match VERSION {version}")
    return problems


def test_checked_in_changelog_passes_the_structure_rules() -> None:
    text = (_REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    version = (_REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert changelog_problems(text, version) == []


_SYNTHETIC_CHANGELOGS = [
    pytest.param(
        "\n".join(
            [
                _UNRELEASED,
                "",
                "## [0.2.0] - 2026-11-12",
                "",
                "- first",
                "",
                "## [0.2.0] - 2026-11-11",
                "",
                "- second",
            ]
        ),
        "0.2.0",
        id="duplicate-version",
    ),
    pytest.param(
        "\n".join(
            [
                _UNRELEASED,
                "",
                "## [0.1.0] - 2026-11-11",
                "",
                "- first",
                "",
                "## [0.2.0] - 2026-11-12",
                "",
                "- second",
            ]
        ),
        "0.1.0",
        id="ascending-pair",
    ),
    pytest.param(
        "\n".join(
            [
                _UNRELEASED,
                "",
                "## [0.2.0] - 2026-11-12",
                "",
                "- first",
                "",
                "## [0.1.0] - 2026-11-11",
                "",
                "### Fixed",
                "",
            ]
        ),
        "0.2.0",
        id="empty-section",
    ),
    pytest.param(
        "\n".join(
            [
                _UNRELEASED,
                "",
                "## [0.2.0] - 2026-11-12",
                "",
                "- first",
            ]
        ),
        "0.3.0",
        id="newest-differs-from-version",
    ),
]


@pytest.mark.parametrize(("text", "version"), _SYNTHETIC_CHANGELOGS)
def test_checker_rejects_a_broken_changelog(text: str, version: str) -> None:
    assert changelog_problems(text, version)


def test_each_reconciled_reference_appears_in_exactly_one_bullet() -> None:
    text = (_REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    bullets = [line for line in text.split("\n") if line.startswith("- ")]
    counts = {
        number: sum(f"(#{number})" in bullet for bullet in bullets)
        for number in _RECONCILED_REFERENCES
    }
    assert {number: count for number, count in counts.items() if count != 1} == {}
