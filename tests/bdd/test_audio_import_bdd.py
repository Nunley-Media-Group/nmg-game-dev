"""pytest-bdd bindings for audio_import.feature: SCN001-SCN010 (#155, #249 AC5).

Godot is ``tests.godot_fakes.FakeGodotRunner``, whose audio probe answers from the ``.import`` file
the import wrote; ffmpeg is a fake encoder. Both are wired in as the runners ``import_audio``
builds, so the CLI and the finalize tool use them too. The fixtures are the committed clips in
``tests/fixtures/audio``. No real Godot or ffmpeg runs and no ElevenLabs call is made. The steps
share one ``state`` dict per scenario.
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
from nmg_game_dev.godot.project import read_config
from nmg_game_dev.pipeline.errors import PipelineError
from tests.godot_fakes import FakeGodotRunner
from tests.unit.audio.conftest import FakeFfmpeg, audio_probe, fake_godot

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "audio"
INVALID_CODES = {"audio.invalid_request", "audio.unsupported_format", "audio.asset_exists"}

scenarios("audio_import.feature")

_FORMAT_FIXTURES = {"WAV": "tone.wav", "MP3": "tone.mp3", "OGG": "tone.ogg", "FLAC": "tone.flac"}


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    root = tmp_path / "project"
    _godot_project(root)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    saved = tmp_path / "saved"
    saved.mkdir()
    values: dict[str, Any] = {
        "root": root,
        "saved": saved,
        "godot": fake_godot(),
        "ffmpeg": FakeFfmpeg(),
        "godot_installed": True,
        "ffmpeg_installed": True,
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

    def _resolve_godot() -> Path:
        if not values["godot_installed"]:
            raise PipelineError(
                "godot.not_found",
                "Godot was not found. Tried: godot on PATH.",
                "Install Godot 4 (latest stable) or set GODOT_BIN to its executable.",
                "godot",
            )
        return Path("/fake/godot")

    def _resolve_ffmpeg() -> Path:
        if not values["ffmpeg_installed"]:
            raise AudioError(
                "audio.ffmpeg_not_found",
                "ffmpeg was not found. Tried: ffmpeg on PATH.",
                "Install ffmpeg or set FFMPEG_BIN to its executable.",
            )
        return Path("/fake/ffmpeg")

    core = "nmg_game_dev.audio.core"
    monkeypatch.setattr(f"{core}.resolve_godot", _resolve_godot)
    monkeypatch.setattr(f"{core}.SubprocessGodotRunner", lambda _binary: values["godot"])
    monkeypatch.setattr(f"{core}.resolve_ffmpeg", _resolve_ffmpeg)
    monkeypatch.setattr(f"{core}.SubprocessFfmpegRunner", lambda _binary: values["ffmpeg"])
    return values


def _godot_project(root: Path) -> None:
    (root / "game").mkdir(parents=True)
    (root / "game" / "project.godot").write_text("config_version=5\n", encoding="utf-8")


def _sidecar(state: dict[str, Any], name: str) -> dict[tuple[str, str], str]:
    return read_config(state["root"] / "game" / "assets" / "Audio" / f"{name}.import")


def _probed(state: dict[str, Any], res: str) -> dict[str, Any]:
    runner: FakeGodotRunner = state["godot"]
    assert runner.count("--import") >= 1
    assert {"stream": res} in runner.params
    answer: dict[str, Any] = audio_probe(state["root"] / "game")({"stream": res})
    return answer


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
    except PipelineError as error:
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
        r"(?: and (?P<tool>an installed Godot|no Godot|no ffmpeg))?$"
    )
)
def _saved_file(state: dict[str, Any], what: str, tool: str | None) -> None:
    _save(state, _FORMAT_FIXTURES.get(what, "tone.wav"))
    if tool == "no Godot":
        state["godot_installed"] = False
    elif tool == "no ffmpeg":
        state["ffmpeg_installed"] = False


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


@when(parsers.parse('it is imported with name "{name}" and kind "{kind}" and loop {flag}'))
def _imported_named_looping(state: dict[str, Any], name: str, kind: str, flag: str) -> None:
    state["loop"] = flag == "true"
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
        except PipelineError as error:
            outcomes.append((case["codes"], error.code))
    state["outcomes"] = outcomes


@when("it runs through the CLI and through the import_audio tool")
def _cli_and_tool(state: dict[str, Any], capsys: pytest.CaptureFixture[str]) -> None:
    cli_root = state["saved"].parent / "cli-project"
    _godot_project(cli_root)
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


@then("res://assets/Audio/DoorCreak.wav is imported as an AudioStreamWAV with looping off")
def _sfx_imported(state: dict[str, Any]) -> None:
    assert state["result"]["godot_asset"] == "res://assets/Audio/DoorCreak.wav"
    assert state["result"]["imported_to_godot"] is True
    assert _sidecar(state, "DoorCreak.wav")[("params", "edit/loop_mode")] == "1"
    probed = _probed(state, "res://assets/Audio/DoorCreak.wav")
    assert probed == {"class": "AudioStreamWAV", "loop_mode": 0}


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


@then("the AudioStreamWAV loops forward")
def _loops(state: dict[str, Any]) -> None:
    config = _sidecar(state, "DoorCreak.wav")
    assert config[("params", "edit/loop_mode")] == "2"
    assert config[("params", "edit/loop_begin")] == "0"
    assert config[("params", "edit/loop_end")] == "-1"
    probed = _probed(state, "res://assets/Audio/DoorCreak.wav")
    assert probed == {"class": "AudioStreamWAV", "loop_mode": 1}


@then("SourceArt/Audio/Music/Theme.wav and game/assets/Audio/Theme.ogg exist")
def _music_files(state: dict[str, Any]) -> None:
    assert state["error"] is None, state["error"]
    assert (state["root"] / "SourceArt" / "Audio" / "Music" / "Theme.wav").is_file()
    assert (state["root"] / "game" / "assets" / "Audio" / "Theme.ogg").is_file()
    [call] = state["ffmpeg"].calls
    assert call[2:6] == ["-c:a", "libvorbis", "-q:a", "5"]


@then("res://assets/Audio/Theme.ogg is imported as an AudioStreamOggVorbis with loop enabled")
def _music_imported(state: dict[str, Any]) -> None:
    assert state["result"]["godot_asset"] == "res://assets/Audio/Theme.ogg"
    config = _sidecar(state, "Theme.ogg")
    assert config[("remap", "importer")] == '"oggvorbisstr"'
    assert config[("params", "loop")] == "true"
    probed = _probed(state, "res://assets/Audio/Theme.ogg")
    assert probed == {"class": "AudioStreamOggVorbis", "loop": True}


@then("it fails with audio.ffmpeg_not_found and a remediation line")
def _no_ffmpeg(state: dict[str, Any]) -> None:
    assert state["error"] is not None and state["error"].code == "audio.ffmpeg_not_found"
    assert state["error"].remediation == "Install ffmpeg or set FFMPEG_BIN to its executable."


@then("game/assets/Audio/Theme.ogg does not exist")
def _no_ogg(state: dict[str, Any]) -> None:
    assert not (state["root"] / "game" / "assets" / "Audio" / "Theme.ogg").exists()
    assert state["godot"].calls == []


@then("the result has imported_to_godot false and warning godot.not_found")
def _warned(state: dict[str, Any]) -> None:
    assert state["result"]["imported_to_godot"] is False
    assert state["result"]["warning"]["code"] == "godot.not_found"


@then("the WAV stays under SourceArt/Audio")
def _wav_kept(state: dict[str, Any]) -> None:
    assert (state["root"] / "SourceArt" / "Audio" / "SFX" / "DoorCreak.wav").is_file()


@then("it fails with audio.invalid_request, audio.unsupported_format, or audio.asset_exists")
def _invalid_codes(state: dict[str, Any]) -> None:
    assert state["outcomes"], "no request was submitted"
    for expected, actual in state["outcomes"]:
        assert actual in expected and actual in INVALID_CODES, f"got {actual}, want {expected}"


@then("nothing is written and Godot is not run")
def _nothing_written(state: dict[str, Any]) -> None:
    assert _tree(state["root"]) == state["before"]
    assert state["godot"].calls == []


@then("it fails with audio.decode_failed and leaves no file behind")
def _decode_failed(state: dict[str, Any]) -> None:
    assert state["error"] is not None and state["error"].code == "audio.decode_failed"
    folder = state["root"] / "SourceArt" / "Audio" / "SFX"
    assert not (folder / "DoorCreak.wav").exists()
    assert not (folder / "DoorCreak.wav.tmp").exists()
    assert state["godot"].calls == []


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
