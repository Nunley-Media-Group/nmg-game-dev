"""pytest-bdd bindings for game_art.feature: SCN001-SCN007 (#253).

Generation runs with the fake worker process and synthetic hardware facts. No mflux model loads
here. The CLI scenarios run ``nmg_game_dev.texture.__main__.main`` with the same environment a
developer's shell would provide.
"""

from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image as PILImage
from pytest_bdd import given, parsers, scenario, then, when

from nmg_game_dev.texture import art, art_finish, deps, generate
from nmg_game_dev.texture.__main__ import main
from nmg_game_dev.texture.art import KINDS, ArtRequest
from nmg_game_dev.texture.errors import TextureGenError
from nmg_game_dev.texture.hardware import HardwareFacts
from tests.texture_fakes import (
    make_models,
    recording_spawn,
    save_png,
    synthetic_disc,
    synthetic_image,
    write_fake_worker,
)

FEATURE = "game_art.feature"
APPLE = HardwareFacts(system="Darwin", machine="arm64", total_ram_gb=32.0)
ICON_FRAMING = KINDS["icon"].framing


@pytest.fixture(autouse=True)
def mflux_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """Report mflux and mlx as importable, so these scenarios keep their meaning on Linux CI."""
    monkeypatch.setattr(deps, "missing_module", lambda: None)


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """The shared scenario state: a project, model folders, the fake worker, and the environment
    the CLI reads."""
    project = tmp_path / "project"
    project.mkdir()
    models = make_models(tmp_path / "models")
    monkeypatch.setenv("TEXTURE_GEN_MODELS_DIR", str(models))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project))
    monkeypatch.setenv("NMG_GAME_DEV_TEXTURE_DIR", str(tmp_path / "out"))
    monkeypatch.setattr(art, "probe", lambda: APPLE)
    return {
        "tmp": tmp_path,
        "project": project,
        "models": models,
        "worker": write_fake_worker(tmp_path / "worker"),
        "log": tmp_path / "worker.log",
        "source": None,
        "captured": [],
        "code": None,
        "error": None,
    }


def _env(ctx: dict[str, Any]) -> dict[str, str]:
    return {
        "TEXTURE_GEN_MODELS_DIR": str(ctx["models"]),
        "CLAUDE_PROJECT_DIR": str(ctx["project"]),
    }


def _spawn(ctx: dict[str, Any]) -> Any:
    """A spawn that runs the fake worker and records each batch file it was given."""
    return recording_spawn(ctx["worker"], ctx["log"], ctx["captured"], ctx["source"])


def _cli(ctx: dict[str, Any], monkeypatch: pytest.MonkeyPatch, command: str) -> int:
    argv = shlex.split(command)
    assert argv[0] == "texture", command
    monkeypatch.setattr(art, "default_spawn", _spawn(ctx))
    return main(argv[1:])


def _raw_icon(ctx: dict[str, Any], seed: int, rgb: np.ndarray) -> Path:
    path = ctx["project"] / "SourceArt" / "Art" / "raw" / "icon" / f"HealthPotion-{seed}.png"
    return save_png(rgb, path)


# --- SCN001 ------------------------------------------------------------------------------------


@scenario(FEATURE, "2D art generates without tiling")
def test_2d_art_generates_without_tiling() -> None:
    """AC1: raw takes are the worker's pixels, with no maps, a JSON manifest, and a sheet."""


@given("the texture models are available through the fake worker")
def _models_available(ctx: dict[str, Any]) -> None:
    ctx["source"] = save_png(synthetic_image(256, seed=3), ctx["tmp"] / "source.png")


@when(parsers.parse('"{command}" runs'))
def _command_runs(ctx: dict[str, Any], monkeypatch: pytest.MonkeyPatch, command: str) -> None:
    ctx["code"] = _cli(ctx, monkeypatch, command)


@then(
    "SourceArt/Art/raw/icon/HealthPotion-1.png, -2.png, and -3.png hold the worker's pixels "
    "unchanged"
)
def _takes_hold_worker_pixels(ctx: dict[str, Any]) -> None:
    assert ctx["code"] == 0
    source = ctx["source"].read_bytes()
    raw = ctx["project"] / "SourceArt" / "Art" / "raw" / "icon"
    for seed in (1, 2, 3):
        assert (raw / f"HealthPotion-{seed}.png").read_bytes() == source


@then("no derived maps are written")
def _no_maps(ctx: dict[str, Any]) -> None:
    raw = ctx["project"] / "SourceArt" / "Art" / "raw" / "icon"
    assert {path.name for path in raw.iterdir()} == {
        "HealthPotion-1.png",
        "HealthPotion-2.png",
        "HealthPotion-3.png",
        "HealthPotion.json",
        "HealthPotion_sheet.png",
    }


