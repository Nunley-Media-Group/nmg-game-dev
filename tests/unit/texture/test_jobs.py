"""Background jobs: the FIFO queue, start, status, the queue runner, and batch jobs (#7 FR14, AC17,
AC20; #143 AC2, AC4, AC5, FR5)."""

from __future__ import annotations

import json
import os
import subprocess
import types
from pathlib import Path
from typing import Any

import pytest

from nmg_game_dev.texture import jobs
from nmg_game_dev.texture.errors import TextureGenError
from nmg_game_dev.texture.generate import TextureRequest, request_as_json
from nmg_game_dev.texture.registry import REGISTRY
from tests.texture_fakes import APPLE_SILICON_32GB, fake_spawn, read_log


class _FakeProc:
    pid = os.getpid()


@pytest.fixture
def spawn_kwargs() -> list[dict[str, Any]]:
    """The keyword arguments of each runner spawn, in order (its stdout handle names the log)."""
    return []


@pytest.fixture
def spawned(monkeypatch: pytest.MonkeyPatch, spawn_kwargs: list[dict[str, Any]]) -> list[list[str]]:
    """Record each runner spawn instead of starting one, so ``start`` only queues."""
    calls: list[list[str]] = []

    def popen(argv: list[str], **kwargs: Any) -> _FakeProc:
        calls.append(argv)
        spawn_kwargs.append(kwargs)
        return _FakeProc()

    shim = types.SimpleNamespace(Popen=popen, DEVNULL=subprocess.DEVNULL)
    monkeypatch.setattr(jobs, "subprocess", shim)
    return calls


def _request(backend: str = "z-image-turbo", seeds: list[int] | None = None) -> TextureRequest:
    return TextureRequest(
        prompt="burlap", backend=backend, seeds=seeds or [1], resolution=256, name="burlap"
    )


@pytest.fixture
def started(
    spawned: list[list[str]], env: dict[str, str], out_root: Path
) -> tuple[str, TextureRequest]:
    request = _request()
    job_id = jobs.start(request, env=env, facts=APPLE_SILICON_32GB, cwd=out_root.parent)
    return job_id, request


def test_start_queues_the_job_and_spawns_the_queue_runner(
    started: tuple[str, TextureRequest],
    spawned: list[list[str]],
    out_root: Path,
    env: dict[str, str],
) -> None:
    job_id, _ = started
    status = jobs.status(job_id, env=env)
    assert status["state"] == "queued" and status["total"] == 1
    assert not (out_root / ".jobs" / "lock").exists()  # start never takes the lock; the runner does
    assert spawned[0][-2:] == ["run-queue", str(out_root / ".jobs")]


def test_request_json_records_the_request_output_root_and_submission_time(
    started: tuple[str, TextureRequest], out_root: Path
) -> None:
    job_id, request = started
    stored = json.loads((out_root / ".jobs" / job_id / "request.json").read_text())
    assert stored["request"] == request_as_json(request)
    assert stored["output_root"] == str(out_root)
    assert stored["submitted_ns"] > 0
    assert REGISTRY["z-image-turbo"].id in stored["request"]["backend"]


def test_a_second_start_while_a_runner_is_alive_is_queued_not_refused(
    started: tuple[str, TextureRequest],
    spawned: list[list[str]],
    env: dict[str, str],
    out_root: Path,
) -> None:
    first, _ = started
    lock = out_root / ".jobs" / "lock"
    lock.write_text(json.dumps({"pid": os.getpid()}))  # a live runner holds the queue
    second = jobs.start(
        _request("flux2-klein-4b"), env=env, facts=APPLE_SILICON_32GB, cwd=out_root.parent
    )
    assert second != first
    assert jobs.status(second, env=env)["state"] == "queued"
    assert len(spawned) == 2


def test_start_refuses_missing_dependencies_before_anything_is_queued(
    spawned: list[list[str]], env: dict[str, str], out_root: Path
) -> None:
    with pytest.raises(TextureGenError) as caught:
        jobs.start(
            _request(),
            env=env,
            facts=APPLE_SILICON_32GB,
            cwd=out_root.parent,
            deps_probe=lambda: "mlx",
        )
    assert caught.value.code == "texture.dependencies_missing"
    assert "mlx" in caught.value.message
    assert "uv run --project" in caught.value.remediation
    assert spawned == []
    assert not (out_root / ".jobs").exists()


