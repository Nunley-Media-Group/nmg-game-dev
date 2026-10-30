#!/usr/bin/env python3
"""Smoke-test VibeUE through Epic's native Unreal MCP endpoint on UE 5.8.

Usage:  scripts/smoke-unreal-mcp.py [--url URL] [--fbx PATH]

Start the editor first with scripts/start-unreal-mcp.sh. Then the script:

1. initializes an MCP session over streamable HTTP (JSON or SSE replies);
2. lists tools, and when ``execute_python_code`` is not native, finds a VibeUE toolset
   that provides it through ``list_toolsets`` / ``describe_toolset`` / ``call_tool``;
3. runs ``execute_python_code`` and checks the engine version contains ``5.8``;
4. imports fixtures/smoke/SM_SmokeCube.fbx into /Game/__NmgSmoke and checks the static mesh;
5. deletes /Game/__NmgSmoke and checks it is gone. Step 5 also runs after a failure in step 4.

Tool argument names come from each tool's ``inputSchema`` when the server publishes one, so
the script adapts to the names the server uses. Calls are strictly sequential because the
native server runs tools on the game thread.

Exit codes:
  0  every check passed
  1  a check failed; stderr shows ``FAIL <step>: <detail>``
  2  the endpoint is unreachable; stderr says to run scripts/start-unreal-mcp.sh

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROTOCOL_VERSION = "2025-06-18"
ENGINE_VERSION = "5.8"
SMOKE_DIR = "/Game/__NmgSmoke"
SMOKE_ASSET = f"{SMOKE_DIR}/SM_SmokeCube"
DEFAULT_PORT = "8000"
REQUEST_TIMEOUT_S = 120.0

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FBX = REPO_ROOT / "fixtures" / "smoke" / "SM_SmokeCube.fbx"

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_UNREACHABLE = 2

CODE_ARG_NAMES = ("code", "script", "python_code", "source")
TOOLSET_ARG_NAMES = ("toolset", "toolset_name", "name")
TOOL_ARG_NAMES = ("tool", "tool_name", "name")
ARGUMENTS_ARG_NAMES = ("arguments", "args", "params")

JsonObject = dict[str, Any]


class SmokeFailureError(Exception):
    """A check failed. ``step`` names the check that failed."""

    def __init__(self, step: str, detail: str) -> None:
        super().__init__(f"{step}: {detail}")
        self.step = step
        self.detail = detail


class EndpointUnreachableError(Exception):
    """The HTTP endpoint could not be reached at all."""


@dataclass(frozen=True)
class PythonRoute:
    """How ``execute_python_code`` is reached: as a native tool, or through ``call_tool``."""

    tool: str
    code_arg: str
    toolset: str | None = None
    toolset_arg: str = "toolset"
    tool_arg: str = "tool"
    arguments_arg: str = "arguments"

    def describe(self) -> str:
        if self.toolset is None:
            return f"native {self.tool}"
        return f"toolset {self.toolset!r} via call_tool"


@dataclass(frozen=True)
class _HttpReply:
    content_type: str
    session: str | None
    body: str


class McpHttpClient:
    """Minimal streamable-HTTP JSON-RPC client for the MCP endpoint."""

    def __init__(self, url: str) -> None:
        self._url = url
        self._session: str | None = None
        self._next_id = 0

    def initialize(self) -> None:
        self.rpc(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "smoke-unreal-mcp", "version": "1.0.0"},
            },
            step="initialize",
        )
        self._post("initialize", {"jsonrpc": "2.0", "method": "notifications/initialized"})

    def rpc(self, method: str, params: JsonObject, *, step: str) -> JsonObject:
        self._next_id += 1
        request_id = self._next_id
        reply = self._post(
            step,
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
        )
        if reply.session is not None:
            self._session = reply.session
        message = _find_message(step, reply, request_id)
        if message is None:
            raise SmokeFailureError(step, f"no JSON-RPC response to {method}")
        if "error" in message:
            raise SmokeFailureError(
                step, f"{method} returned an error: {json.dumps(message['error'])}"
            )
        result = message.get("result")
        if not isinstance(result, dict):
            raise SmokeFailureError(step, f"{method} response has no result object")
        return result

    def call_tool(self, name: str, arguments: JsonObject, *, step: str) -> str:
        result = self.rpc("tools/call", {"name": name, "arguments": arguments}, step=step)
        text = _text_of(result)
        if result.get("isError") is True:
            raise SmokeFailureError(step, f"{name} reported an error: {text[:500]}")
        return text

    def _post(self, step: str, payload: JsonObject) -> _HttpReply:
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
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_S) as response:
                return _HttpReply(
                    content_type=response.headers.get("Content-Type", ""),
                    session=response.headers.get("Mcp-Session-Id"),
                    body=response.read().decode("utf-8", errors="replace"),
                )
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise SmokeFailureError(
                step, f"HTTP {exc.code} from {self._url}: {body[:300]}"
            ) from exc
        except urllib.error.URLError as exc:
            raise EndpointUnreachableError(str(exc.reason)) from exc
        except OSError as exc:
            raise SmokeFailureError(step, f"request to {self._url} failed: {exc}") from exc


def _find_message(step: str, reply: _HttpReply, request_id: int) -> JsonObject | None:
    """Return the JSON-RPC response with ``request_id`` from a JSON or SSE reply."""
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
        except json.JSONDecodeError as exc:
            raise SmokeFailureError(step, f"reply is not valid JSON: {exc}") from exc
        messages = decoded if isinstance(decoded, list) else [decoded]
        for message in messages:
            if isinstance(message, dict) and message.get("id") == request_id:
                return message
    return None


def _text_of(result: JsonObject) -> str:
    """Join the text blocks of a tools/call result, plus any structured content."""
    parts: list[str] = []
    content = result.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
    if "structuredContent" in result:
        parts.append(json.dumps(result["structuredContent"]))
    return "\n".join(parts)


def _json_items(text: str, keys: Sequence[str]) -> list[JsonObject]:
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


def _pick_arg(schema: object, preferred: Sequence[str]) -> str:
    """Choose an argument name from a tool's ``inputSchema``, falling back to ``preferred``."""
    properties: dict[str, object] = {}
    required: list[object] = []
    if isinstance(schema, dict):
        if isinstance(schema.get("properties"), dict):
            properties = schema["properties"]
        if isinstance(schema.get("required"), list):
            required = schema["required"]
    for name in preferred:
        if name in properties:
            return name
    for name in required:
        if isinstance(name, str):
            return name
    if properties:
        return next(iter(properties))
    return preferred[0]


