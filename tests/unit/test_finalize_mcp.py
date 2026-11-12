"""Unit tests for the three ``finalize`` MCP tools (AC3, #69).

The tool functions are tested directly, so the MCP SDK is not needed.  The server module only
registers them.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from nmg_game_dev.audio.__main__ import main as audio_main
from nmg_game_dev.finalize import (
    FinalizeService,
    finalize_asset,
    get_finalize_job,
    import_audio,
    run_finalize_step,
)
from nmg_game_dev.finalize.service import clamp_wait
from nmg_game_dev.pipeline import FinalizeClients, FinalizeRequest, jobs
from tests.finalize_fakes import FakeBlenderSession, FakeStepRunner, FakeUnrealRunner
from tests.unit.fake_unreal_audio import FakeEditor, FakeUnrealPythonClient

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "audio"


def _dead_pid() -> int:
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait()
    return process.pid


def _deferred(cache_root: Path) -> FinalizeService:
    """A service whose launcher records the job without running it, so it stays queued."""
    return FinalizeService(cache_root, launcher=lambda job_dir: _live_pid())


def _live_pid() -> int:
    import os

    return os.getpid()


def _args(tmp_path: Path) -> dict[str, object]:
    blend = tmp_path / "crate.blend"
    blend.write_bytes(b"authored")
    return {
        "collection": "Crate",
        "category": "Props",
        "asset_class": "standard_prop",
        "export_root": str(tmp_path / "export"),
        "blend": str(blend),
    }


def test_wait_seconds_is_clamped_to_zero_through_one_fifty() -> None:
    assert clamp_wait(999) == 150
    assert clamp_wait(-5) == 0
    assert clamp_wait(30) == 30


def test_finalize_asset_returns_a_job_id_immediately_when_not_waiting(tmp_path: Path) -> None:
    response = finalize_asset(**_args(tmp_path), service=_deferred(tmp_path / "cache"))  # type: ignore[arg-type]

    assert response["job_id"]
    assert response["status"] == "queued"
    assert "result" not in response


def test_get_finalize_job_reports_the_status_and_then_the_result(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    service = _deferred(cache)
    response = finalize_asset(**_args(tmp_path), service=service)  # type: ignore[arg-type]
    job_id = str(response["job_id"])

    assert get_finalize_job(job_id, service=service)["state"] == "queued"

    request = FinalizeRequest.model_validate_json(
        (cache / "jobs" / job_id / "request.json").read_text(encoding="utf-8")
    )
    jobs.run_job(
        cache / "jobs" / job_id,
        clients=FinalizeClients(blender=FakeBlenderSession(), unreal=FakeUnrealRunner()),
        runner=FakeStepRunner(request),
    )

    finished = get_finalize_job(job_id, service=service)
    assert finished["state"] == "succeeded"
    assert finished["result"]["desktop_content_path"] == "/Game/Props/Crate/Desktop"


def test_run_finalize_step_names_the_step_it_ran(tmp_path: Path) -> None:
    response = run_finalize_step(
        step="validate",
        **_args(tmp_path),  # type: ignore[arg-type]
        service=_deferred(tmp_path / "cache"),
    )
    assert response["status"] == "queued"


def test_unknown_step_is_a_structured_error(tmp_path: Path) -> None:
    response = run_finalize_step(
        step="generate",
        **_args(tmp_path),  # type: ignore[arg-type]
        service=_deferred(tmp_path / "cache"),
    )
    assert response["error"]["code"] == "finalize.unknown_step"
    assert response["error"]["stage"] == "finalize"


def test_unknown_job_is_finalize_job_not_found(tmp_path: Path) -> None:
    response = get_finalize_job("no-such-job", service=_deferred(tmp_path / "cache"))
    assert response["error"]["code"] == "finalize.job_not_found"


def test_invalid_arguments_are_a_structured_error(tmp_path: Path) -> None:
    args = _args(tmp_path)
    args["asset_class"] = "generated"
    response = finalize_asset(**args, service=_deferred(tmp_path / "cache"))  # type: ignore[arg-type]
    assert response["error"]["code"] == "finalize.invalid_request"


def test_a_failed_job_reports_its_error_when_waited_on(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    service = FinalizeService(cache, launcher=lambda job_dir: _dead_pid())
    response = finalize_asset(
        **_args(tmp_path),  # type: ignore[arg-type]
        service=service,
        wait_seconds=5,
    )
    assert response["status"] == "failed"
    assert response["error"]["code"] == "finalize.job_crashed"


def test_run_finalize_step_accepts_both_clip_steps(tmp_path: Path) -> None:
    # FR9: run_finalize_step takes export_anims and import_anims.
    for step in ("export_anims", "import_anims"):
        response = run_finalize_step(
            step=step,
            **_args(tmp_path),  # type: ignore[arg-type]
            service=_deferred(tmp_path / f"cache-{step}"),
        )
        assert response["status"] == "queued", step


def test_compatible_with_is_accepted_by_both_tools(tmp_path: Path) -> None:
    # FR12: both tools accept compatible_with.
    args = _args(tmp_path)
    response = finalize_asset(
        **args,  # type: ignore[arg-type]
        compatible_with=["Props/Other"],
        service=_deferred(tmp_path / "cache-all"),
    )
    assert response["status"] == "queued"
    response = run_finalize_step(
        step="import_anims",
        **args,  # type: ignore[arg-type]
        compatible_with=["Props/Other"],
        service=_deferred(tmp_path / "cache-step"),
    )
    assert response["status"] == "queued"


def test_an_invalid_compatible_with_item_is_a_structured_error(tmp_path: Path) -> None:
    response = finalize_asset(
        **_args(tmp_path),  # type: ignore[arg-type]
        compatible_with=["props/other"],
        service=_deferred(tmp_path / "cache"),
    )
    assert response["error"]["code"] == "finalize.invalid_request"


# --- import_audio (#155, AC7) ------------------------------------------------------------------


@pytest.fixture
def audio_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakeUnrealPythonClient:
    """A project root and one fake editor, wired in wherever the audio import builds a client."""
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    fake = FakeUnrealPythonClient(FakeEditor())

    def _factory(*_args: object, **_kwargs: object) -> FakeUnrealPythonClient:
        return fake

    monkeypatch.setattr("nmg_game_dev.audio.core.UnrealMcpClient", _factory)
    monkeypatch.setattr("nmg_game_dev.audio.__main__.UnrealMcpClient", _factory)
    return fake


def _saved(tmp_path: Path, name: str, folder: str) -> Path:
    target = tmp_path / folder / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FIXTURES / name, target)
    return target


def test_import_audio_tool_returns_the_result(
    tmp_path: Path, audio_env: FakeUnrealPythonClient
) -> None:
    src = _saved(tmp_path, "tone.wav", "saved")

    response = import_audio(file=str(src), name="DoorCreak", kind="sfx", loop=True)

    assert response["imported_to_unreal"] is True
    assert response["unreal_asset"] == "/Game/Audio/SFX/SW_DoorCreak"
    assert response["looping"] is True
    assert "error" not in response


def test_import_audio_tool_returns_errors_as_an_error_object(
    tmp_path: Path, audio_env: FakeUnrealPythonClient
) -> None:
    response = import_audio(file=str(tmp_path / "gone.wav"), name="DoorCreak", kind="sfx")

    assert set(response) == {"error"}
    assert response["error"]["code"] == "audio.invalid_request"
    assert response["error"]["stage"] == "audio"
    assert response["error"]["remediation"]
    assert audio_env.codes == []


def test_import_audio_tool_and_cli_return_the_same_json(
    tmp_path: Path,
    audio_env: FakeUnrealPythonClient,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli_src = _saved(tmp_path, "tone.mp3", "cli")
    tool_src = _saved(tmp_path, "tone.mp3", "tool")
    cli_root = tmp_path / "cli-project"
    cli_root.mkdir()

    assert (
        audio_main(
            [
                "import",
                "--file",
                str(cli_src),
                "--name",
                "ForestTheme",
                "--kind",
                "music",
                "--project",
                str(cli_root),
            ]
        )
        == 0
    )
    cli_json = json.loads(capsys.readouterr().out)

    # The CLI already imported this name, so the tool runs against an editor that has not seen it.
    audio_env.editor.assets.clear()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path / "project"))
    tool_json = import_audio(file=str(tool_src), name="ForestTheme", kind="music")

    # The two runs stored under different roots, so only the stored path may differ.
    assert cli_json.pop("source_art") == str(cli_root / "SourceArt/Audio/Music/ForestTheme.wav")
    assert tool_json.pop("source_art") == str(
        tmp_path / "project" / "SourceArt/Audio/Music/ForestTheme.wav"
    )
    assert cli_json == tool_json