def test_invalid_request_is_refused_before_a_job_exists(
    spawned: list[list[str]], env: dict[str, str], out_root: Path
) -> None:
    with pytest.raises(TextureGenError):
        jobs.start(
            TextureRequest(prompt=""), env=env, facts=APPLE_SILICON_32GB, cwd=out_root.parent
        )
    assert not (out_root / ".jobs").exists()
    assert spawned == []


def test_a_batch_start_queues_one_job_covering_every_request(
    spawned: list[list[str]], env: dict[str, str], out_root: Path
) -> None:
    requests = [
        _request(seeds=[1, 2]),
        TextureRequest(
            prompt="stone", backend="flux2-klein-4b", seeds=[3], resolution=256, name="stone"
        ),
    ]
    job_id = jobs.start(requests, env=env, facts=APPLE_SILICON_32GB, cwd=out_root.parent)
    status = jobs.status(job_id, env=env)
    assert status["state"] == "queued" and status["total"] == 3
    stored = json.loads((out_root / ".jobs" / job_id / "request.json").read_text())
    assert "request" not in stored
    assert [item["backend"] for item in stored["requests"]] == [
        "z-image-turbo",
        "flux2-klein-4b",
    ]
    assert len(spawned) == 1


def test_unknown_job_id_is_not_found(env: dict[str, str]) -> None:
    with pytest.raises(TextureGenError) as caught:
        jobs.status("nope", env=env)
    assert caught.value.code == "texture.job_not_found"


def test_run_queue_runs_queued_jobs_oldest_first_and_leaves_both_succeeded(
    started: tuple[str, TextureRequest],
    spawned: list[list[str]],
    env: dict[str, str],
    out_root: Path,
    worker: Path,
    log: Path,
) -> None:
    first, _ = started
    second = jobs.start(
        TextureRequest(
            prompt="stone", backend="flux2-klein-4b", seeds=[2], resolution=256, name="s"
        ),
        env=env,
        facts=APPLE_SILICON_32GB,
        cwd=out_root.parent,
    )
    jobs.run_queue(
        out_root / ".jobs", env=env, facts=APPLE_SILICON_32GB, spawn=fake_spawn(worker, log)
    )
    assert jobs.status(first, env=env)["state"] == "succeeded"
    assert jobs.status(second, env=env)["state"] == "succeeded"
    starts = [e["backend"] for e in read_log(log) if e["event"] == "start"]
    assert starts == ["z-image-turbo", "flux2-klein-4b"]
    assert not (out_root / ".jobs" / "lock").exists()


def test_a_live_runner_holds_the_queue_so_a_second_runner_exits_without_running(
    started: tuple[str, TextureRequest],
    env: dict[str, str],
    out_root: Path,
    worker: Path,
    log: Path,
) -> None:
    lock = out_root / ".jobs" / "lock"
    lock.write_text(json.dumps({"pid": os.getpid()}))
    jobs.run_queue(
        out_root / ".jobs", env=env, facts=APPLE_SILICON_32GB, spawn=fake_spawn(worker, log)
    )
    job_id, _ = started
    assert read_log(log) == []
    assert jobs.status(job_id, env=env)["state"] == "queued"
    assert json.loads(lock.read_text())["pid"] == os.getpid()


def test_a_stale_lock_is_replaced_and_the_queue_drains(
    started: tuple[str, TextureRequest],
    env: dict[str, str],
    out_root: Path,
    worker: Path,
    log: Path,
) -> None:
    lock = out_root / ".jobs" / "lock"
    lock.write_text(json.dumps({"pid": 999999}))
    jobs.run_queue(
        out_root / ".jobs", env=env, facts=APPLE_SILICON_32GB, spawn=fake_spawn(worker, log)
    )
    job_id, _ = started
    assert jobs.status(job_id, env=env)["state"] == "succeeded"
    assert not lock.exists()


def test_run_job_records_success_and_the_single_result_shape(
    started: tuple[str, TextureRequest],
    env: dict[str, str],
    worker: Path,
    log: Path,
    out_root: Path,
) -> None:
    job_id, _ = started
    job_dir = out_root / ".jobs" / job_id
    final = jobs.run_job(job_dir, env=env, facts=APPLE_SILICON_32GB, spawn=fake_spawn(worker, log))

    assert final["state"] == "succeeded", final.get("error")
    assert final["completed"] == final["total"] == 1
    assert final["result"]["images"][0]["path"].endswith("z-image-turbo_1_256.png")
    stored = jobs.status(job_id, env=env)
    assert stored["state"] == "succeeded"
    assert not list(job_dir.glob(".status.json.*.tmp"))


