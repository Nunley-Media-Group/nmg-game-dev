# ruff: noqa: E501  -- step decorators repeat the Gherkin text verbatim, so they run long.
"""pytest-bdd bindings for audio_table_names.feature: AC1-AC4 of #302.

Each scenario runs against a temp Godot project with ``refresh_tables`` in process, so no engine
starts. The tool description and the skill are read from their files in the repository.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenario, then, when

from nmg_game_dev.audio import AudioError
from nmg_game_dev.audio.tables import TABLE_NAME, refresh_tables

FEATURE = "audio_table_names.feature"
REPO_ROOT = Path(__file__).resolve().parents[2]
TABLE = Path("game") / "systems" / "Audio" / TABLE_NAME
HEADER = '[gd_resource type="Resource" script_class="NmgAudioTable" load_steps=2 format=3]\n'
REFRESH_CODES = (
    "audio.godot_project_missing",
    "audio.backlog_invalid",
    "audio.table_unreadable",
    "audio.table_unwritable",
    "audio.duplicate_sound",
)


@pytest.fixture
def state(tmp_path: Path) -> dict[str, Any]:
    return {"root": tmp_path / "project", "table_before": b"", "error": None}


def _write_sound(root: Path, relative: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"sound")


@given("a Godot project with an Audio name table")
def _godot_project_with_table(state: dict[str, Any]) -> None:
    root: Path = state["root"]
    (root / "game").mkdir(parents=True)
    (root / "game" / "project.godot").write_text("config_version=5\n", encoding="utf-8")
    table = root / TABLE
    table.parent.mkdir(parents=True)
    table.write_text(HEADER, encoding="utf-8")
    state["table_before"] = table.read_bytes()


@given(parsers.parse('the sound file "{path}"'))
def _sound_file(state: dict[str, Any], path: str) -> None:
    _write_sound(state["root"], path)


@given(parsers.parse('the sound files "{first}" and "{second}"'))
def _sound_files(state: dict[str, Any], first: str, second: str) -> None:
    _write_sound(state["root"], first)
    _write_sound(state["root"], second)


@when("the sound table is refreshed")
def _refresh(state: dict[str, Any]) -> None:
    try:
        refresh_tables(state["root"])
    except AudioError as error:
        state["error"] = error


@then(parsers.parse('the table maps "{stem}" to "{path}"'))
def _table_maps(state: dict[str, Any], stem: str, path: str) -> None:
    assert state["error"] is None
    text = (state["root"] / TABLE).read_text(encoding="utf-8")
    assert f'"{stem}": "{path}"' in text


@then(parsers.parse('the refresh fails with error code "{code}"'))
def _refresh_fails(state: dict[str, Any], code: str) -> None:
    assert state["error"] is not None
    assert state["error"].code == code


@then(parsers.parse('the error message names "{first}" and "{second}"'))
def _message_names(state: dict[str, Any], first: str, second: str) -> None:
    message = state["error"].message
    assert first in message
    assert second in message


@then("the error remediation says to rename or delete the extra file")
def _remediation_says_rename_or_delete(state: dict[str, Any]) -> None:
    assert "rename or delete the extra file" in state["error"].remediation


@then("the name table file is unchanged")
def _table_unchanged(state: dict[str, Any]) -> None:
    assert (state["root"] / TABLE).read_bytes() == state["table_before"]


@then(parsers.parse('docs/mcp/finalize.md documents "{code}" and its resolution'))
def _docs_document_the_code(code: str) -> None:
    text = (REPO_ROOT / "docs" / "mcp" / "finalize.md").read_text(encoding="utf-8")
    section = text.split("## refresh_audio_table", 1)[1].split("\n## ", 1)[0]
    assert code in section
    assert "rename or delete" in section


@given("the refresh_audio_table description in mcp-servers/finalize/tools.json")
def _tools_json_source(state: dict[str, Any]) -> None:
    state["tools_json"] = REPO_ROOT / "mcp-servers" / "finalize" / "tools.json"


@when("it is read")
def _read_description(state: dict[str, Any]) -> None:
    manifest = json.loads(state["tools_json"].read_text(encoding="utf-8"))
    tool = next(entry for entry in manifest["tools"] if entry["name"] == "refresh_audio_table")
    state["description"] = tool["description"]


@then(
    'it names "audio.godot_project_missing", "audio.backlog_invalid", "audio.table_unreadable", "audio.table_unwritable", and "audio.duplicate_sound"'
)
def _names_every_code(state: dict[str, Any]) -> None:
    for code in REFRESH_CODES:
        assert code in state["description"]


@given("the body of skills/generate-audio/SKILL.md")
def _skill_body(state: dict[str, Any]) -> None:
    state["skill"] = (REPO_ROOT / "skills" / "generate-audio" / "SKILL.md").read_text(
        encoding="utf-8"
    )


@when("its import step is read")
def _import_step(state: dict[str, Any]) -> None:
    skill: str = state["skill"]
    start = skill.index("7. **Download and import.**")
    end = skill.index("## Failure modes and remediation")
    state["step"] = skill[start:end]


@then('it says to report "refresh_warning" with its remediation')
def _reports_refresh_warning(state: dict[str, Any]) -> None:
    assert "refresh_warning" in state["step"]
    assert "remediation" in state["step"]


@then("it says the sound is still imported")
def _says_still_imported(state: dict[str, Any]) -> None:
    assert "still imported" in state["step"]


@scenario(FEATURE, "Extensions are matched case-insensitively")
def test_extensions_are_matched_case_insensitively() -> None:
    """AC1: Click.WAV is the sound Click, at its real file name."""


@scenario(FEATURE, "Duplicate stems are reported, not silently collapsed")
def test_duplicate_stems_are_reported_not_silently_collapsed() -> None:
    """AC2: a shared stem fails the refresh, names both files, and leaves the table unchanged."""


@scenario(FEATURE, "The refresh tool description lists every error code")
def test_the_refresh_tool_description_lists_every_error_code() -> None:
    """AC3: tools.json names all five refresh error codes."""


@scenario(FEATURE, "The skill handles refresh_warning")
def test_the_skill_handles_refresh_warning() -> None:
    """AC4: the generate-audio import step reports refresh_warning and says the sound is imported."""