def _discover_tools(client: McpHttpClient) -> dict[str, JsonObject]:
    result = client.rpc("tools/list", {}, step="tools_list")
    tools = result.get("tools")
    if not isinstance(tools, list):
        raise SmokeFailureError("tools_list", "tools/list returned no tools array")
    return {
        tool["name"]: tool
        for tool in tools
        if isinstance(tool, dict) and isinstance(tool.get("name"), str)
    }


def _find_python_route(client: McpHttpClient, tools: dict[str, JsonObject]) -> PythonRoute:
    """Locate execute_python_code: native, or inside a VibeUE toolset."""
    if "execute_python_code" in tools:
        schema = tools["execute_python_code"].get("inputSchema")
        return PythonRoute(
            tool="execute_python_code",
            code_arg=_pick_arg(schema, CODE_ARG_NAMES),
        )

    required = ("list_toolsets", "describe_toolset", "call_tool")
    missing = [name for name in required if name not in tools]
    if missing:
        raise SmokeFailureError(
            "find_toolset",
            f"execute_python_code is not native and the endpoint lacks {', '.join(missing)}",
        )
    call_schema = tools["call_tool"].get("inputSchema")
    describe_schema = tools["describe_toolset"].get("inputSchema")

    listed = client.call_tool("list_toolsets", {}, step="find_toolset")
    toolsets = _json_items(listed, ("toolsets", "items", "toolset_list"))
    candidates = [
        toolset
        for toolset in toolsets
        if "vibeue" in f"{toolset.get('name', '')} {toolset.get('description', '')}".lower()
    ]
    if not candidates:
        seen = ", ".join(str(toolset.get("name")) for toolset in toolsets) or "none"
        raise SmokeFailureError("find_toolset", f"no VibeUE toolset listed (saw: {seen})")

    for toolset in candidates:
        name = str(toolset["name"])
        described = client.call_tool(
            "describe_toolset",
            {_pick_arg(describe_schema, TOOLSET_ARG_NAMES): name},
            step="find_toolset",
        )
        for tool in _json_items(described, ("tools", "items")):
            if tool.get("name") == "execute_python_code":
                return PythonRoute(
                    tool="execute_python_code",
                    code_arg=_pick_arg(tool.get("inputSchema"), CODE_ARG_NAMES),
                    toolset=name,
                    toolset_arg=_pick_arg(call_schema, TOOLSET_ARG_NAMES),
                    tool_arg=_pick_arg(call_schema, TOOL_ARG_NAMES),
                    arguments_arg=_pick_arg(call_schema, ARGUMENTS_ARG_NAMES),
                )
    raise SmokeFailureError(
        "find_toolset",
        "no VibeUE toolset provides execute_python_code (checked: "
        + ", ".join(str(t["name"]) for t in candidates)
        + ")",
    )


