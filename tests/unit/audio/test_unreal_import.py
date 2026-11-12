"""The UE import of one stored WAV (#155 FR4, AC1, AC3).

The generated UE code runs against the fake ``unreal`` module, so these tests check what the editor
would do: the import task's fields, the SoundWave's looping flag, and the one NMG_RESULT line. No
editor is started.
"""

from __future__ import annotations

import ast
import json
from collections.abc import Callable
from pathlib import Path

import pytest

from nmg_game_dev.audio.errors import AudioError
from nmg_game_dev.audio.unreal_import import build_audio_import_code, run_import
from nmg_game_dev.pipeline.errors import PipelineError
from tests.unit.fake_unreal_audio import FakeEditor, FakeOtherAsset, FakeUnrealPythonClient

DEST = "/Game/Audio/SFX"
ASSET = "SW_DoorCreak"
ASSET_PATH = f"{DEST}/{ASSET}"


@pytest.fixture
def wav(tmp_path: Path, fixture_file: Callable[[str], Path]) -> Path:
    path = tmp_path / "DoorCreak.wav"
    path.write_bytes(fixture_file("tone.wav").read_bytes())
    return path


def _run(client: FakeUnrealPythonClient, wav: Path, *, loop: bool = False) -> dict[str, object]:
    return run_import(client, wav=str(wav), dest_folder=DEST, asset_name=ASSET, loop=loop)


def test_the_generated_code_is_valid_python() -> None:
    code = build_audio_import_code("/x/DoorCreak.wav", DEST, ASSET, loop=True)
    ast.parse(code)
    assert "NMG_RESULT " in code


def test_the_import_task_fields_match_the_design(wav: Path) -> None:
    client = FakeUnrealPythonClient()

    _run(client, wav)

    (task,) = client.editor.tasks
    assert task.filename == str(wav)
    assert task.destination_path == DEST
    assert task.destination_name == ASSET
    assert task.automated is True
    assert task.replace_existing is False
    assert task.save is True


def test_a_sound_effect_is_imported_with_looping_off(wav: Path) -> None:
    client = FakeUnrealPythonClient()

    result = _run(client, wav)

    sound = client.editor.sound_wave(ASSET_PATH)
    assert sound is not None
    assert sound.get_editor_property("looping") is False
    assert result == {"ok": True, "asset": ASSET_PATH, "looping": False, "error": None}
    assert client.editor.saved == [ASSET_PATH]


def test_loop_true_sets_looping_on_the_soundwave(wav: Path) -> None:
    client = FakeUnrealPythonClient()

    result = _run(client, wav, loop=True)

    sound = client.editor.sound_wave(ASSET_PATH)
    assert sound is not None
    assert sound.get_editor_property("looping") is True
    assert result["looping"] is True


def test_an_import_that_creates_no_soundwave_fails_with_import_failed(wav: Path) -> None:
    client = FakeUnrealPythonClient(FakeEditor(produces=FakeOtherAsset))

    with pytest.raises(AudioError) as caught:
        _run(client, wav)

    assert caught.value.code == "audio.import_failed"
    assert "no SoundWave" in caught.value.message
    assert caught.value.remediation


def test_an_existing_asset_is_not_overwritten(wav: Path) -> None:
    editor = FakeEditor()
    client = FakeUnrealPythonClient(editor)
    _run(client, wav)
    tasks_before = len(editor.tasks)

    with pytest.raises(AudioError) as caught:
        _run(client, wav)

    assert caught.value.code == "audio.import_failed"
    assert "already exists" in caught.value.message
    assert len(editor.tasks) == tasks_before


def test_a_missing_source_file_fails_with_import_failed(tmp_path: Path) -> None:
    client = FakeUnrealPythonClient()

    with pytest.raises(AudioError) as caught:
        _run(client, tmp_path / "missing.wav")

    assert caught.value.code == "audio.import_failed"


def test_an_unreachable_editor_passes_its_code_through_unchanged(wav: Path) -> None:
    client = FakeUnrealPythonClient(reachable=False)

    with pytest.raises(PipelineError) as caught:
        _run(client, wav)

    assert caught.value.code == "mcp.unreal.unreachable"
    assert not isinstance(caught.value, AudioError)


def test_another_client_error_becomes_import_failed(wav: Path) -> None:
    class _Broken:
        def execute_python_code(self, code: str) -> str:
            raise PipelineError(
                code="import_ue.failed",
                message="Unreal MCP tool execute_python_code reported an error",
                remediation="retry",
                stage="import_ue",
            )

    with pytest.raises(AudioError) as caught:
        run_import(_Broken(), wav=str(wav), dest_folder=DEST, asset_name=ASSET, loop=False)

    assert caught.value.code == "audio.import_failed"
    assert "reported an error" in caught.value.message


def test_output_without_an_nmg_result_line_fails_with_import_failed(wav: Path) -> None:
    class _Silent:
        def execute_python_code(self, code: str) -> str:
            return "Log: nothing to report"

    with pytest.raises(AudioError) as caught:
        run_import(_Silent(), wav=str(wav), dest_folder=DEST, asset_name=ASSET, loop=False)

    assert caught.value.code == "audio.import_failed"


def test_a_ue_error_is_reported_with_its_text(wav: Path) -> None:
    class _Reports:
        def execute_python_code(self, code: str) -> str:
            return "NMG_RESULT " + json.dumps(
                {"ok": False, "asset": ASSET_PATH, "looping": False, "error": "RuntimeError: boom"}
            )

    with pytest.raises(AudioError) as caught:
        run_import(_Reports(), wav=str(wav), dest_folder=DEST, asset_name=ASSET, loop=False)

    assert caught.value.code == "audio.import_failed"
    assert "RuntimeError: boom" in caught.value.message
