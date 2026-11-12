"""Unit tests for the finalize job lifecycle: start, status, lock, crash, and wait (AC2, #69)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

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


class _FakeClock:
    """A clock that moves only when the injected sleep advances it (#149 tests)."""

    def __init__(self) -> None:
        self.now = 0.0

    def read(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def _lock(cache: Path) -> Path:
    return cache / "jobs" / "lock"


def _holding_job(cache: Path, request: FinalizeRequest) -> str:
    """Start a job that holds the cache lock and never runs, like a live process would."""
    return jobs.start(request, cache_root=cache, launcher=lambda d: os.getpid())


def _run_waiting(
    cache: Path,
    job_id: str,
    request: FinalizeRequest,
    *,
    sleep: Callable[[float], None],
    clock: Callable[[], float],
) -> None:
    jobs.run_job(
        cache / "jobs" / job_id,
        clients=FinalizeClients(blender=FakeBlenderSession(), unreal=FakeUnrealRunner()),
        runner=FakeStepRunner(request),
        sleep=sleep,
        clock=clock,
    )


def test_the_claim_records_the_holder_pid_and_job_id(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    job_id = _holding_job(cache, _request(tmp_path))

    assert json.loads(_lock(cache).read_text(encoding="utf-8")) == {
        "pid": os.getpid(),
        "job_id": job_id,
    }


def test_a_legacy_plain_pid_lock_still_refuses_a_live_holder(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    (cache / "jobs").mkdir(parents=True)
    _lock(cache).write_text(str(os.getpid()), encoding="utf-8")

    with pytest.raises(PipelineError) as info:
        jobs.start(_request(tmp_path), cache_root=cache, launcher=lambda d: os.getpid())
    assert info.value.code == "finalize.job_running"
    assert f"PID {os.getpid()}" in info.value.message


def test_a_refused_start_names_the_holder_job_and_keeps_its_lock(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    request = _request(tmp_path)
    holder = _holding_job(cache, request)

    with pytest.raises(PipelineError) as info:
        jobs.start(request, cache_root=cache, launcher=lambda d: os.getpid())
    assert info.value.code == "finalize.job_running"
    assert holder in info.value.message
    assert json.loads(_lock(cache).read_text(encoding="utf-8"))["job_id"] == holder


def test_a_waiting_job_starts_waiting_and_runs_once_the_lock_is_free(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    request = _request(tmp_path)
    holder = _holding_job(cache, request)
    job_id = jobs.start(
        request, cache_root=cache, launcher=lambda d: os.getpid(), wait_for_lock=True
    )

    waiting = jobs.status(job_id, cache_root=cache)
    assert waiting["state"] == "waiting"
    assert holder in waiting["message"]

    _lock(cache).unlink()  # the holder finishes
    sleeps: list[float] = []
    _run_waiting(cache, job_id, request, sleep=sleeps.append, clock=_FakeClock().read)

    assert jobs.status(job_id, cache_root=cache)["state"] == "succeeded"
    assert sleeps == []  # the lock was free on the first try, so nothing was polled
    assert not _lock(cache).exists()


def test_a_waiting_job_polls_with_jitter_until_the_holder_releases(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    request = _request(tmp_path)
    _holding_job(cache, request)
    job_id = jobs.start(
        request, cache_root=cache, launcher=lambda d: os.getpid(), wait_for_lock=True
    )
    clock = _FakeClock()
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock.sleep(seconds)
        if len(sleeps) == 3:
            _lock(cache).unlink()  # the holder finishes during the third poll

    _run_waiting(cache, job_id, request, sleep=sleep, clock=clock.read)

    assert jobs.status(job_id, cache_root=cache)["state"] == "succeeded"
    assert len(sleeps) == 3
    assert all(2.0 <= seconds <= 5.0 for seconds in sleeps)


def test_an_expired_wait_limit_fails_naming_the_holder_and_leaves_its_lock(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    request = _request(tmp_path)
    holder = _holding_job(cache, request)
    job_id = jobs.start(
        request,
        cache_root=cache,
        launcher=lambda d: os.getpid(),
        wait_for_lock=True,
        lock_wait_s=7,
    )
    clock = _FakeClock()

    _run_waiting(cache, job_id, request, sleep=clock.sleep, clock=clock.read)

    status = jobs.status(job_id, cache_root=cache)
    assert status["state"] == "failed"
    assert status["error"]["code"] == "finalize.job_running"
    assert holder in status["error"]["message"]
    assert clock.now == pytest.approx(7.0)  # polling stopped at the limit, not after it
    assert json.loads(_lock(cache).read_text(encoding="utf-8"))["job_id"] == holder


def test_a_waiting_job_clears_a_stale_lock_left_by_a_dead_pid(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    request = _request(tmp_path)
    (cache / "jobs").mkdir(parents=True)
    _lock(cache).write_text(json.dumps({"pid": _dead_pid(), "job_id": "gone"}), encoding="utf-8")
    job_id = jobs.start(
        request, cache_root=cache, launcher=lambda d: os.getpid(), wait_for_lock=True
    )

    _run_waiting(cache, job_id, request, sleep=lambda s: None, clock=_FakeClock().read)

    assert jobs.status(job_id, cache_root=cache)["state"] == "succeeded"
    assert not _lock(cache).exists()


def test_a_negative_lock_wait_limit_is_refused_before_any_job_directory(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    with pytest.raises(PipelineError) as info:
        jobs.start(
            _request(tmp_path),
            cache_root=cache,
            launcher=lambda d: os.getpid(),
            wait_for_lock=True,
            lock_wait_s=-1,
        )
    assert info.value.code == "finalize.invalid_request"
    assert not (cache / "jobs").exists()


def test_a_validate_progress_event_is_in_the_job_status_mid_step(tmp_path: Path) -> None:
    """#133 AC6 (host): a validate event emitted mid-step is what get_finalize_job reads then."""
    cache = tmp_path / "cache"
    request = _request(tmp_path)
    during: list[dict[str, Any]] = []

    class ValidateProgressRunner(FakeStepRunner):
        def run_step(
            self,
            step: str,
            *,
            job_dir: Path,
            in_blend: Path | None,
            inputs: Any = None,
            on_progress: Any = None,
        ) -> dict[str, Any]:
            if step == "validate" and on_progress is not None:
                on_progress(
                    {
                        "state": "running",
                        "step": "validate",
                        "progress": 0.5,
                        "message": "desktop: UV overlap check on SM_Crate",
                    }
                )
                during.append(jobs.status(job_dir.name, cache_root=cache))
            return super().run_step(
                step,
                job_dir=job_dir,
                in_blend=in_blend,
                inputs=inputs,
                on_progress=on_progress,
            )

    def launch(job_dir: Path) -> int:
        jobs.run_job(
            job_dir,
            clients=FinalizeClients(blender=FakeBlenderSession(), unreal=FakeUnrealRunner()),
            runner=ValidateProgressRunner(request),
        )
        return _dead_pid()

    jobs.start(request, cache_root=cache, launcher=launch)

    (status,) = during
    assert status["state"] == "running"
    assert status["step"] == "validate"
    assert status["progress"] == 0.5
    assert status["message"] == "desktop: UV overlap check on SM_Crate"
