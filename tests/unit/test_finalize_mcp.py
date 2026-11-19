"""Unit tests for the ``finalize`` MCP tools (AC3, #69, #249).

The tool functions are tested directly, so the MCP SDK is not needed.  The server module only
registers them.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, get_args

import pytest

from nmg_game_dev.audio.__main__ import main as audio_main
from nmg_game_dev.finalize import (
    FinalizeService,
    finalize_asset,
    get_finalize_job,
    import_audio,
    refresh_audio_table,
    run_finalize_step,
)
from nmg_game_dev.finalize.__main__ import build_parser
from nmg_game_dev.finalize.service import clamp_wait
from nmg_game_dev.pipeline import FinalizeClients, FinalizeRequest, jobs
from nmg_game_dev.pipeline.request import AssetClass
from tests.finalize_fakes import FakeBlenderSession, FakeStepRunner, FinalizeGodot
from tests.godot_fakes import FakeGodotRunner
from tests.unit.audio.conftest import FakeFfmpeg, fake_godot

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "audio"

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_JSON = REPO_ROOT / "mcp-servers" / "finalize" / "tools.json"


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
        clients=FinalizeClients(blender=FakeBlenderSession(), godot=FinalizeGodot(tmp_path)),
        runner=FakeStepRunner(request),
    )

    finished = get_finalize_job(job_id, service=service)
    assert finished["state"] == "succeeded"
    assert finished["result"]["desktop_resource_path"] == (
        "res://export/Props/Crate/Desktop/Crate.glb"
    )
    assert finished["result"]["mobile_resource_path"] == (
        "res://export/Props/Crate/Mobile/Crate.glb"
    )


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


def test_terrain_is_an_accepted_class_for_the_mcp_tools(tmp_path: Path) -> None:
    args = _args(tmp_path)
    args["asset_class"] = "terrain"
    response = finalize_asset(**args, service=_deferred(tmp_path / "cache"))  # type: ignore[arg-type]
    assert response["status"] == "queued"
    assert "error" not in response


def test_terrain_is_an_accepted_class_for_run_finalize_step(tmp_path: Path) -> None:
    args = _args(tmp_path)
    args["asset_class"] = "terrain"
    response = run_finalize_step(
        step="validate",
        **args,  # type: ignore[arg-type]
        service=_deferred(tmp_path / "cache"),
    )
    assert response["status"] == "queued"


def test_terrain_is_an_accepted_class_for_the_cli(tmp_path: Path) -> None:
    parsed = build_parser().parse_args(
        ["validate", "--collection", "Ground", "--export-root", str(tmp_path), "--class", "terrain"]
    )
    assert parsed.asset_class == "terrain"


def test_tools_json_class_enum_matches_the_request_model() -> None:
    """tools.json lists the same asset classes as the finalize request, terrain included (#154)."""
    tools = json.loads(TOOLS_JSON.read_text(encoding="utf-8"))["tools"]
    # reduce_asset (#139) takes a free-form asset_class and refuses terrain, so it has no enum.
    enums = {
        tool["name"]: tool["inputSchema"]["properties"]["asset_class"]["enum"]
        for tool in tools
        if tool["name"] in ("finalize_asset", "run_finalize_step")
    }
    assert set(enums) == {"finalize_asset", "run_finalize_step"}
    expected = list(get_args(AssetClass))
    assert "terrain" in expected
    for name, enum in enums.items():
        assert enum == expected, name


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


class _AudioEnv:
    """The fake Godot and ffmpeg runners the audio import builds when none is injected."""

    def __init__(self, godot: FakeGodotRunner, ffmpeg: FakeFfmpeg) -> None:
        self.godot = godot
        self.ffmpeg = ffmpeg


def _game_project(root: Path) -> Path:
    (root / "game").mkdir(parents=True, exist_ok=True)
    (root / "game" / "project.godot").write_text("config_version=5\n", encoding="utf-8")
    return root


@pytest.fixture
def audio_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _AudioEnv:
    """A Godot consumer root, and fake runners wired in wherever the audio import builds them."""
    root = _game_project(tmp_path / "project")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    env = _AudioEnv(fake_godot(), FakeFfmpeg())

    def _godot(_binary: object) -> FakeGodotRunner:
        return env.godot

    def _ffmpeg(_binary: object) -> FakeFfmpeg:
        return env.ffmpeg

    monkeypatch.setattr("nmg_game_dev.audio.core.resolve_godot", lambda: Path("/fake/godot"))
    monkeypatch.setattr("nmg_game_dev.audio.core.SubprocessGodotRunner", _godot)
    monkeypatch.setattr("nmg_game_dev.audio.core.resolve_ffmpeg", lambda: Path("/fake/ffmpeg"))
    monkeypatch.setattr("nmg_game_dev.audio.core.SubprocessFfmpegRunner", _ffmpeg)
    return env


def _saved(tmp_path: Path, name: str, folder: str) -> Path:
    target = tmp_path / folder / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FIXTURES / name, target)
    return target


