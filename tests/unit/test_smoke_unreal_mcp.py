"""Unit tests for scripts/smoke-unreal-mcp.py against a threaded stub MCP endpoint (issue #68, AC4).

The stub speaks streamable HTTP: JSON or SSE replies, an Mcp-Session-Id that every later request
must echo, and toolset dispatch through list_toolsets / describe_toolset / call_tool. It names
its toolset arguments differently from the script's defaults, so the tests also cover the
inputSchema-driven argument resolution.
"""

from __future__ import annotations

import importlib.util
import json
import socket
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from _scaffold_contract import REPO_ROOT

SESSION_ID = "sess-smoke-test"
SCRIPT = REPO_ROOT / "scripts" / "smoke-unreal-mcp.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("smoke_unreal_mcp", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Dataclasses resolve their module through sys.modules while the class is built.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


smoke = _load_script()


@dataclass
class StubUnreal:
    """Scripted behaviour for the stub endpoint, plus a call log the tests inspect."""

    native_python: bool = False
    engine_version: str = "5.8.4"
    import_result: str = "SMOKE_IMPORT_EXISTS=True"
    delete_result: str = "SMOKE_DIR_GONE=True"
    rpc_methods: list[str] = field(default_factory=list)
    tool_calls: list[str] = field(default_factory=list)
    python_steps: list[str] = field(default_factory=list)


def _ok(message: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message["id"], "result": result}


def _text_result(text: str, *, is_error: bool = False) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def _tool_list(native: bool) -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = [
        {"name": "list_toolsets", "inputSchema": {"type": "object", "properties": {}}},
        {
            "name": "describe_toolset",
            "inputSchema": {
                "type": "object",
                "properties": {"toolset_name": {"type": "string"}},
                "required": ["toolset_name"],
            },
        },
        {
            "name": "call_tool",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "toolset_name": {"type": "string"},
                    "tool_name": {"type": "string"},
                    "args": {"type": "object"},
                },
                "required": ["toolset_name", "tool_name", "args"],
            },
        },
    ]
    if native:
        tools.append(
            {
                "name": "execute_python_code",
                "inputSchema": {
                    "type": "object",
                    "properties": {"code": {"type": "string"}},
                    "required": ["code"],
                },
            }
        )
    return tools


def _run_python(behaviour: StubUnreal, code: str) -> str:
    if "get_engine_version" in code:
        behaviour.python_steps.append("engine")
        return behaviour.engine_version
    if "import_asset_tasks" in code:
        behaviour.python_steps.append("import")
        return behaviour.import_result
    if "delete_directory" in code:
        behaviour.python_steps.append("delete")
        return behaviour.delete_result
    return "unknown code"


def _handler_for(behaviour: StubUnreal) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:
            return

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            message: dict[str, Any] = json.loads(self.rfile.read(length))
            method = str(message.get("method", ""))
            behaviour.rpc_methods.append(method)
            if method == "initialize":
                result = {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "stub-unreal", "version": "0"},
                }
                self._json(200, _ok(message, result), session=SESSION_ID)
                return
            if self.headers.get("Mcp-Session-Id") != SESSION_ID:
                self._json(400, {"error": "missing or wrong Mcp-Session-Id"})
                return
            if method == "notifications/initialized":
                self._empty(202)
                return
            if method == "tools/list":
                self._json(200, _ok(message, {"tools": _tool_list(behaviour.native_python)}))
                return
            if method == "tools/call":
                self._call(message)
                return
            self._json(200, {"jsonrpc": "2.0", "id": message.get("id"), "error": {"code": -1}})

        def _call(self, message: dict[str, Any]) -> None:
            params = message["params"]
            name = str(params["name"])
            args = params.get("arguments") or {}
            behaviour.tool_calls.append(name)
            if name == "list_toolsets":
                toolsets = {
                    "toolsets": [
                        {"name": "Unrelated", "description": "not the one"},
                        {"name": "VibeUE_Editor", "description": "VibeUE editor toolset"},
                    ]
                }
                # SSE reply on purpose, so the script's SSE parsing is exercised.
                self._sse(_ok(message, _text_result(json.dumps(toolsets))))
                return
            if name == "describe_toolset":
                if args.get("toolset_name") != "VibeUE_Editor":
                    self._json(200, _ok(message, _text_result("unknown toolset", is_error=True)))
                    return
                described = {
                    "tools": [
                        {
                            "name": "execute_python_code",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"code": {"type": "string"}},
                                "required": ["code"],
                            },
                        }
                    ]
                }
                self._json(200, _ok(message, _text_result(json.dumps(described))))
                return
            if name == "call_tool":
                inner = args.get("args") or {}
                if args.get("tool_name") != "execute_python_code":
                    self._json(200, _ok(message, _text_result("unknown tool", is_error=True)))
                    return
                output = _run_python(behaviour, str(inner.get("code", "")))
                self._json(200, _ok(message, _text_result(output)))
                return
            if name == "execute_python_code":
                output = _run_python(behaviour, str(args.get("code", "")))
                self._json(200, _ok(message, _text_result(output)))
                return
            self._json(200, _ok(message, _text_result(f"unknown tool {name}", is_error=True)))

        def _json(self, status: int, body: dict[str, Any], session: str | None = None) -> None:
            data = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            if session is not None:
                self.send_header("Mcp-Session-Id", session)
            self.end_headers()
            self.wfile.write(data)

        def _sse(self, body: dict[str, Any]) -> None:
            data = f"event: message\ndata: {json.dumps(body)}\n\n".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _empty(self, status: int) -> None:
            self.send_response(status)
            self.send_header("Content-Length", "0")
            self.end_headers()

    return Handler


