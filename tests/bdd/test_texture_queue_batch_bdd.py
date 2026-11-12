"""pytest-bdd bindings for texture_queue_batch.feature: SCN001–SCN008 (#143).

The scenarios run the real package with the fake worker process and synthetic hardware facts. No
mflux model loads here, and no runner process is started: queued jobs are recorded and then drained
in process with ``jobs.run_queue``.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import tomllib
import types
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenario, then, when

from nmg_game_dev.texture import deps, generate, jobs
from nmg_game_dev.texture.__main__ import main
from nmg_game_dev.texture.batch import Batch, ImageItem, run_backend_batches
from nmg_game_dev.texture.errors import TextureGenError
from nmg_game_dev.texture.generate import TextureRequest, backend_status
from nmg_game_dev.texture.registry import REGISTRY
from tests.texture_fakes import (
    APPLE_SILICON_32GB,
    fake_spawn,
    make_models,
    read_log,
    write_fake_worker,
)

FEATURE = "texture_queue_batch.feature"
REPO = Path(__file__).resolve().parents[2]
MARKER = "sys_platform == 'darwin' and platform_machine == 'arm64'"


@pytest.fixture(autouse=True)
def _all_modules_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """The default probe reports mflux and mlx present. SCN002 passes its own probe (#143 FR2)."""
    monkeypatch.setattr(deps, "missing_module", lambda: None)


def _base(tmp_path: Path, **extra: Any) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "tmp": tmp_path,
        "worker": write_fake_worker(tmp_path / "worker"),
        "log": tmp_path / "worker.log",
        "out": tmp_path / "out",
        "error": None,
    }
    ctx.update(extra)
    return ctx


def _env(tmp_path: Path, models: Path) -> dict[str, str]:
    return {
        "TEXTURE_GEN_MODELS_DIR": str(models),
        "NMG_GAME_DEV_TEXTURE_DIR": str(tmp_path / "out"),
    }


