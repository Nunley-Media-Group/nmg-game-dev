"""pytest-bdd bindings for source_hygiene.feature: SCN001-SCN002 of #286.

SCN001 reads the Blender test runner and checks its comment and the retired-engine guard's
matcher. SCN002 measures every line of the Godot add-on's GDScript. Both only read the working
tree; neither runs Blender or Godot. The steps pass their values along through target fixtures.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from pytest_bdd import given, scenario, then, when

from tests._scaffold_contract import REPO_ROOT
from tests.unit.test_godot_addon_line_length import addon_gd_files, overlong_lines
from tests.unit.test_no_unreal_references import references_engine

FEATURE: Final = "source_hygiene.feature"
RUNNER: Final = REPO_ROOT / "tests" / "blender" / "_runner.py"


def _comment_above(source: str, name: str) -> list[str]:
    """Return the contiguous ``#`` comment lines directly above the assignment to ``name``."""
    lines = source.splitlines()
    index = next(i for i, line in enumerate(lines) if line.startswith(f"{name} ="))
    block: list[str] = []
    for line in reversed(lines[:index]):
        if not line.startswith("#"):
            break
        block.insert(0, line)
    return block


@scenario(FEATURE, "The Blender test runner names no Unreal plugin")
def test_scn001_the_blender_runner_names_no_unreal_plugin() -> None:
    """AC1: the runner has no ue-plugin text, its comment names plugins/, and the guard flags it."""


@given("the text of tests/blender/_runner.py", target_fixture="runner_text")
def runner_text_is_read() -> str:
    return RUNNER.read_text(encoding="utf-8")


@when('it is searched for "ue-plugin"', target_fixture="runner_matches")
def runner_is_searched_for_ue_plugin(runner_text: str) -> list[str]:
    return [line for line in runner_text.splitlines() if "ue-plugin" in line.lower()]


@then("nothing matches")
def nothing_matches(runner_matches: list[str]) -> None:
    assert runner_matches == []


@then("its comment describes the plugins/ layout")
def comment_describes_plugins_layout(runner_text: str) -> None:
    comment = " ".join(_comment_above(runner_text, "_REPO_ROOT"))
    assert "plugins/" in comment, comment


@then('the retired-engine guard flags the text "nmg-game-dev-ue-plugin"')
def guard_flags_ue_plugin() -> None:
    assert references_engine("nmg-game-dev-ue-plugin")


@scenario(FEATURE, "The Godot add-on's GDScript fits 100 columns")
def test_scn002_the_godot_addon_gdscript_fits_one_hundred_columns() -> None:
    """AC2: every line of every add-on .gd file is at most 100 characters."""


@given("every .gd file under plugins/nmg-game-dev-godot-addon/", target_fixture="gd_files")
def every_addon_gd_file() -> list[Path]:
    return addon_gd_files()


@when("each line's length is measured in characters", target_fixture="long_lines")
def each_line_is_measured(gd_files: list[Path]) -> list[str]:
    return overlong_lines(gd_files)


@then("no line is longer than 100 characters")
def no_line_is_too_long(long_lines: list[str]) -> None:
    assert long_lines == [], "lines over 100 characters:\n" + "\n".join(long_lines)
