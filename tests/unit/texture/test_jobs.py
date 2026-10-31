"""Background jobs: start, the one-job lock, stale locks, status, and the detached run (#7 FR14,
AC17, AC20)."""

from __future__ import annotations

import json
import os
import subprocess
import types
from pathlib import Path

import pytest

from nmg_game_dev.texture import jobs
from nmg_game_dev.texture.errors import TextureGenError
from nmg_game_dev.texture.generate import TextureRequest, request_as_json
from nmg_game_dev.texture.registry import REGISTRY
from tests.texture_fakes import APPLE_SILICON_32GB, fake_spawn


class _FakeProc:
    # The live test process stands in for the detached job, so its lock reads as held.
    pid = os.getpid()


def _fake_popen(monkeypatch: pytest.MonkeyPatch) -> None:
    shim = types.SimpleNamespace(Popen=lambda *a, **k: _FakeProc(), DEVNULL=subprocess.DEVNULL)
    monkeypatch.setattr(jobs, "subprocess", shim)


@pytest.fixture
def started(
    monkeypatch: pytest.MonkeyPatch, env: dict[str, str], out_root: Path
) -> tuple[str, TextureRequest]:
    _fake_popen(monkeypatch)
    request = TextureRequest(
        prompt="burlap", backend="z-image-turbo", seeds=[1], resolution=256, name="burlap"
    )
    job_id = jobs.start(request, env=env, facts=APPLE_SILICON_32GB, cwd=out_root.parent)
    return job_id, request


def test_start_returns_a_queued_job_with_a_lock(
    started: tuple[str, TextureRequest], out_root: Path
) -> None:
    job_id, _ = started
    status = jobs.status(job_id, env={"NMG_GAME_DEV_TEXTURE_DIR": str(out_root)})
    assert status["state"] == "queued" and status["total"] == 1
    lock = json.loads((out_root / ".jobs" / "lock").read_text())
    assert lock == {"job_id": job_id, "pid": os.getpid()}


def test_second_start_while_a_job_is_alive_names_the_running_job(
    started: tuple[str, TextureRequest],
    env: dict[str, str],
    out_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id, request = started
    with pytest.raises(TextureGenError) as caught:
        jobs.start(request, env=env, facts=APPLE_SILICON_32GB, cwd=out_root.parent)
    assert caught.value.code == "texture.job_running"
    assert job_id in caught.value.message


def test_stale_lock_is_replaced(
    monkeypatch: pytest.MonkeyPatch, env: dict[str, str], out_root: Path
) -> None:
    lock = out_root / ".jobs" / "lock"
    lock.parent.mkdir(parents=True)
    lock.write_text(json.dumps({"job_id": "gone", "pid": 999999}))
    _fake_popen(monkeypatch)
    request = TextureRequest(prompt="burlap", backend="z-image-turbo", seeds=[1], resolution=256)
    job_id = jobs.start(request, env=env, facts=APPLE_SILICON_32GB, cwd=out_root.parent)
    assert json.loads(lock.read_text())["job_id"] == job_id


def test_unknown_job_id_is_not_found(env: dict[str, str], out_root: Path) -> None:
    with pytest.raises(TextureGenError) as caught:
        jobs.status("nope", env=env)
    assert caught.value.code == "texture.job_not_found"


def test_invalid_request_is_refused_before_a_job_exists(
    env: dict[str, str], out_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_popen(monkeypatch)
    with pytest.raises(TextureGenError):
        jobs.start(
            TextureRequest(prompt=""), env=env, facts=APPLE_SILICON_32GB, cwd=out_root.parent
        )
    assert not (out_root / ".jobs").exists()


def test_run_job_records_success_and_releases_the_lock(
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
    assert not (out_root / ".jobs" / "lock").exists()
    stored = jobs.status(job_id, env=env)
    assert stored["state"] == "succeeded"
    assert not list(job_dir.glob(".status.json.*.tmp"))


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


def test_request_json_is_what_the_job_reads(
    started: tuple[str, TextureRequest], out_root: Path
) -> None:
    job_id, request = started
    stored = json.loads((out_root / ".jobs" / job_id / "request.json").read_text())
    assert stored["request"] == request_as_json(request)
    assert stored["output_root"] == str(out_root)
    assert REGISTRY["z-image-turbo"].id in stored["request"]["backend"]