def _recording_runner(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Record each runner spawn instead of starting one, so ``start`` only queues."""
    spawned: list[list[str]] = []

    class _Runner:
        pid = os.getpid()

    def popen(argv: list[str], **kwargs: Any) -> _Runner:
        spawned.append(argv)
        return _Runner()

    shim = types.SimpleNamespace(Popen=popen, DEVNULL=subprocess.DEVNULL)
    monkeypatch.setattr(jobs, "subprocess", shim)
    return spawned


def _set_apple(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(generate, "probe", lambda: APPLE_SILICON_32GB)
    monkeypatch.setattr(jobs, "probe", lambda: APPLE_SILICON_32GB)


def _request(
    name: str, backend: str = "z-image-turbo", seeds: list[int] | None = None
) -> TextureRequest:
    return TextureRequest(
        prompt=name, backend=backend, seeds=seeds or [1], resolution=256, name=name
    )


def _load_server() -> types.ModuleType:
    path = REPO / "mcp-servers" / "texture-gen" / "src" / "texture_gen_mcp" / "server.py"
    spec = importlib.util.spec_from_file_location("texture_gen_server_queue_bdd", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_toml(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = tomllib.loads(path.read_text(encoding="utf-8"))
    return data


# --- SCN001 ------------------------------


@scenario(FEATURE, "The root project declares the generation dependencies for Apple Silicon")
def test_root_declares_the_generation_dependencies() -> None:
    """AC1: the floors with the arm64 macOS marker, the extra with the same floors, and the server
    pin."""


@given("the root pyproject.toml", target_fixture="ctx")
def _root_pyproject() -> dict[str, Any]:
    return {
        "root": _load_toml(REPO / "pyproject.toml"),
        "server": _load_toml(REPO / "mcp-servers" / "texture-gen" / "pyproject.toml"),
    }


@when("its project dependencies are read")
def _read_dependencies(ctx: dict[str, Any]) -> None:
    project = ctx["root"]["project"]
    ctx["dependencies"] = project["dependencies"]
    ctx["extra"] = project["optional-dependencies"]["texture-ai"]


@then("mflux>=0.24.0 and hf_transfer>=0.1.9 are listed as floors with the arm64 macOS marker")
def _floors_with_marker(ctx: dict[str, Any]) -> None:
    assert f"mflux>=0.24.0; {MARKER}" in ctx["dependencies"]
    assert f"hf_transfer>=0.1.9; {MARKER}" in ctx["dependencies"]


@then("the texture-ai extra uses the same floors with no exact pin")
def _extra_floors(ctx: dict[str, Any]) -> None:
    assert sorted(ctx["extra"]) == ["hf_transfer>=0.1.9", "mflux>=0.24.0"]
    assert not any("==" in entry for entry in ctx["extra"])


@then("the texture-gen server still depends on nmg-game-dev[texture-ai]")
def _server_pin(ctx: dict[str, Any]) -> None:
    assert "nmg-game-dev[texture-ai]" in ctx["server"]["project"]["dependencies"]


# --- SCN002 ------------------------------


@scenario(FEATURE, "Missing mlx fails fast with the plugin-root command")
def test_missing_mlx_fails_fast() -> None:
    """AC2: generation is refused before any worker or job, and status reports
    dependencies_missing."""


@given("an import probe that cannot find mlx", target_fixture="ctx")
def _probe_without_mlx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    models = make_models(tmp_path / "models")
    spawned = _recording_runner(monkeypatch)
    return _base(
        tmp_path,
        models=models,
        env=_env(tmp_path, models),
        probe=lambda: "mlx",
        spawned=spawned,
        job_error=None,
    )


@when("a texture request is generated")
def _generate_without_mlx(ctx: dict[str, Any]) -> None:
    request = _request("burlap")
    try:
        generate.run(
            request,
            env=ctx["env"],
            facts=APPLE_SILICON_32GB,
            spawn=fake_spawn(ctx["worker"], ctx["log"]),
            output_root_override=ctx["out"],
            deps_probe=ctx["probe"],
        )
    except TextureGenError as error:
        ctx["error"] = error
    try:
        jobs.start(
            request,
            env=ctx["env"],
            facts=APPLE_SILICON_32GB,
            cwd=ctx["tmp"],
            deps_probe=ctx["probe"],
        )
    except TextureGenError as error:
        ctx["job_error"] = error


@then('it fails with texture.dependencies_missing naming mlx and "uv run --project"')
def _fails_naming_mlx(ctx: dict[str, Any]) -> None:
    for error in (ctx["error"], ctx["job_error"]):
        assert error is not None and error.code == "texture.dependencies_missing"
        assert "mlx" in error.message
        assert "uv run --project" in error.remediation


@then("no worker is spawned and no job is queued")
def _nothing_started(ctx: dict[str, Any]) -> None:
    assert not ctx["log"].exists()
    assert ctx["spawned"] == []
    assert not (ctx["out"] / ".jobs").exists()


@then("the backend status is dependencies_missing")
def _status_reports_it(ctx: dict[str, Any]) -> None:
    status = backend_status(env=ctx["env"], facts=APPLE_SILICON_32GB, deps_probe=ctx["probe"])
    assert set(status) == set(REGISTRY)
    assert set(status.values()) == {"dependencies_missing"}


# --- SCN003 ------------------------------


@scenario(FEATURE, "A worker import failure names the missing module")
def test_worker_import_failure_names_the_module() -> None:
    """AC3: a ModuleNotFoundError from the worker is named with the plugin-root command."""


@given(parsers.parse('a worker that exits with "{message}"'), target_fixture="ctx")
def _worker_exits(tmp_path: Path, message: str) -> dict[str, Any]:
    module = re.search(r"No module named '([^']+)'", message)
    assert module is not None, message
    models = make_models(tmp_path / "models")
    return _base(tmp_path, models=models, missing=module.group(1))


@when("the backend batch runs")
def _backend_batch_runs(ctx: dict[str, Any]) -> None:
    batch = Batch(
        spec=REGISTRY["z-image-turbo"],
        weights=ctx["models"] / "z-image-turbo-q4",
        items=(
            ImageItem(index=0, prompt="burlap", seed=1, resolution=256, path=ctx["out"] / "a.png"),
        ),
        batch_file=ctx["tmp"] / "batch" / "z-image-turbo.json",
    )
    try:
        run_backend_batches(
            [batch],
            spawn=fake_spawn(ctx["worker"], ctx["log"], missing_module=ctx["missing"]),
        )
    except TextureGenError as error:
        ctx["error"] = error


@then("texture.worker_failed names mlx and the plugin-root command")
def _worker_names_module(ctx: dict[str, Any]) -> None:
    error = ctx["error"]
    assert error is not None and error.code == "texture.worker_failed"
    assert ctx["missing"] in error.remediation
    assert "uv run --project" in error.remediation


@then("it does not mention models or the memory reserve")
def _not_models_or_reserve(ctx: dict[str, Any]) -> None:
    remediation = ctx["error"].remediation
    assert "models" not in remediation
    assert "reserve" not in remediation


# --- SCN004 ------------------------------


@scenario(FEATURE, "A second request is queued and runs after the first")
def test_second_request_is_queued_and_runs_after_the_first() -> None:
    """AC4: a request started while another waits returns a queued job, and jobs run in order."""


@given("a texture job is queued or running", target_fixture="ctx")
def _job_queued(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    models = make_models(tmp_path / "models")
    env = _env(tmp_path, models)
    spawned = _recording_runner(monkeypatch)
    first = jobs.start(_request("burlap"), env=env, facts=APPLE_SILICON_32GB, cwd=tmp_path)
    return _base(tmp_path, models=models, env=env, spawned=spawned, first=first)


@when("another valid request is started")
def _second_started(ctx: dict[str, Any]) -> None:
    ctx["second"] = jobs.start(
        _request("stone", backend="flux2-klein-4b"),
        env=ctx["env"],
        facts=APPLE_SILICON_32GB,
        cwd=ctx["tmp"],
    )


@then("it returns a new job id in state queued")
def _second_is_queued(ctx: dict[str, Any]) -> None:
    assert ctx["second"] != ctx["first"]
    assert jobs.status(ctx["second"], env=ctx["env"])["state"] == "queued"


@then("the queue runner runs both jobs one at a time in submission order")
def _runs_in_submission_order(ctx: dict[str, Any]) -> None:
    jobs.run_queue(
        ctx["out"] / ".jobs",
        env=ctx["env"],
        facts=APPLE_SILICON_32GB,
        spawn=fake_spawn(ctx["worker"], ctx["log"]),
    )
    assert jobs.status(ctx["first"], env=ctx["env"])["state"] == "succeeded"
    assert jobs.status(ctx["second"], env=ctx["env"])["state"] == "succeeded"
    starts = [e["backend"] for e in read_log(ctx["log"]) if e["event"] == "start"]
    assert starts == ["z-image-turbo", "flux2-klein-4b"]


# --- SCN005 ------------------------------


@scenario(FEATURE, "A batch through the MCP tool loads each model once")
def test_mcp_batch_loads_each_model_once() -> None:
    """AC5: one worker per backend covers every image; progress and results follow the batch."""


@given("generate_textures called with two requests for the same backend", target_fixture="ctx")
def _mcp_batch_given(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    models = make_models(tmp_path / "models")
    env = _env(tmp_path, models)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    _set_apple(monkeypatch)
    spawned = _recording_runner(monkeypatch)
    return _base(tmp_path, models=models, env=env, spawned=spawned, server=_load_server())


@when("the job runs")
def _mcp_job_runs(ctx: dict[str, Any]) -> None:
    started = ctx["server"].generate_textures(
        requests=[
            {"prompt": "stone", "name": "stone", "resolution": 256, "seeds": [1, 2]},
            {"prompt": "wood", "name": "wood", "resolution": 256, "seeds": [3]},
        ]
    )
    ctx["started"] = started
    jobs.run_queue(
        ctx["out"] / ".jobs",
        env=dict(os.environ),
        facts=APPLE_SILICON_32GB,
        spawn=fake_spawn(ctx["worker"], ctx["log"]),
    )
    ctx["polled"] = ctx["server"].get_texture_job(started["job_id"])


@then("that backend's worker is spawned once with both requests' images")
def _one_spawn_for_the_batch(ctx: dict[str, Any]) -> None:
    events = read_log(ctx["log"])
    assert [e["event"] for e in events] == ["start", "exit"]
    assert events[0]["items"] == 3


@then("progress counts every image")
def _progress_counts_images(ctx: dict[str, Any]) -> None:
    polled = ctx["polled"]
    assert polled["state"] == "succeeded", polled
    assert polled["completed"] == polled["total"] == 3


@then("the result lists two results in request order")
def _results_in_order(ctx: dict[str, Any]) -> None:
    results = ctx["polled"]["result"]["results"]
    assert [result["name"] for result in results] == ["stone", "wood"]


# --- SCN006 ------------------------------


@scenario(FEATURE, "A batch through the CLI prints a combined result")
def test_cli_batch_prints_a_combined_result() -> None:
    """AC6: generate --batch prints one JSON object whose results hold one entry per request."""


@given("a JSON file with an array of two requests", target_fixture="ctx")
def _cli_batch_given(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    models = make_models(tmp_path / "models")
    env = _env(tmp_path, models)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    _set_apple(monkeypatch)
    worker = write_fake_worker(tmp_path / "worker")
    log = tmp_path / "worker.log"
    monkeypatch.setattr(generate, "default_spawn", fake_spawn(worker, log))
    batch_file = tmp_path / "requests.json"
    batch_file.write_text(
        json.dumps(
            [
                {"prompt": "burlap", "name": "burlap", "resolution": 256, "seeds": [1]},
                {"prompt": "oak", "name": "oak", "resolution": 256, "seeds": [2]},
            ]
        ),
        encoding="utf-8",
    )
    return _base(tmp_path, batch_file=batch_file, env=env, models=models)


@when('"python -m nmg_game_dev.texture generate --batch <file>" runs')
def _cli_batch_runs(ctx: dict[str, Any], capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["generate", "--batch", str(ctx["batch_file"])]) == 0
    ctx["printed"] = json.loads(capsys.readouterr().out)


@then("it prints one JSON object with two results")
def _prints_two_results(ctx: dict[str, Any]) -> None:
    assert list(ctx["printed"]) == ["results"]
    assert [entry["name"] for entry in ctx["printed"]["results"]] == ["burlap", "oak"]


# --- SCN007 ------------------------------


@scenario(FEATURE, "An invalid batch is rejected whole")
def test_invalid_batch_is_rejected_whole() -> None:
    """AC7: one texture.invalid_request names every invalid index; nothing is generated or
    queued."""


@given("a batch whose requests 1 and 3 are invalid", target_fixture="ctx")
def _invalid_batch_given(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    models = make_models(tmp_path / "models")
    requests = [
        _request("ok-zero"),
        TextureRequest(prompt="   ", backend="z-image-turbo", seeds=[2], resolution=256),
        _request("ok-two"),
        TextureRequest(prompt="bad-size", backend="z-image-turbo", seeds=[4], resolution=300),
    ]
    spawned = _recording_runner(monkeypatch)
    return _base(
        tmp_path,
        models=models,
        env=_env(tmp_path, models),
        spawned=spawned,
        requests=requests,
        job_error=None,
    )


@when("it is submitted")
def _submit_invalid_batch(ctx: dict[str, Any]) -> None:
    try:
        generate.run_batch(
            ctx["requests"],
            env=ctx["env"],
            facts=APPLE_SILICON_32GB,
            spawn=fake_spawn(ctx["worker"], ctx["log"]),
            output_root_override=ctx["out"],
        )
    except TextureGenError as error:
        ctx["error"] = error
    try:
        jobs.start(ctx["requests"], env=ctx["env"], facts=APPLE_SILICON_32GB, cwd=ctx["tmp"])
    except TextureGenError as error:
        ctx["job_error"] = error


@then("texture.invalid_request names requests 1 and 3")
def _names_requests_one_and_three(ctx: dict[str, Any]) -> None:
    for error in (ctx["error"], ctx["job_error"]):
        assert error is not None and error.code == "texture.invalid_request"
        assert "request 1" in error.message and "request 3" in error.message


@then("nothing is generated or queued")
def _nothing_generated_or_queued(ctx: dict[str, Any]) -> None:
    assert not ctx["log"].exists()
    assert ctx["spawned"] == []
    assert not ctx["out"].exists()


# --- SCN008 ------------------------------


@scenario(FEATURE, "Single requests keep their shape")
def test_single_requests_keep_their_shape() -> None:
    """AC8: a single request keeps its parameters and its result keys."""


@given("a single request through the CLI or generate_textures", target_fixture="ctx")
def _single_request_given(tmp_path: Path) -> dict[str, Any]:
    models = make_models(tmp_path / "models")
    return _base(tmp_path, models=models, env=_env(tmp_path, models))


@when("it completes")
def _single_completes(ctx: dict[str, Any]) -> None:
    ctx["result"] = generate.run(
        _request("burlap"),
        env=ctx["env"],
        facts=APPLE_SILICON_32GB,
        spawn=fake_spawn(ctx["worker"], ctx["log"]),
        output_root_override=ctx["out"],
    )


@then("its parameters and result keys are unchanged")
def _single_shape_unchanged(ctx: dict[str, Any]) -> None:
    result = ctx["result"]
    payload = result.as_json()
    assert set(payload) == {
        "name",
        "prompt",
        "style_suffix",
        "output_dir",
        "images",
        "skipped",
        "manifest",
        "compare",
        "contact_sheet",
    }
    assert set(payload["images"][0]) == {
        "backend",
        "repo",
        "revision",
        "seed",
        "steps",
        "resolution",
        "seconds",
        "path",
        "maps",
    }
    assert result.name == "burlap" and result.images[0].resolution == 256
