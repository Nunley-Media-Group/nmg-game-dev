"""The Audio component's name table: render, refresh, and the documented flow (#237 AC3, AC8).

``render_table`` and ``refresh_tables`` read the sounds under ``game/assets/Audio/`` and the design
backlog. The sound files here are empty placeholders, since the table holds only their names, so no
Godot process runs. The CLI and MCP refresh are checked in their own test modules.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from nmg_game_dev.audio import AudioError
from nmg_game_dev.audio.tables import TABLE_NAME, refresh_tables, render_table
from nmg_game_dev.design import backlog
from nmg_game_dev.design.__main__ import main as design_main

REPO_ROOT = Path(__file__).resolve().parents[3]
FIELDS_NOT_A_MAPPING = (
    '{"version": 1, "entries": [{"type": "region", "name": "Forest", "asset_name": "Forest", '
    '"source": "docs/design/forest.md", "status": "planned", "fields": 5}]}'
)
TABLE = "game/systems/Audio/audio_table.tres"
HEADER = '[gd_resource type="Resource" script_class="NmgAudioTable" load_steps=2 format=3]\n'


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """A Godot project with no sounds, backlog, or name tables yet."""
    (tmp_path / "game").mkdir()
    (tmp_path / "game" / "project.godot").write_text("config_version=5\n", encoding="utf-8")
    return tmp_path


def _sound(root: Path, file_name: str) -> None:
    path = root / "game" / "assets" / "Audio" / file_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"sound")


def _table(root: Path, system: str = "Audio", text: str = HEADER) -> Path:
    path = root / "game" / "systems" / system / TABLE_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _region(root: Path, name: str, music: str) -> None:
    """Write a region doc that names a music sound, then sync the backlog."""
    doc = root / "docs" / "design" / f"{name.lower()}.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(f"---\ntype: region\nname: {name}\nmusic: {music}\n---\n", encoding="utf-8")
    out, err = io.StringIO(), io.StringIO()
    assert design_main(["sync", "--project", str(root)], stdout=out, stderr=err) == 0


def test_render_lists_sounds_by_file_stem_and_region_themes_in_sorted_order(root: Path) -> None:
    _sound(root, "PunchLight.wav")
    _sound(root, "ForestTheme.ogg")
    _sound(root, "DoorCreak.wav")
    _region(root, "Forest", "ForestTheme")

    text = render_table(root)

    assert text.startswith(HEADER)
    assert 'path="res://addons/nmg_game_dev/audio/nmg_audio_table.gd"' in text
    assert 'script = ExtResource("1_table")' in text
    assert (
        'sounds = {"DoorCreak": "res://assets/Audio/DoorCreak.wav", '
        '"ForestTheme": "res://assets/Audio/ForestTheme.ogg", '
        '"PunchLight": "res://assets/Audio/PunchLight.wav"}'
    ) in text
    assert 'themes = {"Forest": "ForestTheme"}' in text
    assert text.endswith("\n")


def test_render_without_sounds_or_a_backlog_has_empty_maps(root: Path) -> None:
    text = render_table(root)

    assert "sounds = {}" in text
    assert "themes = {}" in text


def test_refresh_rewrites_only_name_tables_and_returns_their_paths(root: Path) -> None:
    _sound(root, "DoorCreak.wav")
    table = _table(root)
    other_text = '[gd_resource type="Resource" script_class="Other" load_steps=1 format=3]\n'
    other = _table(root, system="Inventory", text=other_text)

    assert refresh_tables(root) == [TABLE]

    assert table.read_text(encoding="utf-8") == render_table(root)
    assert other.read_text(encoding="utf-8") == other_text


def test_a_second_refresh_writes_nothing_and_keeps_the_bytes(root: Path) -> None:
    _sound(root, "DoorCreak.wav")
    table = _table(root)
    assert refresh_tables(root) == [TABLE]
    first = table.read_bytes()

    assert refresh_tables(root) == []

    assert table.read_bytes() == first


def test_a_refresh_picks_up_a_sound_added_since_the_last_one(root: Path) -> None:
    _sound(root, "DoorCreak.wav")
    table = _table(root)
    refresh_tables(root)

    _sound(root, "PunchLight.wav")

    assert refresh_tables(root) == [TABLE]
    assert '"PunchLight": "res://assets/Audio/PunchLight.wav"' in table.read_text(encoding="utf-8")


def test_import_and_temporary_files_are_not_sounds(root: Path) -> None:
    _sound(root, "DoorCreak.wav")
    _sound(root, "DoorCreak.wav.import")
    _sound(root, "DoorCreak.wav.tmp")
    _sound(root, "notes.txt")
    table = _table(root)

    refresh_tables(root)

    assert 'sounds = {"DoorCreak": "res://assets/Audio/DoorCreak.wav"}' in table.read_text(
        encoding="utf-8"
    )


def test_refresh_with_no_name_table_returns_an_empty_list(root: Path) -> None:
    _sound(root, "DoorCreak.wav")

    assert refresh_tables(root) == []


def test_refresh_without_a_godot_project_raises_the_missing_project_code(tmp_path: Path) -> None:
    with pytest.raises(AudioError) as caught:
        refresh_tables(tmp_path)

    assert caught.value.code == "audio.godot_project_missing"
    assert caught.value.stage == "audio"
    assert "project.godot" in caught.value.message


def _backlog(root: Path, text: str | bytes) -> None:
    path = root / "docs" / "design" / "backlog.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text if isinstance(text, bytes) else text.encode("utf-8"))


@pytest.mark.parametrize(
    "text",
    [
        "{not json",
        "[]",
        '{"version": 1, "entries": [{"type": "region"}]}',
        FIELDS_NOT_A_MAPPING,
        b"\xff\xfe{}",
    ],
    ids=["not-json", "no-entries", "entry-without-fields", "fields-not-a-mapping", "not-utf8"],
)
def test_an_unreadable_backlog_raises_backlog_invalid_and_writes_nothing(
    root: Path, text: str | bytes
) -> None:
    """#237 review F1: a malformed backlog is an AudioError with a remediation, not a traceback."""
    _sound(root, "DoorCreak.wav")
    table = _table(root)
    _backlog(root, text)

    with pytest.raises(AudioError) as caught:
        refresh_tables(root)

    assert caught.value.code == "audio.backlog_invalid"
    assert caught.value.stage == "audio"
    assert "backlog.json" in caught.value.message
    assert "design sync" in caught.value.remediation
    assert table.read_text(encoding="utf-8") == HEADER


