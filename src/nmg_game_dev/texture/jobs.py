"""Background texture jobs: start, poll, and run detached (#7 FR14, FR16, AC17, AC20).

A job lives in ``<output_root>/.jobs/<job_id>/`` with ``request.json`` and ``status.json``.
``status.json`` is rewritten atomically (temp file, then rename) after every batch and at the end.
One job runs at a time: a PID lock at ``<output_root>/.jobs/lock`` names the running job. A lock
whose PID is no longer alive is stale and gets replaced.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from nmg_game_dev.texture import generate
from nmg_game_dev.texture.batch import Spawn, default_spawn
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


def _job_running_error(job_id: str) -> TextureGenError:
    return TextureGenError(
        "texture.job_running",
        f"Texture job {job_id} is still running.",
        f"Wait for job {job_id} to finish (poll get_texture_job or `python -m nmg_game_dev.texture "
        "status`), then start the new job.",
    )


def _claim_lock(lock: Path, job_id: str, pid: int) -> None:
    """Take the lock for ``pid``. A live holder raises ``texture.job_running``; stale locks go."""
    lock.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            holder = _read_lock(lock) or {}
            holder_pid = int(holder.get("pid", 0) or 0)
            if holder_pid and _pid_alive(holder_pid):
                raise _job_running_error(str(holder.get("job_id", "unknown"))) from None
            lock.unlink(missing_ok=True)
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"job_id": job_id, "pid": pid}, handle)
        return
    raise _job_running_error("unknown")


def _release_lock(lock: Path, job_id: str) -> None:
    holder = _read_lock(lock)
    if holder is not None and holder.get("job_id") == job_id:
        lock.unlink(missing_ok=True)


def _write_status(job_dir: Path, data: Mapping[str, Any]) -> None:
    _write_json_atomic(job_dir / STATUS_NAME, data)


def start(
    request: generate.TextureRequest,
    *,
    registry: Mapping[str, BackendSpec] = REGISTRY,
    env: Mapping[str, str] | None = None,
    facts: HardwareFacts | None = None,
    cwd: Path | None = None,
) -> str:
    """Validate ``request``, start a detached job for it, and return the job id at once."""
    env_map = dict(os.environ) if env is None else dict(env)
    host = probe() if facts is None else facts
    work_dir = cwd or Path.cwd()
    generate.validate_request(request)
    root = output_root(env_map, work_dir)
    jobs = jobs_root(root)
    lock = jobs / LOCK_NAME
    job_id = uuid.uuid4().hex[:12]
    _claim_lock(lock, job_id, os.getpid())
    try:
        selected, _skipped = generate.select_backends(
            request.backend,
            registry,
            models_dir(env_map),
            host,
            reserve_gb(env_map),
        )
        total = generate.plan_total(request, selected)
        job_dir = jobs / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        _write_json_atomic(
            job_dir / REQUEST_NAME,
            {"request": generate.request_as_json(request), "output_root": str(root)},
        )
        _write_status(
            job_dir,
            {"job_id": job_id, "state": "queued", "completed": 0, "total": total},
        )
        log = (job_dir / LOG_NAME).open("ab")
        try:
            proc = subprocess.Popen(
                [sys.executable, "-m", "nmg_game_dev.texture", "run-job", str(job_dir)],
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                start_new_session=True,
                cwd=str(work_dir),
                env=env_map,
            )
        finally:
            log.close()
        _write_json_atomic(lock, {"job_id": job_id, "pid": proc.pid})
    except BaseException:
        lock.unlink(missing_ok=True)
        raise
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


def run_job(
    job_dir: Path,
    *,
    env: Mapping[str, str] | None = None,
    facts: HardwareFacts | None = None,
    spawn: Spawn = default_spawn,
    registry: Mapping[str, BackendSpec] = REGISTRY,
) -> dict[str, Any]:
    """Run the job in ``job_dir`` to completion and record its final status (detached child)."""
    env_map = dict(os.environ) if env is None else dict(env)
    job_id = job_dir.name
    lock = job_dir.parent / LOCK_NAME
    stored = json.loads((job_dir / REQUEST_NAME).read_text(encoding="utf-8"))
    request = generate.request_from_json(stored["request"])
    root = Path(str(stored["output_root"]))
    total = 0
    try:
        total = generate.plan_total(
            request,
            generate.select_backends(
                request.backend,
                registry,
                models_dir(env_map),
                facts or probe(),
                reserve_gb(env_map),
            )[0],
        )
    except TextureGenError:
        total = 0

    def progress(done: int, count: int) -> None:
        _write_status(
            job_dir,
            {"job_id": job_id, "state": "running", "completed": done, "total": count},
        )

    try:
        progress(0, total)
        result = generate.run(
            request,
            registry=registry,
            env=env_map,
            facts=facts,
            spawn=spawn,
            output_root_override=root,
            on_progress=progress,
        )
        final: dict[str, Any] = {
            "job_id": job_id,
            "state": "succeeded",
            "completed": total,
            "total": total,
            "result": result.as_json(),
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
        final = {
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
    finally:
        _release_lock(lock, job_id)
    _write_status(job_dir, final)
    return final
