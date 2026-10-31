"""The meshy MCP server wraps the same jobs and returns structured errors (#98 FR8, AC13)."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from nmg_game_dev.meshy import jobs
from tests.meshy_fakes import (
    ENV,
    TEST_KEY,
    FakeClock,
    FakeMeshy,
    FakeSession,
    RecordingSpawn,
    run_job,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
SERVER_DIR = REPO_ROOT / "mcp-servers" / "meshy"


def _load_server() -> ModuleType:
    src = str(SERVER_DIR / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    spec = importlib.util.spec_from_file_location(
        "_meshy_mcp_server_under_test", SERVER_DIR / "src" / "meshy_mcp" / "server.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


server = _load_server()


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("MESHY_API_KEY", TEST_KEY)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(jobs, "BlenderSessionClient", lambda: FakeSession())
    monkeypatch.setattr(jobs, "default_spawn", RecordingSpawn())
    return tmp_path


def _tools() -> dict[str, Any]:
    listed = asyncio.run(server.mcp.list_tools())
    return {tool.name: tool for tool in listed}


def test_the_server_registers_the_three_tools_in_tools_json() -> None:
    manifest = json.loads((SERVER_DIR / "tools.json").read_text(encoding="utf-8"))
    declared = {tool["name"]: tool for tool in manifest["tools"]}
    registered = _tools()
    assert (
        set(registered) == set(declared) == {"generate_model", "retexture_model", "get_meshy_job"}
    )
    for name, tool in declared.items():
        assert registered[name].description.strip()
        for required in tool["inputSchema"].get("required", []):
            assert required in registered[name].inputSchema["properties"]


def test_generate_model_limits_pose_to_limbed_characters() -> None:
    description = _tools()["generate_model"].description or ""
    assert "characters and creatures with limbs" in description
    assert "never for props" in description


def test_generate_model_returns_a_job_id(project: Path) -> None:
    result = server.generate_model(name="Crate", prompt="weathered wooden crate")
    assert set(result) == {"job_id"}
    assert jobs.status(result["job_id"], env=ENV, cwd=project)["state"] == "queued"


def test_a_refused_generate_returns_a_structured_error(project: Path) -> None:
    result = server.generate_model(name="crate", prompt="x")
    assert set(result["error"]) == {"code", "message", "remediation"}
    assert result["error"]["code"] == "meshy.invalid_request"


def test_a_missing_key_returns_an_error_not_an_exception(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MESHY_API_KEY", raising=False)
    result = server.generate_model(name="Crate", prompt="x")
    assert result["error"]["code"] == "meshy.api_key_missing"
    assert TEST_KEY not in json.dumps(result)


def test_get_meshy_job_matches_the_status_document(project: Path) -> None:
    job_id = server.generate_model(name="Crate", prompt="x")["job_id"]
    assert server.get_meshy_job(job_id) == jobs.status(job_id, env=ENV, cwd=project)


def test_get_meshy_job_reports_unknown_jobs_as_errors(project: Path) -> None:
    result = server.get_meshy_job("missing")
    assert result["error"]["code"] == "meshy.job_not_found"


def test_retexture_model_reports_a_missing_collection(project: Path) -> None:
    result = server.retexture_model(name="Crate", prompt="mossy")
    assert result["error"]["code"] == "meshy.collection_not_found"


def test_a_finished_job_is_readable_through_get_meshy_job(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spawn = RecordingSpawn()
    monkeypatch.setattr(jobs, "default_spawn", spawn)
    job_id = server.generate_model(name="Crate", prompt="x")["job_id"]
    run_job(spawn.jobs[0], meshy=FakeMeshy(), session=FakeSession(), clock=FakeClock(), env=ENV)
    document = server.get_meshy_job(job_id)
    assert document["state"] == "succeeded"
    assert document["result"]["loaded_into_session"] is True
