"""The finalize MCP tool parameters for batches, lock waits, and the export root (#149, #249).

The tool functions are tested directly, so the MCP SDK is not needed.  Batch jobs run in-process
through ``BatchRouter`` with fake steps and a fake Godot runner, so no Blender or Godot process is
started.
"""

from __future__ import annotations

import importlib.util
import json
import os
import struct
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from nmg_game_dev.finalize import (
    FinalizeService,
    check_finalized,
    finalize_asset,
    game_screenshot,
    get_finalize_job,
    import_audio,
    run_finalize_step,
)
from nmg_game_dev.godot.runner import CommandResult
from nmg_game_dev.pipeline import FinalizeRequest
from nmg_game_dev.pipeline.errors import PipelineError
from tests.finalize_fakes import BatchRouter, batch_launcher, dead_pid
from tests.finalize_records_support import (
    asset_request,
    manual_record,
    up_to_date_asset,
    write_record_file,
)
from tests.godot_fakes import FakeGodotRunner
from tests.unit.audio.conftest import fake_godot, sine, write_wav

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_JSON = REPO_ROOT / "mcp-servers" / "finalize" / "tools.json"
VALIDATOR = REPO_ROOT / "scripts" / "validate-mcp-tools.py"
AUDIO_RATE = 22050


def _entries(tmp_path: Path, *names: str) -> list[dict[str, Any]]:
    return [
        {
            "collection": name,
            "category": "Props",
            "asset_class": "standard_prop",
            "export_root": str(tmp_path / "export"),
        }
        for name in names
    ]


def _deferred(cache: Path) -> FinalizeService:
    """A service whose launcher records the job without running it, so it stays queued."""
    return FinalizeService(cache, launcher=lambda job_dir: os.getpid())


def _single_args(tmp_path: Path) -> dict[str, Any]:
    blend = tmp_path / "crate.blend"
    blend.write_bytes(b"authored")
    return {
        "collection": "Crate",
        "category": "Props",
        "asset_class": "standard_prop",
        "export_root": str(tmp_path / "export"),
        "blend": str(blend),
    }


def _job_dirs(cache: Path) -> list[Path]:
    return sorted(path for path in (cache / "jobs").iterdir() if path.is_dir())


