"""Finalize job lifecycle: start, status, wait, batches, and the detached ``run-job`` body.

Single jobs and batches share this lifecycle (#69, #149).

A job lives in ``<cache_root>/jobs/<job_id>/``::

    request.json      the FinalizeRequest (single-collection jobs)
    job.json          {"job_id", "kind", "steps", "force", "wait_for_lock", "lock_wait_s", ...}
                       (batches add "items" and "fail_fast")
    status.json       {"job_id", "state", "step", "progress", "message", "steps", "batch"?,
                       "result"?, "error"?, "pid"}
    items/<index>-<collection>/   one batch item's files (batch jobs)
    checkpoint.blend, <step>.json, <step>.blend, blender-<step>.log, hash.json, ...

``state`` is ``queued``, ``waiting``, ``running``, ``succeeded``, or ``failed``.  One live job runs
per cache root.  ``jobs/lock`` holds JSON ``{"pid", "job_id"}`` for the job that owns it; a legacy
plain-PID lock is still read.  A claim is atomic (``O_CREAT | O_EXCL``), and a lock whose PID is
gone is stale and is removed on every attempt.

Without ``wait_for_lock``, a live holder refuses a new job with ``finalize.job_running``.  With it,
the job starts ``waiting`` and its own ``run-job`` process polls for the lock, with jitter, until it
claims the lock or ``lock_wait_s`` expires.  A batch is one job that claims the lock once, runs its
items in order under that lock, and keeps going past a failed item unless ``fail_fast`` is set.

A job whose process has disappeared before it reached a terminal state is reported as ``failed``
with ``finalize.job_crashed``.
"""

from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import time
import uuid
from collections.abc import Callable, Sequence
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
Sleep = Callable[[float], None]
Clock = Callable[[], float]

TERMINAL_STATES: Final = frozenset({"succeeded", "failed"})
_ITEM_DONE_STATES: Final = frozenset({"succeeded", "failed", "skipped"})
_LOCK_NAME: Final = "lock"
_POLL_S: Final = 0.5
_LOCK_POLL_MIN_S: Final = 2.0
_LOCK_POLL_MAX_S: Final = 5.0
_LOCK_WRITE_GRACE_S: Final = 5.0
_CLAIM_ATTEMPTS: Final = 5
_BATCH_KIND: Final = "batch"


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
    wait_for_lock: bool = False,
    lock_wait_s: float | None = None,
) -> str:
    """Create a single-collection job, launch its ``run-job`` process, and return its job id.

    Raises ``finalize.job_running`` when another live job holds the cache root and
    ``wait_for_lock`` is false.  With ``wait_for_lock``, the job waits for the lock, for at most
    ``lock_wait_s`` seconds when that is given.
    """
    return _submit(
        {"kind": "single", "steps": list(steps), "force": force},
        request_json=request.to_json_dict(),
        cache_root=cache_root,
        launcher=launcher,
        wait_for_lock=wait_for_lock,
        lock_wait_s=lock_wait_s,
    )