def test_run_job_records_a_batch_as_results_with_counts_over_every_image(
    spawned: list[list[str]], env: dict[str, str], out_root: Path, worker: Path, log: Path
) -> None:
    requests = [
        TextureRequest(
            prompt="stone", backend="z-image-turbo", seeds=[1, 2], resolution=256, name="a"
        ),
        TextureRequest(prompt="wood", backend="z-image-turbo", seeds=[3], resolution=256, name="b"),
    ]
    job_id = jobs.start(requests, env=env, facts=APPLE_SILICON_32GB, cwd=out_root.parent)
    final = jobs.run_job(
        out_root / ".jobs" / job_id,
        env=env,
        facts=APPLE_SILICON_32GB,
        spawn=fake_spawn(worker, log),
    )
    assert final["state"] == "succeeded", final.get("error")
    assert final["completed"] == final["total"] == 3
    results = final["result"]["results"]
    assert [result["name"] for result in results] == ["a", "b"]
    assert [len(result["images"]) for result in results] == [2, 1]
    assert [e["event"] for e in read_log(log)] == ["start", "exit"]


def test_run_job_records_worker_failure(
    started: tuple[str, TextureRequest],
    env: dict[str, str],
    worker: Path,
    log: Path,
    out_root: Path,
) -> None:
    job_id, _ = started
    job_dir = out_root / ".jobs" / job_id
    final = jobs.run_job(
        job_dir, env=env, facts=APPLE_SILICON_32GB, spawn=fake_spawn(worker, log, fail=True)
    )
    assert final["state"] == "failed"
    assert final["error"]["code"] == "texture.worker_failed"
    assert final["error"]["remediation"]


def test_a_batch_with_a_shared_output_name_is_refused_before_a_job_exists(
    spawned: list[list[str]], env: dict[str, str], out_root: Path
) -> None:
    requests = [
        _request(),  # slugifies to burlap
        TextureRequest(
            prompt="stone", backend="z-image-turbo", seeds=[2], resolution=256, name="stone"
        ),
        TextureRequest(
            prompt="burlap", backend="flux2-klein-4b", seeds=[3], resolution=256, name="Burlap"
        ),
    ]
    with pytest.raises(TextureGenError) as caught:
        jobs.start(requests, env=env, facts=APPLE_SILICON_32GB, cwd=out_root.parent)
    assert caught.value.code == "texture.invalid_request"
    assert "requests 0, 2: output name 'burlap' is used more than once" in caught.value.message
    assert not (out_root / ".jobs").exists()
    assert spawned == []