@then("HealthPotion.json and HealthPotion_sheet.png are written")
def _manifest_and_sheet(ctx: dict[str, Any]) -> None:
    raw = ctx["project"] / "SourceArt" / "Art" / "raw" / "icon"
    manifest = json.loads((raw / "HealthPotion.json").read_text(encoding="utf-8"))
    assert manifest["prompt"] == "red potion bottle"
    assert (raw / "HealthPotion_sheet.png").is_file()


# --- SCN002 ------------------------------------------------------------------------------------


@scenario(FEATURE, "Kinds set framing and size")
def test_kinds_set_framing_and_size() -> None:
    """AC2: each kind writes its aspect at a 1024 px long side with its framing text."""


@when(
    parsers.parse(
        'art of kind "{kind}" with aspect "{aspect}" is generated at resolution {resolution:d}'
    )
)
def _art_of_kind(ctx: dict[str, Any], kind: str, aspect: str, resolution: int) -> None:
    request = ArtRequest(
        kind=kind,
        name="Sample",
        prompt="sample",
        seeds=[1],
        aspect=aspect or None,
        resolution=resolution,
    )
    ctx["result"] = art.run(
        request, env=_env(ctx), facts=APPLE, spawn=_spawn(ctx), cwd=ctx["project"]
    )


@then(
    parsers.parse(
        'the raw image is {width:d} by {height:d} and its prompt carries the "{kind}" framing text'
    )
)
def _raw_image_size(ctx: dict[str, Any], width: int, height: int, kind: str) -> None:
    take = ctx["result"].images[0].path
    with PILImage.open(take) as image:
        assert image.size == (width, height)
    assert KINDS[kind].framing in ctx["captured"][-1]["items"][0]["prompt"]


# --- SCN003 ------------------------------------------------------------------------------------


@scenario(FEATURE, "The project style is shared")
def test_the_project_style_is_shared() -> None:
    """AC3: the style sentence joins art prompts and is recorded, and texture prompts stay put."""


@given(parsers.parse('SourceArt/Art/style.json with style "{style}"'))
def _style_file(ctx: dict[str, Any], style: str) -> None:
    path = ctx["project"] / "SourceArt" / "Art" / "style.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"style": style}), encoding="utf-8")


@when("icon art and a tiling texture are generated")
def _art_and_texture(ctx: dict[str, Any]) -> None:
    art.run(
        ArtRequest(kind="icon", name="HealthPotion", prompt="red potion bottle", seeds=[1]),
        env=_env(ctx),
        facts=APPLE,
        spawn=_spawn(ctx),
        cwd=ctx["project"],
    )
    generate.run(
        generate.TextureRequest(prompt="burlap", seeds=[1], resolution=256),
        env=_env(ctx),
        facts=APPLE,
        spawn=_spawn(ctx),
        cwd=ctx["project"],
        output_root_override=ctx["tmp"] / "out",
    )


@then(parsers.parse('the art prompt is "{prompt}"'))
def _art_prompt(ctx: dict[str, Any], prompt: str) -> None:
    expected = prompt.replace("<icon framing text>", ICON_FRAMING)
    assert ctx["captured"][0]["items"][0]["prompt"] == expected


@then("the texture prompt is unchanged and textures.json records the project style")
def _texture_prompt(ctx: dict[str, Any]) -> None:
    assert ctx["captured"][1]["items"][0]["prompt"] == f"burlap, {generate.STYLE_SUFFIX}"
    manifest = json.loads((ctx["tmp"] / "out" / "burlap" / "textures.json").read_text("utf-8"))
    assert manifest["project_style"] == "hand-painted, warm palette"


# --- SCN004 ------------------------------------------------------------------------------------


@scenario(FEATURE, "Existing takes are skipped")
def test_existing_takes_are_skipped() -> None:
    """AC4: a take that exists is skipped, and a request with nothing missing starts no worker."""


@given("SourceArt/Art/raw/icon/HealthPotion-2.png exists")
def _existing_take(ctx: dict[str, Any]) -> None:
    ctx["existing"] = _raw_icon(ctx, 2, synthetic_image(256, seed=9)).read_bytes()


@when("the HealthPotion request with seeds 1,2,3 runs again")
def _request_again(ctx: dict[str, Any]) -> None:
    ctx["result"] = art.run(
        ArtRequest(kind="icon", name="HealthPotion", prompt="red potion bottle", seeds=[1, 2, 3]),
        env=_env(ctx),
        facts=APPLE,
        spawn=_spawn(ctx),
        cwd=ctx["project"],
    )


@then("seed 2 is reported as skipped and only seeds 1 and 3 are generated")
def _seed_two_skipped(ctx: dict[str, Any]) -> None:
    assert ctx["result"].skipped == (2,)
    assert [item["seed"] for item in ctx["captured"][-1]["items"]] == [1, 3]
    assert (ctx["project"] / "SourceArt/Art/raw/icon/HealthPotion-2.png").read_bytes() == ctx[
        "existing"
    ]