def start_batch(
    requests: Sequence[FinalizeRequest],
    steps: tuple[str, ...] | list[str] = STEP_ORDER,
    *,
    force: bool = False,
    fail_fast: bool = False,
    cache_root: Path | None = None,
    launcher: Launcher | None = None,
    wait_for_lock: bool = False,
    lock_wait_s: float | None = None,
) -> str:
    """Create one job that finalizes ``requests`` in order and return its job id.

    The requests must already be validated (``finalize.invalid_batch`` is the service's check).
    The batch holds the cache lock from start to end.
    """
    if not requests:
        raise PipelineError(
            code="finalize.invalid_batch",
            message="The batch has no collections to finalize",
            remediation="Pass at least one collection or batch entry.",
            stage="finalize",
        )
    items = [
        {"index": index, "collection": request.collection, "state": "pending", "error": None}
        for index, request in enumerate(requests)
    ]
    batch = {
        "total": len(items),
        "completed": 0,
        "current": None,
        "current_index": None,
        "items": items,
    }
    return _submit(
        {
            "kind": _BATCH_KIND,
            "steps": list(steps),
            "force": force,
            "fail_fast": fail_fast,
            "items": [request.to_json_dict() for request in requests],
        },
        request_json=None,
        batch=batch,
        cache_root=cache_root,
        launcher=launcher,
        wait_for_lock=wait_for_lock,
        lock_wait_s=lock_wait_s,
    )


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
    detail = f" (last step: {last_step})" if last_step else ""
    current["state"] = "failed"
    current["error"] = {
        "code": "finalize.job_crashed",
        "message": f"The background job exited before finishing{detail}.",
        "remediation": f"Read {job_dir} (blender-*.log) for the output, then rerun the job.",
        "stage": str(last_step or "finalize"),
    }
    _write_json(job_dir / "status.json", current)
    _release_lock(jobs_root(cache_root), job_id=job_id)
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
    sleep: Sleep = time.sleep,
    clock: Clock = time.monotonic,
) -> dict[str, Any]:
    """Execute the job in ``job_dir`` and write its terminal status.  This is the detached body.

    A ``wait_for_lock`` job first waits for the cache lock.  The cache root is the job directory's
    grandparent, so a job always uses the cache it was started under.
    """
    root = job_dir.parent
    cache = ArtifactCache(root.parent)
    job = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
    job_id = str(job["job_id"])
    steps = tuple(str(step) for step in job["steps"])
    force = bool(job["force"])
    current = _read_status_file(job_dir, job_id)

    try:
        if job.get("wait_for_lock"):
            limit = job.get("lock_wait_s")
            limit_s = None if limit is None else float(limit)
            holder = _wait_for_lock(
                root,
                job_id=job_id,
                current=current,
                job_dir=job_dir,
                limit_s=limit_s,
                sleep=sleep,
                clock=clock,
            )
            if holder is not None:
                current.update(
                    state="failed",
                    message="gave up waiting for the cache lock",
                    error={
                        "code": "finalize.job_running",
                        "message": f"The {_holder_text(holder)} still holds the cache lock after "
                        f"{limit_s:g} s, so this job did not run",
                        "remediation": "Check the holding job with get_finalize_job and stop its "
                        "process if it is stuck, or rerun with a longer lock_wait_seconds (CLI "
                        "--wait-limit).",
                        "stage": "finalize",
                    },
                )
                return current

        current.update(state="running", pid=os.getpid(), progress=0.0, message="starting")
        _write_json(job_dir / "status.json", current)
        if job.get("kind") == _BATCH_KIND:
            _run_batch(job_dir, job, current, cache=cache, clients=clients, runner=runner)
        else:
            _run_single(
                job_dir,
                current,
                steps=steps,
                force=force,
                cache=cache,
                clients=clients,
                runner=runner,
            )
    finally:
        _write_json(job_dir / "status.json", current)
        _release_lock(root, job_id=job_id)
    return current


def _run_single(
    job_dir: Path,
    current: dict[str, Any],
    *,
    steps: tuple[str, ...],
    force: bool,
    cache: ArtifactCache,
    clients: FinalizeClients | None,
    runner: StepRunner | None,
) -> None:
    request = FinalizeRequest.model_validate_json((job_dir / "request.json").read_text("utf-8"))

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
    except Exception as error:
        current.update(state="failed", error=_failure_dict(error, current.get("step")))
    else:
        result = _mark_backlog(request, steps, result)
        current.update(state="succeeded", result=result.model_dump(mode="json"), progress=1.0)


def _run_batch(
    job_dir: Path,
    job: dict[str, Any],
    current: dict[str, Any],
    *,
    cache: ArtifactCache,
    clients: FinalizeClients | None,
    runner: StepRunner | None,
) -> None:
    """Run every batch item in order under the lock this job already holds (#149, AC2-AC4)."""
    requests = [FinalizeRequest.model_validate(item) for item in job["items"]]
    steps = tuple(str(step) for step in job["steps"])
    force = bool(job["force"])
    fail_fast = bool(job.get("fail_fast"))
    batch: dict[str, Any] = current.setdefault("batch", {})
    items: list[dict[str, Any]] = batch.get("items") or [
        {"index": index, "collection": request.collection, "state": "pending", "error": None}
        for index, request in enumerate(requests)
    ]
    batch.update(total=len(requests), completed=0, current=None, current_index=None, items=items)

    stop = False
    for index, request in enumerate(requests):
        if stop:
            items[index]["state"] = "skipped"
        else:
            _run_item(
                job_dir,
                index,
                request,
                items[index],
                batch,
                current,
                steps=steps,
                force=force,
                cache=cache,
                clients=clients,
                runner=runner,
            )
            stop = fail_fast and items[index]["state"] == "failed"
        batch["completed"] = sum(1 for item in items if item["state"] in _ITEM_DONE_STATES)
        _write_json(job_dir / "status.json", current)

    counts = {
        state: sum(1 for item in items if item["state"] == state) for state in _ITEM_DONE_STATES
    }
    failed, skipped = counts["failed"], counts["skipped"]
    batch.update(current=None, current_index=None)
    current["result"] = {
        "batch": {
            "total": len(requests),
            "succeeded": counts["succeeded"],
            "failed": failed,
            "skipped": skipped,
            "items": items,
        }
    }
    if failed == 0 and skipped == 0:
        current.update(state="succeeded", progress=1.0, message="batch finished")
        return
    current.update(
        state="failed",
        message="batch finished with failures",
        error={
            "code": "finalize.batch_failed",
            "message": f"{failed} of {len(requests)} collections failed and {skipped} were skipped",
            "remediation": "Read result.batch for each collection's error, fix it, and rerun the "
            "batch. Steps that already passed are served from the cache.",
            "stage": "finalize",
        },
    )


