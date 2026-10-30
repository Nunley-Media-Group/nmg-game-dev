"""Unit tests for the finalize job lifecycle: start, status, lock, crash, and wait (AC2, #69)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from nmg_game_dev.pipeline import FinalizeClients, FinalizeRequest, PipelineError, jobs
from tests.finalize_fakes import FakeBlenderSession, FakeStepRunner, FakeUnrealRunner


def _request(tmp_path: Path) -> FinalizeRequest:
    blend = tmp_path / "crate.blend"
    blend.write_bytes(b"authored")
    return FinalizeRequest(
        collection="Crate",
        category="Props",
        asset_class="standard_prop",
        export_root=tmp_path / "export",
        blend=blend,
    )


def _dead_pid() -> int:
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait()
    return process.pid


def _run_now(job_dir: Path, request: FinalizeRequest) -> None:
    jobs.run_job(
        job_dir,
        clients=FinalizeClients(blender=FakeBlenderSession(), unreal=FakeUnrealRunner()),
        runner=FakeStepRunner(request),
    )


def test_start_then_run_writes_a_succeeded_status_with_each_step(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    request = _request(tmp_path)
    job_id = jobs.start(
        request, cache_root=cache, launcher=lambda d: _run_and_return_dead(d, request)
    )

    status = jobs.status(job_id, cache_root=cache)
    assert status["state"] == "succeeded"
    assert set(status["steps"]) == {
        "validate",
        "bake",
        "variants",
        "export",
        "reimport",
        "import_ue",
    }
    assert status["result"]["desktop_content_path"] == "/Game/Props/Crate/Desktop"


def _run_and_return_dead(job_dir: Path, request: FinalizeRequest) -> int:
    _run_now(job_dir, request)
    return _dead_pid()


def test_the_lock_is_released_after_the_job_finishes(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    request = _request(tmp_path)
    jobs.start(request, cache_root=cache, launcher=lambda d: _run_and_return_dead(d, request))
    assert not (cache / "jobs" / "lock").exists()


def test_a_live_job_refuses_a_second_start_with_job_running(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    request = _request(tmp_path)
    jobs.start(request, cache_root=cache, launcher=lambda d: os.getpid())

    with pytest.raises(PipelineError) as info:
        jobs.start(request, cache_root=cache, launcher=lambda d: os.getpid())
    assert info.value.code == "finalize.job_running"


def test_a_stale_lock_is_cleared_and_the_new_job_starts(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    request = _request(tmp_path)
    (cache / "jobs").mkdir(parents=True)
    (cache / "jobs" / "lock").write_text(str(_dead_pid()), encoding="utf-8")

    job_id = jobs.start(
        request, cache_root=cache, launcher=lambda d: _run_and_return_dead(d, request)
    )
    assert jobs.status(job_id, cache_root=cache)["state"] == "succeeded"


def test_a_vanished_job_process_is_reported_as_job_crashed(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    request = _request(tmp_path)
    job_id = jobs.start(request, cache_root=cache, launcher=lambda d: _dead_pid())

    status = jobs.status(job_id, cache_root=cache)
    assert status["state"] == "failed"
    assert status["error"]["code"] == "finalize.job_crashed"


def test_unknown_job_id_is_finalize_job_not_found(tmp_path: Path) -> None:
    with pytest.raises(PipelineError) as info:
        jobs.status("missing", cache_root=tmp_path / "cache")
    assert info.value.code == "finalize.job_not_found"


def test_path_like_job_ids_are_not_found_rather_than_read(tmp_path: Path) -> None:
    with pytest.raises(PipelineError) as info:
        jobs.status("../escape", cache_root=tmp_path / "cache")
    assert info.value.code == "finalize.job_not_found"


def test_wait_returns_the_terminal_status(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    request = _request(tmp_path)
    job_id = jobs.start(
        request, cache_root=cache, launcher=lambda d: _run_and_return_dead(d, request)
    )
    final = jobs.wait(job_id, timeout_s=5, cache_root=cache, poll_s=0.01)
    assert final["state"] == "succeeded"


def test_wait_times_out_on_a_job_that_never_finishes(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    request = _request(tmp_path)
    job_id = jobs.start(request, cache_root=cache, launcher=lambda d: os.getpid())
    status = jobs.wait(job_id, timeout_s=0, cache_root=cache, poll_s=0.01)
    assert status["state"] == "queued"


def test_a_failing_step_writes_a_failed_status_with_the_error(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    request = _request(tmp_path)

    def launch(job_dir: Path) -> int:
        jobs.run_job(
            job_dir,
            clients=FinalizeClients(blender=FakeBlenderSession(), unreal=FakeUnrealRunner()),
            runner=FakeStepRunner(request, failures={"bake": ("texture.bake_failed", "no", "fix")}),
        )
        return _dead_pid()

    job_id = jobs.start(request, cache_root=cache, launcher=launch)
    status = jobs.status(job_id, cache_root=cache)
    assert status["state"] == "failed"
    assert status["error"]["code"] == "bake.texture.bake_failed"
    assert status["error"]["stage"] == "bake"
