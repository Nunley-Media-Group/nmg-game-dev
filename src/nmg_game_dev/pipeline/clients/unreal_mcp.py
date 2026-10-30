"""Unreal MCP client for the ``import_ue`` finalize step (#69, FR6).

Speaks streamable-HTTP JSON-RPC to the Unreal MCP endpoint that UE 5.8's editor serves at
``http://127.0.0.1:$UE_MCP_PORT/mcp`` (default port 8000). Epic's native
``execute_python_code`` tool is used when the server publishes it. Otherwise the client finds
VibeUE's toolset through ``list_toolsets`` / ``describe_toolset`` and calls the tool through
``call_tool``. Calls are strictly sequential because the native server runs tools on the game
thread, so one lock serializes every request.

Stdout is never written here. stdout is the MCP channel for other tools.
"""

from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Final, NoReturn, cast

from nmg_game_dev.pipeline.errors import PipelineError

PROTOCOL_VERSION: Final = "2025-06-18"
DEFAULT_PORT: Final = "8000"
DEFAULT_TIMEOUT_S: Final = 120.0
_STAGE: Final = "import_ue"
_CLIENT_NAME: Final = "nmg-game-dev-finalize"
_CLIENT_VERSION: Final = "1.0.0"
_ERROR_BODY_CHARS: Final = 300

_CODE_ARG_NAMES: Final = ("code", "script", "python_code", "source")
_TOOLSET_ARG_NAMES: Final = ("toolset", "toolset_name", "name")
_TOOL_ARG_NAMES: Final = ("tool", "tool_name", "name")
_ARGUMENTS_ARG_NAMES: Final = ("arguments", "args", "params")
_REQUIRED_VIBEUE_TOOLS: Final = ("list_toolsets", "describe_toolset", "call_tool")

_UNREACHABLE_REMEDIATION: Final = (
    "Run scripts/start-unreal-mcp.sh, wait for the UE 5.8 editor to finish loading, and confirm "
    "UE_MCP_PORT matches the port the editor serves (default 8000)."
)
_FAILED_REMEDIATION: Final = (
    "Read the Unreal MCP error text above. Confirm the editor is idle, the project loaded the "
    "nmg-game-dev plugin, and VibeUE provides execute_python_code on the endpoint."
)

JsonObject = dict[str, Any]


def default_url() -> str:
    """Return ``http://127.0.0.1:$UE_MCP_PORT/mcp``, falling back to port 8000."""
    port = os.environ.get("UE_MCP_PORT", "").strip() or DEFAULT_PORT
    return f"http://127.0.0.1:{port}/mcp"


def _fail(code: str, message: str, remediation: str) -> NoReturn:
    raise PipelineError(code=code, message=message, remediation=remediation, stage=_STAGE)


@dataclass(frozen=True)
class _Reply:
    content_type: str
    session: str | None
    body: str


@dataclass(frozen=True)
class _PythonRoute:
    """How ``execute_python_code`` is reached: a native tool, or VibeUE's ``call_tool``."""

    tool: str
    code_arg: str
    toolset: str | None = None
    toolset_arg: str = "toolset"
    tool_arg: str = "tool"
    arguments_arg: str = "arguments"


