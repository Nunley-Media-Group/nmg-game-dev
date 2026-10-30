#!/usr/bin/env python3
"""Smoke-test the latest Blender MCP server end to end over stdio.

Usage:  scripts/smoke-blender-mcp.py [--mcp-json PATH] [--timeout SECONDS]

Reads ``mcpServers.blender`` from .mcp.json, starts its ``command`` and ``args`` with its
``env`` merged over the current environment, and speaks newline-delimited JSON-RPC on
stdin/stdout:

1. ``initialize`` and ``notifications/initialized``;
2. ``tools/list``, which must offer ``execute_blender_code``;
3. ``tools/call execute_blender_code`` with ``import bpy`` and ``print(bpy.app.version_string)``.
   A non-error reply containing a version string passes.

Blender must be running with the add-on started: scripts/install-blender-mcp-addon.sh, then
scripts/start-blender-mcp.sh. Each read waits up to ``--timeout`` seconds (default 120).
The server process is terminated on exit.

Exit codes:
  0  every check passed
  1  a check failed; stderr shows ``FAIL <step>: <detail>``
  2  Blender or the add-on is not reachable; stderr names both remediation scripts

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import IO, Any

PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "blender"
TOOL_NAME = "execute_blender_code"
PROBE_CODE = "import bpy\nprint(bpy.app.version_string)"
DEFAULT_TIMEOUT_S = 120.0
STDERR_TAIL_LINES = 20

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MCP_JSON = REPO_ROOT / ".mcp.json"

VERSION_PATTERN = re.compile(r"\b\d+\.\d+(?:\.\d+)?\b")
NOT_CONNECTED_PATTERN = re.compile(
    r"(?:could not|couldn't|cannot|can't) connect to blender", re.IGNORECASE
)

REMEDIATION = (
    "Run scripts/install-blender-mcp-addon.sh once, then scripts/start-blender-mcp.sh, "
    "and re-run this smoke test."
)

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_UNREACHABLE = 2


class SmokeFailureError(Exception):
    """A check failed. ``step`` names the check that failed."""

    def __init__(self, step: str, detail: str) -> None:
        super().__init__(f"{step}: {detail}")
        self.step = step
        self.detail = detail


class BlenderUnreachableError(Exception):
    """The MCP server could not reach Blender, or could not be started at all."""


class StdioSession:
    """Newline-delimited JSON-RPC over a child process's stdin and stdout."""

    def __init__(self, command: list[str], env: dict[str, str], timeout: float) -> None:
        self._timeout = timeout
        self._next_id = 0
        self._lines: queue.Queue[str | None] = queue.Queue()
        self._stderr_tail: list[str] = []
        try:
            self._proc = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
            )
        except OSError as exc:
            raise BlenderUnreachableError(f"could not start {command[0]!r} ({exc})") from exc
        _start_pump(self._proc.stdout, self._pump_stdout)
        _start_pump(self._proc.stderr, self._pump_stderr)

    def _pump_stdout(self, stream: IO[str]) -> None:
        for line in stream:
            self._lines.put(line)
        self._lines.put(None)

    def _pump_stderr(self, stream: IO[str]) -> None:
        for line in stream:
            self._stderr_tail.append(line.rstrip())
            del self._stderr_tail[:-STDERR_TAIL_LINES]

    def request(self, method: str, params: dict[str, Any], *, step: str) -> dict[str, Any]:
        self._next_id += 1
        request_id = self._next_id
        self._send(step, {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        message = self._read_response(step, request_id)
        if "error" in message:
            raise SmokeFailureError(
                step, f"{method} returned an error: {json.dumps(message['error'])}"
            )
        result = message.get("result")
        if not isinstance(result, dict):
            raise SmokeFailureError(step, f"{method} response has no result object")
        return result

    def notify(self, method: str, *, step: str) -> None:
        self._send(step, {"jsonrpc": "2.0", "method": method, "params": {}})

    def close(self) -> None:
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait()

    def _send(self, step: str, payload: dict[str, Any]) -> None:
        assert self._proc.stdin is not None
        try:
            self._proc.stdin.write(json.dumps(payload) + "\n")
            self._proc.stdin.flush()
        except OSError as exc:
            detail = f"server stopped accepting input ({exc}){self._stderr()}"
            raise SmokeFailureError(step, detail) from exc

    def _read_response(self, step: str, request_id: int) -> dict[str, Any]:
        deadline = time.monotonic() + self._timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SmokeFailureError(step, f"no response within {self._timeout:g}s")
            try:
                line = self._lines.get(timeout=remaining)
            except queue.Empty:
                raise SmokeFailureError(step, f"no response within {self._timeout:g}s") from None
            if line is None:
                raise SmokeFailureError(step, f"server exited before responding{self._stderr()}")
            try:
                message: Any = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(message, dict) and message.get("id") == request_id:
                return message

    def _stderr(self) -> str:
        if not self._stderr_tail:
            return ""
        return "; server stderr: " + " | ".join(self._stderr_tail[-5:])


def _start_pump(stream: IO[str] | None, target: Callable[[IO[str]], None]) -> None:
    assert stream is not None
    threading.Thread(target=target, args=(stream,), daemon=True).start()


def load_blender_server(path: Path) -> tuple[list[str], dict[str, str]]:
    """Return the ``blender`` server's argv and environment from an .mcp.json file."""
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SmokeFailureError("preflight", f"cannot read {path}: {exc}") from exc
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    server = servers.get(SERVER_NAME) if isinstance(servers, dict) else None
    if not isinstance(server, dict) or not isinstance(server.get("command"), str):
        raise SmokeFailureError("preflight", f"{path} has no mcpServers.{SERVER_NAME}.command")
    args = server.get("args", [])
    if not isinstance(args, list):
        raise SmokeFailureError("preflight", f"mcpServers.{SERVER_NAME}.args must be a list")
    command = [server["command"], *(str(arg) for arg in args)]
    env = dict(os.environ)
    extra = server.get("env", {})
    if isinstance(extra, dict):
        env.update({str(key): str(value) for key, value in extra.items()})
    return command, env


def _text_of(result: dict[str, Any]) -> str:
    content = result.get("content")
    if not isinstance(content, list):
        return ""
    return "\n".join(
        str(block.get("text", ""))
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    )


def run_smoke(
    command: list[str], env: dict[str, str], timeout: float, *, log: Callable[[str], None]
) -> None:
    session = StdioSession(command, env, timeout)
    try:
        session.request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "smoke-blender-mcp", "version": "1.0.0"},
            },
            step="initialize",
        )
        session.notify("notifications/initialized", step="initialize")
        log("OK initialize: stdio MCP session established")

        listed = session.request("tools/list", {}, step="tools_list")
        tools = listed.get("tools")
        names = [
            str(tool.get("name"))
            for tool in (tools if isinstance(tools, list) else [])
            if isinstance(tool, dict)
        ]
        if TOOL_NAME not in names:
            raise SmokeFailureError(
                "tools_list", f"{TOOL_NAME} not offered (saw: {', '.join(names)})"
            )
        log(f"OK tools_list: {TOOL_NAME} offered")

        result = session.request(
            "tools/call",
            {"name": TOOL_NAME, "arguments": {"code": PROBE_CODE}},
            step="execute",
        )
        text = _text_of(result)
        if NOT_CONNECTED_PATTERN.search(text):
            reply = text.strip()[:300]
            raise BlenderUnreachableError(f"Blender reports it could not be reached: {reply}")
        if result.get("isError") is True:
            raise SmokeFailureError(
                "execute", f"{TOOL_NAME} reported an error: {text.strip()[:300]}"
            )
        if not VERSION_PATTERN.search(text):
            raise SmokeFailureError(
                "execute", f"no Blender version string in reply: {text[:300]!r}"
            )
        log(f"OK execute: Blender reports {text.strip()[:80]}")
    finally:
        session.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke-test the Blender MCP server over stdio.")
    parser.add_argument("--mcp-json", type=Path, default=DEFAULT_MCP_JSON, help=".mcp.json path")
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_S,
        help="seconds to wait for each reply",
    )
    args = parser.parse_args(argv)

    try:
        command, env = load_blender_server(args.mcp_json)
        run_smoke(command, env, args.timeout, log=print)
    except BlenderUnreachableError as exc:
        print(f"UNREACHABLE: {exc.args[0]}. {REMEDIATION}", file=sys.stderr)
        return EXIT_UNREACHABLE
    except SmokeFailureError as exc:
        print(f"FAIL {exc.step}: {exc.detail}", file=sys.stderr)
        return EXIT_FAILED

    print("PASS blender smoke: execute_blender_code returned the Blender version")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
