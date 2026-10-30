"""Client for the open Blender session through the MCP for Blender add-on socket (#69).

The add-on takes one JSON object per request on its socket and answers with one JSON object::

    request:  {"type": "execute_code", "params": {"code": "..."}}
    reply:    {"status": "success", "result": {"executed": true, "result": "<captured stdout>"}}
              {"status": "error", "message": "..."}

Finalize sends ``execute_code`` requests that run ``scripts/blender/finalize_session.py`` in the
session and read one ``NMG_RESULT {json}`` line from the captured stdout.  Connection failure is
``mcp.blender.unreachable``.  Every call is bounded by the 180 s Blender MCP limit.
"""

from __future__ import annotations

import json
import os
import socket
from collections.abc import Mapping
from contextlib import closing
from pathlib import Path
from typing import Any, Final

from nmg_game_dev.pipeline.errors import PipelineError

REPO_ROOT: Final = Path(__file__).resolve().parents[4]
SESSION_SCRIPT: Final = REPO_ROOT / "scripts" / "blender" / "finalize_session.py"
ADDON_DIR: Final = REPO_ROOT / "plugins" / "nmg-game-dev-blender-addon"
DEFAULT_HOST: Final = "127.0.0.1"
DEFAULT_PORT: Final = 9876
_TIMEOUT_S: Final = 170.0
_RESULT_PREFIX: Final = "NMG_RESULT "
_REMEDIATION: Final = (
    "Run scripts/start-blender-mcp.sh so the MCP for Blender add-on listens on "
    "BLENDER_MCP_PORT (default 9876), then retry."
)


class BlenderSessionClient:
    """Reads and writes the open Blender session.

    Parameters:
        host: Address of the add-on socket.
        port: Port of the add-on socket.  Defaults to ``BLENDER_MCP_PORT`` or 9876.
        timeout: Seconds to wait for each reply.
    """

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int | None = None,
        *,
        timeout: float = _TIMEOUT_S,
    ) -> None:
        self._host = host
        self._port = port if port is not None else _port_from_env()
        self._timeout = timeout

    def execute(self, code: str) -> dict[str, Any]:
        """Run ``code`` in the session and return the ``NMG_RESULT`` object it printed."""
        request = json.dumps({"type": "execute_code", "params": {"code": code}}).encode("utf-8")
        try:
            sock = socket.create_connection((self._host, self._port), timeout=self._timeout)
        except OSError as error:
            raise PipelineError(
                code="mcp.blender.unreachable",
                message=f"Blender MCP is not reachable at {self._host}:{self._port} ({error})",
                remediation=_REMEDIATION,
                stage="finalize",
            ) from error

        with closing(sock):
            try:
                sock.sendall(request)
                reply = _read_reply(sock)
            except OSError as error:
                raise PipelineError(
                    code="mcp.blender.unreachable",
                    message=f"Blender MCP dropped the connection: {error}",
                    remediation=_REMEDIATION,
                    stage="finalize",
                ) from error

        if reply.get("status") != "success":
            raise PipelineError(
                code="mcp.blender.failed",
                message=f"Blender reported an error: {reply.get('message', 'no message')}",
                remediation="Read the Blender console for the traceback, fix it, and rerun.",
                stage="finalize",
            )
        return _result_from_reply(reply)

    def run_session_op(self, op: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Run one ``finalize_session.py`` operation and return its ``NMG_RESULT`` object."""
        return self.execute(session_code(op, payload))

    def checkpoint(self, *, collection: str, path: Path) -> str:
        """Save a checkpoint copy of the session to ``path`` and return the collection hash."""
        result = self.run_session_op("checkpoint", {"collection": collection, "path": str(path)})
        _raise_if_error(result, stage="checkpoint")
        value = result.get("hash")
        if not isinstance(value, str) or not value:
            raise PipelineError(
                code="mcp.blender.invalid_response",
                message="Blender returned no content hash for the checkpoint",
                remediation="Check that the collection exists in the open session.",
                stage="finalize",
            )
        return value

    def load_back(
        self,
        *,
        result_blend: Path,
        collection: str,
        expected_hash: str,
    ) -> dict[str, Any]:
        """Load the baked collections into the session unless the session changed meanwhile."""
        result = self.run_session_op(
            "load_back",
            {
                "result_blend": str(result_blend),
                "collection": collection,
                "expected_hash": expected_hash,
            },
        )
        _raise_if_error(result, stage="load_back")
        return result


def session_code(op: str, payload: Mapping[str, Any]) -> str:
    """Return the code string that runs ``finalize_session.py`` with ``op`` and ``payload``.

    The JSON is embedded as string literals, so no caller value is interpolated as Python source.
    """
    script = str(SESSION_SCRIPT)
    # The session script loads the add-on package from addon_dir: exec'd code has no __file__.
    body = {"addon_dir": str(ADDON_DIR), **dict(payload)}
    return "\n".join(
        [
            "import json as _json",
            f"NMG_OP = {json.dumps(op)}",
            f"NMG_PAYLOAD = _json.loads({json.dumps(json.dumps(body))})",
            f"exec(compile(open({json.dumps(script)}, encoding='utf-8').read(), "
            f"{json.dumps(script)}, 'exec'))",
        ]
    )


def _port_from_env() -> int:
    raw = os.environ.get("BLENDER_MCP_PORT", "")
    try:
        return int(raw) if raw else DEFAULT_PORT
    except ValueError:
        return DEFAULT_PORT


def _read_reply(sock: socket.socket) -> dict[str, Any]:
    """Read until the buffer holds one complete JSON object."""
    buffer = b""
    while True:
        try:
            chunk = sock.recv(65536)
        except TimeoutError as error:
            raise PipelineError(
                code="mcp.blender.timeout",
                message="Blender did not reply within the 180 s MCP limit",
                remediation="Split the work into smaller steps, or check that Blender is not "
                "blocked by a modal dialog, then rerun.",
                stage="finalize",
            ) from error
        if not chunk:
            break
        buffer += chunk
        try:
            parsed = json.loads(buffer.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(parsed, dict):
            return parsed
    raise PipelineError(
        code="mcp.blender.invalid_response",
        message="Blender closed the connection without a complete reply",
        remediation=_REMEDIATION,
        stage="finalize",
    )


def _result_from_reply(reply: Mapping[str, Any]) -> dict[str, Any]:
    result = reply.get("result")
    stdout = result.get("result", "") if isinstance(result, dict) else ""
    if isinstance(stdout, str):
        for line in stdout.splitlines():
            if line.startswith(_RESULT_PREFIX):
                parsed = json.loads(line[len(_RESULT_PREFIX) :])
                if isinstance(parsed, dict):
                    return parsed
    raise PipelineError(
        code="mcp.blender.invalid_response",
        message="Blender replied without an NMG_RESULT line",
        remediation="Check that the add-on is the nmg-game-dev finalize build and rerun.",
        stage="finalize",
    )


def _raise_if_error(result: Mapping[str, Any], *, stage: str) -> None:
    if result.get("ok") is True:
        return
    error = result.get("error")
    if isinstance(error, dict):
        raise PipelineError(
            code=str(error.get("code", "finalize.session_failed")),
            message=str(error.get("message", f"The session {stage} failed")),
            remediation=str(error.get("remediation", "Check the Blender console and rerun.")),
            stage="finalize",
        )
    raise PipelineError(
        code="finalize.session_failed",
        message=f"The session {stage} failed without an error description",
        remediation="Check the Blender console and rerun.",
        stage="finalize",
    )