@then("a request for seed 2 alone starts no worker")
def _seed_two_alone(ctx: dict[str, Any]) -> None:
    def refuse(batch_file: Path) -> subprocess.CompletedProcess[str]:
        raise AssertionError("a request whose only take exists must not start a worker")

    result = art.run(
        ArtRequest(kind="icon", name="HealthPotion", prompt="red potion bottle", seeds=[2]),
        env=_env(ctx),
        facts=APPLE,
        spawn=refuse,
        cwd=ctx["project"],
    )
    assert result.skipped == (2,) and result.images == ()


# --- SCN005 ------------------------------------------------------------------------------------


@scenario(FEATURE, "Icons are cut out")
def test_icons_are_cut_out() -> None:
    """AC5: the cut-out icon is 512 px with a 64 px copy, and rerunning gives identical bytes."""


@given("a raw icon take of a disc on a flat grey background")
def _disc_take(ctx: dict[str, Any]) -> None:
    _raw_icon(ctx, 2, synthetic_disc())


@when(parsers.parse('"{command}" runs twice'))
def _finish_twice(ctx: dict[str, Any], monkeypatch: pytest.MonkeyPatch, command: str) -> None:
    icons = ctx["project"] / "game" / "assets" / "UI" / "Icons"
    assert _cli(ctx, monkeypatch, command) == 0
    ctx["first"] = (
        (icons / "HealthPotion.png").read_bytes(),
        (icons / "HealthPotion_small.png").read_bytes(),
    )
    assert _cli(ctx, monkeypatch, command) == 0


@then(
    "game/assets/UI/Icons/HealthPotion.png is 512 px with transparent corners and a feathered edge"
)
def _icon_full(ctx: dict[str, Any]) -> None:
    path = ctx["project"] / "game" / "assets" / "UI" / "Icons" / "HealthPotion.png"
    with PILImage.open(path) as image:
        assert image.size == (512, 512)
        alpha = np.asarray(image)[..., 3]
    assert alpha[0, 0] == 0 and alpha[-1, -1] == 0
    assert any(0 < value < 255 for value in alpha[256, :].tolist())


@then("HealthPotion_small.png is 64 px")
def _icon_small(ctx: dict[str, Any]) -> None:
    path = ctx["project"] / "game" / "assets" / "UI" / "Icons" / "HealthPotion_small.png"
    with PILImage.open(path) as image:
        assert image.size == (64, 64)


@then("the second run's files are byte-identical to the first")
def _identical_rerun(ctx: dict[str, Any]) -> None:
    icons = ctx["project"] / "game" / "assets" / "UI" / "Icons"
    second = (
        (icons / "HealthPotion.png").read_bytes(),
        (icons / "HealthPotion_small.png").read_bytes(),
    )
    assert second == ctx["first"]


# --- SCN006 ------------------------------------------------------------------------------------


@scenario(FEATURE, "A non-flat background is rejected")
def test_a_non_flat_background_is_rejected() -> None:
    """AC6: a take with mixed corners or an edge-touching subject fails and writes nothing."""


@given(parsers.re(r"a raw icon take (?P<problem>whose .+)"))
def _problem_take(ctx: dict[str, Any], problem: str) -> None:
    if "corners" in problem:
        gradient = np.zeros((512, 512, 3), dtype=np.uint8)
        gradient[..., 0] = np.linspace(0, 255, 512, dtype=np.uint8)[None, :]
        _raw_icon(ctx, 2, gradient)
    else:
        _raw_icon(ctx, 2, synthetic_disc(center_x=40, radius=60))


@when("art-finish runs")
def _art_finish_runs(ctx: dict[str, Any]) -> None:
    try:
        art_finish.finish(ctx["project"], "icon", "HealthPotion", 2)
    except TextureGenError as error:
        ctx["error"] = error


@then(parsers.parse('it fails with "{code}" and a remediation and writes nothing'))
def _fails_with(ctx: dict[str, Any], code: str) -> None:
    error = ctx["error"]
    assert error is not None and error.code == code
    assert error.remediation
    assert not (ctx["project"] / "game").exists()


# --- SCN007 ------------------------------------------------------------------------------------


@scenario(FEATURE, "Paintings are finished without a cut-out")
def test_paintings_are_finished_without_a_cut_out() -> None:
    """AC7: a painting is resized to its width at its aspect ratio, as RGB with no alpha."""


@given("a raw 16:9 painting take")
def _painting_take(ctx: dict[str, Any]) -> None:
    yy, xx = np.mgrid[0:576, 0:1024]
    rgb = np.stack([xx % 256, yy % 256, (xx + yy) % 256], axis=-1).astype(np.uint8)
    save_png(rgb, ctx["project"] / "SourceArt" / "Art" / "raw" / "painting" / "Dawn-1.png")


@then("game/assets/UI/Paintings/Dawn.png is 1920 by 1080 with no alpha channel")
def _painting_out(ctx: dict[str, Any]) -> None:
    assert ctx["code"] == 0
    painting = ctx["project"] / "game" / "assets" / "UI" / "Paintings" / "Dawn.png"
    with PILImage.open(painting) as image:
        assert image.size == (1920, 1080)
        assert image.mode == "RGB"
