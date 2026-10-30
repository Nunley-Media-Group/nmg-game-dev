"""UnrealMcpClient against a stub streamable-HTTP MCP endpoint (#69, FR6).

The stub server speaks the subset of MCP the client uses: initialize, notifications, tools/list,
and tools/call. It records every request so the tests can check sessions and routing. No
network beyond 127.0.0.1 is used.
"""

from __future__ import annotations

import json
import socket
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from nmg_game_dev.pipeline.clients.unreal_mcp import UnrealMcpClient, default_url
from nmg_game_dev.pipeline.errors import PipelineError

JsonObject = dict[str, Any]


@dataclass
class _Scripted:
    """What the stub endpoint answers. Tests mutate it before the client connects."""

    tools: list[JsonObject] = field(default_factory=list)
    outputs: dict[str, Callable[[JsonObject], str]] = field(default_factory=dict)
    error_tools: set[str] = field(default_factory=set)
    sse: bool = False
    http_status: int | None = None
    requests: list[tuple[str, dict[str, str]]] = field(default_factory=list)
    calls: list[tuple[str, JsonObject]] = field(default_factory=list)
    initializations: int = 0

    def respond(self, method: str, params: JsonObject) -> tuple[JsonObject, str | None]:
        if method == "initialize":
            self.initializations += 1
            return (
                {"protocolVersion": "2025-06-18", "capabilities": {}, "serverInfo": {}},
                "sess-1",
            )
        if method == "tools/list":
            return {"tools": self.tools}, None
        if method == "tools/call":
            name = str(params["name"])
            arguments = params.get("arguments", {})
            self.calls.append((name, arguments))
            text = self.outputs[name](arguments) if name in self.outputs else ""
            result: JsonObject = {"content": [{"type": "text", "text": text}]}
            if name in self.error_tools:
                result["isError"] = True
            return result, None
        raise AssertionError(f"unexpected MCP method {method}")


class _Handler(BaseHTTPRequestHandler):
    server: _StubServer

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - base signature
        return

    def do_POST(self) -> None:
        state = self.server.state
        length = int(self.headers.get("Content-Length", "0"))
        payload: JsonObject = json.loads(self.rfile.read(length) or b"{}")
        method = str(payload.get("method", ""))
        state.requests.append((method, {key.lower(): value for key, value in self.headers.items()}))

        if state.http_status is not None:
            body = b"upstream exploded"
            self.send_response(state.http_status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if method == "notifications/initialized":
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        result, session = state.respond(method, payload.get("params", {}))
        envelope: JsonObject = {"jsonrpc": "2.0", "id": payload["id"], "result": result}
        if state.sse:
            body = f"event: message\ndata: {json.dumps(envelope)}\n\n".encode()
            content_type = "text/event-stream"
        else:
            body = json.dumps(envelope).encode()
            content_type = "application/json"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        if session is not None:
            self.send_header("Mcp-Session-Id", session)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _StubServer(ThreadingHTTPServer):
    state: _Scripted


@pytest.fixture
def stub() -> Iterator[tuple[str, _Scripted]]:
    server = _StubServer(("127.0.0.1", 0), _Handler)
    server.state = _Scripted()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/mcp", server.state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _native_tool() -> JsonObject:
    return {
        "name": "execute_python_code",
        "inputSchema": {"type": "object", "properties": {"code": {"type": "string"}}},
    }


def _vibeue_tools() -> list[JsonObject]:
    return [
        {
            "name": "list_toolsets",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "describe_toolset",
            "inputSchema": {
                "type": "object",
                "properties": {"toolset": {"type": "string"}},
                "required": ["toolset"],
            },
        },
        {
            "name": "call_tool",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "toolset": {"type": "string"},
                    "tool": {"type": "string"},
                    "arguments": {"type": "object"},
                },
            },
        },
    ]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def test_native_execute_python_code_returns_text_and_reuses_session(
    stub: tuple[str, _Scripted],
) -> None:
    url, state = stub
    state.tools = [_native_tool()]
    state.outputs["execute_python_code"] = lambda args: 'NMG_RESULT {"ok": true}'

    with UnrealMcpClient(url) as client:
        first = client.execute_python_code("print('hi')")
        second = client.execute_python_code("print('again')")

    assert first == 'NMG_RESULT {"ok": true}'
    assert second == 'NMG_RESULT {"ok": true}'
    assert state.initializations == 1
    assert state.calls == [
        ("execute_python_code", {"code": "print('hi')"}),
        ("execute_python_code", {"code": "print('again')"}),
    ]
    methods = [method for method, _ in state.requests]
    assert methods == [
        "initialize",
        "notifications/initialized",
        "tools/list",
        "tools/call",
        "tools/call",
    ]
    later_headers = state.requests[-1][1]
    assert later_headers["mcp-session-id"] == "sess-1"
    assert later_headers["mcp-protocol-version"] == "2025-06-18"


