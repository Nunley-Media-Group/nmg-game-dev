"""The art CLI (``texture art`` and ``texture art-finish``) and the texture-gen MCP tools
``generate_art`` and ``finish_art`` (#253 FR3, AC1, AC4, AC5)."""

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

from nmg_game_dev.texture import art, jobs
from nmg_game_dev.texture.__main__ import main
from tests.texture_fakes import APPLE_SILICON_32GB, fake_spawn, save_png, synthetic_disc

REPO = Path(__file__).resolve().parents[3]
SERVER_FILE = REPO / "mcp-servers" / "texture-gen" / "src" / "texture_gen_mcp" / "server.py"
TOOLS_JSON = REPO / "mcp-servers" / "texture-gen" / "tools.json"


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    monkeypatch.setenv("NMG_GAME_DEV_TEXTURE_DIR", str(tmp_path / "out"))
    return root


@pytest.fixture
def cli_env(
    project: Path,
    models: Path,
    worker: Path,
    log: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    monkeypatch.setenv("TEXTURE_GEN_MODELS_DIR", str(models))
    monkeypatch.setattr(art, "probe", lambda: APPLE_SILICON_32GB)
    monkeypatch.setattr(art, "default_spawn", fake_spawn(worker, log))
    return project


def _disc_take(root: Path, kind: str, name: str, pick: int) -> Path:
    take = root / "SourceArt" / "Art" / "raw" / kind / f"{name}-{pick}.png"
    return save_png(synthetic_disc(), take)


# --- CLI ---------------------------------------------------------------------------------------


def test_art_prints_the_result_json_and_writes_the_takes(
    cli_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        [
            "art",
            "--kind",
            "icon",
            "--name",
            "HealthPotion",
            "--prompt",
            "red potion bottle",
            "--seeds",
            "1,2,3",
        ]
    )
    assert code == 0
    printed = json.loads(capsys.readouterr().out)
    assert [image["seed"] for image in printed["images"]] == [1, 2, 3]
    assert printed["skipped"] == []
    assert Path(printed["contact_sheet"]).is_file()
    assert (cli_env / "SourceArt/Art/raw/icon/HealthPotion-3.png").is_file()


def test_art_without_the_models_exits_one_with_the_remediation(
    project: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("TEXTURE_GEN_MODELS_DIR", str(tmp_path / "no-models"))
    monkeypatch.setattr(art, "probe", lambda: APPLE_SILICON_32GB)
    code = main(["art", "--kind", "icon", "--name", "Rock", "--prompt", "rock", "--seeds", "1"])
    assert code == 1
    err = capsys.readouterr().err
    assert "ERROR [texture.model_not_installed]" in err
    assert "Remediation:" in err


def test_art_with_bad_seeds_exits_one_as_invalid(
    cli_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["art", "--kind", "icon", "--name", "Rock", "--prompt", "rock", "--seeds", "1,x"])
    assert code == 1
    assert "ERROR [texture.invalid_request]" in capsys.readouterr().err


def test_art_with_an_unknown_kind_is_an_argument_error(cli_env: Path) -> None:
    with pytest.raises(SystemExit) as caught:
        main(["art", "--kind", "sprite", "--name", "Rock", "--prompt", "rock"])
    assert caught.value.code == 2


def test_art_finish_writes_the_game_files_and_prints_them(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _disc_take(project, "icon", "HealthPotion", 2)
    code = main(["art-finish", "--kind", "icon", "--name", "HealthPotion", "--pick", "2"])
    assert code == 0
    printed = json.loads(capsys.readouterr().out)
    assert (project / "game/assets/UI/Icons/HealthPotion.png").is_file()
    assert {Path(entry["path"]).name for entry in printed["files"]} == {
        "HealthPotion.png",
        "HealthPotion_small.png",
    }


def test_art_finish_on_a_missing_take_exits_one(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["art-finish", "--kind", "icon", "--name", "HealthPotion", "--pick", "7"])
    assert code == 1
    err = capsys.readouterr().err
    assert "ERROR [art.take_not_found]" in err and "Remediation:" in err


# --- MCP ---------------------------------------------------------------------------------------


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    src = str(SERVER_FILE.parents[1])
    if src not in sys.path:
        sys.path.insert(0, src)
    spec = importlib.util.spec_from_file_location("texture_gen_art_server_under_test", SERVER_FILE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.delenv("TEXTURE_GEN_MODELS_DIR", raising=False)
    return module


def test_the_art_tools_are_registered_and_declared(server: ModuleType) -> None:
    registered = {tool.name for tool in asyncio.run(server.mcp.list_tools())}
    declared = {tool["name"] for tool in json.loads(TOOLS_JSON.read_text())["tools"]}
    assert {"generate_art", "finish_art"} <= registered
    assert {"generate_art", "finish_art"} <= declared


def test_generate_art_returns_a_job_id_and_the_job_is_polled_with_get_texture_job(
    server: ModuleType,
    project: Path,
    models: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEXTURE_GEN_MODELS_DIR", str(models))
    monkeypatch.setattr(jobs, "probe", lambda: APPLE_SILICON_32GB)

    class _Runner:
        pid = os.getpid()

    spawned: list[list[str]] = []

    def popen(argv: list[str], **kwargs: object) -> _Runner:
        spawned.append(argv)
        return _Runner()

    monkeypatch.setattr(
        jobs, "subprocess", types.SimpleNamespace(Popen=popen, DEVNULL=subprocess.DEVNULL)
    )
    started = server.generate_art(kind="icon", name="HealthPotion", prompt="potion", seeds=[1, 2])
    assert set(started) == {"job_id"}
    status = server.get_texture_job(started["job_id"])
    assert status["state"] == "queued" and status["total"] == 2
    assert spawned and spawned[0][-2] == "run-queue"


def test_generate_art_reports_a_bad_request_as_a_structured_error(server: ModuleType) -> None:
    result = server.generate_art(kind="sprite", name="Rock", prompt="rock")
    assert set(result) == {"error"}
    assert result["error"]["code"] == "texture.invalid_request"
    assert result["error"]["remediation"]


def test_generate_art_refuses_an_empty_seed_list(server: ModuleType) -> None:
    result = server.generate_art(kind="icon", name="HealthPotion", prompt="potion", seeds=[])
    assert set(result) == {"error"}
    assert result["error"]["code"] == "texture.invalid_request"
    assert "seed" in result["error"]["message"].lower()


def test_finish_art_writes_the_files_and_reports_a_missing_take_as_an_error(
    server: ModuleType, project: Path
) -> None:
    _disc_take(project, "icon", "HealthPotion", 2)
    result = server.finish_art(kind="icon", name="HealthPotion", pick=2)
    assert "files" in result
    assert (project / "game/assets/UI/Icons/HealthPotion.png").is_file()
    missing = server.finish_art(kind="icon", name="HealthPotion", pick=9)
    assert set(missing) == {"error"}
    assert missing["error"]["code"] == "art.take_not_found"
