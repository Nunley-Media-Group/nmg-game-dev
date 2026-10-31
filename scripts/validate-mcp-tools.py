#!/usr/bin/env python3
"""Check every MCP server under mcp-servers/ against its tools.json (#7 FR18; gate-mcp-schema).

For each ``mcp-servers/<name>/`` with a ``tools.json``, this imports ``src/*/server.py``, reads the
tools registered on its module-level ``mcp`` (a FastMCP instance), and exits 1 when the names differ
from ``tools.json``, when a registered tool has no description or input schema, or when a required
parameter in ``tools.json`` is missing from the registered schema.

Run it in an environment that has ``mcp`` installed, for example
``uv run python scripts/validate-mcp-tools.py`` from the repository root.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVERS_ROOT = REPO_ROOT / "mcp-servers"


def _load_server(module_path: Path, unique: str) -> ModuleType:
    src_dir = module_path.parents[1]
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    spec = importlib.util.spec_from_file_location(unique, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _registered(module: ModuleType) -> dict[str, dict[str, Any]]:
    server = getattr(module, "mcp", None)
    if server is None:
        raise AttributeError("module has no 'mcp' FastMCP instance")
    tools = asyncio.run(server.list_tools())
    return {
        tool.name: {
            "description": tool.description or "",
            "inputSchema": tool.inputSchema or {},
        }
        for tool in tools
    }


def check_server(server_dir: Path) -> list[str]:
    """Return the list of problems for one server directory (empty when it is consistent)."""
    problems: list[str] = []
    tools_path = server_dir / "tools.json"
    expected: dict[str, Any] = json.loads(tools_path.read_text(encoding="utf-8"))
    expected_tools = {tool["name"]: tool for tool in expected.get("tools", [])}
    module_paths = sorted((server_dir / "src").glob("*/server.py"))
    if len(module_paths) != 1:
        found = len(module_paths)
        return [f"{server_dir.name}: expected exactly one src/*/server.py, found {found}"]
    unique = f"_mcp_check_{server_dir.name.replace('-', '_')}"
    try:
        module = _load_server(module_paths[0], unique)
        registered = _registered(module)
    except Exception as error:  # noqa: BLE001 - report any import or registration failure
        return [f"{server_dir.name}: cannot read registered tools: {error}"]

    missing = sorted(set(expected_tools) - set(registered))
    extra = sorted(set(registered) - set(expected_tools))
    if missing:
        problems.append(f"{server_dir.name}: tools.json lists tools not registered: {missing}")
    if extra:
        problems.append(f"{server_dir.name}: registered tools missing from tools.json: {extra}")
    for name, tool in registered.items():
        if not tool["description"].strip():
            problems.append(f"{server_dir.name}: tool {name} has no description")
        if not tool["inputSchema"]:
            problems.append(f"{server_dir.name}: tool {name} has no input schema")
    for name, spec in expected_tools.items():
        if name not in registered:
            continue
        properties = registered[name]["inputSchema"].get("properties", {})
        for param in spec.get("inputSchema", {}).get("required", []):
            if param not in properties:
                problems.append(f"{server_dir.name}: {name} lacks required parameter {param!r}")
    return problems


def main() -> int:
    problems: list[str] = []
    for server_dir in sorted(SERVERS_ROOT.iterdir()):
        if (server_dir / "tools.json").is_file():
            problems.extend(check_server(server_dir))
    for problem in problems:
        print(f"ERROR: {problem}", file=sys.stderr)
    if problems:
        return 1
    print("MCP tools match tools.json for every server under mcp-servers/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
