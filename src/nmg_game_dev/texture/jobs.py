"""Background texture jobs: queue, start, poll, and run detached (#7 FR14, FR16, AC17, AC20; #143
FR5).

A job lives in ``<output_root>/.jobs/<job_id>/`` with ``request.json`` and ``status.json``.
``request.json`` holds one ``request`` (or a ``requests`` list for a batch), the ``output_root``,
and
the ``submitted_ns`` that orders the queue. ``status.json`` is rewritten atomically (temp file, then
rename) as the job runs and when it ends.

``start`` validates the request or batch, writes the job as ``queued``, and spawns a detached
``run-queue`` runner. The runner takes the PID lock at ``<output_root>/.jobs/lock``, runs queued
jobs
one at a time in submission order, and exits when none remain. A lock whose PID is no longer alive
is stale and is replaced. A busy queue never refuses a start: the new job waits its turn.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from nmg_game_dev.texture import generate
from nmg_game_dev.texture.batch import Spawn
from nmg_game_dev.texture.deps import DepsProbe, require_dependencies
from nmg_game_dev.texture.errors import TextureGenError
from nmg_game_dev.texture.hardware import HardwareFacts, probe, reserve_gb
from nmg_game_dev.texture.paths import models_dir, output_root
from nmg_game_dev.texture.registry import REGISTRY, BackendSpec

JOBS_DIR_NAME = ".jobs"
LOCK_NAME = "lock"
STATUS_NAME = "status.json"
REQUEST_NAME = "request.json"
LOG_NAME = "job.log"
STATES = ("queued", "running", "succeeded", "failed")
# An unreadable lock this young is a runner still writing it, so it counts as held.
LOCK_WRITE_GRACE_SECONDS = 10.0


def jobs_root(root: Path) -> Path:
    return root / JOBS_DIR_NAME


def _write_json_atomic(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(dict(data), handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _read_lock(lock: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(lock.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _lock_is_live(lock: Path) -> bool:
    """Whether the lock belongs to a runner that is still alive (an unreadable, fresh lock
    counts)."""
    holder = _read_lock(lock)
    if holder is None:
        try:
            age = time.time() - lock.stat().st_mtime
        except OSError:
            return False
        return age < LOCK_WRITE_GRACE_SECONDS
    pid = holder.get("pid")
    return isinstance(pid, int) and _pid_alive(pid)


def _claim_lock(lock: Path, pid: int) -> bool:
    """Take the queue lock for ``pid``. Returns False while a live runner holds it; stale locks
    go."""
    lock.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if _lock_is_live(lock):
                return False
            lock.unlink(missing_ok=True)
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"pid": pid}, handle)
        return True
    return False


def _release_lock(lock: Path, pid: int) -> None:
    holder = _read_lock(lock)
    if holder is not None and holder.get("pid") == pid:
        lock.unlink(missing_ok=True)


def _write_status(job_dir: Path, data: Mapping[str, Any]) -> None:
    _write_json_atomic(job_dir / STATUS_NAME, data)


def _total_images(
    requests: Sequence[generate.TextureRequest],
    registry: Mapping[str, BackendSpec],
    env_map: Mapping[str, str],
    facts: HardwareFacts,
    deps_probe: DepsProbe | None,
) -> int:
    """How many images the requests will produce across every backend they select."""
    root = models_dir(env_map)
    reserve = reserve_gb(env_map)
    total = 0
    for request in requests:
        selected, _skipped = generate.select_backends(
            request.backend, registry, root, facts, reserve, deps_probe
        )
        total += generate.plan_total(request, selected)
    return total


def start(
    request_or_requests: generate.TextureRequest | Sequence[generate.TextureRequest],
    *,
    registry: Mapping[str, BackendSpec] = REGISTRY,
    env: Mapping[str, str] | None = None,
    facts: HardwareFacts | None = None,
    cwd: Path | None = None,
    deps_probe: DepsProbe | None = None,
) -> str:
    """Validate a request or batch, queue it, start the queue runner, and return the job id at
    once."""
    env_map = dict(os.environ) if env is None else dict(env)
    host = probe() if facts is None else facts
    work_dir = cwd or Path.cwd()
    payload: dict[str, Any]
    requests: tuple[generate.TextureRequest, ...]
    if isinstance(request_or_requests, generate.TextureRequest):
        generate.validate_request(request_or_requests)
        requests = (request_or_requests,)
        payload = {"request": generate.request_as_json(request_or_requests)}
    else:
        generate.validate_batch(request_or_requests)
        requests = tuple(request_or_requests)
        payload = {"requests": [generate.request_as_json(item) for item in requests]}
    root = output_root(env_map, work_dir)
    total = _total_images(requests, registry, env_map, host, deps_probe)
    require_dependencies(deps_probe)

    jobs = jobs_root(root)
    job_id = uuid.uuid4().hex[:12]
    job_dir = jobs / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(
        job_dir / REQUEST_NAME,
        {**payload, "output_root": str(root), "submitted_ns": time.time_ns()},
    )
    _write_status(
        job_dir,
        {"job_id": job_id, "state": "queued", "completed": 0, "total": total},
    )
    log = (job_dir / LOG_NAME).open("ab")
    try:
        subprocess.Popen(
            [sys.executable, "-m", "nmg_game_dev.texture", "run-queue", str(jobs)],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
            cwd=str(work_dir),
            env=env_map,
        )
    except BaseException:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    finally:
        log.close()
    return job_id


def status(
    job_id: str, *, env: Mapping[str, str] | None = None, cwd: Path | None = None
) -> dict[str, Any]:
    """Return the status document of ``job_id``. Unknown ids raise ``texture.job_not_found``."""
    env_map = dict(os.environ) if env is None else dict(env)
    root = output_root(env_map, cwd or Path.cwd())
    path = jobs_root(root) / job_id / STATUS_NAME
    if "/" in job_id or job_id in ("", ".", "..") or not path.is_file():
        raise TextureGenError(
            "texture.job_not_found",
            f"No texture job {job_id!r} under {root}.",
            "Use the job_id returned by generate_textures, or start a new job.",
        )
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def _next_queued(jobs: Path) -> Path | None:
    """The oldest queued job directory by ``(submitted_ns, job_id)``, or None when none is
    queued."""
    if not jobs.is_dir():
        return None
    queued: list[tuple[int, str, Path]] = []
    for job_dir in jobs.iterdir():
        if not job_dir.is_dir():
            continue
        try:
            state = json.loads((job_dir / STATUS_NAME).read_text(encoding="utf-8")).get("state")
            submitted = int(
                json.loads((job_dir / REQUEST_NAME).read_text(encoding="utf-8"))["submitted_ns"]
            )
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue
        if state == "queued":
            queued.append((submitted, job_dir.name, job_dir))
    return min(queued)[2] if queued else None


def run_queue(
    jobs: Path,
    *,
    env: Mapping[str, str] | None = None,
    facts: HardwareFacts | None = None,
    spawn: Spawn | None = None,
    registry: Mapping[str, BackendSpec] = REGISTRY,
) -> None:
    """Run queued jobs one at a time, oldest submission first, under the PID lock (#143 FR5).

    While another live runner holds the lock this returns at once, because that runner picks the
    queued job up. The lock is released and the queue re-checked, so a job queued during the release
    is not left waiting.
    """
    lock = jobs / LOCK_NAME
    pid = os.getpid()
    while _claim_lock(lock, pid):
        try:
            while (job_dir := _next_queued(jobs)) is not None:
                run_job(job_dir, env=env, facts=facts, spawn=spawn, registry=registry)
        finally:
            _release_lock(lock, pid)
        if _next_queued(jobs) is None:
            return


def _requests_of(stored: Mapping[str, Any]) -> tuple[generate.TextureRequest, ...]:
    """The job's requests: its single ``request``, or every entry of a ``requests`` batch."""
    if "requests" in stored:
        return tuple(generate.request_from_json(item) for item in stored["requests"])
    return (generate.request_from_json(stored["request"]),)


def _crash_status(job_dir: Path, job_id: str, total: int, error: Exception) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "state": "failed",
        "completed": 0,
        "total": total,
        "error": {
            "code": "texture.job_crashed",
            "message": f"{type(error).__name__}: {error}",
            "remediation": f"Read {job_dir / LOG_NAME} for the traceback, then start over.",
        },
    }


