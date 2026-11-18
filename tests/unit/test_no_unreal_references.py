"""Guard: no tracked file outside the exemptions references the retired engine (#249 AC14).

Every tracked path and text body is checked against case-insensitive ``unreal``, ``vibeue``,
``.uproject`` and ``.uasset``, plus the case-sensitive whole word ``UE``. ``specs/`` and
``CHANGELOG.md`` keep history; ``EXEMPT`` lists the conversion command's files, which must name
what they convert from.
"""

from __future__ import annotations

import re
import subprocess
from typing import Final

from tests._scaffold_contract import REPO_ROOT

INSENSITIVE: Final = re.compile(r"unreal|vibeue|\.uproject|\.uasset", re.IGNORECASE)
SENSITIVE: Final = re.compile(r"\bUE\b")

HISTORY: Final = ("specs/", "CHANGELOG.md")
EXEMPT: Final = (
    "src/nmg_game_dev/convert/",
    "skills/convert-to-godot/",
    "docs/skills/convert-to-godot.md",
    "tests/unit/convert/",
    "tests/convert_fakes.py",
    "tests/bdd/features/convert_to_godot.feature",
    "tests/bdd/test_convert_to_godot_bdd.py",
    "tests/unit/test_no_unreal_references.py",
)


def references_engine(text: str) -> bool:
    """Return True when ``text`` names the retired engine, its plugin, or its file types."""
    return bool(INSENSITIVE.search(text) or SENSITIVE.search(text))


def _skipped(path: str) -> bool:
    return any(path == entry or path.startswith(entry) for entry in (*HISTORY, *EXEMPT))


def _tracked_files() -> list[str]:
    output = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
    ).stdout
    return [name for name in output.decode("utf-8").split("\0") if name]


def test_no_tracked_file_references_the_retired_engine() -> None:
    offenders: list[str] = []
    for path in _tracked_files():
        if _skipped(path):
            continue
        if references_engine(path):
            offenders.append(f"{path}: path")
            continue
        file = REPO_ROOT / path
        if not file.is_file():
            continue
        data = file.read_bytes()
        if b"\0" in data[:8192]:
            continue
        text = data.decode("utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), start=1):
            if references_engine(line):
                offenders.append(f"{path}:{number}: {line.strip()[:120]}")
                break
    assert offenders == [], "retired engine references:\n" + "\n".join(offenders)


def test_exemptions_are_exactly_the_conversion_files_and_exist() -> None:
    assert EXEMPT == (
        "src/nmg_game_dev/convert/",
        "skills/convert-to-godot/",
        "docs/skills/convert-to-godot.md",
        "tests/unit/convert/",
        "tests/convert_fakes.py",
        "tests/bdd/features/convert_to_godot.feature",
        "tests/bdd/test_convert_to_godot_bdd.py",
        "tests/unit/test_no_unreal_references.py",
    )
    missing = [entry for entry in EXEMPT if not (REPO_ROOT / entry).exists()]
    assert missing == []


def test_matcher_whole_word_abbreviation_and_any_case_engine_name() -> None:
    assert references_engine("Import into UE 5.8")
    assert not references_engine("the job queue drains")
    assert not references_engine("a TRUE value")
    assert not references_engine("ue lowercase is not the abbreviation")
    assert references_engine("UNREAL")
    assert references_engine("Unreal Engine")
    assert references_engine("unreal")
    assert references_engine("Game.uproject")
    assert references_engine("SM_Crate.uasset")
    assert references_engine("VibeUE")
