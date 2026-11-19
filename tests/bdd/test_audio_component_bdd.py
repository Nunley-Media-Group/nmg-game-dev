# ruff: noqa: E501  -- step decorators repeat the Gherkin text verbatim, so they run long.
"""pytest-bdd bindings for audio_component.feature: SCN001-SCN009 of #237.

SCN001-SCN004, SCN008, and SCN009 run here against temp projects: scaffold, sync, and refresh run in
process, and ``import_audio`` runs with the fake Godot runner, so no engine starts. SCN005-SCN007
describe NmgAudio's playback, which only Godot can run. They are bound to the GDScript tests in
``test_nmg_audio.gd``, which the headless add-on run (gate-godot-headless) executes, so each binding
checks that its test method exists.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenario, then, when

from nmg_game_dev.audio import import_audio
from nmg_game_dev.audio.__main__ import main as audio_main
from nmg_game_dev.audio.tables import TABLE_NAME
from nmg_game_dev.design.__main__ import main as design_main
from tests.unit.audio.conftest import fake_godot, sine, write_wav

FEATURE = "audio_component.feature"
REPO_ROOT = Path(__file__).resolve().parents[2]
NMG_AUDIO_TESTS = (
    REPO_ROOT
    / "plugins"
    / "nmg-game-dev-godot-addon"
    / "addons"
    / "nmg_game_dev"
    / "tests"
    / "test_nmg_audio.gd"
)
TABLE_DIR = Path("game") / "systems" / "Audio"
HEADER = '[gd_resource type="Resource" script_class="NmgAudioTable" load_steps=2 format=3]\n'
DOCS = {
    "elevenlabs": "docs/mcp/elevenlabs.md",
    "contract": "docs/design-contract.md",
    "finalize": "docs/mcp/finalize.md",
}


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    root = tmp_path / "project"
    (root / "game").mkdir(parents=True)
    (root / "game" / "project.godot").write_text("config_version=5\n", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    return {"root": root, "out": "", "exit": None}


def _doc(root: Path, file_name: str, text: str) -> None:
    path = root / "docs" / "design" / file_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _sync(state: dict[str, Any]) -> None:
    out, err = io.StringIO(), io.StringIO()
    code = design_main(["sync", "--project", str(state["root"])], stdout=out, stderr=err)
    assert code == 0, out.getvalue() + err.getvalue()


def _write_table_stub(root: Path) -> Path:
    table = root / TABLE_DIR / TABLE_NAME
    table.parent.mkdir(parents=True, exist_ok=True)
    table.write_text(HEADER, encoding="utf-8")
    return table


def _assert_gd_defines(method: str) -> None:
    assert f"func {method}(" in NMG_AUDIO_TESTS.read_text(encoding="utf-8")


@scenario(FEATURE, "Scaffold creates an Audio component")
def test_scaffold_creates_an_audio_component() -> None:
    """SCN001: scaffold writes the NmgAudio script that loads the table, and the NmgAudioTable (AC1)."""


@given(parsers.parse('a system entry "{name}" with template "{template}" in the backlog'))
def _system_entry(state: dict[str, Any], name: str, template: str) -> None:
    _doc(
        state["root"],
        f"{name.lower()}.md",
        f"---\ntype: system\nname: {name}\ntemplate: {template}\n---\n",
    )
    _sync(state)


@when("design scaffold runs")
def _scaffold_runs(state: dict[str, Any]) -> None:
    out, err = io.StringIO(), io.StringIO()
    state["exit"] = design_main(
        ["scaffold", "--project", str(state["root"])], stdout=out, stderr=err
    )
    state["out"] = out.getvalue()


@then(parsers.parse('"{path}" declares "{base}" and loads "{res}"'))
def _script_declares(state: dict[str, Any], path: str, base: str, res: str) -> None:
    text = (state["root"] / path).read_text(encoding="utf-8")
    assert base in text
    assert f'load("{res}")' in text


@then(parsers.parse('"{path}" is an NmgAudioTable resource'))
def _table_is_resource(state: dict[str, Any], path: str) -> None:
    text = (state["root"] / path).read_text(encoding="utf-8")
    assert text.startswith("[gd_resource ")
    assert 'script_class="NmgAudioTable"' in text.splitlines()[0]


@scenario(FEATURE, "Existing systems are unchanged")
def test_existing_systems_are_unchanged() -> None:
    """SCN002: an entry without template keeps the plain Node script, and no existing file is overwritten (AC2)."""


@given(parsers.parse('a system entry "{name}" without template and an existing "{path}"'))
def _plain_entry_and_existing_script(state: dict[str, Any], name: str, path: str) -> None:
    root = state["root"]
    _doc(root, f"{name.lower()}.md", f"---\ntype: system\nname: {name}\n---\n")
    # The Audio entry is the one that would scaffold into the existing script.
    _doc(root, "audio.md", "---\ntype: system\nname: Audio\ntemplate: audio\n---\n")
    existing = root / path
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_text("# existing, not ours\n", encoding="utf-8")
    state["existing"] = existing
    _sync(state)


@then(parsers.parse('"{path}" extends Node'))
def _extends_node(state: dict[str, Any], path: str) -> None:
    assert "extends Node\n" in (state["root"] / path).read_text(encoding="utf-8")


@then("the existing Audio script is reported unchanged and not rewritten")
def _existing_unchanged(state: dict[str, Any]) -> None:
    assert state["existing"].read_text(encoding="utf-8") == "# existing, not ours\n"
    assert "unchanged system Audio: game/systems/Audio/audio.gd" in state["out"].splitlines()


@scenario(FEATURE, "Refresh fills the name table")
def test_refresh_fills_the_name_table() -> None:
    """SCN003: the CLI refresh maps sounds and region music into the table, and a rerun is byte-identical (AC3)."""


@given(parsers.parse('"{wav}", "{ogg}", and region "{region}" with music "{music}"'))
def _sounds_and_region(state: dict[str, Any], wav: str, ogg: str, region: str, music: str) -> None:
    root = state["root"]
    for relative in (wav, ogg):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"sound")
    _doc(root, f"{region.lower()}.md", f"---\ntype: region\nname: {region}\nmusic: {music}\n---\n")
    _sync(state)
    state["table"] = _write_table_stub(root)


@when("python -m nmg_game_dev.audio refresh runs twice")
def _refresh_runs_twice(state: dict[str, Any], capsys: pytest.CaptureFixture[str]) -> None:
    root = str(state["root"])
    state["runs"], state["bytes"] = [], []
    for _ in range(2):
        assert audio_main(["refresh", "--project", root]) == 0
        state["runs"].append(json.loads(capsys.readouterr().out))
        state["bytes"].append(state["table"].read_bytes())


@then(
    parsers.parse(
        'the table maps "{sound_a}" and "{sound_b}" to their res:// paths and theme "{region}" to "{theme}"'
    )
)
def _table_maps_sounds_and_theme(
    state: dict[str, Any], sound_a: str, sound_b: str, region: str, theme: str
) -> None:
    text = state["table"].read_text(encoding="utf-8")
    assert f'"{sound_a}": "res://assets/Audio/{sound_a}.wav"' in text
    assert f'"{sound_b}": "res://assets/Audio/{sound_b}.ogg"' in text
    assert f'"{region}": "{theme}"' in text


@then("the second run leaves the table byte-identical")
def _second_run_identical(state: dict[str, Any]) -> None:
    assert state["bytes"][1] == state["bytes"][0]
    assert state["runs"][1] == {"refreshed_tables": []}


@scenario(FEATURE, "import_audio refreshes automatically")
def test_import_audio_refreshes_automatically() -> None:
    """SCN004: a successful import adds the sound to the table and lists the table in refreshed_tables (AC4)."""


@given("a project with an Audio component table")
def _project_with_table(state: dict[str, Any]) -> None:
    state["table"] = _write_table_stub(state["root"])


@when(parsers.parse('import_audio imports sound effect "{name}"'))
def _import_sound(state: dict[str, Any], tmp_path: Path, name: str) -> None:
    saved = tmp_path / "saved" / f"{name}.wav"
    saved.parent.mkdir(parents=True, exist_ok=True)
    write_wav(saved, sine(0.25, 22050), 22050)
    state["result"] = import_audio(
        saved, name, "sfx", project_root=state["root"], godot=fake_godot()
    )


@then(parsers.re(r'^the table maps "(?P<name>[^"]+)" to "(?P<res>[^"]+)"$'))
def _table_maps_sound(state: dict[str, Any], name: str, res: str) -> None:
    assert f'"{name}": "{res}"' in state["table"].read_text(encoding="utf-8")


@then("the result's refreshed_tables lists the table")
def _result_lists_table(state: dict[str, Any]) -> None:
    assert state["result"]["refreshed_tables"] == [f"{TABLE_DIR.as_posix()}/{TABLE_NAME}"]


def test_scn005_calling_a_missing_sound_is_safe() -> None:
    """SCN005: bound to test_nmg_audio.gd, which the headless Godot run executes (AC5)."""
    _assert_gd_defines("test_missing_sound_plays_nothing_and_warns_once")


def test_scn006_music_crossfades_loops_and_ducks_for_stingers() -> None:
    """SCN006: bound to test_nmg_audio.gd, which the headless Godot run executes (AC6)."""
    _assert_gd_defines("test_music_repeat_crossfade_loop_and_stinger_duck")


def test_scn007_volumes_persist() -> None:
    """SCN007: bound to test_nmg_audio.gd, which the headless Godot run executes (AC7)."""
    _assert_gd_defines("test_volumes_persist_to_a_new_component")


@scenario(FEATURE, "The flow and fields are documented")
def test_the_flow_and_fields_are_documented() -> None:
    """SCN008: the ElevenLabs, design contract, and finalize docs describe the flow, fields, and tool (AC8)."""


@given("the ElevenLabs, design contract, and finalize MCP docs")
def _docs(state: dict[str, Any]) -> None:
    state["docs"] = {
        key: (REPO_ROOT / rel).read_text(encoding="utf-8") for key, rel in DOCS.items()
    }


@when("a reader looks up the audio component")
def _reader_looks_up(state: dict[str, Any]) -> None:
    state["section"] = (
        state["docs"]["elevenlabs"].split("## The audio component", 1)[1].split("\n## ", 1)[0]
    )


@then(
    "they describe scaffold, import, refresh, and gameplay calls, the template and music fields, and refresh_audio_table"
)
def _docs_describe_flow(state: dict[str, Any]) -> None:
    section, docs = state["section"], state["docs"]
    for word in ("**Scaffold.**", "**Import.**", "**Refresh.**", "sfx(", "music("):
        assert word in section
    assert "`template`" in docs["contract"] and "`music`" in docs["contract"]
    assert "refresh_audio_table" in docs["finalize"]


@scenario(FEATURE, "Sync validates the new fields")
def test_sync_validates_the_new_fields() -> None:
    """SCN009: design sync reports design.invalid_field for template and for music (AC9)."""


@given('a system entry with template "lights" and a region entry with an empty music value')
def _invalid_fields(state: dict[str, Any]) -> None:
    _doc(state["root"], "lights.md", "---\ntype: system\nname: Lights\ntemplate: lights\n---\n")
    _doc(state["root"], "forest.md", "---\ntype: region\nname: Forest\nmusic: ''\n---\n")


@when("design sync runs")
def _sync_runs(state: dict[str, Any]) -> None:
    out, err = io.StringIO(), io.StringIO()
    state["exit"] = design_main(["sync", "--project", str(state["root"])], stdout=out, stderr=err)
    state["out"] = out.getvalue()


@then('it reports design.invalid_field for "template" and for "music"')
def _reports_invalid_fields(state: dict[str, Any]) -> None:
    lines = state["out"].splitlines()
    assert (
        'error design.invalid_field docs/design/lights.md: template — template must be "audio" or left out'
        in lines
    )
    assert any(
        line.startswith("error design.invalid_field docs/design/forest.md: music — ")
        for line in lines
    )
    assert state["exit"] == 1