def test_import_audio_tool_returns_the_result(tmp_path: Path, audio_env: _AudioEnv) -> None:
    src = _saved(tmp_path, "tone.wav", "saved")

    response = import_audio(file=str(src), name="DoorCreak", kind="sfx", loop=True)

    assert response["imported_to_godot"] is True
    assert response["godot_asset"] == "res://assets/Audio/DoorCreak.wav"
    assert response["looping"] is True
    assert "error" not in response
    assert audio_env.godot.count("--import") == 1


def test_import_audio_tool_takes_an_injected_runner_and_project(tmp_path: Path) -> None:
    root = _game_project(tmp_path / "elsewhere")
    godot = fake_godot()
    src = _saved(tmp_path, "tone.wav", "saved")

    response = import_audio(
        file=str(src), name="DoorCreak", kind="sfx", project_root=str(root), godot=godot
    )

    assert response["imported_to_godot"] is True
    assert (root / "game" / "assets" / "Audio" / "DoorCreak.wav").is_file()
    assert godot.projects[0] == root / "game"


def test_import_audio_tool_returns_errors_as_an_error_object(
    tmp_path: Path, audio_env: _AudioEnv
) -> None:
    response = import_audio(file=str(tmp_path / "gone.wav"), name="DoorCreak", kind="sfx")

    assert set(response) == {"error"}
    assert response["error"]["code"] == "audio.invalid_request"
    assert response["error"]["stage"] == "audio"
    assert response["error"]["remediation"]
    assert audio_env.godot.calls == []


def test_import_audio_tool_and_cli_return_the_same_json(
    tmp_path: Path,
    audio_env: _AudioEnv,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli_src = _saved(tmp_path, "tone.mp3", "cli")
    tool_src = _saved(tmp_path, "tone.mp3", "tool")
    cli_root = _game_project(tmp_path / "cli-project")

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
    cli_json: dict[str, Any] = json.loads(capsys.readouterr().out)

    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path / "project"))
    tool_json = import_audio(file=str(tool_src), name="ForestTheme", kind="music")

    # The two runs stored under different roots, so only the stored path may differ.
    assert cli_json.pop("source_art") == str(cli_root / "SourceArt/Audio/Music/ForestTheme.wav")
    assert tool_json.pop("source_art") == str(
        tmp_path / "project" / "SourceArt/Audio/Music/ForestTheme.wav"
    )
    assert cli_json == tool_json
    assert tool_json["godot_asset"] == "res://assets/Audio/ForestTheme.ogg"


_AUDIO_TABLE_HEADER = (
    '[gd_resource type="Resource" script_class="NmgAudioTable" load_steps=2 format=3]\n'
)


