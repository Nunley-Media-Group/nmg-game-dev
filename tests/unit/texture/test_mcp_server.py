"""The texture-gen MCP server: tools, structured errors, and the registered tool list (#7 FR16,
AC20)."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import subprocess
import sys
import types
from pathlib import Path
from types import ModuleType

import pytest

from tests.texture_fakes import APPLE_SILICON_32GB, make_models, save_png, synthetic_image

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


def _set_with_albedo(root: Path, name: str) -> None:
    albedo = save_png(synthetic_image(256), root / name / "z-image-turbo_1_256.png")
    manifest = {
        "name": name,
        "images": [{"backend": "z-image-turbo", "seed": 1, "path": str(albedo)}],
    }
    (root / name / "textures.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_texture_contact_sheet_is_registered_and_declared(server: ModuleType) -> None:
    registered = {tool.name for tool in asyncio.run(server.mcp.list_tools())}
    declared = {tool["name"] for tool in json.loads(TOOLS_JSON.read_text())["tools"]}
    assert "texture_contact_sheet" in registered and "texture_contact_sheet" in declared


def test_texture_contact_sheet_returns_pages_for_the_output_root(
    server: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "out"
    _set_with_albedo(root, "rusted-steel")
    monkeypatch.setenv("NMG_GAME_DEV_TEXTURE_DIR", str(root))
    result = server.texture_contact_sheet()
    assert set(result) == {"pages", "cells", "skipped"}
    assert result == {"pages": [str(root / "contact_sheet_001.png")], "cells": 1, "skipped": []}


def test_texture_contact_sheet_returns_the_structured_error_on_an_empty_root(
    server: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NMG_GAME_DEV_TEXTURE_DIR", str(tmp_path / "empty"))
    result = server.texture_contact_sheet()
    assert set(result) == {"error"}
    assert result["error"]["code"] == "texture.no_texture_sets"
    assert result["error"]["message"] and result["error"]["remediation"]


def test_texture_contact_sheet_needs_no_backend(
    server: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nmg_game_dev.texture import generate, hardware

    def refuse() -> None:
        raise AssertionError("the contact sheet tool must not probe the host")

    monkeypatch.setattr(generate, "probe", refuse)
    monkeypatch.setattr(hardware, "probe", refuse)
    root = tmp_path / "out"
    _set_with_albedo(root, "steel")
    monkeypatch.setenv("NMG_GAME_DEV_TEXTURE_DIR", str(root))
    assert "pages" in server.texture_contact_sheet()


def test_generate_textures_takes_a_prompt_or_requests_but_not_both_or_neither(
    server: ModuleType,
) -> None:
    both = server.generate_textures(prompt="x", requests=[{"prompt": "y"}])
    neither = server.generate_textures()
    for result in (both, neither):
        assert set(result) == {"error"}
        assert result["error"]["code"] == "texture.invalid_request"


def test_a_batch_request_starts_one_queued_job_covering_every_request(
    server: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nmg_game_dev.texture import generate, jobs

    models = make_models(tmp_path / "models")
    monkeypatch.setenv("TEXTURE_GEN_MODELS_DIR", str(models))
    monkeypatch.setenv("NMG_GAME_DEV_TEXTURE_DIR", str(tmp_path / "out"))
    monkeypatch.setattr(generate, "probe", lambda: APPLE_SILICON_32GB)
    monkeypatch.setattr(jobs, "probe", lambda: APPLE_SILICON_32GB)
    spawned: list[list[str]] = []

    class _Runner:
        pid = os.getpid()

    def popen(argv: list[str], **kwargs: object) -> _Runner:
        spawned.append(argv)
        return _Runner()

    shim = types.SimpleNamespace(Popen=popen, DEVNULL=subprocess.DEVNULL)
    monkeypatch.setattr(jobs, "subprocess", shim)

    started = server.generate_textures(
        requests=[
            {"prompt": "burlap", "name": "burlap", "resolution": 256, "seeds": [1, 2]},
            {
                "prompt": "oak",
                "name": "oak",
                "backend": "z-image-turbo",
                "resolution": 256,
                "seeds": [3],
            },
        ]
    )
    assert set(started) == {"job_id"}
    status = server.get_texture_job(started["job_id"])
    assert status["state"] == "queued" and status["total"] == 3
    assert spawned and spawned[0][-2] == "run-queue"


def test_tools_json_declares_requests_as_a_batch_input_and_no_required_prompt() -> None:
    tools = {tool["name"]: tool for tool in json.loads(TOOLS_JSON.read_text())["tools"]}
    schema = tools["generate_textures"]["inputSchema"]
    assert "requests" in schema["properties"]
    assert "prompt" not in schema.get("required", [])
    assert "queue" in tools["generate_textures"]["description"]