def _run_item(
    job_dir: Path,
    index: int,
    request: FinalizeRequest,
    item: dict[str, Any],
    batch: dict[str, Any],
    current: dict[str, Any],
    *,
    steps: tuple[str, ...],
    force: bool,
    cache: ArtifactCache,
    clients: FinalizeClients | None,
    runner: StepRunner | None,
) -> None:
    item_dir = job_dir / "items" / f"{index}-{request.collection}"
    item["state"] = "running"
    batch.update(current=request.collection, current_index=index)
    current.update(steps={}, step=None, progress=_batch_progress(batch, 0.0), message="starting")
    _write_json(job_dir / "status.json", current)

    def on_progress(event: dict[str, Any]) -> None:
        fraction = event.get("progress")
        current.update(
            state="running",
            step=event.get("step"),
            progress=_batch_progress(batch, fraction),
            message=event.get("message", ""),
        )
        _write_json(job_dir / "status.json", current)

    def on_step(result: Any) -> None:
        current.setdefault("steps", {})[result.step] = result.model_dump(mode="json")
        _write_json(job_dir / "status.json", current)

    try:
        result = execute(
            request,
            steps,
            force=force,
            cache=cache,
            job_dir=item_dir,
            runner=runner or SubprocessStepRunner(),
            clients=clients,
            progress=on_progress,
            on_step=on_step,
        )
    except Exception as error:
        item.update(state="failed", error=_failure_dict(error, current.get("step")))
    else:
        _mark_backlog(request, steps, result)
        item["state"] = "succeeded"
    finally:
        batch.update(current=None, current_index=None)


def _batch_progress(batch: dict[str, Any], fraction: object) -> float:
    """Overall batch progress: finished items plus the running item's own fraction."""
    total = max(int(batch.get("total") or 1), 1)
    done = float(batch.get("completed") or 0)
    item = float(fraction) if isinstance(fraction, (int, float)) else 0.0
    return min(1.0, (done + item) / total)


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


def _submit(
    job_fields: dict[str, Any],
    *,
    request_json: dict[str, object] | None,
    batch: dict[str, Any] | None = None,
    cache_root: Path | None,
    launcher: Launcher | None,
    wait_for_lock: bool,
    lock_wait_s: float | None,
) -> str:
    """Write a job directory, launch its process, and return the job id (shared by every start)."""
    if lock_wait_s is not None and lock_wait_s < 0:
        raise PipelineError(
            code="finalize.invalid_request",
            message=f"The lock wait limit must not be negative, got {lock_wait_s}",
            remediation="Pass 0 or a positive number of seconds, or omit the limit to wait "
            "without one.",
            stage="finalize",
        )
    root = jobs_root(cache_root)
    root.mkdir(parents=True, exist_ok=True)
    job_id = f"{time.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"
    if not wait_for_lock:
        holder = _claim(root, job_id=job_id, pid=os.getpid())
        if holder is not None:
            raise _job_running(holder)

    job_dir = root / job_id
    try:
        job_dir.mkdir(parents=True)
        if request_json is not None:
            _write_json(job_dir / "request.json", request_json)
        _write_json(
            job_dir / "job.json",
            {
                "job_id": job_id,
                "wait_for_lock": wait_for_lock,
                "lock_wait_s": lock_wait_s,
                **job_fields,
            },
        )
        initial = _status(job_id, "waiting" if wait_for_lock else "queued", pid=None)
        if wait_for_lock:
            initial["message"] = _waiting_message(_lock_holder(root / _LOCK_NAME))
        if batch is not None:
            initial["batch"] = batch
        _write_json(job_dir / "status.json", initial)
        pid = (launcher or _spawn_run_job)(job_dir)
    except BaseException:
        if not wait_for_lock:
            _release_lock(root, job_id=job_id)
        raise

    final = _read_status_file(job_dir, job_id)
    if final.get("state") in TERMINAL_STATES:
        # The job finished before the lock was handed over, so its own release already ran.
        _release_lock(root, job_id=job_id)
    else:
        final["pid"] = pid
        _write_json(job_dir / "status.json", final)
        if not wait_for_lock:
            _hand_lock_to(root, job_id=job_id, pid=pid)
    return job_id