def run_job(
    job_dir: Path,
    *,
    env: Mapping[str, str] | None = None,
    facts: HardwareFacts | None = None,
    spawn: Spawn | None = None,
    registry: Mapping[str, BackendSpec] = REGISTRY,
) -> dict[str, Any]:
    """Run the job in ``job_dir`` to completion and record its final status (queue runner or
    detached child).

    A batch job's succeeded result is ``{"results": [...]}``. Counts cover every image in the job.
    """
    env_map = dict(os.environ) if env is None else dict(env)
    job_id = job_dir.name
    try:
        stored = json.loads((job_dir / REQUEST_NAME).read_text(encoding="utf-8"))
        is_batch = "requests" in stored
        requests = _requests_of(stored)
        root = Path(str(stored["output_root"]))
    except (OSError, ValueError, KeyError, TypeError) as error:
        final = _crash_status(job_dir, job_id, 0, error)
        _write_status(job_dir, final)
        return final

    try:
        total = _total_images(requests, registry, env_map, facts or probe(), None)
    except TextureGenError:
        total = 0

    def progress(done: int, count: int) -> None:
        _write_status(
            job_dir,
            {"job_id": job_id, "state": "running", "completed": done, "total": count},
        )

    try:
        progress(0, total)
        result: dict[str, Any]
        if is_batch:
            result = generate.run_batch(
                requests,
                registry=registry,
                env=env_map,
                facts=facts,
                spawn=spawn,
                output_root_override=root,
                on_progress=progress,
            ).as_json()
        else:
            result = generate.run(
                requests[0],
                registry=registry,
                env=env_map,
                facts=facts,
                spawn=spawn,
                output_root_override=root,
                on_progress=progress,
            ).as_json()
        final = {
            "job_id": job_id,
            "state": "succeeded",
            "completed": total,
            "total": total,
            "result": result,
        }
    except TextureGenError as error:
        final = {
            "job_id": job_id,
            "state": "failed",
            "completed": 0,
            "total": total,
            "error": {
                "code": error.code,
                "message": error.message,
                "remediation": error.remediation,
            },
        }
    except Exception as error:  # noqa: BLE001 - a crashed job must still report a final state
        final = _crash_status(job_dir, job_id, total, error)
    _write_status(job_dir, final)
    return final