def test_without_a_name_table_refresh_reads_no_backlog(root: Path) -> None:
    """#237 review F4: no Audio component means nothing to refresh, so a bad backlog is not read."""
    _sound(root, "DoorCreak.wav")
    _table(root, system="Combat", text='[gd_resource type="Resource" format=3]\n')
    _backlog(root, "{not json")

    assert refresh_tables(root) == []


def test_a_table_that_is_not_utf8_is_not_a_name_table_and_is_left_alone(root: Path) -> None:
    """#237 review F1: a binary audio_table.tres is skipped; the real name table still refreshes."""
    _sound(root, "DoorCreak.wav")
    table = _table(root)
    binary = root / "game" / "systems" / "Binary" / TABLE_NAME
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"\xff\xfe\x00garbage")

    assert refresh_tables(root) == [TABLE]
    assert binary.read_bytes() == b"\xff\xfe\x00garbage"
    assert "DoorCreak" in table.read_text(encoding="utf-8")


def test_an_unreadable_table_raises_table_unreadable(root: Path) -> None:
    """#237 review F1: a table path that cannot be read is an AudioError, not an OSError."""
    (root / "game" / "systems" / "Audio" / TABLE_NAME).mkdir(parents=True)

    with pytest.raises(AudioError) as caught:
        refresh_tables(root)

    assert caught.value.code == "audio.table_unreadable"
    assert caught.value.stage == "audio"
    assert TABLE_NAME in caught.value.message
    assert caught.value.remediation


def test_a_table_that_cannot_be_written_raises_table_unwritable(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#237 review F1: a failed atomic write is an AudioError, and the table keeps its text."""
    _sound(root, "DoorCreak.wav")
    table = _table(root)

    def refuse(path: Path, text: str) -> None:
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr(backlog, "write_atomic", refuse)
    with pytest.raises(AudioError) as caught:
        refresh_tables(root)

    assert caught.value.code == "audio.table_unwritable"
    assert caught.value.stage == "audio"
    assert "Permission denied" in caught.value.message
    assert table.read_text(encoding="utf-8") == HEADER


def test_uppercase_extensions_map_by_stem_to_the_real_file_name(root: Path) -> None:
    """#302 AC1: Click.WAV and Door.OGG are sounds, keyed by stem with their real file names."""
    _sound(root, "Click.WAV")
    _sound(root, "Door.OGG")
    table = _table(root)

    refresh_tables(root)

    assert (
        'sounds = {"Click": "res://assets/Audio/Click.WAV", "Door": "res://assets/Audio/Door.OGG"}'
    ) in table.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "names",
    [
        ("Theme.wav", "Theme.ogg"),
        ("Theme.wav", "Theme.ogg", "Door.wav", "Door.ogg"),
    ],
    ids=["one-group", "two-groups"],
)
def test_files_sharing_a_stem_raise_duplicate_sound_and_write_nothing(
    root: Path, names: tuple[str, ...]
) -> None:
    """#302 AC2: every file that shares a sound name is named, and no table is rewritten."""
    for name in names:
        _sound(root, name)
    table = _table(root)

    with pytest.raises(AudioError) as caught:
        refresh_tables(root)

    assert caught.value.code == "audio.duplicate_sound"
    assert caught.value.stage == "audio"
    for name in names:
        assert name in caught.value.message
    assert "rename or delete the extra file" in caught.value.remediation
    assert "refresh the audio tables again" in caught.value.remediation
    assert table.read_text(encoding="utf-8") == HEADER


def test_docs_describe_the_audio_component_flow_fields_and_tool() -> None:
    elevenlabs = (REPO_ROOT / "docs" / "mcp" / "elevenlabs.md").read_text(encoding="utf-8")
    contract = (REPO_ROOT / "docs" / "design-contract.md").read_text(encoding="utf-8")
    finalize = (REPO_ROOT / "docs" / "mcp" / "finalize.md").read_text(encoding="utf-8")
    section = elevenlabs.split("## The audio component", 1)[1].split("\n## ", 1)[0]

    for step in ("**Scaffold.**", "**Import.**", "**Refresh.**", "**Play.**"):
        assert step in section
    for call in ("sfx(", "ui(", "music(", "stinger(", "region_music()", "set_volumes("):
        assert call in section
    assert "`template`" in contract and "`music`" in contract
    assert "audio_table.tres" in contract and "NmgAudio" in contract
    assert "refresh_audio_table" in finalize and "refreshed_tables" in finalize
