"""Finalize job lifecycle: start, status, wait, and the detached ``run-job`` body (#69).

A job lives in ``<cache_root>/jobs/<job_id>/``::

    request.json      the FinalizeRequest
    job.json          {"job_id", "steps", "force"}
    status.json       {"job_id", "state", "step", "progress", "message", "steps", "result"?,
                       "error"?, "pid"}
    checkpoint.blend, <step>.json, <step>.blend, blender-<step>.log, hash.json, ...

``state`` is ``queued``, ``running``, ``succeeded``, or ``failed``.  One live job runs per cache
root: ``jobs/lock`` holds the PID of the job process.  A live lock refuses a new job with
``finalize.job_running``, and a stale lock is cleared.  A job whose process has disappeared before
it reached a terminal state is reported as ``failed`` with ``finalize.job_crashed``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

from nmg_game_dev.design import backlog as design_backlog

from .blender_proc import StepRunner, SubprocessStepRunner
from .cache import ArtifactCache, default_cache_root
from .engine import FinalizeClients, FinalizeSessionChangedError, execute
from .errors import PipelineError
from .request import FinalizeRequest
from .result import FinalizeResult
from .steps import STEP_ORDER

Launcher = Callable[[Path], int]

TERMINAL_STATES: Final = frozenset({"succeeded", "failed"})
_LOCK_NAME: Final = "lock"
_POLL_S: Final = 0.5


def jobs_root(cache_root: Path | None = None) -> Path:
    """Return the ``jobs`` directory under ``cache_root`` (default cache root when ``None``)."""
    root = cache_root if cache_root is not None else default_cache_root()
    return root / "jobs"


def start(
    request: FinalizeRequest,
    steps: tuple[str, ...] | list[str] = STEP_ORDER,
    *,
    force: bool = False,
    cache_root: Path | None = None,
    launcher: Launcher | None = None,
) -> str:
    """Create a job, launch its ``run-job`` process, and return its job id.

    Raises ``finalize.job_running`` when another live job holds the cache root.
    """
    root = jobs_root(cache_root)
    root.mkdir(parents=True, exist_ok=True)
    _acquire_lock(root)

    job_id = f"{time.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"
    job_dir = root / job_id
    try:
        job_dir.mkdir(parents=True)
        _write_json(job_dir / "request.json", request.to_json_dict())
        _write_json(job_dir / "job.json", {"job_id": job_id, "steps": list(steps), "force": force})
        _write_json(job_dir / "status.json", _status(job_id, "queued", pid=None))
        pid = (launcher or _spawn_run_job)(job_dir)
    except BaseException:
        _release_lock(root, pid=None)
        raise

    _write_text(root / _LOCK_NAME, str(pid))
    status = _read_status_file(job_dir, job_id)
    if status.get("state") in TERMINAL_STATES:
        # The job finished before the lock was written, so its own release already ran.
        _release_lock(root, pid=pid)
    else:
        status["pid"] = pid
        _write_json(job_dir / "status.json", status)
    return job_id


def status(job_id: str, *, cache_root: Path | None = None) -> dict[str, Any]:
    """Return the job's status.  A job whose process is gone is marked ``failed`` (crashed)."""
    job_dir = _job_dir(job_id, cache_root)
    current = _read_status_file(job_dir, job_id)
    if current.get("state") in TERMINAL_STATES:
        return current
    pid = current.get("pid")
    if not isinstance(pid, int) or _alive(pid):
        return current

    last_step = current.get("step")
    current["state"] = "failed"
    current["error"] = {
        "code": "finalize.job_crashed",
        "message": f"The background job exited before finishing (last step: {last_step}).",
        "remediation": f"Read {job_dir} (blender-*.log) for the output, then rerun the job.",
        "stage": str(last_step or "finalize"),
    }
    _write_json(job_dir / "status.json", current)
    _release_lock(jobs_root(cache_root), pid=pid)
    return current


def wait(
    job_id: str,
    *,
    timeout_s: float,
    cache_root: Path | None = None,
    poll_s: float = _POLL_S,
) -> dict[str, Any]:
    """Poll until the job is terminal or ``timeout_s`` elapses, and return the last status."""
    deadline = time.monotonic() + max(timeout_s, 0.0)
    current = status(job_id, cache_root=cache_root)
    while current.get("state") not in TERMINAL_STATES and time.monotonic() < deadline:
        time.sleep(poll_s)
        current = status(job_id, cache_root=cache_root)
    return current


