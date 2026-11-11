"""pytest-bdd bindings for audio_import.feature: SCN001-SCN008 (#155).

The Unreal side is the fake editor in ``tests/unit/fake_unreal_audio.py``, which runs the
generated UE code against a fake ``unreal`` module. The fixtures are the committed clips in
``tests/fixtures/audio``. No live editor is started and no ElevenLabs call is made. The steps share
one ``state`` dict per scenario.
"""

from __future__ import annotations

import json
import shutil
import wave
from pathlib import Path
from typing import Any

import miniaudio
import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from nmg_game_dev.audio import AudioError, import_audio
from nmg_game_dev.audio.__main__ import main as audio_main
from nmg_game_dev.finalize import import_audio as import_audio_tool
from tests.unit.fake_unreal_audio import FakeEditor, FakeUnrealPythonClient

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "audio"
SFX_ASSET = "/Game/Audio/SFX/SW_DoorCreak"
MUSIC_ASSET = "/Game/Audio/Music/SW_ForestTheme"
INVALID_CODES = {"audio.invalid_request", "audio.unsupported_format", "audio.asset_exists"}

scenarios("audio_import.feature")

_FORMAT_FIXTURES = {"WAV": "tone.wav", "MP3": "tone.mp3", "OGG": "tone.ogg", "FLAC": "tone.flac"}


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    saved = tmp_path / "saved"
    saved.mkdir()
    values: dict[str, Any] = {
        "root": root,
        "saved": saved,
        "client": FakeUnrealPythonClient(FakeEditor()),
        "name": "DoorCreak",
        "kind": "sfx",
        "loop": False,
        "src": None,
        "result": None,
        "error": None,
        "outcomes": [],
        "cases": [],
        "before": None,
        "cli": None,
        "tool": None,
        "repo": None,
    }

    def _factory(*_args: Any, **_kwargs: Any) -> FakeUnrealPythonClient:
        client: FakeUnrealPythonClient = values["client"]
        return client

    monkeypatch.setattr("nmg_game_dev.audio.core.UnrealMcpClient", _factory)
    monkeypatch.setattr("nmg_game_dev.audio.__main__.UnrealMcpClient", _factory)
    return values


def _save(state: dict[str, Any], fixture: str) -> Path:
    target: Path = state["saved"] / fixture
    shutil.copyfile(FIXTURES / fixture, target)
    state["src"] = target
    return target


def _import(state: dict[str, Any], name: str | None = None, kind: str | None = None) -> None:
    if name is not None:
        state["name"] = name
    if kind is not None:
        state["kind"] = kind
    state["error"] = None
    try:
        state["result"] = import_audio(state["src"], state["name"], state["kind"], state["loop"])
    except AudioError as error:
        state["result"] = None
        state["error"] = error


def _tree(root: Path) -> list[tuple[str, bytes | None]]:
    """Every path under ``root`` with its bytes for files, so a write of any kind shows up."""
    entries: list[tuple[str, bytes | None]] = []
    for path in sorted(root.rglob("*")):
        rel = str(path.relative_to(root))
        entries.append((rel, path.read_bytes() if path.is_file() else None))
    return entries


# --- Given ---------------------------------------------------------------------------------------


@given(
    parsers.re(
        r"^a saved (?P<what>WAV|MP3|OGG|FLAC|audio) file"
        r"(?: and (?:a|an) (?P<link>reachable|unreachable) Unreal MCP)?$"
    )
)
def _saved_file(state: dict[str, Any], what: str, link: str | None) -> None:
    _save(state, _FORMAT_FIXTURES.get(what, "tone.wav"))
    if link == "unreachable":
        state["client"] = FakeUnrealPythonClient(reachable=False)


@given("an import request with a bad name, kind, path, format, or an existing target")
def _bad_requests(state: dict[str, Any]) -> None:
    existing = state["root"] / "SourceArt" / "Audio" / "SFX" / "DoorCreak.wav"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"keep me")
    src = _save(state, "tone.wav")
    odd = state["saved"] / "clip.m4a"
    odd.write_bytes(b"not decoded")
    state["cases"] = [
        {"name": "doorCreak", "kind": "sfx", "src": src, "codes": {"audio.invalid_request"}},
        {"name": "SFX_DoorCreak", "kind": "sfx", "src": src, "codes": {"audio.invalid_request"}},
        {"name": "DoorCreak", "kind": "voice", "src": src, "codes": {"audio.invalid_request"}},
        {
            "name": "DoorCreak",
            "kind": "sfx",
            "src": state["saved"] / "absent.wav",
            "codes": {"audio.invalid_request"},
        },
        {"name": "DoorCreak", "kind": "sfx", "src": odd, "codes": {"audio.unsupported_format"}},
        {"name": "DoorCreak", "kind": "sfx", "src": src, "codes": {"audio.asset_exists"}},
    ]


@given("a corrupt MP3 file")
def _corrupt(state: dict[str, Any]) -> None:
    _save(state, "corrupt.mp3")


@given("the same request and fakes")
def _same_request(state: dict[str, Any]) -> None:
    _save(state, "tone.wav")
    state["name"] = "DoorCreak"
    state["kind"] = "sfx"


@given("the repository")
def _repository(state: dict[str, Any]) -> None:
    state["repo"] = REPO_ROOT


# --- When ----------------------------------------------------------------------------------------


@when(parsers.parse('import_audio runs with name "{name}" and kind "{kind}"'))
def _tool_run(state: dict[str, Any], name: str, kind: str) -> None:
    _import(state, name, kind)