def _audio_project(root: Path) -> Path:
    """A Godot project with one imported sound and an Audio name table that has not seen it yet."""
    (root / "game" / "assets" / "Audio").mkdir(parents=True)
    (root / "game" / "assets" / "Audio" / "DoorCreak.wav").write_bytes(b"sound")
    (root / "game" / "project.godot").write_text("config_version=5\n", encoding="utf-8")
    table = root / "game" / "systems" / "Audio" / "audio_table.tres"
    table.parent.mkdir(parents=True)
    table.write_text(_AUDIO_TABLE_HEADER, encoding="utf-8")
    return root


def test_refresh_audio_table_returns_the_tables_it_changed(tmp_path: Path) -> None:
    """#237 AC3 via the MCP tool: the first refresh rewrites the table, a rerun changes nothing."""
    project = _audio_project(tmp_path / "project")

    assert refresh_audio_table(str(project)) == {
        "refreshed_tables": ["game/systems/Audio/audio_table.tres"]
    }
    assert refresh_audio_table(str(project)) == {"refreshed_tables": []}
    table = project / "game" / "systems" / "Audio" / "audio_table.tres"
    assert '"DoorCreak": "res://assets/Audio/DoorCreak.wav"' in table.read_text(encoding="utf-8")


def test_refresh_audio_table_defaults_to_the_claude_project_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _audio_project(tmp_path / "project")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project))

    assert refresh_audio_table() == {"refreshed_tables": ["game/systems/Audio/audio_table.tres"]}


def test_refresh_audio_table_without_a_godot_project_returns_the_error(tmp_path: Path) -> None:
    result = refresh_audio_table(str(tmp_path))

    assert result["error"]["code"] == "audio.godot_project_missing"
    assert result["error"]["stage"] == "audio"
    assert result["error"]["remediation"]


def test_refresh_audio_table_with_an_unreadable_backlog_returns_the_error(tmp_path: Path) -> None:
    """#237 review F1: a malformed backlog comes back as a structured error, not an exception."""
    project = _audio_project(tmp_path / "project")
    backlog = project / "docs" / "design" / "backlog.json"
    backlog.parent.mkdir(parents=True)
    backlog.write_text("[]", encoding="utf-8")

    result = refresh_audio_table(str(project))

    assert result["error"]["code"] == "audio.backlog_invalid"
    assert result["error"]["stage"] == "audio"
    assert result["error"]["remediation"]


def test_refresh_audio_table_with_a_backlog_entry_whose_fields_is_not_a_mapping(
    tmp_path: Path,
) -> None:
    """#237 review F1: a TypeError in the backlog loader reaches the tool as a structured error."""
    project = _audio_project(tmp_path / "project")
    backlog = project / "docs" / "design" / "backlog.json"
    backlog.parent.mkdir(parents=True)
    backlog.write_text(
        '{"version": 1, "entries": [{"type": "region", "name": "Forest", "asset_name": "Forest", '
        '"source": "docs/design/forest.md", "status": "planned", "fields": 5}]}',
        encoding="utf-8",
    )

    result = refresh_audio_table(str(project))

    assert result["error"]["code"] == "audio.backlog_invalid"
    assert result["error"]["stage"] == "audio"
    assert result["error"]["remediation"]


def test_refresh_audio_table_with_an_unreadable_table_returns_the_error(tmp_path: Path) -> None:
    """#237 review F1: a table that cannot be read is a structured error, not an OSError."""
    project = _audio_project(tmp_path / "project")
    (project / "game" / "systems" / "Broken" / "audio_table.tres").mkdir(parents=True)

    result = refresh_audio_table(str(project))

    assert result["error"]["code"] == "audio.table_unreadable"
    assert result["error"]["stage"] == "audio"
    assert result["error"]["remediation"]


def test_tools_json_lists_refresh_audio_table_with_an_optional_project() -> None:
    tools = {
        tool["name"]: tool for tool in json.loads(TOOLS_JSON.read_text(encoding="utf-8"))["tools"]
    }

    schema = tools["refresh_audio_table"]["inputSchema"]
    assert "project" in schema["properties"]
    assert schema["required"] == []
