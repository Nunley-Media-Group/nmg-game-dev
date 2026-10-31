"""Background Meshy jobs: start, poll, and run detached (#98 FR4–FR7, AC1–AC11).

A job lives in ``SourceArt/Meshy/.jobs/<job_id>/`` with ``request.json``, ``status.json``, and
``job.log``; a retexture job also keeps ``input.glb``. Both JSON files are rewritten atomically
(temp file, then rename). No job file holds the key: the detached child re-resolves it from the
environment or ``.env``, and every message passes through ``redact`` before it is recorded.

``start_*`` runs synchronously and returns the job id at once. ``run_job`` runs in the detached
child and writes the final state. An unreachable Blender session at import or apply time is a
warning, and the downloaded files stay on disk.
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
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from nmg_game_dev.meshy import config
from nmg_game_dev.meshy.client import TERMINAL_FAILURES, MeshyClient, Transport
from nmg_game_dev.meshy.errors import MeshyError
from nmg_game_dev.meshy.paths import glb_path, jobs_root, maps_dir
from nmg_game_dev.meshy.request import (
    GLB_MIME,
    GenerateRequest,
    RetextureRequest,
    clean_prompt,
    data_uri,
    image_data_uri,
    route,
)
from nmg_game_dev.meshy.session import MeshySession, SessionClient
from nmg_game_dev.pipeline.clients.blender_session import BlenderSessionClient
from nmg_game_dev.pipeline.errors import PipelineError

REQUEST_NAME: Final = "request.json"
STATUS_NAME: Final = "status.json"
LOG_NAME: Final = "job.log"
INPUT_NAME: Final = "input.glb"
JOB_ID_CHARS: Final = 12
POLL_INTERVAL_S: Final = 5.0
TIMEOUT_S: Final = 30 * 60
UNREACHABLE: Final = "mcp.blender.unreachable"
MAP_KINDS: Final = ("base_color", "normal", "roughness", "metallic")
TERMINAL_STATES: Final = ("succeeded", "failed")

Spawn = Callable[[Path, Mapping[str, str], Path], None]
Sleep = Callable[[float], None]
Clock = Callable[[], float]


def default_spawn(job_dir: Path, env: Mapping[str, str], cwd: Path) -> None:
    """Start ``python -m nmg_game_dev.meshy run-job <job_dir>`` detached, logging to ``job.log``."""
    log = (job_dir / LOG_NAME).open("ab")
    try:
        subprocess.Popen(
            [sys.executable, "-m", "nmg_game_dev.meshy", "run-job", str(job_dir)],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
            cwd=str(cwd),
            env=dict(env),
        )
    finally:
        log.close()


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


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _env_and_cwd(env: Mapping[str, str] | None, cwd: Path | None) -> tuple[dict[str, str], Path]:
    env_map = dict(os.environ) if env is None else dict(env)
    return env_map, cwd or Path.cwd()


def _meshy_session(session: SessionClient | None) -> MeshySession:
    return MeshySession(session if session is not None else BlenderSessionClient())


def _job_not_found(job_id: str) -> MeshyError:
    return MeshyError(
        "meshy.job_not_found",
        f"No Meshy job {job_id!r} exists under this project.",
        "Use the job_id that generate_model or retexture_model returned, or start a new job.",
    )


def _new_job_dir(root: Path) -> tuple[str, Path]:
    job_id = uuid.uuid4().hex[:JOB_ID_CHARS]
    job_dir = jobs_root(root) / job_id
    job_dir.mkdir(parents=True, exist_ok=False)
    return job_id, job_dir


def _queue(
    job_dir: Path,
    job_id: str,
    kind: str,
    fields: Mapping[str, Any],
    root: Path,
) -> None:
    _write_json_atomic(job_dir / REQUEST_NAME, {**fields, "kind": kind, "project_root": str(root)})
    _write_json_atomic(
        job_dir / STATUS_NAME,
        {"job_id": job_id, "kind": kind, "state": "queued", "stage": "queued", "progress": 0},
    )


def _reachable_state(session: MeshySession, name: str) -> str | None:
    """Return the collection state, or None when the Blender session is unreachable."""
    try:
        return session.collection_state(name)
    except PipelineError as error:
        if error.code == UNREACHABLE:
            return None
        raise


def start_generate(
    request: GenerateRequest,
    *,
    env: Mapping[str, str] | None = None,
    cwd: Path | None = None,
    session: SessionClient | None = None,
    spawn: Spawn | None = None,
) -> str:
    """Validate, check the key and the session, start a detached generate job, return its id."""
    request.validate()
    env_map, work_dir = _env_and_cwd(env, cwd)
    config.api_key(env_map, work_dir)
    root = config.project_root(env_map, work_dir)
    meshy_session = _meshy_session(session)
    if _reachable_state(meshy_session, request.name) in ("exists", "no_mesh"):
        raise MeshyError(
            "meshy.collection_exists",
            f"The open Blender session already has a collection named {request.name!r}.",
            f"Pick another name, or delete the {request.name} collection in Blender, then retry.",
        )
    job_id, job_dir = _new_job_dir(root)
    fields = {
        "name": request.name,
        "prompt": clean_prompt(request.prompt),
        "image_paths": list(request.image_paths),
        "texture": request.texture,
        "pose": request.pose,
    }
    try:
        _queue(job_dir, job_id, "generate", fields, root)
        (spawn or default_spawn)(job_dir, env_map, work_dir)
    except BaseException:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    return job_id


def start_retexture(
    request: RetextureRequest,
    *,
    env: Mapping[str, str] | None = None,
    cwd: Path | None = None,
    session: SessionClient | None = None,
    spawn: Spawn | None = None,
) -> str:
    """Validate, check the key, export the collection, start a detached retexture job."""
    request.validate()
    env_map, work_dir = _env_and_cwd(env, cwd)
    config.api_key(env_map, work_dir)
    root = config.project_root(env_map, work_dir)
    meshy_session = _meshy_session(session)
    job_id, job_dir = _new_job_dir(root)
    fields = {
        "name": request.name,
        "prompt": clean_prompt(request.prompt),
        "image_path": request.image_path,
    }
    try:
        meshy_session.export_glb(request.name, job_dir / INPUT_NAME)
        _queue(job_dir, job_id, "retexture", fields, root)
        (spawn or default_spawn)(job_dir, env_map, work_dir)
    except BaseException:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    return job_id


def status(
    job_id: str, *, env: Mapping[str, str] | None = None, cwd: Path | None = None
) -> dict[str, Any]:
    """Return the status document of ``job_id``. Unknown ids raise ``meshy.job_not_found``."""
    env_map, work_dir = _env_and_cwd(env, cwd)
    root = config.project_root(env_map, work_dir)
    if not job_id or job_id in (".", "..") or "/" in job_id or "\\" in job_id:
        raise _job_not_found(job_id)
    path = jobs_root(root) / job_id / STATUS_NAME
    if not path.is_file():
        raise _job_not_found(job_id)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise _job_not_found(job_id)
    return data


def wait(
    job_id: str,
    *,
    env: Mapping[str, str] | None = None,
    cwd: Path | None = None,
    sleep: Sleep = time.sleep,
    poll_interval: float = POLL_INTERVAL_S,
) -> dict[str, Any]:
    """Poll ``status`` until the job succeeds or fails, then return that final document."""
    while True:
        document = status(job_id, env=env, cwd=cwd)
        if document.get("state") in TERMINAL_STATES:
            return document
        sleep(poll_interval)


@dataclass(frozen=True)
class _Run:
    """What one detached run needs: where the job lives, who it calls, and how it waits."""

    job_dir: Path
    job_id: str
    kind: str
    root: Path
    client: MeshyClient
    session: MeshySession
    sleep: Sleep
    clock: Clock
    poll_interval: float
    timeout: float


def run_job(
    job_dir: Path,
    *,
    env: Mapping[str, str] | None = None,
    transport: Transport | None = None,
    session: SessionClient | None = None,
    sleep: Sleep = time.sleep,
    clock: Clock = time.monotonic,
    poll_interval: float = POLL_INTERVAL_S,
    timeout: float = TIMEOUT_S,
) -> dict[str, Any]:
    """Run the job in ``job_dir`` to its final state, record it, and return it (detached child)."""
    env_map = dict(os.environ) if env is None else dict(env)
    job_id = job_dir.name
    kind = "unknown"
    key = ""
    try:
        stored = json.loads((job_dir / REQUEST_NAME).read_text(encoding="utf-8"))
        kind = str(stored.get("kind", "unknown"))
        root = Path(str(stored["project_root"]))
        key = config.api_key(env_map, root)
        run = _Run(
            job_dir=job_dir,
            job_id=job_id,
            kind=kind,
            root=root,
            client=MeshyClient(key, transport),
            session=_meshy_session(session),
            sleep=sleep,
            clock=clock,
            poll_interval=poll_interval,
            timeout=timeout,
        )
        _report(run, "start", 0)
        if kind == "generate":
            result = _run_generate(run, stored)
        elif kind == "retexture":
            result = _run_retexture(run, stored)
        else:
            raise MeshyError(
                "meshy.job_crashed",
                f"The job has an unknown kind {kind!r}.",
                "Start the job again with generate_model or retexture_model.",
            )
        final: dict[str, Any] = {
            "job_id": job_id,
            "kind": kind,
            "state": "succeeded",
            "stage": "done",
            "progress": 100,
            "result": result,
        }
    except PipelineError as error:
        final = _failed(job_id, kind, error.code, error.message, error.remediation, key)
    except Exception as error:  # noqa: BLE001 - a crashed job must still record a final state
        final = _failed(
            job_id,
            kind,
            "meshy.job_crashed",
            f"{type(error).__name__}: {error}",
            f"Read {job_dir / LOG_NAME} for the traceback, then start the job again.",
            key,
        )
    _write_json_atomic(job_dir / STATUS_NAME, final)
    return final


def _failed(
    job_id: str,
    kind: str,
    code: str,
    message: str,
    remediation: str,
    key: str,
) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "kind": kind,
        "state": "failed",
        "stage": "failed",
        "progress": 0,
        "error": {
            "code": code,
            "message": config.redact(message, key),
            "remediation": config.redact(remediation, key),
        },
    }


def _report(run: _Run, stage: str, progress: object) -> None:
    value = (
        int(progress)
        if isinstance(progress, (int, float)) and not isinstance(progress, bool)
        else 0
    )
    _write_json_atomic(
        run.job_dir / STATUS_NAME,
        {
            "job_id": run.job_id,
            "kind": run.kind,
            "state": "running",
            "stage": stage,
            "progress": max(0, min(100, value)),
        },
    )


def _warning(error: PipelineError) -> dict[str, str]:
    return {"code": error.code, "message": error.message, "remediation": error.remediation}


def _poll(run: _Run, kind: str, task_id: str, stage: str) -> dict[str, Any]:
    """Poll a Meshy task until it succeeds, fails, or runs past the timeout."""
    started = run.clock()
    while True:
        task = run.client.get_task(kind, task_id)
        state = str(task.get("status", "")).upper()
        if state == "SUCCEEDED":
            return task
        if state in TERMINAL_FAILURES:
            raise _task_failed(task, state)
        _report(run, stage, task.get("progress"))
        if run.clock() - started >= run.timeout:
            raise MeshyError(
                "meshy.task_timeout",
                f"Meshy did not finish the {stage} task within {int(run.timeout // 60)} minutes.",
                "Retry the job; if it times out again, simplify the prompt or use fewer images.",
            )
        run.sleep(run.poll_interval)


def _task_failed(task: Mapping[str, Any], state: str) -> MeshyError:
    error = task.get("task_error")
    detail = error.get("message") if isinstance(error, dict) else None
    message = f"Meshy ended the task {state}"
    if isinstance(detail, str) and detail.strip():
        message = f"{message}: {detail.strip()}"
    return MeshyError(
        "meshy.task_failed",
        message,
        "Adjust the prompt or the reference images, then start a new job.",
    )


def _glb_url(task: Mapping[str, Any]) -> str:
    urls = task.get("model_urls")
    glb = urls.get("glb") if isinstance(urls, dict) else None
    if not isinstance(glb, str) or not glb:
        raise MeshyError(
            "meshy.task_failed",
            "Meshy finished the task without a GLB model.",
            "Retry the job.",
        )
    return glb


def _texture_urls(task: Mapping[str, Any]) -> dict[str, str]:
    entries = task.get("texture_urls")
    if not isinstance(entries, list) or not entries or not isinstance(entries[0], dict):
        return {}
    return {str(kind): url for kind, url in entries[0].items() if isinstance(url, str) and url}


def _run_generate(run: _Run, stored: Mapping[str, Any]) -> dict[str, Any]:
    request = GenerateRequest(
        name=str(stored["name"]),
        prompt=stored.get("prompt"),
        image_paths=tuple(str(item) for item in stored.get("image_paths", [])),
        texture=bool(stored.get("texture", True)),
        pose=stored.get("pose"),
    )
    request.validate()
    shape = route(request)
    if shape == "text":
        task = _generate_text(run, request)
    else:
        task = _generate_images(run, shape, request)
    glb_url = _glb_url(task)
    _report(run, "download", 90)
    target = glb_path(run.root, request.name)
    _write_bytes(target, run.client.download(glb_url))
    _report(run, "import", 95)
    result: dict[str, Any] = {
        "name": request.name,
        "route": shape,
        "glb_path": str(target),
        "loaded_into_session": False,
        "warnings": [],
    }
    try:
        imported = run.session.import_glb(request.name, target)
    except PipelineError as error:
        if error.code != UNREACHABLE:
            raise
        result["warnings"].append(_warning(error))
    else:
        result["loaded_into_session"] = True
        result["collection"] = imported.get("collection")
        result["mesh"] = imported.get("mesh")
        result["material"] = imported.get("material")
    return result


def _generate_text(run: _Run, request: GenerateRequest) -> dict[str, Any]:
    prompt = clean_prompt(request.prompt)
    if prompt is None:
        raise MeshyError(
            "meshy.invalid_request",
            "A text generation needs a prompt.",
            "Pass prompt=<text>, or pass reference images instead.",
        )
    _report(run, "preview", 0)
    preview_id = run.client.create_text_preview(prompt, pose_mode=request.pose)
    task = _poll(run, "text", preview_id, "preview")
    if not request.texture:
        return task
    refine_id = run.client.create_text_refine(preview_id)
    return _poll(run, "text", refine_id, "refine")


def _generate_images(run: _Run, shape: str, request: GenerateRequest) -> dict[str, Any]:
    uris = [image_data_uri(Path(path)) for path in request.image_paths]
    prompt = clean_prompt(request.prompt)
    _report(run, "submit", 0)
    if shape == "image":
        task_id = run.client.create_image_to_3d(
            uris[0],
            texture=request.texture,
            texture_prompt=prompt,
            pose_mode=request.pose,
        )
    else:
        task_id = run.client.create_multi_image_to_3d(
            uris,
            texture=request.texture,
            texture_prompt=prompt,
            pose_mode=request.pose,
        )
    return _poll(run, shape, task_id, f"{shape}_to_3d")


def _run_retexture(run: _Run, stored: Mapping[str, Any]) -> dict[str, Any]:
    name = str(stored["name"])
    prompt = clean_prompt(stored.get("prompt"))
    image_path = stored.get("image_path")
    model_uri = data_uri((run.job_dir / INPUT_NAME).read_bytes(), GLB_MIME)
    style_uri = image_data_uri(Path(str(image_path))) if prompt is None and image_path else None
    _report(run, "submit", 0)
    task_id = run.client.create_retexture(
        model_uri,
        text_style_prompt=prompt,
        image_style_uri=style_uri,
    )
    task = _poll(run, "retexture", task_id, "retexture")
    urls = _texture_urls(task)
    if "base_color" not in urls:
        raise MeshyError(
            "meshy.task_failed",
            "Meshy finished the retexture without a base color map.",
            "Retry with a different prompt or style image.",
        )
    out_dir = maps_dir(run.root, name)
    maps: dict[str, Path] = {}
    for kind in MAP_KINDS:
        url = urls.get(kind)
        if url is None:
            continue
        _report(run, "download", 80)
        maps[kind] = out_dir / f"{kind}.png"
        _write_bytes(maps[kind], run.client.download(url))
    result: dict[str, Any] = {
        "name": name,
        "maps": {kind: str(path) for kind, path in maps.items()},
        "applied_to_session": False,
        "warnings": [],
    }
    _report(run, "apply", 95)
    try:
        run.session.apply_maps(name, maps)
    except PipelineError as error:
        if error.code != UNREACHABLE:
            raise
        result["warnings"].append(_warning(error))
    else:
        result["applied_to_session"] = True
    return result
