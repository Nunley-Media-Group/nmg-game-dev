"""Fakes for the Meshy transport, the Blender session client, spawning, and time (#98 FR12).

No test that uses these touches the network or a running Blender. ``FakeMeshy`` implements the
``Transport`` protocol with scripted task states, ``FakeSession`` implements the session protocol
with in-memory collections, ``RecordingSpawn`` records detached jobs instead of starting them, and
``FakeClock`` advances only when the code sleeps.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlsplit

from nmg_game_dev.meshy import jobs
from nmg_game_dev.meshy.client import TERMINAL_FAILURES
from nmg_game_dev.meshy.request import GenerateRequest, RetextureRequest
from nmg_game_dev.pipeline.errors import PipelineError

API: Final = "https://api.meshy.ai"
GLB_BYTES: Final = b"glTF-fake-binary"
GLB_URL: Final = "https://assets.meshy.test/model.glb"
MAP_NAMES: Final = ("base_color", "normal", "roughness", "metallic")
MAP_URLS: Final[Mapping[str, str]] = {
    kind: f"https://assets.meshy.test/{kind}.png" for kind in MAP_NAMES
}
MAP_BYTES: Final = b"\x89PNG-fake-map"
PNG_BYTES: Final = b"\x89PNG\r\n\x1a\nfake"
ALL_OPS: Final = frozenset({"collection_state", "import_glb", "export_glb", "apply_maps"})
# What the session's import_glb reports about its normalization (#105 AC4); the values are fixed.
IMPORT_NORMALIZATION: Final[Mapping[str, Any]] = {
    "merged_vertices": 16,
    "origin_offset": [0.0, 0.0, 0.5],
}
TEST_KEY: Final = "test-key-do-not-leak"
ENV: Final[Mapping[str, str]] = {"MESHY_API_KEY": TEST_KEY}


@dataclass(frozen=True)
class SentRequest:
    method: str
    url: str
    headers: dict[str, str]
    body: bytes | None

    def json_body(self) -> dict[str, Any]:
        return json.loads(self.body) if self.body else {}


class FakeMeshy:
    """A scripted Meshy transport: creates tasks, reports their states, and serves assets.

    ``task_states`` is the sequence of statuses each task reports on successive polls; the last one
    repeats. ``create_status`` and ``poll_status`` replace the normal answer with an HTTP error.
    """

    def __init__(
        self,
        *,
        create_status: int = 200,
        poll_status: int = 200,
        task_states: Iterable[str] = ("SUCCEEDED",),
        task_error: str = "",
        texture_maps: bool = True,
        poll_progress: int = 40,
        glb_url: str | None = GLB_URL,
        send_error: OSError | None = None,
    ) -> None:
        self.create_status = create_status
        self.poll_status = poll_status
        self.task_states = list(task_states)
        self.task_error = task_error
        self.texture_maps = texture_maps
        self.poll_progress = poll_progress
        self.glb_url = glb_url
        self.send_error = send_error
        self.sent: list[SentRequest] = []
        self._task_count = 0
        self._polls: dict[str, int] = {}

    def send(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None,
    ) -> tuple[int, bytes]:
        self.sent.append(SentRequest(method, url, dict(headers), body))
        if self.send_error is not None:
            raise self.send_error
        path = urlsplit(url).path
        if url.startswith(API) and method == "POST":
            return self._create()
        if url.startswith(API) and method == "GET":
            return self._poll(path)
        if url == GLB_URL or url in MAP_URLS.values():
            return 200, GLB_BYTES if url == GLB_URL else MAP_BYTES
        return 404, b'{"message": "not found"}'

    def _create(self) -> tuple[int, bytes]:
        if self.create_status != 200:
            return self.create_status, json.dumps({"message": "rejected by fake"}).encode()
        self._task_count += 1
        return 200, json.dumps({"result": f"task-{self._task_count}"}).encode()

    def _poll(self, path: str) -> tuple[int, bytes]:
        if self.poll_status != 200:
            return self.poll_status, json.dumps({"message": "fake poll failure"}).encode()
        task_id = path.rsplit("/", 1)[-1]
        index = self._polls.get(task_id, 0)
        self._polls[task_id] = index + 1
        state = self.task_states[min(index, len(self.task_states) - 1)]
        document: dict[str, Any] = {"id": task_id, "status": state, "progress": self.poll_progress}
        if state == "SUCCEEDED":
            if self.glb_url is not None:
                document["model_urls"] = {"glb": self.glb_url}
            if self.texture_maps:
                document["texture_urls"] = [dict(MAP_URLS)]
        if state in TERMINAL_FAILURES:
            document["task_error"] = {"message": self.task_error}
        return 200, json.dumps(document).encode()

    def posts(self) -> list[tuple[str, dict[str, Any]]]:
        """Return ``(path, body)`` for every create request, in order."""
        return [
            (urlsplit(sent.url).path, sent.json_body())
            for sent in self.sent
            if sent.method == "POST"
        ]

    def gets(self) -> list[SentRequest]:
        return [sent for sent in self.sent if sent.method == "GET"]


class FakeSession:
    """A scripted Blender session: in-memory collections, every operation recorded.

    ``down`` names operations that raise ``mcp.blender.unreachable``, as an unopened Blender does.
    """

    def __init__(
        self,
        *,
        collections: Iterable[str] = (),
        down: Iterable[str] = (),
    ) -> None:
        self.collections: dict[str, dict[str, Any]] = {
            name: _collection(name) for name in collections
        }
        self.down = frozenset(down)
        self.ops: list[tuple[str, dict[str, Any]]] = []
        self.scripts: list[Path] = []
        self.import_results: dict[str, dict[str, Any]] = {}

    def run_session_op(
        self,
        op: str,
        payload: Mapping[str, Any],
        *,
        script: Path,
    ) -> dict[str, Any]:
        self.ops.append((op, dict(payload)))
        self.scripts.append(script)
        if op in self.down:
            raise PipelineError(
                code="mcp.blender.unreachable",
                message="Blender MCP is not reachable at 127.0.0.1:9876 (connection refused)",
                remediation="Run scripts/start-blender-mcp.sh, then retry.",
                stage="finalize",
            )
        return self._answer(op, dict(payload))

    def _answer(self, op: str, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name", ""))
        if op == "collection_state":
            return {"ok": True, "state": "exists" if name in self.collections else "missing"}
        if op == "import_glb":
            if name in self.collections:
                return _error("meshy.collection_exists", f"{name!r} already exists.")
            self.collections[name] = _collection(name)
            imported = {"ok": True, **_collection(name), **IMPORT_NORMALIZATION}
            self.import_results[name] = imported
            return imported
        if name not in self.collections:
            return _error("meshy.collection_not_found", f"No collection {name!r}.")
        if op == "export_glb":
            Path(str(payload["path"])).write_bytes(b"glTF-exported")
            return {"ok": True, "path": payload["path"], "meshes": 1}
        if op == "apply_maps":
            self.collections[name]["maps"] = sorted(payload["maps"])
            return {"ok": True, "material": f"M_{name}_Body", "maps": sorted(payload["maps"])}
        return _error("meshy.session_failed", f"Unknown operation {op!r}.")

    def ops_named(self, op: str) -> list[dict[str, Any]]:
        return [payload for name, payload in self.ops if name == op]


def _collection(name: str) -> dict[str, Any]:
    return {"collection": name, "mesh": f"SM_{name}", "material": f"M_{name}_Body"}


def _error(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message, "remediation": "Fix it."}}


class RecordingSpawn:
    """Records each detached job directory instead of starting a process."""

    def __init__(self) -> None:
        self.jobs: list[Path] = []

    def __call__(self, job_dir: Path, env: Mapping[str, str], cwd: Path) -> None:
        self.jobs.append(job_dir)


class FakeClock:
    """A clock that moves only when the code under test sleeps."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def make_png(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(PNG_BYTES)
    return path