def _run_python(client: McpHttpClient, route: PythonRoute, code: str, *, step: str) -> str:
    if route.toolset is None:
        return client.call_tool(route.tool, {route.code_arg: code}, step=step)
    arguments: JsonObject = {
        route.toolset_arg: route.toolset,
        route.tool_arg: route.tool,
        route.arguments_arg: {route.code_arg: code},
    }
    return client.call_tool("call_tool", arguments, step=step)


def _import_code(fbx: Path) -> str:
    return "\n".join(
        [
            "import unreal",
            "task = unreal.AssetImportTask()",
            f"task.filename = {json.dumps(str(fbx))}",
            f"task.destination_path = {json.dumps(SMOKE_DIR)}",
            "task.automated = True",
            "task.save = False",
            "task.replace_existing = True",
            "unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])",
            "print('SMOKE_IMPORT_EXISTS=' + str(unreal.EditorAssetLibrary.does_asset_exist("
            f"{json.dumps(SMOKE_ASSET)})))",
        ]
    )


def _delete_code() -> str:
    return "\n".join(
        [
            "import unreal",
            f"unreal.EditorAssetLibrary.delete_directory({json.dumps(SMOKE_DIR)})",
            "print('SMOKE_DIR_GONE=' + str(not unreal.EditorAssetLibrary.does_directory_exist("
            f"{json.dumps(SMOKE_DIR)})))",
        ]
    )


def _import_and_check(client: McpHttpClient, route: PythonRoute, fbx: Path) -> None:
    output = _run_python(client, route, _import_code(fbx), step="import")
    if "SMOKE_IMPORT_EXISTS=True" not in output:
        raise SmokeFailureError(
            "import_check",
            f"{SMOKE_ASSET} was not found after import; output: {output.strip()[:300]!r}",
        )


def _delete_and_check(client: McpHttpClient, route: PythonRoute) -> None:
    output = _run_python(client, route, _delete_code(), step="delete")
    if "SMOKE_DIR_GONE=True" not in output:
        raise SmokeFailureError(
            "delete_check",
            f"{SMOKE_DIR} still exists after delete_directory; output: {output.strip()[:300]!r}",
        )


def run_smoke(url: str, fbx: Path, *, log: Callable[[str], None]) -> None:
    client = McpHttpClient(url)
    client.initialize()
    log(f"OK initialize: MCP session established at {url}")

    tools = _discover_tools(client)
    route = _find_python_route(client, tools)
    log(f"OK find_toolset: execute_python_code via {route.describe()}")

    version = _run_python(
        client,
        route,
        "import unreal\nprint(unreal.SystemLibrary.get_engine_version())",
        step="engine_version",
    )
    if ENGINE_VERSION not in version:
        raise SmokeFailureError(
            "engine_version",
            f"expected an engine version containing {ENGINE_VERSION!r}; "
            f"got {version.strip()[:200]!r}",
        )
    log(f"OK engine_version: {version.strip()[:80]}")

    # Step 4 failures must not skip step 5: clean up first, then report the first failure.
    import_failure: SmokeFailureError | None = None
    try:
        _import_and_check(client, route, fbx)
        log(f"OK import_check: {SMOKE_ASSET} exists")
    except SmokeFailureError as exc:
        import_failure = exc
    try:
        _delete_and_check(client, route)
        log(f"OK delete_check: {SMOKE_DIR} removed")
    except SmokeFailureError as exc:
        if import_failure is None:
            raise
        print(f"WARN cleanup also failed: {exc}", file=sys.stderr)
    if import_failure is not None:
        raise import_failure


def _default_url() -> str:
    port = os.environ.get("UE_MCP_PORT") or DEFAULT_PORT
    return f"http://127.0.0.1:{port}/mcp"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke-test VibeUE via the Unreal MCP endpoint.")
    parser.add_argument("--url", default=_default_url(), help="MCP endpoint URL")
    parser.add_argument("--fbx", type=Path, default=DEFAULT_FBX, help="FBX to import")
    args = parser.parse_args(argv)

    if not args.fbx.is_file():
        print(
            f"FAIL preflight: smoke FBX not found at {args.fbx}; see fixtures/README.md",
            file=sys.stderr,
        )
        return EXIT_FAILED

    try:
        run_smoke(args.url, args.fbx, log=print)
    except EndpointUnreachableError as exc:
        print(
            f"UNREACHABLE: could not reach {args.url} ({exc}). "
            "Run scripts/start-unreal-mcp.sh first.",
            file=sys.stderr,
        )
        return EXIT_UNREACHABLE
    except SmokeFailureError as exc:
        print(f"FAIL {exc.step}: {exc.detail}", file=sys.stderr)
        return EXIT_FAILED

    print(f"PASS unreal smoke: VibeUE on UE {ENGINE_VERSION} imported and removed {SMOKE_ASSET}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
