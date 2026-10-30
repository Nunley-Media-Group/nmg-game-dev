"""Unit tests for scripts/smoke-blender-mcp.py against a stub stdio MCP server (issue #68, AC5).

Each test writes a stub server script and an .mcp.json that points its ``blender`` entry at it,
then runs the real smoke script against that config. ``STUB_BLENDER_MODE`` selects the behaviour
the stub shows.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import textwrap
from pathlib import Path
from types import ModuleType

import pytest
from _scaffold_contract import REPO_ROOT

SCRIPT = REPO_ROOT / "scripts" / "smoke-blender-mcp.py"

STUB_SERVER = textwrap.dedent(
    """
    import json
    import os
    import sys
    import time

    MODE = os.environ.get("STUB_BLENDER_MODE", "ok")
    print("stub blender server starting", file=sys.stderr, flush=True)
    TOOL_NAMES = ["get_scene_info"] if MODE == "missing_tool" else [
        "get_scene_info",
        "execute_blender_code",
    ]


    def reply(message_id, result):
        print(json.dumps({"jsonrpc": "2.0", "id": message_id, "result": result}), flush=True)


    def text_result(text, is_error=False):
        return {"content": [{"type": "text", "text": text}], "isError": is_error}


    for raw in sys.stdin:
        message = json.loads(raw)
        method = message.get("method")
        if method == "notifications/initialized":
            continue
        if method == "initialize":
            reply(message["id"], {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "stub-blender", "version": "0"},
            })
        elif method == "tools/list":
            tools = [{"name": name, "inputSchema": {"type": "object"}} for name in TOOL_NAMES]
            reply(message["id"], {"tools": tools})
        elif method == "tools/call":
            if MODE == "hang":
                time.sleep(60)
            elif MODE == "disconnected":
                reply(message["id"], text_result(
                    "Error: Could not connect to Blender. Make sure the add-on is running.",
                    is_error=True,
                ))
            else:
                reply(message["id"], text_result("5.2.3 (2026-10-22)"))
    """
)


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("smoke_blender_mcp", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Dataclasses resolve their module through sys.modules while the class is built.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


smoke = _load_script()


def _write_mcp_json(tmp_path: Path, mode: str, *, command: str | None = None) -> Path:
    stub = tmp_path / "stub_blender_server.py"
    stub.write_text(STUB_SERVER, encoding="utf-8")
    config = {
        "mcpServers": {
            "blender": {
                "command": command or sys.executable,
                "args": [str(stub)],
                "env": {"STUB_BLENDER_MODE": mode},
            }
        }
    }
    path = tmp_path / ".mcp.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def test_passes_when_execute_blender_code_reports_version(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mcp_json = _write_mcp_json(tmp_path, "ok")
    code = smoke.main(["--mcp-json", str(mcp_json), "--timeout", "10"])
    out, err = capsys.readouterr()
    assert code == 0, err
    assert "OK tools_list: execute_blender_code offered" in out
    assert "OK execute: Blender reports 5.2.3" in out
    assert "PASS blender smoke" in out


def test_missing_execute_blender_code_fails_tools_list(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mcp_json = _write_mcp_json(tmp_path, "missing_tool")
    code = smoke.main(["--mcp-json", str(mcp_json), "--timeout", "10"])
    _, err = capsys.readouterr()
    assert code == 1
    assert "FAIL tools_list" in err
    assert "execute_blender_code" in err


def test_blender_not_connected_exits_2_with_both_remediations(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mcp_json = _write_mcp_json(tmp_path, "disconnected")
    code = smoke.main(["--mcp-json", str(mcp_json), "--timeout", "10"])
    _, err = capsys.readouterr()
    assert code == 2
    assert "UNREACHABLE" in err
    assert "scripts/install-blender-mcp-addon.sh" in err
    assert "scripts/start-blender-mcp.sh" in err


def test_silent_server_times_out_naming_execute_step(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mcp_json = _write_mcp_json(tmp_path, "hang")
    code = smoke.main(["--mcp-json", str(mcp_json), "--timeout", "1"])
    _, err = capsys.readouterr()
    assert code == 1
    assert "FAIL execute: no response within 1s" in err


def test_unstartable_server_command_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mcp_json = _write_mcp_json(tmp_path, "ok", command=str(tmp_path / "no-such-uvx"))
    code = smoke.main(["--mcp-json", str(mcp_json), "--timeout", "10"])
    _, err = capsys.readouterr()
    assert code == 2
    assert "could not start" in err
    assert "scripts/start-blender-mcp.sh" in err


def test_mcp_json_without_blender_entry_fails_preflight(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mcp_json = tmp_path / ".mcp.json"
    mcp_json.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
    code = smoke.main(["--mcp-json", str(mcp_json)])
    _, err = capsys.readouterr()
    assert code == 1
    assert "FAIL preflight" in err
