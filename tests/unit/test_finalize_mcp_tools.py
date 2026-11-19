"""The finalize MCP tool parameters for batches, lock waits, and the export root (#149, #249).

The tool functions are tested directly, so the MCP SDK is not needed.  Batch jobs run in-process
through ``BatchRouter`` with fake steps and a fake Godot runner, so no Blender or Godot process is
started.
"""

from __future__ import annotations

import json
import os
import struct
from pathlib import Path
from typing import Any

import pytest

from nmg_game_dev.finalize import (
    FinalizeService,
    finalize_asset,
    game_screenshot,
    get_finalize_job,
    run_finalize_step,
)
from nmg_game_dev.godot.runner import CommandResult
from nmg_game_dev.pipeline import FinalizeRequest
from nmg_game_dev.pipeline.errors import PipelineError
from tests.finalize_fakes import BatchRouter, batch_launcher, dead_pid
from tests.godot_fakes import FakeGodotRunner


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
