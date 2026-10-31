"""The texture-gen MCP server: tools, structured errors, and the registered tool list (#7 FR16,
AC20)."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[3]
SERVER_FILE = REPO / "mcp-servers" / "texture-gen" / "src" / "texture_gen_mcp" / "server.py"
TOOLS_JSON = REPO / "mcp-servers" / "texture-gen" / "tools.json"


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    src = str(SERVER_FILE.parents[1])
    if src not in sys.path:
        sys.path.insert(0, src)
    spec = importlib.util.spec_from_file_location("texture_gen_server_under_test", SERVER_FILE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.delenv("TEXTURE_GEN_MODELS_DIR", raising=False)
    return module


def test_registered_tools_match_tools_json(server: ModuleType) -> None:
    names = {tool.name for tool in asyncio.run(server.mcp.list_tools())}
    assert names == {tool["name"] for tool in json.loads(TOOLS_JSON.read_text())["tools"]}


def test_generate_textures_returns_a_structured_error_for_a_bad_request(server: ModuleType) -> None:
    result = server.generate_textures(prompt="   ")
    assert set(result) == {"error"}
    assert result["error"]["code"] == "texture.invalid_request"
    assert result["error"]["remediation"]


def test_get_texture_job_reports_unknown_jobs_as_errors(
    server: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NMG_GAME_DEV_TEXTURE_DIR", str(tmp_path))
    result = server.get_texture_job("missing")
    assert result["error"]["code"] == "texture.job_not_found"


def test_texture_backends_reports_each_backend(
    server: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nmg_game_dev.texture import generate
    from tests.texture_fakes import APPLE_SILICON_32GB

    monkeypatch.setattr(generate, "probe", lambda: APPLE_SILICON_32GB)
    result = server.texture_backends()
    assert set(result["backends"]) == {"z-image-turbo", "flux2-klein-4b"}
    assert set(result["backends"].values()) <= {"available", "not_installed", "insufficient_memory"}