def start_generate(
    request: GenerateRequest,
    project: Path,
    *,
    env: Mapping[str, str] = ENV,
    session: FakeSession | None = None,
) -> tuple[str, RecordingSpawn]:
    spawn = RecordingSpawn()
    job_id = jobs.start_generate(
        request,
        env=env,
        cwd=project,
        session=session if session is not None else FakeSession(),
        spawn=spawn,
    )
    return job_id, spawn


def start_retexture(
    request: RetextureRequest,
    project: Path,
    *,
    env: Mapping[str, str] = ENV,
    session: FakeSession,
) -> tuple[str, RecordingSpawn]:
    spawn = RecordingSpawn()
    job_id = jobs.start_retexture(request, env=env, cwd=project, session=session, spawn=spawn)
    return job_id, spawn


def run_job(
    job_dir: Path,
    *,
    meshy: FakeMeshy,
    session: FakeSession,
    clock: FakeClock | None = None,
    env: Mapping[str, str] = ENV,
    timeout: float = jobs.TIMEOUT_S,
) -> dict[str, Any]:
    clock = clock if clock is not None else FakeClock()
    return jobs.run_job(
        job_dir,
        env=env,
        transport=meshy,
        session=session,
        sleep=clock.sleep,
        clock=clock,
        poll_interval=jobs.POLL_INTERVAL_S,
        timeout=timeout,
    )


def generate_and_run(
    request: GenerateRequest,
    project: Path,
    *,
    meshy: FakeMeshy | None = None,
    session: FakeSession | None = None,
    env: Mapping[str, str] = ENV,
) -> tuple[str, dict[str, Any], FakeMeshy, FakeSession]:
    meshy = meshy if meshy is not None else FakeMeshy()
    session = session if session is not None else FakeSession()
    job_id, spawn = start_generate(request, project, env=env, session=session)
    final = run_job(spawn.jobs[0], meshy=meshy, session=session, env=env)
    return job_id, final, meshy, session


def retexture_and_run(
    request: RetextureRequest,
    project: Path,
    *,
    meshy: FakeMeshy | None = None,
    session: FakeSession,
    env: Mapping[str, str] = ENV,
) -> tuple[str, dict[str, Any], FakeMeshy]:
    meshy = meshy if meshy is not None else FakeMeshy()
    job_id, spawn = start_retexture(request, project, env=env, session=session)
    final = run_job(spawn.jobs[0], meshy=meshy, session=session, env=env)
    return job_id, final, meshy


def all_job_text(job_dir: Path) -> str:
    """Return the text of every file under a job directory, for leak checks."""
    parts = []
    for path in sorted(job_dir.rglob("*")):
        if path.is_file() and path.suffix != ".glb":
            parts.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(parts)
