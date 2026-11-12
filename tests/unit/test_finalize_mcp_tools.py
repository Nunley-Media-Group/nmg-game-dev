"""The finalize MCP tool parameters for batches, lock waits, and PIE (#149, AC2, AC5, AC10).

The tool functions are tested directly, so the MCP SDK is not needed.  Batch jobs run in-process
through ``BatchRouter`` with fake steps, so no Blender or Unreal editor is started.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from nmg_game_dev.finalize import (
    FinalizeService,
    finalize_asset,
    get_finalize_job,
    run_finalize_step,
)
from nmg_game_dev.pipeline import FinalizeRequest
from tests.finalize_fakes import BatchRouter, batch_launcher, dead_pid


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


def test_a_single_collection_still_needs_an_export_root(tmp_path: Path) -> None:
    response = finalize_asset(collection="Crate", service=_deferred(tmp_path / "cache"))
    assert response["error"]["code"] == "finalize.invalid_request"
    assert "export_root" in response["error"]["message"]


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


def test_the_single_wait_and_pie_options_reach_the_request(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    response = finalize_asset(
        **_single_args(tmp_path),
        wait_for_lock=True,
        lock_wait_seconds=12,
        pie_mode="refuse",
        pie_wait_seconds=30,
        service=_deferred(cache),
    )

    assert response["status"] == "waiting"
    (job_dir,) = _job_dirs(cache)
    request = json.loads((job_dir / "request.json").read_text(encoding="utf-8"))
    job = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
    assert request["pie_mode"] == "refuse"
    assert request["pie_wait_seconds"] == 30
    assert job["lock_wait_s"] == 12


def test_run_finalize_step_accepts_the_wait_and_pie_options(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    response = run_finalize_step(
        step="validate",
        **_single_args(tmp_path),
        wait_for_lock=True,
        pie_mode="wait",
        pie_wait_seconds=60,
        service=_deferred(cache),
    )

    assert "error" not in response
    (job_dir,) = _job_dirs(cache)
    job = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
    assert job["wait_for_lock"] is True


def test_an_unknown_pie_mode_is_a_structured_invalid_request(tmp_path: Path) -> None:
    response = finalize_asset(
        **_single_args(tmp_path),
        pie_mode="ignore",
        service=_deferred(tmp_path / "cache"),
    )
    assert response["error"]["code"] == "finalize.invalid_request"


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