def test_sse_replies_are_parsed(stub: tuple[str, _Scripted]) -> None:
    url, state = stub
    state.sse = True
    state.tools = [_native_tool()]
    state.outputs["execute_python_code"] = lambda args: "from sse"

    with UnrealMcpClient(url) as client:
        assert client.execute_python_code("x = 1") == "from sse"


def test_vibeue_route_calls_through_call_tool(stub: tuple[str, _Scripted]) -> None:
    url, state = stub
    state.tools = _vibeue_tools()
    state.outputs["list_toolsets"] = lambda args: json.dumps(
        {"toolsets": [{"name": "VibeUE", "description": "VibeUE toolsets"}]}
    )
    state.outputs["describe_toolset"] = lambda args: json.dumps(
        {"tools": [{"name": "execute_python_code", "inputSchema": {"properties": {"code": {}}}}]}
    )
    state.outputs["call_tool"] = lambda args: "wrapped output NMG_RESULT {}"

    with UnrealMcpClient(url) as client:
        text = client.execute_python_code("import unreal")

    assert text == "wrapped output NMG_RESULT {}"
    assert ("list_toolsets", {}) in state.calls
    assert ("describe_toolset", {"toolset": "VibeUE"}) in state.calls
    call_name, call_args = state.calls[-1]
    assert call_name == "call_tool"
    assert call_args == {
        "toolset": "VibeUE",
        "tool": "execute_python_code",
        "arguments": {"code": "import unreal"},
    }


def test_no_python_route_is_import_ue_failed(stub: tuple[str, _Scripted]) -> None:
    url, state = stub
    state.tools = [{"name": "get_scene", "inputSchema": {"type": "object"}}]

    with UnrealMcpClient(url) as client, pytest.raises(PipelineError) as raised:
        client.execute_python_code("print(1)")

    assert raised.value.code == "import_ue.failed"
    assert raised.value.stage == "import_ue"
    assert "execute_python_code" in raised.value.message


def test_vibeue_without_python_tool_is_import_ue_failed(stub: tuple[str, _Scripted]) -> None:
    url, state = stub
    state.tools = _vibeue_tools()
    state.outputs["list_toolsets"] = lambda args: json.dumps(
        {"toolsets": [{"name": "VibeUE", "description": "VibeUE"}]}
    )
    state.outputs["describe_toolset"] = lambda args: json.dumps({"tools": []})

    with UnrealMcpClient(url) as client, pytest.raises(PipelineError) as raised:
        client.execute_python_code("print(1)")

    assert raised.value.code == "import_ue.failed"


def test_tool_error_is_import_ue_failed(stub: tuple[str, _Scripted]) -> None:
    url, state = stub
    state.tools = [_native_tool()]
    state.outputs["execute_python_code"] = lambda args: "Traceback: boom"
    state.error_tools.add("execute_python_code")

    with UnrealMcpClient(url) as client, pytest.raises(PipelineError) as raised:
        client.execute_python_code("raise RuntimeError('boom')")

    assert raised.value.code == "import_ue.failed"
    assert "Traceback: boom" in raised.value.message


def test_http_error_is_import_ue_failed(stub: tuple[str, _Scripted]) -> None:
    url, state = stub
    state.http_status = 500

    with UnrealMcpClient(url) as client, pytest.raises(PipelineError) as raised:
        client.execute_python_code("print(1)")

    assert raised.value.code == "import_ue.failed"
    assert "HTTP 500" in raised.value.message


def test_unreachable_endpoint_is_mcp_unreal_unreachable(capsys: pytest.CaptureFixture[str]) -> None:
    url = f"http://127.0.0.1:{_free_port()}/mcp"

    with UnrealMcpClient(url, timeout=5) as client, pytest.raises(PipelineError) as raised:
        client.execute_python_code("print(1)")

    assert raised.value.code == "mcp.unreal.unreachable"
    assert raised.value.stage == "import_ue"
    assert "start-unreal-mcp.sh" in raised.value.remediation
    assert capsys.readouterr().out == ""


def test_close_forgets_the_session(stub: tuple[str, _Scripted]) -> None:
    url, state = stub
    state.tools = [_native_tool()]
    state.outputs["execute_python_code"] = lambda args: "ok"

    client = UnrealMcpClient(url)
    client.execute_python_code("print(1)")
    client.close()
    client.execute_python_code("print(2)")
    client.close()

    assert state.initializations == 2


def test_default_url_reads_ue_mcp_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UE_MCP_PORT", raising=False)
    assert default_url() == "http://127.0.0.1:8000/mcp"
    monkeypatch.setenv("UE_MCP_PORT", "9123")
    assert default_url() == "http://127.0.0.1:9123/mcp"
    assert UnrealMcpClient().url == "http://127.0.0.1:9123/mcp"
    monkeypatch.setenv("UE_MCP_PORT", "")
    assert default_url() == "http://127.0.0.1:8000/mcp"