@when("it is imported")
def _imported(state: dict[str, Any]) -> None:
    _import(state)


@when(parsers.parse('it is imported with name "{name}" and kind "{kind}"'))
def _imported_named(state: dict[str, Any], name: str, kind: str) -> None:
    _import(state, name, kind)


@when(parsers.parse("it is imported with loop {flag}"))
def _imported_looping(state: dict[str, Any], flag: str) -> None:
    state["loop"] = flag == "true"
    _import(state)


@when("it is submitted")
def _submitted(state: dict[str, Any]) -> None:
    state["before"] = _tree(state["root"])
    outcomes: list[tuple[set[str], str | None]] = []
    for case in state["cases"]:
        try:
            import_audio(case["src"], case["name"], case["kind"])
            outcomes.append((case["codes"], None))
        except AudioError as error:
            outcomes.append((case["codes"], error.code))
    state["outcomes"] = outcomes


@when("it runs through the CLI and through the import_audio tool")
def _cli_and_tool(state: dict[str, Any], capsys: pytest.CaptureFixture[str]) -> None:
    cli_root = state["saved"].parent / "cli-project"
    cli_root.mkdir()
    code = audio_main(
        [
            "import",
            "--file",
            str(state["src"]),
            "--name",
            state["name"],
            "--kind",
            state["kind"],
            "--project",
            str(cli_root),
        ]
    )
    state["cli"] = (code, json.loads(capsys.readouterr().out))
    # The CLI already imported this name, so the tool gets a fresh editor to import into.
    state["client"].editor.assets.clear()
    state["tool"] = import_audio_tool(str(state["src"]), state["name"], state["kind"])


@when("the guards run")
def _guards(state: dict[str, Any]) -> None:
    state["mcp_json"] = json.loads((state["repo"] / ".mcp.json").read_text(encoding="utf-8"))
    state["mcp_text"] = (state["repo"] / ".mcp.json").read_text(encoding="utf-8")


# --- Then ----------------------------------------------------------------------------------------


@then("SourceArt/Audio/SFX/DoorCreak.wav holds the file")
def _sfx_stored(state: dict[str, Any]) -> None:
    stored = state["root"] / "SourceArt" / "Audio" / "SFX" / "DoorCreak.wav"
    assert stored.read_bytes() == state["src"].read_bytes()


@then("/Game/Audio/SFX/SW_DoorCreak is imported with looping off")
def _sfx_imported(state: dict[str, Any]) -> None:
    sound = state["client"].editor.sound_wave(SFX_ASSET)
    assert sound is not None, "no SoundWave was imported"
    assert sound.get_editor_property("looping") is False


@then("SourceArt/Audio/Music/ForestTheme.wav is a 16-bit PCM WAV at the source rate and channels")
def _music_wav(state: dict[str, Any]) -> None:
    info = miniaudio.get_file_info(str(state["src"]))
    stored = state["root"] / "SourceArt" / "Audio" / "Music" / "ForestTheme.wav"
    with wave.open(str(stored), "rb") as reader:
        assert reader.getsampwidth() == 2
        assert reader.getframerate() == info.sample_rate
        assert reader.getnchannels() == info.nchannels


@then("the result reports converted true")
def _converted(state: dict[str, Any]) -> None:
    assert state["result"]["converted"] is True


@then("the SoundWave loops")
def _loops(state: dict[str, Any]) -> None:
    sound = state["client"].editor.sound_wave(SFX_ASSET)
    assert sound is not None
    assert sound.get_editor_property("looping") is True


@then("the result has imported_to_unreal false and warning mcp.unreal.unreachable")
def _warned(state: dict[str, Any]) -> None:
    assert state["result"]["imported_to_unreal"] is False
    assert state["result"]["warning"]["code"] == "mcp.unreal.unreachable"


@then("the WAV stays under SourceArt/Audio")
def _wav_kept(state: dict[str, Any]) -> None:
    assert (state["root"] / "SourceArt" / "Audio" / "SFX" / "DoorCreak.wav").is_file()


@then("it fails with audio.invalid_request, audio.unsupported_format, or audio.asset_exists")
def _invalid_codes(state: dict[str, Any]) -> None:
    assert state["outcomes"], "no request was submitted"
    for expected, actual in state["outcomes"]:
        assert actual in expected and actual in INVALID_CODES, f"got {actual}, want {expected}"


@then("nothing is written and Unreal is not called")
def _nothing_written(state: dict[str, Any]) -> None:
    assert _tree(state["root"]) == state["before"]
    assert state["client"].codes == []


@then("it fails with audio.decode_failed and leaves no file behind")
def _decode_failed(state: dict[str, Any]) -> None:
    assert state["error"] is not None and state["error"].code == "audio.decode_failed"
    folder = state["root"] / "SourceArt" / "Audio" / "SFX"
    assert not (folder / "DoorCreak.wav").exists()
    assert not (folder / "DoorCreak.wav.tmp").exists()
    assert state["client"].codes == []


@then("both return the same result JSON")
def _same_json(state: dict[str, Any]) -> None:
    code, cli_json = state["cli"]
    assert code == 0
    tool_json = state["tool"]
    assert "error" not in tool_json
    cli_json.pop("source_art")
    tool_json.pop("source_art")
    assert cli_json == tool_json


@then(".mcp.json has no elevenlabs entry and no ELEVENLABS text")
def _no_elevenlabs(state: dict[str, Any]) -> None:
    assert "elevenlabs" not in state["mcp_json"]["mcpServers"]
    assert "ELEVENLABS" not in state["mcp_text"]
