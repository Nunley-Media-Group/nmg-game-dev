"""Per-asset finalize records, log copies, and the cheap up-to-date check (#247).

A finished finalize run (``succeeded`` or ``failed``) writes its record to
``<consumer>/.nmg/finalize/<Category>/<Name>.json``, where ``<consumer>`` is the parent of the
directory that holds ``project.godot``.  The run's logs are copied beside it into
``<Name>.logs/``, which each run replaces.  ``check`` answers from the record and file metadata
alone: it starts no Blender or Godot, takes no cache lock, and writes nothing.

The record is written from ``jobs.py`` at each terminal state.  A failure to write it becomes a
``finalize.record_not_written`` warning and never changes the run's result.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from nmg_game_dev import __version__

from .errors import PipelineError
from .request import FinalizeRequest
from .result import FinalizeResult
from .steps import STEP_ORDER

RECORD_SCHEMA_VERSION: Final = 1
RECORDS_DIR: Final = Path(".nmg") / "finalize"
RECORD_NOT_WRITTEN: Final = "finalize.record_not_written"
REASONS: Final = (
    "up_to_date",
    "project_missing",
    "no_record",
    "record_unreadable",
    "last_run_failed",
    "not_full_run",
    "no_source_blend",
    "source_missing",
    "source_newer",
    "import_missing",
)
ASSET_NAME: Final = re.compile(r"^[A-Z][A-Za-z0-9]*$")
_RES_PREFIX: Final = "res://"
# Godot's own resource formats load as they are and never get a ``.import`` file.  A terrain run
# records its ``<Variant>/<Name>.tscn`` scenes, so only the other paths need the sidecar.
_NATIVE_SUFFIXES: Final = frozenset({".tscn", ".scn", ".tres", ".res"})
_TERMINAL_STATES: Final = frozenset({"succeeded", "failed"})
_TEXT_FIELDS: Final = ("category", "collection", "job_id", "started_at", "ended_at")


@dataclass(frozen=True)
class CheckResult:
    """The answer to "is this asset up to date?" (#247 AC5-AC8).

    Attributes:
        up_to_date: ``True`` only for reason ``up_to_date``.
        reason: One of ``REASONS``.
        record: The parsed record, or ``None`` when there is no readable record.
    """

    up_to_date: bool
    reason: str
    record: dict[str, Any] | None


def valid_asset_names(category: str, collection: str) -> bool:
    """Return ``True`` when both names are PascalCase, as finalize requires."""
    return (
        ASSET_NAME.fullmatch(category) is not None and ASSET_NAME.fullmatch(collection) is not None
    )


def now() -> str:
    """Return the current UTC time as an ISO 8601 string, with microseconds."""
    return datetime.now(UTC).isoformat()


def record_file(consumer: Path, category: str, collection: str) -> Path:
    """Return ``<consumer>/.nmg/finalize/<category>/<collection>.json``."""
    return consumer / RECORDS_DIR / category / f"{collection}.json"


def record_path(export_root: Path, category: str, collection: str) -> Path:
    """Return the record path for an asset under ``export_root``.

    Raises ``PipelineError`` (``import_godot.project_missing``) when no Godot project holds the
    export root.  The godot package imports the pipeline, so its import stays local.
    """
    from nmg_game_dev.godot.project import find_project

    return record_file(find_project(export_root).parent, category, collection)


def source_at_start(request: FinalizeRequest) -> dict[str, Any] | None:
    """Return the source ``.blend`` snapshot taken at run start, or ``None`` for a session run."""
    if request.blend is None:
        return None
    blend = Path(os.path.abspath(request.blend))
    try:
        mtime: float | None = blend.stat().st_mtime
    except OSError:
        mtime = None
    return {"blend": str(blend), "mtime": mtime}


def write_record(
    request: FinalizeRequest,
    *,
    requested: Sequence[str],
    job_dir: Path,
    run_dir: Path,
    job_id: str,
    started_at: str,
    ended_at: str,
    state: str,
    source: Mapping[str, Any] | None,
    steps: Sequence[Mapping[str, Any]],
    result: FinalizeResult | None,
    error: Mapping[str, Any] | None,
) -> list[dict[str, str]]:
    """Copy the run's logs, then write its record atomically.  Return the warnings.

    ``job_dir`` holds the shared ``job.log`` and ``run_dir`` the run's ``blender-<step>.log`` files
    (the same directory for a single job, the item directory for a batch item).  A write that fails
    adds one ``finalize.record_not_written`` warning and removes any record an earlier run left, so
    the check cannot report that older run as current.
    """
    try:
        path = record_path(request.export_root, request.category, request.collection)
    except PipelineError as problem:
        return [_not_written(problem.message)]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        logs = _copy_logs(job_dir, run_dir, path)
        record = {
            "schema_version": RECORD_SCHEMA_VERSION,
            "category": request.category,
            "collection": request.collection,
            "job_id": job_id,
            "state": state,
            "started_at": started_at,
            "ended_at": ended_at,
            "nmg_game_dev_version": __version__,
            "full_run": tuple(requested) == STEP_ORDER,
            "steps": [
                {"step": str(step["step"]), "cache_hit": bool(step["cache_hit"])} for step in steps
            ],
            "source": None if source is None else dict(source),
            "imported": _imported(result),
            "content_hash": _content_hash(run_dir),
            "logs": logs,
            "error": _error(error),
        }
        _write_atomic(path, json.dumps(record, indent=2, sort_keys=True) + "\n")
    except (OSError, ValueError) as problem:
        _discard(path)
        return [_not_written(str(problem))]
    return []


def check(category: str, collection: str, export_root: Path) -> CheckResult:
    """Return whether the asset is up to date, applying the ordered rule of design.md (#247).

    Reads only the record and file metadata.  Missing or unreadable data is a reason, never an
    exception.
    """
    from nmg_game_dev.godot.project import find_project

    try:
        project = find_project(export_root)
    except PipelineError:
        return CheckResult(False, "project_missing", None)
    path = record_file(project.parent, category, collection)
    if not path.is_file():
        return CheckResult(False, "no_record", None)
    record = _read_record(path)
    if record is None:
        return CheckResult(False, "record_unreadable", None)
    if record["state"] != "succeeded":
        return CheckResult(False, "last_run_failed", record)
    if record["full_run"] is not True:
        return CheckResult(False, "not_full_run", record)
    source = record["source"]
    if source is None:
        return CheckResult(False, "no_source_blend", record)
    blend = Path(str(source["blend"]))
    try:
        blend_mtime = blend.stat().st_mtime if blend.is_file() else None
    except OSError:
        blend_mtime = None
    if blend_mtime is None:
        return CheckResult(False, "source_missing", record)
    started = _parse_time(str(record["started_at"]))
    if started is None or blend_mtime > started.timestamp():
        return CheckResult(False, "source_newer", record)
    for resource in record["imported"]:
        relative = str(resource).removeprefix(_RES_PREFIX)
        if not (project / relative).is_file() or not _import_sidecar_present(project, relative):
            return CheckResult(False, "import_missing", record)
    return CheckResult(True, "up_to_date", record)


def summary(record: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Return the short record summary the MCP tool reports, or ``None`` without a record."""
    if record is None:
        return None
    error = record.get("error")
    return {
        "state": record.get("state"),
        "ended_at": record.get("ended_at"),
        "error_code": error.get("code") if isinstance(error, Mapping) else None,
    }


def _not_written(reason: str) -> dict[str, str]:
    return {
        "code": RECORD_NOT_WRITTEN,
        "message": f"The finalize record was not written: {reason}",
        "remediation": "Check that <consumer>/.nmg/finalize is writable and that export_root is "
        "inside the Godot project.",
    }


def _copy_logs(job_dir: Path, run_dir: Path, record: Path) -> dict[str, Any]:
    """Replace ``<Name>.logs/`` with copies of the run's logs and return the names they take."""
    logs_dir = record.with_name(f"{record.stem}.logs")
    staging = record.with_name(f"{record.stem}.logs.{uuid.uuid4().hex}.tmp")
    staging.mkdir()
    names: dict[str, Any] = {"job": None, "steps": {}}
    try:
        job_log = job_dir / "job.log"
        if job_log.is_file():
            shutil.copyfile(job_log, staging / "job.log")
            names["job"] = f"{logs_dir.name}/job.log"
        for source in sorted(run_dir.glob("blender-*.log")):
            step = source.name.removeprefix("blender-").removesuffix(".log")
            shutil.copyfile(source, staging / source.name)
            names["steps"][step] = f"{logs_dir.name}/{source.name}"
        if logs_dir.exists():
            shutil.rmtree(logs_dir)
        os.replace(staging, logs_dir)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return names


def _import_sidecar_present(project: Path, relative: str) -> bool:
    """Return whether Godot's ``.import`` file is beside an imported (non-native) resource."""
    if Path(relative).suffix.lower() in _NATIVE_SUFFIXES:
        return True
    return (project / f"{relative}.import").is_file()


def _imported(result: FinalizeResult | None) -> list[str]:
    """Return the ``res://`` paths of the variants and clips the run imported."""
    if result is None:
        return []
    paths: list[object] = [result.desktop_resource_path, result.mobile_resource_path]
    clips = (result.animations or {}).get("clips") or []
    paths.extend(clip.get("asset_path") for clip in clips if isinstance(clip, Mapping))
    return list(dict.fromkeys(str(path) for path in paths if path))


def _content_hash(run_dir: Path) -> str | None:
    """Return the content hash the run recorded in ``hash.json``, or ``None``."""
    try:
        data = json.loads((run_dir / "hash.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    value = data.get("hash") if isinstance(data, dict) else None
    return value if isinstance(value, str) and value else None


def _error(error: Mapping[str, Any] | None) -> dict[str, str] | None:
    if error is None:
        return None
    return {key: str(error.get(key, "")) for key in ("code", "message", "remediation", "stage")}


def _write_atomic(path: Path, text: str) -> None:
    staged = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        staged.write_text(text, encoding="utf-8")
        os.replace(staged, path)
    except BaseException:
        staged.unlink(missing_ok=True)
        raise


def _discard(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _read_record(path: Path) -> dict[str, Any] | None:
    try:
        record: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return record if _is_valid(record) else None


def _is_valid(record: object) -> bool:
    if not isinstance(record, dict) or record.get("schema_version") != RECORD_SCHEMA_VERSION:
        return False
    if record.get("state") not in _TERMINAL_STATES or not isinstance(record.get("full_run"), bool):
        return False
    if not all(isinstance(record.get(name), str) for name in _TEXT_FIELDS):
        return False
    if _parse_time(str(record["started_at"])) is None:
        return False
    source = record.get("source")
    if source is not None and not (
        isinstance(source, dict) and isinstance(source.get("blend"), str)
    ):
        return False
    imported = record.get("imported")
    if not isinstance(imported, list) or not all(
        isinstance(path, str) and path.startswith(_RES_PREFIX) for path in imported
    ):
        return False
    return isinstance(record.get("steps"), list) and isinstance(record.get("logs"), dict)


def _parse_time(text: str) -> datetime | None:
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
