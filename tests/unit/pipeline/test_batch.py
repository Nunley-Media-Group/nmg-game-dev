"""Batch finalize: one job, one lock, items in order (#149, AC2-AC5, FR2-FR4, FR10).

Every test runs the batch in-process through ``BatchRouter`` with fake steps, a fake session, and a
fake Unreal client.  No Blender or Unreal editor is started.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from nmg_game_dev.finalize import FinalizeService, finalize_asset
from nmg_game_dev.finalize.service import build_batch
from nmg_game_dev.pipeline import FinalizeRequest, PipelineError, jobs
from tests.finalize_fakes import BatchRouter, Failure, batch_launcher, dead_pid


def _request(tmp_path: Path, collection: str) -> FinalizeRequest:
    return FinalizeRequest(
        collection=collection,
        category="Props",
        asset_class="standard_prop",
        export_root=tmp_path / "export",
    )


def _requests(tmp_path: Path, *names: str) -> dict[str, FinalizeRequest]:
    return {name: _request(tmp_path, name) for name in names}


def _service(
    cache: Path,
    requests: dict[str, FinalizeRequest],
    *,
    failures: dict[str, dict[str, Failure]] | None = None,
    on_step: Callable[[Path, str], None] | None = None,
) -> FinalizeService:
    def make_router(_: dict[str, FinalizeRequest]) -> BatchRouter:
        return BatchRouter(requests, failures=failures, on_step=on_step)

    return FinalizeService(cache, launcher=batch_launcher(make_router))


def _batch_items(tmp_path: Path, *names: str) -> list[dict[str, Any]]:
    return [
        {
            "collection": name,
            "category": "Props",
            "asset_class": "standard_prop",
            "export_root": str(tmp_path / "export"),
        }
        for name in names
    ]


def test_items_run_in_the_order_given_and_each_gets_its_own_directory(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    requests = _requests(tmp_path, "Alpha", "Beta", "Gamma")
    router_holder: list[BatchRouter] = []

    def make_router(batch_requests: dict[str, FinalizeRequest]) -> BatchRouter:
        router = BatchRouter(batch_requests)
        router_holder.append(router)
        return router

    service = FinalizeService(cache, launcher=batch_launcher(make_router))
    job_id = service.start_batch(list(requests.values()))

    assert router_holder[0].order == ["Alpha", "Beta", "Gamma"]
    items = cache / "jobs" / job_id / "items"
    assert sorted(path.name for path in items.iterdir()) == [
        "0-Alpha",
        "1-Beta",
        "2-Gamma",
    ]


def test_status_reports_the_running_collection_and_the_completed_count(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    seen: list[dict[str, Any]] = []

    def on_step(item_dir: Path, step: str) -> None:
        if item_dir.name == "1-Beta" and step == "validate":
            batch_dir = item_dir.parent.parent
            seen.append(jobs.status(batch_dir.name, cache_root=batch_dir.parent.parent))

    requests = _requests(tmp_path, "Alpha", "Beta", "Gamma")
    service = _service(cache, requests, on_step=on_step)
    job_id = service.start_batch(list(requests.values()))

    (during,) = seen
    assert during["state"] == "running"
    assert during["batch"]["total"] == 3
    assert during["batch"]["completed"] == 1
    assert during["batch"]["current"] == "Beta"
    assert during["batch"]["current_index"] == 1
    assert [item["state"] for item in during["batch"]["items"]] == [
        "succeeded",
        "running",
        "pending",
    ]
    final = jobs.status(job_id, cache_root=cache)
    assert final["state"] == "succeeded"
    assert final["batch"]["completed"] == 3
    assert final["batch"]["current"] is None


def test_the_batch_holds_the_lock_for_every_item_and_releases_it_at_the_end(
    tmp_path: Path,
) -> None:
    cache = tmp_path / "cache"
    lock_owners: list[str] = []

    def on_step(item_dir: Path, step: str) -> None:
        lock_owners.append(json.loads((cache / "jobs" / "lock").read_text())["job_id"])

    service = _service(cache, _requests(tmp_path, "Alpha", "Beta"), on_step=on_step)
    job_id = service.start_batch(list(_requests(tmp_path, "Alpha", "Beta").values()))

    assert lock_owners and set(lock_owners) == {job_id}
    assert not (cache / "jobs" / "lock").exists()


def test_a_failed_item_is_reported_with_its_code_message_and_stage(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    failures = {"Beta": {"bake": ("texture.bake_failed", "Alpha is linked.", "Set it to 1.")}}
    service = _service(cache, _requests(tmp_path, "Alpha", "Beta", "Gamma"), failures=failures)
    job_id = service.start_batch(list(_requests(tmp_path, "Alpha", "Beta", "Gamma").values()))

    final = jobs.status(job_id, cache_root=cache)
    assert final["state"] == "failed"
    assert final["error"]["code"] == "finalize.batch_failed"
    assert "1 of 3 collections failed and 0 were skipped" in final["error"]["message"]

    batch = final["result"]["batch"]
    assert (batch["succeeded"], batch["failed"], batch["skipped"]) == (2, 1, 0)
    states = {item["collection"]: item["state"] for item in batch["items"]}
    assert states == {"Alpha": "succeeded", "Beta": "failed", "Gamma": "succeeded"}
    beta = batch["items"][1]["error"]
    assert beta["code"] == "bake.texture.bake_failed"
    assert beta["message"] == "Alpha is linked."
    assert beta["stage"] == "bake"
    assert beta["remediation"] == "Set it to 1."


def test_without_fail_fast_the_items_after_a_failure_still_run(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    failures = {"Alpha": {"validate": ("contract.bad", "no", "fix")}}
    requests = _requests(tmp_path, "Alpha", "Beta")
    service = _service(cache, requests, failures=failures)
    job_id = service.start_batch(list(requests.values()), fail_fast=False)

    items = jobs.status(job_id, cache_root=cache)["result"]["batch"]["items"]
    assert [item["state"] for item in items] == ["failed", "succeeded"]


def test_with_fail_fast_the_items_after_a_failure_are_skipped(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    failures = {"Beta": {"validate": ("contract.bad", "no", "fix")}}
    requests = _requests(tmp_path, "Alpha", "Beta", "Gamma")
    service = _service(cache, requests, failures=failures)
    job_id = service.start_batch(list(requests.values()), fail_fast=True)

    final = jobs.status(job_id, cache_root=cache)
    batch = final["result"]["batch"]
    assert [item["state"] for item in batch["items"]] == ["succeeded", "failed", "skipped"]
    assert (batch["succeeded"], batch["failed"], batch["skipped"]) == (1, 1, 1)
    assert "1 were skipped" in final["error"]["message"]


def test_an_all_green_batch_succeeds_with_every_item_succeeded(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    requests = _requests(tmp_path, "Alpha", "Beta")
    service = _service(cache, requests)
    job_id = service.start_batch(list(requests.values()), fail_fast=True)

    final = jobs.status(job_id, cache_root=cache)
    assert final["state"] == "succeeded"
    assert final.get("error") is None
    assert final["result"]["batch"]["succeeded"] == 2


def test_a_batch_waiting_for_the_lock_fails_when_its_limit_expires_first(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    requests = _requests(tmp_path, "Alpha")
    service = _service(cache, requests)
    holder = jobs.start(
        _request(tmp_path, "Holder"), cache_root=cache, launcher=lambda d: os.getpid()
    )
    job_id = service.start_batch(list(requests.values()), wait_for_lock=True, lock_wait_s=0)

    final = jobs.status(job_id, cache_root=cache)
    assert final["state"] == "failed"
    assert final["error"]["code"] == "finalize.job_running"
    assert holder in final["error"]["message"]


def test_invalid_entries_are_all_named_and_no_job_directory_is_written(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    entries = [
        *_batch_items(tmp_path, "Alpha"),
        {
            "collection": "bad name",
            "category": "Props",
            "asset_class": "standard_prop",
            "export_root": str(tmp_path / "export"),
        },
        *_batch_items(tmp_path, "Gamma"),
        {
            "collection": "Delta",
            "category": "Props",
            "asset_class": "standard_prop",
            "export_root": str(tmp_path / "export"),
            "bogus": True,
        },
    ]

    response = finalize_asset(
        requests=entries,
        service=FinalizeService(cache, launcher=lambda d: dead_pid()),
    )

    error = response["error"]
    assert error["code"] == "finalize.invalid_batch"
    assert "index 1:" in error["message"]
    assert "index 3:" in error["message"]
    assert "index 0" not in error["message"]
    assert not (cache / "jobs").exists()


def test_build_batch_fills_missing_keys_from_the_defaults(tmp_path: Path) -> None:
    (request,) = build_batch(
        [{"collection": "Alpha"}],
        defaults={
            "category": "Props",
            "asset_class": "standard_prop",
            "export_root": str(tmp_path / "export"),
            "pie_mode": "refuse",
            "pie_wait_seconds": 30,
        },
    )
    assert request.category == "Props"
    assert request.pie_mode == "refuse"
    assert request.pie_wait_seconds == 30


def test_an_entry_value_of_zero_is_kept_not_replaced_by_the_default(tmp_path: Path) -> None:
    (request,) = build_batch(
        [
            {
                "collection": "Alpha",
                "category": "Props",
                "asset_class": "standard_prop",
                "export_root": str(tmp_path / "export"),
                "pie_wait_seconds": 0,
            }
        ],
    )
    assert request.pie_wait_seconds == 0


def test_an_entry_with_an_unknown_key_names_the_key(tmp_path: Path) -> None:
    with pytest.raises(PipelineError) as info:
        build_batch(
            [{"collection": "Alpha", "export_root": str(tmp_path), "fail_fast": True}],
            defaults={"category": "Props", "asset_class": "standard_prop"},
        )
    assert info.value.code == "finalize.invalid_batch"
    assert "index 0" in info.value.message
    assert "unknown key(s): fail_fast" in info.value.message


def test_each_entry_carries_its_own_compatible_with(tmp_path: Path) -> None:
    defaults = {
        "category": "Characters",
        "asset_class": "character",
        "export_root": str(tmp_path / "export"),
    }
    hero, guard = build_batch(
        [
            {"collection": "Hero", "compatible_with": ["Characters/Guard"]},
            {"collection": "Guard"},
        ],
        defaults=defaults,
    )
    assert hero.compatible_with == ("Characters/Guard",)
    assert guard.compatible_with == ()


def test_a_compatible_with_that_is_not_a_list_names_the_entry(tmp_path: Path) -> None:
    with pytest.raises(PipelineError) as info:
        build_batch(
            [{"collection": "Hero", "compatible_with": "Characters/Guard"}],
            defaults={
                "category": "Characters",
                "asset_class": "character",
                "export_root": str(tmp_path),
            },
        )
    assert info.value.code == "finalize.invalid_batch"
    assert "index 0: compatible_with must be a list" in info.value.message


def test_an_empty_batch_is_refused_before_anything_is_written(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    with pytest.raises(PipelineError) as info:
        FinalizeService(cache).start_batch([])
    assert info.value.code == "finalize.invalid_batch"
    assert not (cache / "jobs").exists()