class UnrealMcpClient:
    """Sequential streamable-HTTP client that runs UE Python through the Unreal MCP endpoint.

    Parameters:
        url: Full endpoint URL. Defaults to ``http://127.0.0.1:$UE_MCP_PORT/mcp``.
        timeout: Per-request timeout in seconds. Editor imports can be slow.

    Connection failures raise ``mcp.unreal.unreachable``. Protocol, HTTP, and tool errors raise
    ``import_ue.failed``. Both carry ``stage="import_ue"``.
    """

    def __init__(self, url: str | None = None, *, timeout: float = DEFAULT_TIMEOUT_S) -> None:
        self._url: Final = url if url is not None else default_url()
        self._timeout: Final = timeout
        self._lock = threading.Lock()
        self._session: str | None = None
        self._initialized = False
        self._route: _PythonRoute | None = None
        self._next_id = 0

    @property
    def url(self) -> str:
        """The endpoint this client talks to."""
        return self._url

    def __enter__(self) -> UnrealMcpClient:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        """Forget the session so the next call re-initializes. No network traffic."""
        with self._lock:
            self._session = None
            self._initialized = False
            self._route = None

    def execute_python_code(self, code: str) -> str:
        """Run ``code`` as UE Python and return the tool's text output.

        The caller parses the ``NMG_RESULT {json}`` line out of the returned text.
        """
        with self._lock:
            if not self._initialized:
                self._initialize()
            if self._route is None:
                self._route = self._discover_route()
            return self._run(self._route, code)

    # --- session ---------------------------------------------------------------------------

    def _initialize(self) -> None:
        self._rpc(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": _CLIENT_NAME, "version": _CLIENT_VERSION},
            },
        )
        # Notifications have no id and no reply body, so the reply is discarded.
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self._initialized = True

    def _rpc(self, method: str, params: JsonObject) -> JsonObject:
        self._next_id += 1
        request_id = self._next_id
        reply = self._post({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        message = _find_message(reply, request_id, method)
        if message is None:
            _fail(
                "import_ue.failed",
                f"Unreal MCP returned no JSON-RPC response to {method} at {self._url}",
                _FAILED_REMEDIATION,
            )
        if "error" in message:
            _fail(
                "import_ue.failed",
                f"Unreal MCP {method} returned an error: {json.dumps(message['error'])[:500]}",
                _FAILED_REMEDIATION,
            )
        result = message.get("result")
        if not isinstance(result, dict):
            _fail(
                "import_ue.failed",
                f"Unreal MCP {method} response has no result object",
                _FAILED_REMEDIATION,
            )
        return cast(JsonObject, result)

    def _post(self, payload: JsonObject) -> _Reply:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": PROTOCOL_VERSION,
        }
        if self._session is not None:
            headers["Mcp-Session-Id"] = self._session
        request = urllib.request.Request(
            self._url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                reply = _Reply(
                    content_type=response.headers.get("Content-Type", ""),
                    session=response.headers.get("Mcp-Session-Id"),
                    body=response.read().decode("utf-8", errors="replace"),
                )
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")[:_ERROR_BODY_CHARS]
            _fail(
                "import_ue.failed",
                f"Unreal MCP returned HTTP {error.code} from {self._url}: {body}",
                _FAILED_REMEDIATION,
            )
        except TimeoutError as error:
            _fail(
                "import_ue.failed",
                f"Unreal MCP request timed out after {self._timeout:g} s at {self._url}",
                f"Raise the timeout or wait for the editor to finish its current work. ({error})",
            )
        except urllib.error.URLError as error:
            if isinstance(error.reason, TimeoutError):
                _fail(
                    "import_ue.failed",
                    f"Unreal MCP request timed out after {self._timeout:g} s at {self._url}",
                    "Wait for the editor to finish its current work, then retry.",
                )
            _fail(
                "mcp.unreal.unreachable",
                f"Unreal MCP is unreachable at {self._url}: {error.reason}",
                _UNREACHABLE_REMEDIATION,
            )
        except OSError as error:
            _fail(
                "mcp.unreal.unreachable",
                f"Unreal MCP is unreachable at {self._url}: {error}",
                _UNREACHABLE_REMEDIATION,
            )
        if reply.session is not None:
            self._session = reply.session
        return reply

    # --- routing ----------------------------------------------------------------------------

    def _discover_route(self) -> _PythonRoute:
        tools = self._list_tools()
        if "execute_python_code" in tools:
            return _PythonRoute(
                tool="execute_python_code",
                code_arg=_pick_arg(
                    tools["execute_python_code"].get("inputSchema"), _CODE_ARG_NAMES
                ),
            )

        missing = [name for name in _REQUIRED_VIBEUE_TOOLS if name not in tools]
        if missing:
            _fail(
                "import_ue.failed",
                "execute_python_code is not native and the endpoint lacks " + ", ".join(missing),
                "Enable VibeUE in the UE editor project so its toolsets register on the endpoint.",
            )
        call_schema = tools["call_tool"].get("inputSchema")
        describe_schema = tools["describe_toolset"].get("inputSchema")

        listed = self._call_tool("list_toolsets", {})
        toolsets = _json_items(listed, ("toolsets", "items", "toolset_list"))
        candidates = [
            toolset
            for toolset in toolsets
            if "vibeue" in f"{toolset.get('name', '')} {toolset.get('description', '')}".lower()
        ]
        for toolset in candidates:
            name = str(toolset["name"])
            described = self._call_tool(
                "describe_toolset",
                {_pick_arg(describe_schema, _TOOLSET_ARG_NAMES): name},
            )
            for tool in _json_items(described, ("tools", "items")):
                if tool.get("name") == "execute_python_code":
                    return _PythonRoute(
                        tool="execute_python_code",
                        code_arg=_pick_arg(tool.get("inputSchema"), _CODE_ARG_NAMES),
                        toolset=name,
                        toolset_arg=_pick_arg(call_schema, _TOOLSET_ARG_NAMES),
                        tool_arg=_pick_arg(call_schema, _TOOL_ARG_NAMES),
                        arguments_arg=_pick_arg(call_schema, _ARGUMENTS_ARG_NAMES),
                    )
        seen = ", ".join(str(toolset.get("name")) for toolset in toolsets) or "none"
        _fail(
            "import_ue.failed",
            f"no VibeUE toolset provides execute_python_code (toolsets seen: {seen})",
            _FAILED_REMEDIATION,
        )

    def _list_tools(self) -> dict[str, JsonObject]:
        result = self._rpc("tools/list", {})
        tools = result.get("tools")
        if not isinstance(tools, list):
            _fail("import_ue.failed", "tools/list returned no tools array", _FAILED_REMEDIATION)
        return {
            str(tool["name"]): cast(JsonObject, tool)
            for tool in tools
            if isinstance(tool, dict) and isinstance(tool.get("name"), str)
        }

    def _run(self, route: _PythonRoute, code: str) -> str:
        if route.toolset is None:
            return self._call_tool(route.tool, {route.code_arg: code})
        return self._call_tool(
            "call_tool",
            {
                route.toolset_arg: route.toolset,
                route.tool_arg: route.tool,
                route.arguments_arg: {route.code_arg: code},
            },
        )

    def _call_tool(self, name: str, arguments: JsonObject) -> str:
        result = self._rpc("tools/call", {"name": name, "arguments": arguments})
        text = _text_of(result)
        if result.get("isError") is True:
            _fail(
                "import_ue.failed",
                f"Unreal MCP tool {name} reported an error: {text[:500]}",
                _FAILED_REMEDIATION,
            )
        return text


def _find_message(reply: _Reply, request_id: int, method: str) -> JsonObject | None:
    """Return the JSON-RPC response with ``request_id`` from a JSON or SSE reply body."""
    chunks: list[str]
    if "text/event-stream" in reply.content_type:
        chunks = [
            line[len("data:") :].strip()
            for line in reply.body.splitlines()
            if line.startswith("data:") and line[len("data:") :].strip()
        ]
    elif reply.body.strip():
        chunks = [reply.body]
    else:
        return None
    for chunk in chunks:
        try:
            decoded: Any = json.loads(chunk)
        except json.JSONDecodeError as error:
            _fail(
                "import_ue.failed",
                f"Unreal MCP reply to {method} is not valid JSON: {error}",
                _FAILED_REMEDIATION,
            )
        messages = decoded if isinstance(decoded, list) else [decoded]
        for message in messages:
            if isinstance(message, dict) and message.get("id") == request_id:
                return cast(JsonObject, message)
    return None


def _text_of(result: JsonObject) -> str:
    """Join the text blocks of a ``tools/call`` result, plus any structured content."""
    parts: list[str] = []
    content = result.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
    if "structuredContent" in result:
        parts.append(json.dumps(result["structuredContent"]))
    return "\n".join(parts)


def _json_items(text: str, keys: tuple[str, ...]) -> list[JsonObject]:
    """Return the named-object list inside a JSON tool reply, or ``[]`` when unparseable."""
    try:
        data: Any = json.loads(text)
    except json.JSONDecodeError:
        return []
    items: Any = data
    if isinstance(data, dict):
        items = next((data[key] for key in keys if isinstance(data.get(key), list)), [])
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict) and isinstance(item.get("name"), str)]


def _pick_arg(schema: object, preferred: tuple[str, ...]) -> str:
    """Choose an argument name from a tool's ``inputSchema``, falling back to ``preferred``."""
    properties: dict[str, object] = {}
    required: list[object] = []
    if isinstance(schema, dict):
        if isinstance(schema.get("properties"), dict):
            properties = cast(dict[str, object], schema["properties"])
        if isinstance(schema.get("required"), list):
            required = cast(list[object], schema["required"])
    for choice in preferred:
        if choice in properties:
            return choice
    for needed in required:
        if isinstance(needed, str):
            return needed
    if properties:
        return next(iter(properties))
    return preferred[0]