def test_finalize_asset_with_requests_returns_a_batch_job_id_at_once(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    response = finalize_asset(
        requests=_entries(tmp_path, "Alpha", "Beta", "Gamma"),
        service=_deferred(cache),
    )

    assert response["job_id"]
    assert response["status"] == "queued"
    assert "result" not in response
    batch = get_finalize_job(response["job_id"], service=_deferred(cache))["batch"]
    assert batch["total"] == 3
    assert batch["completed"] == 0
    assert batch["current"] is None
    assert [item["state"] for item in batch["items"]] == ["pending", "pending", "pending"]


def test_get_finalize_job_reports_the_running_collection_and_the_totals(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    reported: list[dict[str, Any]] = []
    requests = [
        FinalizeRequest(
            collection=name,
            category="Props",
            asset_class="standard_prop",
            export_root=tmp_path / "export",
        )
        for name in ("Alpha", "Beta")
    ]

    def on_step(item_dir: Path, step: str) -> None:
        if item_dir.name == "1-Beta" and step == "validate":
            batch_dir = item_dir.parent.parent
            reported.append(get_finalize_job(batch_dir.name, service=_deferred(cache)))

    def make_router(batch_requests: dict[str, FinalizeRequest]) -> BatchRouter:
        return BatchRouter(batch_requests, on_step=on_step)

    service = FinalizeService(cache, launcher=batch_launcher(make_router))
    job_id = service.start_batch(requests)

    (during,) = reported
    assert during["state"] == "running"
    assert during["batch"]["current"] == "Beta"
    assert during["batch"]["completed"] == 1
    assert during["batch"]["total"] == 2
    final = get_finalize_job(job_id, service=service)
    assert final["state"] == "succeeded"
    assert final["batch"]["completed"] == 2
    assert final["result"]["batch"]["succeeded"] == 2


def test_a_finished_batch_reports_its_result_when_waited_on(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    service = FinalizeService(
        cache,
        launcher=batch_launcher(lambda requests: BatchRouter(requests)),
    )
    response = finalize_asset(
        requests=_entries(tmp_path, "Alpha", "Beta"),
        service=service,
        wait_seconds=5,
    )

    assert response["status"] == "succeeded"
    assert response["result"]["batch"]["succeeded"] == 2
    assert [item["collection"] for item in response["result"]["batch"]["items"]] == [
        "Alpha",
        "Beta",
    ]


def test_requests_and_collection_are_mutually_exclusive(tmp_path: Path) -> None:
    response = finalize_asset(
        collection="Crate",
        export_root=str(tmp_path / "export"),
        requests=_entries(tmp_path, "Alpha"),
        service=_deferred(tmp_path / "cache"),
    )
    assert response["error"]["code"] == "finalize.invalid_request"


def test_a_single_collection_without_export_root_uses_the_project_game_assets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    cache = tmp_path / "cache"
    response = finalize_asset(
        collection="Crate",
        category="Props",
        asset_class="standard_prop",
        service=_deferred(cache),
    )

    assert "error" not in response
    (job_dir,) = _job_dirs(cache)
    request = json.loads((job_dir / "request.json").read_text(encoding="utf-8"))
    assert Path(request["export_root"]) == tmp_path / "game" / "assets"


def test_run_finalize_step_without_export_root_uses_the_project_game_assets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    cache = tmp_path / "cache"
    response = run_finalize_step(
        step="validate",
        collection="Crate",
        category="Props",
        asset_class="standard_prop",
        service=_deferred(cache),
    )

    assert "error" not in response
    (job_dir,) = _job_dirs(cache)
    request = json.loads((job_dir / "request.json").read_text(encoding="utf-8"))
    assert Path(request["export_root"]) == tmp_path / "game" / "assets"


def test_a_batch_entry_without_export_root_uses_the_project_game_assets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    cache = tmp_path / "cache"
    entries = [{"collection": "Alpha", "category": "Props", "asset_class": "standard_prop"}]

    response = finalize_asset(requests=entries, service=_deferred(cache))

    assert "error" not in response
    (job_dir,) = _job_dirs(cache)
    job = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
    assert Path(job["items"][0]["export_root"]) == tmp_path / "game" / "assets"


def test_an_invalid_batch_entry_is_refused_and_writes_no_job(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    entries = _entries(tmp_path, "Alpha")
    entries.append({"collection": "bad name", "export_root": str(tmp_path / "export")})
    entries.append(_entries(tmp_path, "Gamma")[0])
    entries.append(
        {
            "collection": "Delta",
            "export_root": str(tmp_path / "export"),
            "category": "Props",
            "asset_class": "not_a_class",
        }
    )

    response = finalize_asset(requests=entries, service=_deferred(cache))

    assert response["error"]["code"] == "finalize.invalid_batch"
    assert "index 1:" in response["error"]["message"]
    assert "index 3:" in response["error"]["message"]
    assert not (cache / "jobs").exists()


def test_an_empty_batch_is_refused(tmp_path: Path) -> None:
    response = finalize_asset(requests=[], service=_deferred(tmp_path / "cache"))
    assert response["error"]["code"] == "finalize.invalid_batch"


def test_the_batch_wait_options_reach_the_job(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    response = finalize_asset(
        requests=_entries(tmp_path, "Alpha"),
        fail_fast=True,
        wait_for_lock=True,
        lock_wait_seconds=30,
        service=_deferred(cache),
    )

    assert response["status"] == "waiting"
    (job_dir,) = _job_dirs(cache)
    job = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
    assert job["fail_fast"] is True
    assert job["wait_for_lock"] is True
    assert job["lock_wait_s"] == 30


def test_the_single_wait_options_reach_the_job(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    response = finalize_asset(
        **_single_args(tmp_path),
        wait_for_lock=True,
        lock_wait_seconds=12,
        service=_deferred(cache),
    )

    assert response["status"] == "waiting"
    (job_dir,) = _job_dirs(cache)
    request = json.loads((job_dir / "request.json").read_text(encoding="utf-8"))
    job = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
    assert "pie_mode" not in request
    assert "pie_wait_seconds" not in request
    assert job["lock_wait_s"] == 12


def test_run_finalize_step_accepts_the_wait_options(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    response = run_finalize_step(
        step="validate",
        **_single_args(tmp_path),
        wait_for_lock=True,
        service=_deferred(cache),
    )

    assert "error" not in response
    (job_dir,) = _job_dirs(cache)
    job = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
    assert job["wait_for_lock"] is True


@pytest.mark.parametrize("option", ["pie_mode", "pie_wait_seconds"])
def test_the_removed_play_in_editor_options_are_not_parameters(tmp_path: Path, option: str) -> None:
    arguments: dict[str, Any] = {**_single_args(tmp_path), option: "refuse"}
    with pytest.raises(TypeError):
        finalize_asset(**arguments, service=_deferred(tmp_path / "cache"))


def test_a_batch_entry_with_a_play_in_editor_key_is_an_unknown_key(tmp_path: Path) -> None:
    entries = _entries(tmp_path, "Alpha")
    entries[0]["pie_mode"] = "refuse"

    response = finalize_asset(requests=entries, service=_deferred(tmp_path / "cache"))

    assert response["error"]["code"] == "finalize.invalid_batch"
    assert "unknown key(s): pie_mode" in response["error"]["message"]


def test_a_negative_lock_wait_is_a_structured_invalid_request(tmp_path: Path) -> None:
    response = finalize_asset(
        **_single_args(tmp_path),
        wait_for_lock=True,
        lock_wait_seconds=-1,
        service=_deferred(tmp_path / "cache"),
    )
    assert response["error"]["code"] == "finalize.invalid_request"


def test_a_held_lock_without_wait_fails_the_batch_at_once(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    service = _deferred(cache)
    holder = service.start(
        FinalizeRequest(
            collection="Holder",
            category="Props",
            asset_class="standard_prop",
            export_root=tmp_path / "export",
        )
    )

    response = finalize_asset(requests=_entries(tmp_path, "Alpha"), service=service)

    assert response["error"]["code"] == "finalize.job_running"
    assert holder in response["error"]["message"]


def test_a_job_whose_process_vanished_is_reported_as_crashed(tmp_path: Path) -> None:
    service = FinalizeService(tmp_path / "cache", launcher=lambda job_dir: dead_pid())
    response = finalize_asset(requests=_entries(tmp_path, "Alpha"), service=service)

    assert response["status"] == "failed"
    assert response["error"]["code"] == "finalize.job_crashed"


# game_screenshot (#251 FR4, AC5, AC6) -----------------------------------------------------------


def _consumer(root: Path) -> Path:
    """A consumer root holding game/project.godot, the Godot project the screenshot runs."""
    (root / "game").mkdir(parents=True)
    (root / "game" / "project.godot").write_text("config_version=5\n", encoding="utf-8")
    return root


def _shot_godot(width: int = 1280, height: int = 720) -> FakeGodotRunner:
    def run(args: list[str], project: Path) -> CommandResult:
        target = next(arg for arg in args if arg.startswith("--nmg-shot=")).removeprefix(
            "--nmg-shot="
        )
        header = (
            b"\x89PNG\r\n\x1a\n"
            + struct.pack(">I", 13)
            + b"IHDR"
            + struct.pack(">II", width, height)
            + bytes([8, 6, 0, 0, 0])
        )
        Path(target).write_bytes(header + b"\x00\x00\x00\x00")
        return CommandResult(0)

    return FakeGodotRunner({"--": run})


def test_game_screenshot_saves_a_relative_path_under_the_consumer_root(tmp_path: Path) -> None:
    root = _consumer(tmp_path)
    godot = _shot_godot()
    response = game_screenshot(
        "build/shots/forest.png",
        after=3,
        options=["--at=Forest", "--hour=18"],
        project_root=root,
        godot=godot,
    )
    target = root / "build" / "shots" / "forest.png"
    assert response == {"path": str(target.absolute()), "width": 1280, "height": 720}
    assert target.is_file()
    assert godot.calls[0][:4] == ["--", "--at=Forest", "--hour=18", "--nmg-test-saves"]
    assert godot.calls[0][-1] == "--nmg-shot-after=3"


def test_game_screenshot_defaults_after_to_three_seconds(tmp_path: Path) -> None:
    godot = _shot_godot()
    game_screenshot("a.png", project_root=_consumer(tmp_path), godot=godot)
    assert godot.calls[0][-1] == "--nmg-shot-after=3"


@pytest.mark.parametrize("after", [-1, 61])
def test_game_screenshot_refuses_an_after_outside_0_to_60(tmp_path: Path, after: float) -> None:
    response = game_screenshot(
        "a.png", after=after, project_root=_consumer(tmp_path), godot=FakeGodotRunner()
    )
    assert response["error"]["code"] == "shot.invalid_after"


def test_game_screenshot_without_a_project_is_godot_project_missing(tmp_path: Path) -> None:
    response = game_screenshot("a.png", project_root=tmp_path, godot=FakeGodotRunner())
    assert response["error"]["code"] == "godot.project_missing"
    assert response["error"]["stage"] == "godot"


def test_game_screenshot_without_a_png_returns_shot_no_image(tmp_path: Path) -> None:
    godot = FakeGodotRunner({"--": CommandResult(1, stdout="SCRIPT ERROR: crashed\n")})
    response = game_screenshot("a.png", project_root=_consumer(tmp_path), godot=godot)
    assert response["error"]["code"] == "shot.no_image"
    assert "SCRIPT ERROR: crashed" in response["error"]["message"]


def test_game_screenshot_without_godot_returns_godot_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _missing(env: object = None, *args: object, **kwargs: object) -> Path:
        raise PipelineError(
            code="godot.not_found",
            message="Godot was not found.",
            remediation="Install Godot 4.",
            stage="godot",
        )

    monkeypatch.setattr("nmg_game_dev.godot.shot.resolve_godot", _missing)
    response = game_screenshot("a.png", project_root=_consumer(tmp_path))
    assert response["error"]["code"] == "godot.not_found"


# --- import_audio finishing settings (#252 FR2, T004) -------------------------------


def _audio_project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / "game").mkdir(parents=True)
    (root / "game" / "project.godot").write_text("config_version=5\n", encoding="utf-8")
    return root


def _audio_source(tmp_path: Path) -> Path:
    return write_wav(
        tmp_path / "saved" / "Whoosh.wav", sine(2.0, AUDIO_RATE, 440.0, 0.5), AUDIO_RATE
    )


def test_the_import_audio_tool_passes_the_finishing_settings_through(tmp_path: Path) -> None:
    response = import_audio(
        file=str(_audio_source(tmp_path)),
        name="Whoosh",
        kind="sfx",
        max_seconds=0.5,
        loudness_lufs=-14.0,
        loop_crossfade_ms=100,
        project_root=str(_audio_project(tmp_path)),
        godot=fake_godot(),
    )

    assert "error" not in response
    assert response["settings"] == {
        "finish": True,
        "max_seconds": 0.5,
        "loudness_lufs": -14.0,
        "loop_crossfade_ms": 100,
    }
    assert response["finish"]["cut"] is True
    assert response["finish"]["loudness_lufs"] == pytest.approx(-14.0, abs=0.1)


def test_the_import_audio_tool_reports_finish_false_as_not_applied(tmp_path: Path) -> None:
    response = import_audio(
        file=str(_audio_source(tmp_path)),
        name="Whoosh",
        kind="sfx",
        finish=False,
        project_root=str(_audio_project(tmp_path)),
        godot=fake_godot(),
    )

    assert response["finish"] == {"applied": False}
    assert response["settings"]["finish"] is False


def test_the_import_audio_tool_returns_an_out_of_range_setting_as_an_error(tmp_path: Path) -> None:
    response = import_audio(
        file=str(_audio_source(tmp_path)),
        name="Whoosh",
        kind="sfx",
        loudness_lufs=0.0,
        project_root=str(_audio_project(tmp_path)),
        godot=fake_godot(),
    )

    assert set(response) == {"error"}
    assert response["error"]["code"] == "audio.invalid_request"
    assert response["error"]["stage"] == "audio"


def test_tools_json_declares_the_optional_settings_with_their_bounds() -> None:
    tools = json.loads(TOOLS_JSON.read_text(encoding="utf-8"))["tools"]
    schema = next(tool for tool in tools if tool["name"] == "import_audio")["inputSchema"]

    props = schema["properties"]
    assert props["max_seconds"]["exclusiveMinimum"] == 0
    assert props["loudness_lufs"]["minimum"] == -40
    assert props["loudness_lufs"]["maximum"] == -5
    assert props["loop_crossfade_ms"]["minimum"] == 0
    assert "finish" in props
    assert props["loop"]["type"] == ["boolean", "null"]
    assert "default" not in props["loop"]
    assert schema["required"] == ["file", "name", "kind"]


def test_the_registered_server_schema_matches_tools_json() -> None:
    spec = importlib.util.spec_from_file_location("validate_mcp_tools", VALIDATOR)
    assert spec is not None and spec.loader is not None
    validator: ModuleType = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)

    assert validator.check_server(REPO_ROOT / "mcp-servers" / "finalize") == []


# check_finalized and the batch skip option (#247 AC6, AC11).


def test_check_finalized_reports_each_asset_from_its_record(tmp_path: Path) -> None:
    crate = up_to_date_asset(tmp_path, "Crate")
    barrel = asset_request(tmp_path, "Barrel")
    result = check_finalized(
        assets=[
            {"category": "Props", "collection": "Crate"},
            {"category": "Props", "collection": "Barrel"},
        ],
        export_root=str(crate.export_root),
    )

    rows = {row["collection"]: row for row in result["assets"]}
    assert set(rows) == {"Crate", "Barrel"}
    assert rows["Crate"]["up_to_date"] is True
    assert rows["Crate"]["reason"] == "up_to_date"
    assert set(rows["Crate"]["record"]) == {"state", "ended_at", "error_code"}
    assert rows["Barrel"]["up_to_date"] is False
    assert rows["Barrel"]["reason"] == "no_record"
    assert rows["Barrel"]["record"] is None
    assert barrel.blend is not None


def test_check_finalized_takes_one_category_and_collection(tmp_path: Path) -> None:
    crate = up_to_date_asset(tmp_path, "Crate")
    result = check_finalized(
        category="Props", collection="Crate", export_root=str(crate.export_root)
    )
    assert [row["collection"] for row in result["assets"]] == ["Crate"]
    assert result["assets"][0]["up_to_date"] is True


def test_check_finalized_reports_an_error_record_code(tmp_path: Path) -> None:
    request = asset_request(tmp_path)
    write_record_file(
        request,
        manual_record(
            request,
            state="failed",
            error={"code": "bake.quality.bad", "message": "m", "remediation": "r", "stage": "bake"},
        ),
    )
    row = check_finalized(
        category="Props", collection="Crate", export_root=str(request.export_root)
    )["assets"][0]
    assert row["reason"] == "last_run_failed"
    assert row["record"]["error_code"] == "bake.quality.bad"


@pytest.mark.parametrize(
    "arguments",
    [
        {
            "category": "Props",
            "collection": "Crate",
            "assets": [{"category": "Props", "collection": "Crate"}],
        },
        {"category": "Props"},
        {},
        {"assets": []},
        {"assets": [{"category": "Props"}]},
        {"category": "props", "collection": "Crate"},
    ],
)
def test_check_finalized_refuses_an_invalid_request(arguments: dict[str, Any]) -> None:
    result = check_finalized(**arguments)
    assert result["error"]["code"] == "finalize.invalid_request"
    assert result["error"]["stage"] == "finalize"
    assert result["error"]["remediation"]


def test_finalize_asset_refuses_skip_up_to_date_for_one_collection(tmp_path: Path) -> None:
    result = finalize_asset(
        collection="Crate",
        category="Props",
        asset_class="standard_prop",
        export_root=str(tmp_path / "game" / "assets"),
        skip_up_to_date=True,
    )
    assert result["error"]["code"] == "finalize.invalid_request"


def test_tools_json_lists_check_finalized_and_the_skip_option() -> None:
    tools = {
        tool["name"]: tool for tool in json.loads(TOOLS_JSON.read_text(encoding="utf-8"))["tools"]
    }
    check_schema = tools["check_finalized"]["inputSchema"]
    assert {"category", "collection", "assets", "export_root"} <= set(check_schema["properties"])
    assert check_schema["required"] == []
    skip = tools["finalize_asset"]["inputSchema"]["properties"]["skip_up_to_date"]
    assert skip["type"] == "boolean" and skip["default"] is False
