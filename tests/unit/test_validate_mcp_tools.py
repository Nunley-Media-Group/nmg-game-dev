"""scripts/validate-mcp-tools.py: tools.json must match what each server registers (#7 FR18)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def validator() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "validate_mcp_tools", REPO / "scripts" / "validate-mcp-tools.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SERVER = '''
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("fake")


@mcp.tool()
def ping(msg: str) -> str:
    """Echo the message back."""
    return msg
'''


def _server_dir(root: Path, tools: list[dict[str, Any]], server_source: str = SERVER) -> Path:
    server_dir = root / "fake-server"
    (server_dir / "src" / "fake_mcp").mkdir(parents=True)
    (server_dir / "src" / "fake_mcp" / "server.py").write_text(server_source)
    (server_dir / "tools.json").write_text(json.dumps({"server": "fake", "tools": tools}))
    return server_dir


PING = {
    "name": "ping",
    "description": "Echo the message back.",
    "inputSchema": {
        "type": "object",
        "properties": {"msg": {"type": "string"}},
        "required": ["msg"],
    },
}


def test_matching_tools_pass(validator: ModuleType, tmp_path: Path) -> None:
    assert validator.check_server(_server_dir(tmp_path, [PING])) == []


def test_a_tool_missing_from_tools_json_fails(validator: ModuleType, tmp_path: Path) -> None:
    problems = validator.check_server(_server_dir(tmp_path, []))
    assert any("missing from tools.json" in p and "ping" in p for p in problems)


def test_a_listed_tool_that_is_not_registered_fails(validator: ModuleType, tmp_path: Path) -> None:
    ghost = {**PING, "name": "ghost"}
    problems = validator.check_server(_server_dir(tmp_path, [PING, ghost]))
    assert any("not registered" in p and "ghost" in p for p in problems)


def test_a_required_parameter_missing_from_the_schema_fails(
    validator: ModuleType, tmp_path: Path
) -> None:
    listed = {
        **PING,
        "inputSchema": {"type": "object", "properties": {}, "required": ["msg", "extra"]},
    }
    problems = validator.check_server(_server_dir(tmp_path, [listed]))
    assert any(
        "lacks required parameter 'msg'" in p or "lacks required parameter 'extra'" in p
        for p in problems
    )
    assert any("'extra'" in p for p in problems)


def test_the_real_repository_is_consistent(
    validator: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    assert validator.main() == 0