def _wait_for_lock(
    root: Path,
    *,
    job_id: str,
    current: dict[str, Any],
    job_dir: Path,
    limit_s: float | None,
    sleep: Sleep,
    clock: Clock,
) -> dict[str, Any] | None:
    """Poll for the cache lock until this job claims it.  Return the live holder on timeout."""
    deadline = None if limit_s is None else clock() + limit_s
    while True:
        holder = _claim(root, job_id=job_id, pid=os.getpid())
        if holder is None:
            return None
        if deadline is not None and clock() >= deadline:
            return holder
        current.update(state="waiting", message=_waiting_message(holder))
        _write_json(job_dir / "status.json", current)
        pause = random.uniform(_LOCK_POLL_MIN_S, _LOCK_POLL_MAX_S)
        if deadline is not None:
            pause = min(pause, max(deadline - clock(), 0.0))
        sleep(pause)


def _claim(root: Path, *, job_id: str, pid: int) -> dict[str, Any] | None:
    """Atomically claim the cache lock for ``job_id``.  Return ``None`` if claimed, else the holder.

    A stale lock (its PID is gone, or it is unreadable) is removed and the claim is tried again.
    """
    lock = root / _LOCK_NAME
    for _ in range(_CLAIM_ATTEMPTS):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            holder = _lock_holder(lock)
            if holder is not None:
                return holder
            lock.unlink(missing_ok=True)
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps({"pid": pid, "job_id": job_id}))
        return None
    return _lock_holder(lock) or {"pid": None, "job_id": None}


def _lock_holder(lock: Path) -> dict[str, Any] | None:
    """Return the live holder recorded in ``lock``, or ``None`` when the lock is absent or stale."""
    try:
        text = lock.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    holder = _parse_lock(text)
    if holder is None:
        # An empty file may be a claim whose owner has not written its record yet.
        if not text and _younger_than(lock, _LOCK_WRITE_GRACE_S):
            return {"pid": None, "job_id": None}
        return None
    pid = holder["pid"]
    if isinstance(pid, int) and _alive(pid):
        return holder
    return None


def _hand_lock_to(root: Path, *, job_id: str, pid: int) -> None:
    """Record the spawned process as the lock's owner, if this job still holds the lock."""
    lock = root / _LOCK_NAME
    holder = _parse_lock(_read_text(lock))
    if holder is not None and holder.get("job_id") == job_id:
        _write_json(lock, {"pid": pid, "job_id": job_id})


def _release_lock(root: Path, *, job_id: str) -> None:
    """Remove the lock only when ``job_id`` owns it, so one job never drops another's lock."""
    lock = root / _LOCK_NAME
    holder = _parse_lock(_read_text(lock))
    if holder is not None and holder.get("job_id") == job_id:
        lock.unlink(missing_ok=True)


def _parse_lock(text: str) -> dict[str, Any] | None:
    """Parse a lock record: JSON ``{"pid", "job_id"}``, or a legacy plain PID."""
    if not text:
        return None
    try:
        return {"pid": int(text), "job_id": None}
    except ValueError:
        pass
    try:
        data: Any = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("pid"), int):
        return None
    job = data.get("job_id")
    return {"pid": data["pid"], "job_id": job if isinstance(job, str) else None}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _younger_than(path: Path, seconds: float) -> bool:
    try:
        return time.time() - path.stat().st_mtime < seconds
    except OSError:
        return False


def _holder_text(holder: dict[str, Any]) -> str:
    job = holder.get("job_id")
    pid = holder.get("pid")
    name = f"finalize job {job}" if job else "finalize job"
    return f"{name} (PID {pid})" if pid is not None else name


def _waiting_message(holder: dict[str, Any] | None) -> str:
    if holder is None:
        return "waiting for the cache lock"
    return f"waiting for the {_holder_text(holder)} to release the cache lock"


def _job_running(holder: dict[str, Any]) -> PipelineError:
    return PipelineError(
        code="finalize.job_running",
        message=f"Another {_holder_text(holder)} is running for this cache",
        remediation="Rerun with wait_for_lock (CLI --wait) so finalize waits for the lock itself. "
        "If the holder is stuck, check it with get_finalize_job and stop its process.",
        stage="finalize",
    )


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


def _failure_dict(error: Exception, step: object) -> dict[str, str]:
    if isinstance(error, PipelineError):
        return _error_dict(error)
    # Every failure must reach status.json, so this catch-all is deliberate.
    return {
        "code": "finalize.internal_error",
        "message": f"Unexpected error: {error}",
        "remediation": "Report this as a bug with the job's status.json.",
        "stage": str(step or "finalize"),
    }


def _write_json(path: Path, data: object) -> None:
    _write_text(path, json.dumps(data, indent=2, sort_keys=True, default=str) + "\n")


def _write_text(path: Path, text: str) -> None:
    staged = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    staged.write_text(text, encoding="utf-8")
    os.replace(staged, path)
