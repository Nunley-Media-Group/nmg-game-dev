"""AC4: release notes headed by the version, with changelog text, gates, and artifacts."""

from __future__ import annotations

from pathlib import Path

from nmg_game_dev.ship.artifacts import ReleaseEntry
from nmg_game_dev.ship.release_notes import RELEASE_NOTES_NAME, write_release_notes

_SHA = "a" * 64


def test_notes_carry_the_version_changes_gates_and_artifacts(tmp_path: Path) -> None:
    path = write_release_notes(
        tmp_path,
        "macos",
        [ReleaseEntry(platform="macos", path="macos/Dogfood.app", sha256=_SHA)],
        False,
        ("macos",),
        version="1.3.0",
        changes="- Faster loading.",
        gates=[
            ("version", "1.2.3 -> 1.3.0"),
            ("changelog", "## 1.3.0 found"),
            ("tests", "42 passed, 0 failed"),
            ("mobile budgets", "not applicable"),
        ],
    )
    assert path == tmp_path / RELEASE_NOTES_NAME
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines[0] == "# Release notes — 1.3.0"
    assert "- Version: 1.3.0" in lines
    assert lines.index("## Changes") < lines.index("## Gates") < lines.index("## Artifacts")
    changes = lines[lines.index("## Changes") + 1 : lines.index("## Gates")]
    assert "- Faster loading." in changes
    gates = lines[lines.index("## Gates") + 1 : lines.index("## Artifacts")]
    assert "- tests: 42 passed, 0 failed" in gates
    assert "- version: 1.2.3 -> 1.3.0" in gates
    assert "- mobile budgets: not applicable" in gates
    assert f"| macos | `macos/Dogfood.app` | `{_SHA}` |" in lines


def test_notes_without_a_version_keep_the_plain_heading(tmp_path: Path) -> None:
    path = write_release_notes(tmp_path, "web", [], False, ("web",))
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# Release notes\n")
    assert "## Changes" not in text
    assert "## Gates" not in text
    assert "| - | none | - |" in text


def test_a_dry_run_is_marked_and_lists_no_artifact(tmp_path: Path) -> None:
    path = write_release_notes(
        tmp_path,
        "windows",
        [],
        True,
        ("windows",),
        version="1.2.4",
        changes="- Fixed a crash.",
        gates=[("import", "planned (dry run)")],
    )
    text = path.read_text(encoding="utf-8")
    assert "# Release notes — 1.2.4" in text
    assert "DRY RUN" in text
    assert "- import: planned (dry run)" in text
    assert "| - | none | - |" in text
