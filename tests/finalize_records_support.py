"""Shared helpers for the per-asset finalize record tests (#247).

Every helper runs in-process through the finalize fakes, so no Blender or Godot process starts.  A
consumer project in these tests is a temporary directory holding ``game/project.godot``; its export
root is ``game/assets``, so the records land in ``<tmp>/.nmg/finalize/`` as they do in a real
consumer.  Import them as ``from tests.finalize_records_support import ...``.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nmg_game_dev.pipeline import STEP_ORDER, FinalizeClients, FinalizeRequest, jobs
from nmg_game_dev.pipeline.records import record_file
from tests.finalize_fakes import FakeBlenderSession, FakeStepRunner, FinalizeGodot, dead_pid

PAST = "2000-01-01T00:00:00+00:00"
RECORD_FIELDS = frozenset(
    {
        "schema_version",
        "category",
        "collection",
        "job_id",
        "state",
        "started_at",
        "ended_at",
        "nmg_game_dev_version",
        "full_run",
        "steps",
        "source",
        "imported",
        "content_hash",
        "logs",
        "error",
    }
)


class LoggingRunner(FakeStepRunner):
    """The fake step runner, plus the files the real runner leaves in a job directory.

    Each step writes ``blender-<step>.log``, and the content hash pass writes ``hash.json``, as
    ``pipeline.blender_proc`` does.  The record and its log copies read those files.
    """

    def hash(self, *, job_dir: Path, in_blend: Path) -> str:
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "hash.json").write_text(json.dumps({"hash": self.hash_value}), encoding="utf-8")
        return super().hash(job_dir=job_dir, in_blend=in_blend)

    def run_step(
        self,
        step: str,
        *,
        job_dir: Path,
        in_blend: Path | None,
        inputs: Any = None,
        on_progress: Any = None,
    ) -> dict[str, Any]:
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / f"blender-{step}.log").write_text(f"{step} output\n", encoding="utf-8")
        return super().run_step(
            step, job_dir=job_dir, in_blend=in_blend, inputs=inputs, on_progress=on_progress
        )


def asset_request(root: Path, collection: str = "Crate", *, blend: bool = True) -> FinalizeRequest:
    """Return a Props request whose export root is ``<root>/game/assets``.

    With ``blend`` a saved ``<root>/<collection>.blend`` is the source; without it the request is a
    session run and has no source blend.
    """
    source = None
    if blend:
        source = root / f"{collection.lower()}.blend"
        source.write_bytes(b"authored")
    project = root / "game"
    project.mkdir(parents=True, exist_ok=True)
    (project / "project.godot").touch(exist_ok=True)
    return FinalizeRequest(
        collection=collection,
        category="Props",
        asset_class="standard_prop",
        export_root=project / "assets",
        blend=source,
    )


def consumer_of(request: FinalizeRequest) -> Path:
    """Return the consumer project root: the parent of the folder that holds ``project.godot``."""
    return request.export_root.parent.parent


def record_of(request: FinalizeRequest) -> Path:
    """Return the record path of the request's asset."""
    return record_file(consumer_of(request), request.category, request.collection)


def logs_of(request: FinalizeRequest) -> Path:
    """Return the ``<Name>.logs/`` folder beside the request's record."""
    return record_of(request).with_name(f"{request.collection}.logs")


def run_finalize(
    cache: Path,
    request: FinalizeRequest,
    *,
    steps: tuple[str, ...] = STEP_ORDER,
    godot: bool = True,
    runner: FakeStepRunner | None = None,
) -> dict[str, Any]:
    """Run one finalize job to completion in-process and return its status.

    ``job.log`` is written in the job directory, as the detached ``run-job`` process would have
    written it.  ``godot=False`` gives the job no Godot client, for steps that never import.
    """

    def launch(job_dir: Path) -> int:
        (job_dir / "job.log").write_text(f"job {job_dir.name}\n", encoding="utf-8")
        clients = FinalizeClients(
            blender=FakeBlenderSession(),
            godot=FinalizeGodot(request.export_root.parent) if godot else None,
        )
        jobs.run_job(job_dir, clients=clients, runner=runner or LoggingRunner(request))
        return dead_pid()

    job_id = jobs.start(request, steps, cache_root=cache, launcher=launch)
    return jobs.status(job_id, cache_root=cache)


def manual_record(request: FinalizeRequest, **changes: Any) -> dict[str, Any]:
    """Return a valid, successful, full-run record for the request, with ``changes`` applied.

    ``started_at`` is now, so a source blend written before this call is older than the run.
    """
    now = datetime.now(UTC).isoformat()
    source = None
    if request.blend is not None:
        source = {"blend": str(request.blend), "mtime": request.blend.stat().st_mtime}
    base = request.collection
    record: dict[str, Any] = {
        "schema_version": 1,
        "category": request.category,
        "collection": request.collection,
        "job_id": "manual-job",
        "state": "succeeded",
        "started_at": now,
        "ended_at": now,
        "nmg_game_dev_version": "0.0.0",
        "full_run": True,
        "steps": [{"step": "validate", "cache_hit": False}],
        "source": source,
        "imported": [
            f"res://assets/Props/{base}/Desktop/{base}.glb",
            f"res://assets/Props/{base}/Mobile/{base}.glb",
        ],
        "content_hash": None,
        "logs": {"job": None, "steps": {}},
        "error": None,
    }
    record.update(changes)
    return record


def write_record_file(request: FinalizeRequest, record: dict[str, Any] | str) -> Path:
    """Write ``record`` (or raw text) to the request's record path and return it."""
    path = record_of(request)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = record if isinstance(record, str) else json.dumps(record, indent=2, sort_keys=True)
    path.write_text(text + "\n", encoding="utf-8")
    return path


def write_imports(request: FinalizeRequest) -> None:
    """Create the Desktop and Mobile ``.glb`` files and their ``.import`` files, as Godot would."""
    for variant in ("Desktop", "Mobile"):
        glb = (
            request.export_root
            / request.category
            / request.collection
            / variant
            / f"{request.collection}.glb"
        )
        glb.parent.mkdir(parents=True, exist_ok=True)
        glb.touch(exist_ok=True)
        Path(f"{glb}.import").touch()


def up_to_date_asset(root: Path, collection: str = "Crate") -> FinalizeRequest:
    """Return a request whose record says up to date: clean full run, source and imports on disk."""
    request = asset_request(root, collection)
    write_imports(request)
    write_record_file(request, manual_record(request))
    return request


def snapshot(root: Path) -> dict[str, tuple[int, int]]:
    """Return ``{relative path: (size, mtime_ns)}`` for every file and folder under ``root``."""
    entries: dict[str, tuple[int, int]] = {}
    for path in sorted(root.rglob("*")):
        stat = path.stat()
        entries[str(path.relative_to(root))] = (stat.st_size, stat.st_mtime_ns)
    return entries


def hold_cache_lock(cache: Path) -> None:
    """Write a lock that a live process holds, as a running finalize job would."""
    (cache / "jobs").mkdir(parents=True, exist_ok=True)
    (cache / "jobs" / "lock").write_text(
        json.dumps({"pid": os.getpid(), "job_id": "holder"}), encoding="utf-8"
    )
