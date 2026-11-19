"""Per-asset finalize records, log copies, and the up-to-date check (#247, AC1-AC10, FR10).

Every test uses temporary directories, a temporary ``game/project.godot``, and the in-process fakes.
No Blender or Godot process starts.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from nmg_game_dev import __version__
from nmg_game_dev.pipeline import FinalizeRequest
from nmg_game_dev.pipeline.records import REASONS, check, record_file, summary
from tests.finalize_fakes import FakeStepRunner
from tests.finalize_records_support import (
    PAST,
    RECORD_FIELDS,
    TerrainLoggingRunner,
    asset_request,
    consumer_of,
    hold_cache_lock,
    logs_of,
    manual_record,
    record_of,
    run_finalize,
    snapshot,
    terrain_asset_request,
    up_to_date_asset,
    write_imports,
    write_record_file,
)


def _check(request: FinalizeRequest) -> Any:
    return check(request.category, request.collection, request.export_root)


def _read(path: Path) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


# AC1: the record holds every field of design.md.


def test_a_finished_run_writes_a_record_with_every_field(tmp_path: Path) -> None:
    request = asset_request(tmp_path)
    status = run_finalize(tmp_path / "cache", request)

    assert status["state"] == "succeeded"
    record = _read(record_of(request))
    assert set(record) == RECORD_FIELDS
    assert record["schema_version"] == 1
    assert (record["category"], record["collection"]) == ("Props", "Crate")
    assert record["job_id"] == status["job_id"]
    assert record["state"] == "succeeded"
    assert record["nmg_game_dev_version"] == __version__
    assert record["full_run"] is True
    assert datetime.fromisoformat(record["started_at"]) <= datetime.fromisoformat(
        record["ended_at"]
    )
    assert [step["step"] for step in record["steps"]] == [
        step["step"] for step in status["result"]["steps"]
    ]
    assert all(step["cache_hit"] is False for step in record["steps"])
    assert record["source"]["blend"] == str(request.blend)
    assert isinstance(record["source"]["mtime"], float)
    assert record["imported"] == [
        status["result"]["desktop_resource_path"],
        status["result"]["mobile_resource_path"],
    ]
    assert record["content_hash"] == "asset-hash-0"
    assert record["error"] is None


def test_a_session_run_records_a_null_source(tmp_path: Path) -> None:
    request = asset_request(tmp_path, blend=False)
    run_finalize(tmp_path / "cache", request)
    assert _read(record_of(request))["source"] is None


def test_a_failed_run_writes_a_failed_record_with_its_error(tmp_path: Path) -> None:
    request = asset_request(tmp_path)
    runner = FakeStepRunner(
        request, failures={"bake": ("quality.contract_failed", "bad bake", "fix it")}
    )
    status = run_finalize(tmp_path / "cache", request, runner=runner)

    assert status["state"] == "failed"
    record = _read(record_of(request))
    assert record["state"] == "failed"
    assert record["error"] == status["error"]
    assert record["error"]["code"].endswith("quality.contract_failed")
    assert record["imported"] == []


# AC2: the log copies outlive the job directory.


def test_the_log_copies_survive_deletion_of_the_job_directory(tmp_path: Path) -> None:
    request = asset_request(tmp_path)
    cache = tmp_path / "cache"
    status = run_finalize(cache, request)
    shutil.rmtree(cache / "jobs" / status["job_id"])

    record = _read(record_of(request))
    assert record["logs"]["job"] == "Crate.logs/job.log"
    assert "validate" in record["logs"]["steps"]
    assert (logs_of(request) / "job.log").read_text(encoding="utf-8") == (
        f"job {status['job_id']}\n"
    )
    for relative in record["logs"]["steps"].values():
        assert (record_of(request).parent / relative).is_file(), relative


# AC4: a new run replaces the record and the logs.


def test_a_new_run_replaces_the_record_and_keeps_only_its_logs(tmp_path: Path) -> None:
    request = asset_request(tmp_path)
    cache = tmp_path / "cache"
    run_finalize(cache, request)
    (logs_of(request) / "stale-from-an-older-run.log").write_text("old", encoding="utf-8")

    second = run_finalize(cache, request)

    record = _read(record_of(request))
    assert record["job_id"] == second["job_id"]
    assert not (logs_of(request) / "stale-from-an-older-run.log").exists()
    assert (logs_of(request) / "job.log").read_text(encoding="utf-8") == (
        f"job {second['job_id']}\n"
    )
    names = {path.name for path in logs_of(request).iterdir()}
    assert names == {"job.log"} | {Path(rel).name for rel in record["logs"]["steps"].values()}


def test_a_failed_record_write_removes_the_stale_record(tmp_path: Path) -> None:
    request = asset_request(tmp_path)
    cache = tmp_path / "cache"
    run_finalize(cache, request)
    assert record_of(request).is_file()
    # Put a file where the logs folder must go, so the next run's log copy cannot be written.
    shutil.rmtree(logs_of(request))
    logs_of(request).write_text("not a folder", encoding="utf-8")

    second = run_finalize(cache, request)

    assert second["state"] == "succeeded"
    assert [w["code"] for w in second["result"]["warnings"]] == ["finalize.record_not_written"]
    assert not record_of(request).exists(), "an older record must not describe the new run"


# AC10: record writing never changes a run's result.


def test_an_unwritable_records_folder_warns_and_leaves_the_run_unchanged(tmp_path: Path) -> None:
    request = asset_request(tmp_path)
    (tmp_path / ".nmg").mkdir()
    (tmp_path / ".nmg" / "finalize").write_text("a file, not a folder", encoding="utf-8")

    status = run_finalize(tmp_path / "cache", request)

    assert status["state"] == "succeeded"
    assert status.get("error") is None
    assert status["result"]["desktop_resource_path"] == (
        "res://assets/Props/Crate/Desktop/Crate.glb"
    )
    warnings = status["result"]["warnings"]
    assert [w["code"] for w in warnings] == ["finalize.record_not_written"]
    assert "The finalize record was not written" in warnings[0]["message"]


def test_an_unresolvable_project_warns_and_the_run_still_succeeds(tmp_path: Path) -> None:
    export_root = tmp_path / "loose" / "assets"
    request = FinalizeRequest(
        collection="Crate",
        category="Props",
        asset_class="standard_prop",
        export_root=export_root,
    )
    steps = ("validate", "bake", "variants", "export")

    status = run_finalize(tmp_path / "cache", request, steps=steps, godot=False)

    assert status["state"] == "succeeded"
    warnings = status["result"]["warnings"]
    assert [w["code"] for w in warnings] == ["finalize.record_not_written"]
    assert "project.godot" in warnings[0]["message"]


# AC5-AC8: the check's rule and its reasons.


def test_an_asset_whose_record_passes_every_rule_is_up_to_date(tmp_path: Path) -> None:
    request = up_to_date_asset(tmp_path)
    result = _check(request)
    assert (result.up_to_date, result.reason) == (True, "up_to_date")
    assert result.record is not None and result.record["collection"] == "Crate"


def test_no_record_is_not_up_to_date(tmp_path: Path) -> None:
    request = asset_request(tmp_path)
    write_imports(request)
    result = _check(request)
    assert (result.up_to_date, result.reason, result.record) == (False, "no_record", None)


def test_a_record_that_is_not_valid_json_is_unreadable(tmp_path: Path) -> None:
    request = asset_request(tmp_path)
    write_record_file(request, "{not json")
    assert _check(request).reason == "record_unreadable"


def test_a_record_that_does_not_match_the_schema_is_unreadable(tmp_path: Path) -> None:
    request = asset_request(tmp_path)
    write_record_file(request, manual_record(request, state="running"))
    result = _check(request)
    assert (result.up_to_date, result.reason, result.record) == (False, "record_unreadable", None)


def test_a_failed_last_run_is_not_up_to_date(tmp_path: Path) -> None:
    request = up_to_date_asset(tmp_path)
    write_record_file(request, manual_record(request, state="failed"))
    assert _check(request).reason == "last_run_failed"


def test_a_one_step_run_is_not_a_full_run(tmp_path: Path) -> None:
    request = up_to_date_asset(tmp_path)
    write_record_file(request, manual_record(request, full_run=False))
    assert _check(request).reason == "not_full_run"


def test_a_run_without_a_source_blend_is_not_up_to_date(tmp_path: Path) -> None:
    request = asset_request(tmp_path, blend=False)
    write_imports(request)
    write_record_file(request, manual_record(request))
    assert _check(request).reason == "no_source_blend"


def test_a_deleted_source_blend_is_source_missing(tmp_path: Path) -> None:
    request = up_to_date_asset(tmp_path)
    assert request.blend is not None
    request.blend.unlink()
    assert _check(request).reason == "source_missing"


def test_a_source_blend_changed_after_the_run_began_is_source_newer(tmp_path: Path) -> None:
    request = up_to_date_asset(tmp_path)
    write_record_file(request, manual_record(request, started_at=PAST))
    assert _check(request).reason == "source_newer"


def test_a_missing_mobile_import_file_is_import_missing(tmp_path: Path) -> None:
    request = up_to_date_asset(tmp_path)
    (request.export_root / "Props" / "Crate" / "Mobile" / "Crate.glb.import").unlink()
    assert _check(request).reason == "import_missing"


def test_a_native_scene_needs_no_import_file_but_must_exist(tmp_path: Path) -> None:
    request = up_to_date_asset(tmp_path)
    scene = request.export_root / "Props" / "Crate" / "Desktop" / "Crate.tscn"
    imported = ["res://assets/Props/Crate/Desktop/Crate.tscn"]
    write_record_file(request, manual_record(request, imported=imported))
    assert _check(request).reason == "import_missing"
    scene.touch()
    assert _check(request).reason == "up_to_date"


# AC7 round trip: a record a finished job wrote checks as up to date once Godot has imported.


def test_a_record_written_by_a_finished_prop_run_is_up_to_date(tmp_path: Path) -> None:
    request = asset_request(tmp_path)
    status = run_finalize(tmp_path / "cache", request)
    assert status["state"] == "succeeded"
    result = _check(request)
    assert (result.reason, result.up_to_date) == ("up_to_date", True)
    (request.export_root / "Props" / "Crate" / "Mobile" / "Crate.glb.import").unlink()
    assert _check(request).reason == "import_missing"


def test_a_record_written_by_a_finished_terrain_run_is_up_to_date(tmp_path: Path) -> None:
    request = terrain_asset_request(tmp_path)
    status = run_finalize(tmp_path / "cache", request, runner=TerrainLoggingRunner(request))
    assert status["state"] == "succeeded"
    record = _read(record_of(request))
    assert record["imported"] == [
        "res://assets/Environment/Hills/Desktop/Hills.tscn",
        "res://assets/Environment/Hills/Mobile/Hills.tscn",
    ]
    result = _check(request)
    assert (result.reason, result.up_to_date) == ("up_to_date", True)
    (request.export_root / "Environment" / "Hills" / "Mobile" / "Hills.tscn").unlink()
    assert _check(request).reason == "import_missing"


def test_an_export_root_outside_any_godot_project_is_project_missing(tmp_path: Path) -> None:
    request = up_to_date_asset(tmp_path)
    result = check("Props", "Crate", tmp_path / "loose" / "assets")
    assert (result.up_to_date, result.reason) == (False, "project_missing")
    assert record_file(consumer_of(request), "Props", "Crate").is_file()


def test_every_reason_the_spec_names_is_reachable() -> None:
    assert set(REASONS) == {
        "up_to_date",
        "project_missing",
        "no_record",
        "record_unreadable",
        "last_run_failed",
        "not_full_run",
        "no_source_blend",
        "source_missing",
        "source_newer",
        "import_missing",
    }


def test_the_summary_names_state_end_time_and_error_code() -> None:
    assert summary(None) is None
    assert summary({"state": "failed", "ended_at": "t", "error": {"code": "x.y"}}) == {
        "state": "failed",
        "ended_at": "t",
        "error_code": "x.y",
    }
    succeeded = summary({"state": "succeeded", "ended_at": "t", "error": None})
    assert succeeded is not None and succeeded["error_code"] is None


# AC9: the check is cheap and leaves the trees alone, even while a job holds the lock.


def test_the_check_answers_while_the_cache_lock_is_held_and_writes_nothing(tmp_path: Path) -> None:
    request = up_to_date_asset(tmp_path)
    cache = tmp_path / "cache"
    hold_cache_lock(cache)
    before_project = snapshot(tmp_path)
    before_cache = snapshot(cache)

    result = _check(request)

    assert result.up_to_date
    assert snapshot(tmp_path) == before_project
    assert snapshot(cache) == before_cache


def test_the_record_path_is_the_consumer_nmg_finalize_folder(tmp_path: Path) -> None:
    request = asset_request(tmp_path)
    assert record_file(consumer_of(request), "Props", "Crate") == (
        tmp_path / ".nmg" / "finalize" / "Props" / "Crate.json"
    )