@contextmanager
def serve_stub(behaviour: StubUnreal) -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_for(behaviour))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/mcp"
    finally:
        server.shutdown()
        server.server_close()


def _closed_port_url() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return f"http://127.0.0.1:{port}/mcp"


@pytest.fixture
def fbx(tmp_path: Path) -> Path:
    path = tmp_path / "SM_SmokeCube.fbx"
    path.write_bytes(b"stub fbx")
    return path


def test_passes_with_vibeue_toolset_reached_through_call_tool(
    fbx: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    behaviour = StubUnreal()
    with serve_stub(behaviour) as url:
        code = smoke.main(["--url", url, "--fbx", str(fbx)])
    out, err = capsys.readouterr()
    assert code == 0, err
    assert "PASS unreal smoke" in out
    assert behaviour.python_steps == ["engine", "import", "delete"]
    assert "list_toolsets" in behaviour.tool_calls
    assert behaviour.rpc_methods[0] == "initialize"


def test_native_execute_python_code_is_called_directly(
    fbx: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    behaviour = StubUnreal(native_python=True)
    with serve_stub(behaviour) as url:
        code = smoke.main(["--url", url, "--fbx", str(fbx)])
    _, err = capsys.readouterr()
    assert code == 0, err
    assert behaviour.python_steps == ["engine", "import", "delete"]
    assert "list_toolsets" not in behaviour.tool_calls
    assert "execute_python_code" in behaviour.tool_calls


def test_failed_import_check_names_step_and_still_cleans_up(
    fbx: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    behaviour = StubUnreal(import_result="SMOKE_IMPORT_EXISTS=False")
    with serve_stub(behaviour) as url:
        code = smoke.main(["--url", url, "--fbx", str(fbx)])
    _, err = capsys.readouterr()
    assert code == 1
    assert "FAIL import_check" in err
    assert behaviour.python_steps == ["engine", "import", "delete"]


def test_engine_version_mismatch_fails_engine_step(
    fbx: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    behaviour = StubUnreal(engine_version="5.7.3")
    with serve_stub(behaviour) as url:
        code = smoke.main(["--url", url, "--fbx", str(fbx)])
    _, err = capsys.readouterr()
    assert code == 1
    assert "FAIL engine_version" in err
    assert behaviour.python_steps == ["engine"]


def test_unreachable_endpoint_exits_2_naming_start_script(
    fbx: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = smoke.main(["--url", _closed_port_url(), "--fbx", str(fbx)])
    _, err = capsys.readouterr()
    assert code == 2
    assert "UNREACHABLE" in err
    assert "scripts/start-unreal-mcp.sh" in err


def test_missing_fbx_fails_preflight(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = smoke.main(["--url", _closed_port_url(), "--fbx", str(tmp_path / "missing.fbx")])
    _, err = capsys.readouterr()
    assert code == 1
    assert "FAIL preflight" in err