def run_job(
    job_dir: Path,
    *,
    clients: FinalizeClients | None = None,
    runner: StepRunner | None = None,
) -> dict[str, Any]:
    """Execute the job in ``job_dir`` and write its terminal status.  This is the detached body.

    The cache root is the job directory's grandparent, so a job always uses the cache it was
    started under.
    """
    cache = ArtifactCache(job_dir.parent.parent)
    request = FinalizeRequest.model_validate_json((job_dir / "request.json").read_text("utf-8"))
    job = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
    job_id = str(job["job_id"])
    steps = tuple(str(step) for step in job["steps"])
    force = bool(job["force"])

    current = _read_status_file(job_dir, job_id)
    current.update(state="running", pid=os.getpid(), progress=0.0, message="starting")
    _write_json(job_dir / "status.json", current)

    def on_progress(event: dict[str, Any]) -> None:
        current.update(
            state="running",
            step=event.get("step"),
            progress=event.get("progress"),
            message=event.get("message", ""),
        )
        _write_json(job_dir / "status.json", current)

    def on_step(result: Any) -> None:
        steps_status = current.setdefault("steps", {})
        steps_status[result.step] = result.model_dump(mode="json")
        _write_json(job_dir / "status.json", current)

    try:
        result = execute(
            request,
            steps,
            force=force,
            cache=cache,
            job_dir=job_dir,
            runner=runner or SubprocessStepRunner(),
            clients=clients,
            progress=on_progress,
            on_step=on_step,
        )
    except FinalizeSessionChangedError as error:
        current.update(
            state="failed", error=_error_dict(error), result=error.result.model_dump(mode="json")
        )
    except PipelineError as error:
        current.update(state="failed", error=_error_dict(error))
    except Exception as error:
        # Every failure must reach status.json, so this catch-all is deliberate.
        current.update(
            state="failed",
            error={
                "code": "finalize.internal_error",
                "message": f"Unexpected error: {error}",
                "remediation": "Report this as a bug with the job's status.json.",
                "stage": str(current.get("step") or "finalize"),
            },
        )
    else:
        result = _mark_backlog(request, steps, result)
        current.update(state="succeeded", result=result.model_dump(mode="json"), progress=1.0)
    finally:
        _write_json(job_dir / "status.json", current)
        _release_lock(job_dir.parent, pid=os.getpid())
    return current


def _mark_backlog(
    request: FinalizeRequest, steps: tuple[str, ...], result: FinalizeResult
) -> FinalizeResult:
    """Mark the request's design-backlog entry ``finalized`` after a full successful run (#112).

    Only a run of every step marks the entry, so ``run_finalize_step`` never does.  A failed
    backlog write adds a ``design.backlog_update_failed`` warning and does not fail the job.
    """
    if request.backlog_path is None or steps != STEP_ORDER:
        return result
    try:
        design_backlog.mark(request.backlog_path, request.collection, "finalized")
    except (OSError, ValueError) as error:
        warning = {
            "code": "design.backlog_update_failed",
            "message": f"{request.collection} was finalized, but its design backlog entry was not "
            f"marked finalized in {request.backlog_path}: {error}",
            "remediation": "Check that docs/design/backlog.json is writable, then run "
            "`python -m nmg_game_dev.design sync`.",
        }
        return result.model_copy(update={"warnings": [*result.warnings, warning]})
    return result


#: Child processes this interpreter started.  Kept so a finished child is reaped and not mistaken
#: for a live one (a zombie still answers ``os.kill(pid, 0)``).
_CHILDREN: dict[int, subprocess.Popen[bytes]] = {}


def _spawn_run_job(job_dir: Path) -> int:
    """Start ``python -m nmg_game_dev.finalize run-job <job_dir>`` detached and return its PID."""
    log = (job_dir / "job.log").open("w", encoding="utf-8")
    process = subprocess.Popen(
        [sys.executable, "-m", "nmg_game_dev.finalize", "run-job", str(job_dir)],
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        close_fds=True,
    )
    log.close()
    _CHILDREN[process.pid] = process
    return process.pid


def _acquire_lock(root: Path) -> None:
    lock = root / _LOCK_NAME
    if lock.exists():
        pid = _read_pid(lock)
        if pid is not None and _alive(pid):
            raise PipelineError(
                code="finalize.job_running",
                message=f"Another finalize job (PID {pid}) is running for this cache",
                remediation="Wait for it to finish, check it with get_finalize_job, or stop its "
                "process, then retry.",
                stage="finalize",
            )
        lock.unlink(missing_ok=True)


def _release_lock(root: Path, *, pid: int | None) -> None:
    lock = root / _LOCK_NAME
    if not lock.exists():
        return
    owner = _read_pid(lock)
    if pid is None or owner is None or owner == pid:
        lock.unlink(missing_ok=True)


def _read_pid(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _alive(pid: int) -> bool:
    child = _CHILDREN.get(pid)
    if child is not None:
        if child.poll() is None:
            return True
        _CHILDREN.pop(pid, None)
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _job_dir(job_id: str, cache_root: Path | None) -> Path:
    if not job_id or "/" in job_id or job_id.startswith("."):
        raise _not_found(job_id)
    job_dir = jobs_root(cache_root) / job_id
    if not (job_dir / "status.json").is_file():
        raise _not_found(job_id)
    return job_dir


def _not_found(job_id: str) -> PipelineError:
    return PipelineError(
        code="finalize.job_not_found",
        message=f"No finalize job with id {job_id!r}",
        remediation="Check the job id returned by finalize_asset or run_finalize_step.",
        stage="finalize",
    )


def _status(job_id: str, state: str, *, pid: int | None) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "state": state,
        "step": None,
        "progress": 0.0,
        "message": "queued",
        "steps": {},
        "pid": pid,
    }


def _read_status_file(job_dir: Path, job_id: str) -> dict[str, Any]:
    try:
        data: dict[str, Any] = json.loads((job_dir / "status.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _status(job_id, "failed", pid=None)
    return data


def _error_dict(error: PipelineError) -> dict[str, str]:
    return {
        "code": error.code,
        "message": error.message,
        "remediation": error.remediation,
        "stage": error.stage,
    }


def _write_json(path: Path, data: object) -> None:
    _write_text(path, json.dumps(data, indent=2, sort_keys=True, default=str) + "\n")


def _write_text(path: Path, text: str) -> None:
    staged = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    staged.write_text(text, encoding="utf-8")
    os.replace(staged, path)