def _mark_running(job_dir: Path, *, completed: int = 0, total: int = 1) -> None:
    """Leave a job as a runner that died mid-job would: ``running``, with no final state."""
    status = {"job_id": job_dir.name, "state": "running", "completed": completed, "total": total}
    (job_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")


def test_a_job_orphaned_by_a_dead_runner_is_marked_failed_and_the_queue_moves_on(
    spawned: list[list[str]], env: dict[str, str], out_root: Path, worker: Path, log: Path
) -> None:
    jobs_dir = out_root / ".jobs"
    orphan = jobs.start(_request(), env=env, facts=APPLE_SILICON_32GB, cwd=out_root.parent)
    second = jobs.start(
        TextureRequest(
            prompt="stone", backend="flux2-klein-4b", seeds=[2], resolution=256, name="stone"
        ),
        env=env,
        facts=APPLE_SILICON_32GB,
        cwd=out_root.parent,
    )
    third = jobs.start(
        TextureRequest(
            prompt="oak", backend="z-image-turbo", seeds=[3], resolution=256, name="oak"
        ),
        env=env,
        facts=APPLE_SILICON_32GB,
        cwd=out_root.parent,
    )
    _mark_running(jobs_dir / orphan)
    (jobs_dir / orphan / "runner.json").write_text(json.dumps({"pid": 999999}), encoding="utf-8")
    (jobs_dir / "lock").write_text(json.dumps({"pid": 999999}), encoding="utf-8")

    jobs.run_queue(jobs_dir, env=env, facts=APPLE_SILICON_32GB, spawn=fake_spawn(worker, log))

    failed = jobs.status(orphan, env=env)
    assert failed["state"] == "failed"
    assert failed["error"]["code"] == "texture.runner_exited"
    assert "PID 999999" in failed["error"]["message"]
    assert jobs.status(second, env=env)["state"] == "succeeded"
    assert jobs.status(third, env=env)["state"] == "succeeded"
    starts = [e["backend"] for e in read_log(log) if e["event"] == "start"]
    assert starts == ["flux2-klein-4b", "z-image-turbo"]
    assert not (jobs_dir / "lock").exists()


def test_a_running_job_whose_runner_is_alive_is_left_running(
    started: tuple[str, TextureRequest],
    env: dict[str, str],
    out_root: Path,
    worker: Path,
    log: Path,
) -> None:
    job_id, _ = started
    job_dir = out_root / ".jobs" / job_id
    _mark_running(job_dir)
    (job_dir / "runner.json").write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
    jobs.run_queue(
        out_root / ".jobs", env=env, facts=APPLE_SILICON_32GB, spawn=fake_spawn(worker, log)
    )
    assert jobs.status(job_id, env=env)["state"] == "running"
    assert read_log(log) == []


def test_a_running_job_with_no_runner_record_is_marked_failed_with_an_unknown_pid(
    started: tuple[str, TextureRequest],
    env: dict[str, str],
    out_root: Path,
    worker: Path,
    log: Path,
) -> None:
    job_id, _ = started
    _mark_running(out_root / ".jobs" / job_id, completed=1, total=2)
    jobs.run_queue(
        out_root / ".jobs", env=env, facts=APPLE_SILICON_32GB, spawn=fake_spawn(worker, log)
    )
    status = jobs.status(job_id, env=env)
    assert status["state"] == "failed"
    assert status["error"]["code"] == "texture.runner_exited"
    assert "PID unknown" in status["error"]["message"]
    assert (status["completed"], status["total"]) == (1, 2)
    assert str(out_root / ".jobs" / "runner.log") in status["error"]["remediation"]


def test_run_job_records_the_pid_of_the_process_that_ran_it(
    started: tuple[str, TextureRequest],
    env: dict[str, str],
    out_root: Path,
    worker: Path,
    log: Path,
) -> None:
    job_id, _ = started
    job_dir = out_root / ".jobs" / job_id
    jobs.run_job(job_dir, env=env, facts=APPLE_SILICON_32GB, spawn=fake_spawn(worker, log))
    assert json.loads((job_dir / "runner.json").read_text(encoding="utf-8")) == {"pid": os.getpid()}


def test_the_runner_writes_its_own_log_and_each_job_log_holds_only_its_job(
    spawned: list[list[str]],
    spawn_kwargs: list[dict[str, Any]],
    env: dict[str, str],
    out_root: Path,
    worker: Path,
    log: Path,
) -> None:
    jobs_dir = out_root / ".jobs"
    first = jobs.start(_request(), env=env, facts=APPLE_SILICON_32GB, cwd=out_root.parent)
    second = jobs.start(
        TextureRequest(
            prompt="stone", backend="flux2-klein-4b", seeds=[2], resolution=256, name="stone"
        ),
        env=env,
        facts=APPLE_SILICON_32GB,
        cwd=out_root.parent,
    )
    assert Path(spawn_kwargs[0]["stdout"].name) == jobs_dir / "runner.log"
    assert Path(spawn_kwargs[0]["stderr"].name) == jobs_dir / "runner.log"

    jobs.run_queue(jobs_dir, env=env, facts=APPLE_SILICON_32GB, spawn=fake_spawn(worker, log))

    runner_log = (jobs_dir / "runner.log").read_text(encoding="utf-8")
    assert first in runner_log and second in runner_log
    first_log = (jobs_dir / first / "job.log").read_text(encoding="utf-8")
    second_log = (jobs_dir / second / "job.log").read_text(encoding="utf-8")
    assert first in first_log and second not in first_log
    assert second in second_log and first not in second_log


def test_a_crashed_job_writes_its_traceback_to_its_own_job_log(
    started: tuple[str, TextureRequest], env: dict[str, str], out_root: Path
) -> None:
    job_id, _ = started
    job_dir = out_root / ".jobs" / job_id

    def crash(batch_file: Path) -> subprocess.CompletedProcess[str]:
        raise RuntimeError("worker exploded")

    final = jobs.run_job(job_dir, env=env, facts=APPLE_SILICON_32GB, spawn=crash)
    assert final["error"]["code"] == "texture.job_crashed"
    job_log = (job_dir / "job.log").read_text(encoding="utf-8")
    assert "RuntimeError: worker exploded" in job_log
    assert f"job {job_id} failed" in job_log
