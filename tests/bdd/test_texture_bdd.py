"""pytest-bdd bindings for texture_generation.feature: SCN012–SCN020 (#7).

Generation runs with the fake worker process and synthetic hardware facts. No mflux model loads
here;
the opt-in real-model test lives in tests/e2e/test_texture_models_e2e.py.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import types
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image as PILImage
from pytest_bdd import given, parsers, scenario, then, when

from nmg_game_dev.texture import generate, jobs
from nmg_game_dev.texture.errors import TextureGenError
from nmg_game_dev.texture.generate import TextureRequest
from nmg_game_dev.texture.hardware import HardwareFacts, require_available, reserve_gb
from nmg_game_dev.texture.maps import PRESETS, derive
from nmg_game_dev.texture.paths import install_command
from nmg_game_dev.texture.registry import REGISTRY, resolve
from nmg_game_dev.texture.seamless import interior_mad, make_seamless, seam_mad
from tests.texture_fakes import (
    APPLE_SILICON_32GB,
    INTEL_LINUX,
    fake_spawn,
    make_models,
    read_log,
    save_png,
    synthetic_image,
    write_fake_worker,
)

FEATURE = "texture_generation.feature"
MACHINES = {
    "an x86_64 Linux host": INTEL_LINUX,
    "an Apple Silicon Mac with 16 GB RAM": HardwareFacts(
        system="Darwin", machine="arm64", total_ram_gb=16.0
    ),
}
REPO = Path(__file__).resolve().parents[2]


def _ctx(tmp_path: Path, **extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "tmp": tmp_path,
        "worker": write_fake_worker(tmp_path / "worker"),
        "log": tmp_path / "worker.log",
        "out": tmp_path / "out",
        "error": None,
    }
    base.update(extra)
    return base


# --- SCN012 ------------------------------


@scenario(FEATURE, "The texture registry holds exactly the two pinned models")
def test_registry_holds_the_two_pinned_models() -> None:
    """AC12: exactly two pinned backends, and the registry cannot grow at runtime."""


@given("the texture registry", target_fixture="ctx")
def _registry() -> dict[str, Any]:
    return {"registry": REGISTRY}


@when("its backends are listed")
def _list_backends(ctx: dict[str, Any]) -> None:
    ctx["listed"] = list(ctx["registry"])


@then(
    'it contains exactly "z-image-turbo" and "flux2-klein-4b" with their pinned repo, revision, '
    "license, quantization, steps, and peak memory"
)
def _exactly_two(ctx: dict[str, Any]) -> None:
    assert ctx["listed"] == ["z-image-turbo", "flux2-klein-4b"]
    zimage = REGISTRY["z-image-turbo"]
    flux = REGISTRY["flux2-klein-4b"]
    assert zimage.revision == "f332072aa78be7aecdf3ee76d5c247082da564a6"
    assert flux.revision == "e7b7dc27f91deacad38e78976d1f2b499d76a294"
    assert {zimage.license, flux.license} == {"apache-2.0"}
    assert (zimage.quantization, zimage.default_steps, zimage.peak_memory_gb) == (4, 9, 14.6)
    assert (flux.quantization, flux.default_steps, flux.peak_memory_gb) == (4, 4, 12.9)


@then("the registry cannot be extended at runtime")
def _cannot_extend(ctx: dict[str, Any]) -> None:
    with pytest.raises(TypeError):
        ctx["registry"]["sdxl"] = REGISTRY["z-image-turbo"]


# --- SCN013 ------------------------------


@scenario(FEATURE, "Only the pinned models load")
def test_only_pinned_models_load() -> None:
    """AC13: unpinned repos and unknown backend ids raise with the allowlist in the remediation."""


@given(parsers.parse("a texture request for {model}"), target_fixture="ctx")
def _request_for(model: str) -> dict[str, Any]:
    return {"model": model}


@when("generation is requested")
def _generation_requested(ctx: dict[str, Any]) -> None:
    text = ctx["model"]
    target = text[len("repo ") :] if text.startswith("repo ") else text.split('"')[1]
    try:
        resolve(target)
    except TextureGenError as error:
        ctx["error"] = error


@then(parsers.parse('it raises "{code}" with a remediation listing the two allowed backends'))
def _raises_listing(ctx: dict[str, Any], code: str) -> None:
    error = ctx["error"]
    assert error is not None and error.code == code
    assert "z-image-turbo" in error.remediation and "flux2-klein-4b" in error.remediation
    assert "black-forest-labs/FLUX.2-klein-4B" in error.remediation


# --- SCN014 ------------------------------


@scenario(FEATURE, "Missing weights point at onboarding")
def test_missing_weights_point_at_onboarding() -> None:
    """AC14: availability is not_installed and generation names /onboard-consumer and the
    command."""


@given("TEXTURE_GEN_MODELS_DIR without a flux2-klein-4b-q4 directory", target_fixture="ctx")
def _no_flux(tmp_path: Path) -> dict[str, Any]:
    models = make_models(tmp_path / "models", ids=("z-image-turbo",))
    return _ctx(tmp_path, models=models)


@when("flux2-klein-4b availability is checked and generation is requested")
def _check_flux(ctx: dict[str, Any]) -> None:
    from nmg_game_dev.texture.hardware import availability

    spec = REGISTRY["flux2-klein-4b"]
    ctx["status"] = availability(spec, APPLE_SILICON_32GB, ctx["models"], reserve_gb({}))
    try:
        generate.run(
            TextureRequest(prompt="burlap", backend="flux2-klein-4b", seeds=[1], resolution=256),
            env={"TEXTURE_GEN_MODELS_DIR": str(ctx["models"])},
            facts=APPLE_SILICON_32GB,
            spawn=fake_spawn(ctx["worker"], ctx["log"]),
            output_root_override=ctx["out"],
        )
    except TextureGenError as error:
        ctx["error"] = error


@then(parsers.parse('availability is "{status}"'))
def _availability_is(ctx: dict[str, Any], status: str) -> None:
    assert ctx["status"] == status


@then(
    'generation raises "texture.model_not_installed" naming /onboard-consumer, '
    "the mflux-save command, and the expected path"
)
def _names_remediation(ctx: dict[str, Any]) -> None:
    error = ctx["error"]
    assert error is not None and error.code == "texture.model_not_installed"
    expected = ctx["models"] / "flux2-klein-4b-q4"
    assert "/onboard-consumer" in error.remediation
    assert install_command("flux2-klein-4b", ctx["models"]) in error.remediation
    assert str(expected) in error.remediation


# --- SCN015 ------------------------------


@scenario(FEATURE, "The hardware check refuses unfit backends")
def test_hardware_check_refuses_unfit_backends() -> None:
    """AC15: non-Apple-Silicon and low-memory hosts are refused with a remediation."""


@given(parsers.parse("hardware facts for {machine}"), target_fixture="ctx")
def _facts_for(tmp_path: Path, machine: str) -> dict[str, Any]:
    return _ctx(tmp_path, facts=MACHINES[machine])


@when("z-image-turbo is requested explicitly")
def _explicit(ctx: dict[str, Any]) -> None:
    models = make_models(ctx["tmp"] / "models")
    try:
        require_available(REGISTRY["z-image-turbo"], ctx["facts"], models, reserve_gb({}))
    except TextureGenError as error:
        ctx["error"] = error


@then(parsers.parse('it raises "{code}" with a remediation'))
def _raises_with_remediation(ctx: dict[str, Any], code: str) -> None:
    error = ctx["error"]
    assert error is not None and error.code == code
    assert error.remediation


# --- SCN016 ------------------------------


@scenario(FEATURE, "Each backend batch runs in one isolated process")
def test_one_process_per_batch() -> None:
    """AC16: one child process loads the model once and writes one seamless PNG per request."""


@given("a fake worker and a batch of three requests for flux2-klein-4b", target_fixture="ctx")
def _three_requests(tmp_path: Path) -> dict[str, Any]:
    models = make_models(tmp_path / "models")
    return _ctx(tmp_path, models=models, env={"TEXTURE_GEN_MODELS_DIR": str(models)})


@when("the batch is generated")
def _generate_batch(ctx: dict[str, Any]) -> None:
    ctx["result"] = generate.run(
        TextureRequest(
            prompt="stone",
            backend="flux2-klein-4b",
            seeds=[21, 22, 23],
            resolution=256,
            name="stone",
        ),
        env=ctx["env"],
        facts=APPLE_SILICON_32GB,
        spawn=fake_spawn(ctx["worker"], ctx["log"]),
        output_root_override=ctx["out"],
    )


@then("the worker loaded the model once and three seamless PNGs were written")
def _one_load_three_pngs(ctx: dict[str, Any]) -> None:
    events = read_log(ctx["log"])
    assert [e["event"] for e in events] == ["start", "exit"]
    records = ctx["result"].images
    assert len(records) == 3 and all(r.path.exists() for r in records)
    for record in records:
        image = np.asarray(PILImage.open(record.path).convert("RGB"))
        assert seam_mad(image, 0) <= 1.5 * interior_mad(image, 0)
        assert seam_mad(image, 1) <= 1.5 * interior_mad(image, 1)


# --- SCN017 ------------------------------


@scenario(FEATURE, "Models never run concurrently")
def test_models_never_run_concurrently() -> None:
    """AC17: the second backend starts only after the first exits; a second job is refused."""


@given('a fake worker and a request for backend "both"', target_fixture="ctx")
def _both_request(tmp_path: Path) -> dict[str, Any]:
    models = make_models(tmp_path / "models")
    return _ctx(tmp_path, models=models, env={"TEXTURE_GEN_MODELS_DIR": str(models)})


@when("generation runs")
def _run_both(ctx: dict[str, Any]) -> None:
    ctx["result"] = generate.run(
        TextureRequest(prompt="burlap", backend="both", seeds=[3], resolution=256, name="burlap"),
        env=ctx["env"],
        facts=APPLE_SILICON_32GB,
        spawn=fake_spawn(ctx["worker"], ctx["log"]),
        output_root_override=ctx["out"],
    )


@then("the flux2-klein-4b worker started only after the z-image-turbo worker exited")
def _sequential(ctx: dict[str, Any]) -> None:
    events = read_log(ctx["log"])
    z_exit = next(e for e in events if e["backend"] == "z-image-turbo" and e["event"] == "exit")
    flux_start = next(
        e for e in events if e["backend"] == "flux2-klein-4b" and e["event"] == "start"
    )
    assert z_exit["t"] <= flux_start["t"]


@then('starting a second job while one is running raises "texture.job_running"')
def _second_job_refused(ctx: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    lock = ctx["out"] / ".jobs" / "lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(json.dumps({"job_id": "running-job", "pid": os.getpid()}))
    try:
        jobs.start(
            TextureRequest(prompt="burlap", backend="z-image-turbo", seeds=[1], resolution=256),
            env={**ctx["env"], "NMG_GAME_DEV_TEXTURE_DIR": str(ctx["out"])},
            facts=APPLE_SILICON_32GB,
            cwd=ctx["tmp"],
        )
    except TextureGenError as error:
        assert error.code == "texture.job_running"
        assert "running-job" in error.message
    else:
        raise AssertionError("second job was not refused")


# --- SCN018 ------------------------------


@scenario(FEATURE, "Outputs tile seamlessly")
def test_outputs_tile_seamlessly() -> None:
    """AC18: the seamless post-process keeps dimensions and meets the seam threshold."""


@given("a 256x256 non-tiling synthetic image", target_fixture="ctx")
def _synthetic(tmp_path: Path) -> dict[str, Any]:
    return {"image": synthetic_image(256)}


@when("the seamless post-process runs")
def _seamless(ctx: dict[str, Any]) -> None:
    ctx["out_image"] = make_seamless(ctx["image"])


@then(
    "the dimensions are unchanged and both wrap seams are within 1.5x the interior pixel difference"
)
def _seams_within(ctx: dict[str, Any]) -> None:
    assert ctx["out_image"].shape == ctx["image"].shape
    for axis in (0, 1):
        assert seam_mad(ctx["out_image"], axis) <= 1.5 * interior_mad(ctx["out_image"], axis)


# --- SCN019 ------------------------------


@scenario(FEATURE, "Derived PBR maps are seamless")
def test_derived_maps_are_seamless() -> None:
    """AC19: N, R, M, and AO maps at the albedo resolution, each passing the seam check."""


@given('a seamless albedo and the "stone" preset', target_fixture="ctx")
def _albedo(tmp_path: Path) -> dict[str, Any]:
    albedo = save_png(make_seamless(synthetic_image(256)), tmp_path / "albedo" / "stone_1_256.png")
    return {"albedo": albedo, "preset": PRESETS["stone"]}


@when("derived maps are requested with AO")
def _derive(ctx: dict[str, Any]) -> None:
    ctx["maps"] = derive(ctx["albedo"], ctx["preset"][0], ctx["preset"][1], ao=True)


@then("_N, _R, _M, and _AO PNGs exist at the albedo resolution and each passes the seam check")
def _maps_checked(ctx: dict[str, Any]) -> None:
    paths = [ctx["maps"].normal, ctx["maps"].roughness, ctx["maps"].metallic, ctx["maps"].ao]
    assert [p.name for p in paths if p is not None] == [
        "stone_1_256_N.png",
        "stone_1_256_R.png",
        "stone_1_256_M.png",
        "stone_1_256_AO.png",
    ]
    for path in paths:
        assert path is not None and path.exists()
        mode = "L" if path.name.endswith(("_R.png", "_M.png", "_AO.png")) else "RGB"
        image = np.asarray(PILImage.open(path).convert(mode))
        assert image.shape[:2] == (256, 256)
        for axis in (0, 1):
            assert (
                seam_mad(image, axis) <= 1.5 * interior_mad(image, axis)
                or interior_mad(image, axis) == 0
            )


# --- SCN020 ------------------------------


@scenario(FEATURE, "The agent generates textures through the MCP tools")
def test_agent_generates_through_mcp() -> None:
    """AC20: generate_textures returns a job at once; the job runs, then reports the files."""


def _load_server() -> types.ModuleType:
    path = REPO / "mcp-servers" / "texture-gen" / "src" / "texture_gen_mcp" / "server.py"
    spec = importlib.util.spec_from_file_location("texture_gen_server_bdd", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@given("a consumer project, a fake worker, and both backends available", target_fixture="ctx")
def _consumer_both(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    project = tmp_path / "project"
    project.mkdir()
    models = make_models(tmp_path / "models")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project))
    monkeypatch.setenv("TEXTURE_GEN_MODELS_DIR", str(models))
    monkeypatch.delenv("NMG_GAME_DEV_TEXTURE_DIR", raising=False)
    return _ctx(tmp_path, project=project, models=models)


@when(
    'the agent calls generate_textures for "burlap" with backend "both" and polls get_texture_job'
)
def _mcp_flow(ctx: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    states: list[str] = []
    job_dir_holder: dict[str, Path] = {}
    spawn_inner = fake_spawn(ctx["worker"], ctx["log"])

    def recording_spawn(batch_file: Path) -> subprocess.CompletedProcess[str]:
        status = json.loads((job_dir_holder["dir"] / "status.json").read_text())
        states.append(status["state"])
        return spawn_inner(batch_file)

    class _Done:
        pid = os.getpid()

    def inline_popen(argv: list[str], **kwargs: Any) -> _Done:
        job_dir = Path(argv[-1])
        job_dir_holder["dir"] = job_dir
        jobs.run_job(
            job_dir,
            env=dict(os.environ),
            facts=APPLE_SILICON_32GB,
            spawn=recording_spawn,
        )
        return _Done()

    shim = types.SimpleNamespace(Popen=inline_popen, DEVNULL=subprocess.DEVNULL)
    monkeypatch.setattr(jobs, "subprocess", shim)
    server = _load_server()
    started = server.generate_textures(
        prompt="burlap", backend="both", seeds=[5], resolution=256, name="burlap"
    )
    ctx["started"] = started
    ctx["polled"] = server.get_texture_job(started["job_id"])
    ctx["states"] = states


@then("the job reports running and then succeeded with PNG paths and timings")
def _running_then_succeeded(ctx: dict[str, Any]) -> None:
    assert "job_id" in ctx["started"]
    assert "running" in ctx["states"]
    polled = ctx["polled"]
    assert polled["state"] == "succeeded", polled
    assert polled["completed"] == polled["total"] == 2
    images = polled["result"]["images"]
    assert len(images) == 2
    assert all(Path(image["path"]).suffix == ".png" and image["seconds"] >= 0 for image in images)


@then(
    "the files are under SourceArt/Textures/Generated/burlap "
    "with textures.json and burlap_compare.png"
)
def _files_under_project(ctx: dict[str, Any]) -> None:
    folder = ctx["project"] / "SourceArt" / "Textures" / "Generated" / "burlap"
    assert (folder / "textures.json").is_file()
    assert (folder / "burlap_compare.png").is_file()
    manifest = json.loads((folder / "textures.json").read_text())
    assert manifest["name"] == "burlap"
