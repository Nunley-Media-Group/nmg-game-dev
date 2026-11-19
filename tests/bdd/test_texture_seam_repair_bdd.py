"""pytest-bdd bindings for texture_seam_repair.feature: SCN001-SCN006 (#238).

Generation runs with the fake worker copying the low-contrast band-limited fixture, the derived
maps are written by ``maps.derive``, and the ``seamless`` CLI runs in process through ``main``.
SCN005 runs the existing texture unit and BDD modules in a child pytest process.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image as PILImage
from pytest_bdd import given, parsers, scenarios, then, when

from nmg_game_dev.texture import deps
from nmg_game_dev.texture.__main__ import main
from nmg_game_dev.texture.generate import TextureRequest, run
from nmg_game_dev.texture.maps import PRESETS, derive
from nmg_game_dev.texture.seamless import is_seamless, make_seamless, seam_wraps
from tests.texture_fakes import (
    APPLE_SILICON_32GB,
    fake_spawn,
    low_contrast_crop,
    make_models,
    narrow_seam_albedo,
    save_png,
    stepped_normal_map,
    synthetic_image,
    write_fake_worker,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

scenarios("texture_seam_repair.feature")


def _pixels(path: Path) -> np.ndarray:
    with PILImage.open(path) as opened:
        return np.asarray(opened)


@pytest.fixture
def ctx(tmp_path: Path) -> dict[str, Any]:
    return {"tmp": tmp_path}


# --- SCN001 ---------------------------------------------------------------------------------------


@given("a fake worker that writes the low-contrast band-limited image")
def _low_contrast_worker(ctx: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(deps, "missing_module", lambda: None)
    tmp: Path = ctx["tmp"]
    source = save_png(low_contrast_crop(), tmp / "source" / "low_contrast.png")
    ctx["spawn"] = fake_spawn(
        write_fake_worker(tmp / "worker"), tmp / "worker.log", source_png=source
    )


@given(parsers.parse('a request with the "{preset}" preset and AO'))
def _request(ctx: dict[str, Any], preset: str) -> None:
    ctx["request"] = TextureRequest(
        prompt=preset,
        backend="flux2-klein-4b",
        seeds=[5],
        resolution=256,
        name=preset,
        maps=preset,
        ao=True,
    )


@when("texture generation runs")
def _generate(ctx: dict[str, Any]) -> None:
    tmp: Path = ctx["tmp"]
    out_root = tmp / "out"
    env = {
        "TEXTURE_GEN_MODELS_DIR": str(make_models(tmp / "models")),
        "NMG_GAME_DEV_TEXTURE_DIR": str(out_root),
    }
    result = run(
        ctx["request"],
        env=env,
        facts=APPLE_SILICON_32GB,
        spawn=ctx["spawn"],
        cwd=tmp,
        output_root_override=out_root,
    )
    image = result.images[0]
    assert set(image.maps) == {"N", "R", "M", "AO"}
    ctx["written"] = [image.path, *(Path(path) for path in image.maps.values())]


@then("the albedo and its N, R, M and AO PNGs each pass is_seamless")
def _generated_pass(ctx: dict[str, Any]) -> None:
    assert len(ctx["written"]) == 5
    for path in ctx["written"]:
        assert is_seamless(_pixels(path)), path.name


# --- SCN002 ---------------------------------------------------------------------------------------

_PASSING_ALBEDOS = {
    "seamless synthetic": lambda: make_seamless(synthetic_image(128)),
    "seamless low-contrast": lambda: make_seamless(low_contrast_crop()),
}


@given(parsers.parse('the passing albedo "{albedo}"'))
def _passing_albedo(ctx: dict[str, Any], albedo: str) -> None:
    image = _PASSING_ALBEDOS[albedo]()
    assert is_seamless(image)
    ctx["albedo"] = save_png(image, ctx["tmp"] / "albedo" / "tex_1.png")


@when("maps.derive writes N, R, M and AO")
def _derive(ctx: dict[str, Any]) -> None:
    maps = derive(ctx["albedo"], *PRESETS["stone"], ao=True)
    ctx["written"] = [maps.normal, maps.roughness, maps.metallic, maps.ao]


@then("each derived map passes is_seamless")
def _derived_pass(ctx: dict[str, Any]) -> None:
    for path in ctx["written"]:
        assert path is not None
        assert is_seamless(_pixels(path)), path.name


# --- SCN003 / SCN004 ------------------------------------------------------------------------------

_FAILING_IMAGES = {
    "non-tiling synthetic": lambda: synthetic_image(256),
    "narrow seam albedo": narrow_seam_albedo,
    "stepped normal map": stepped_normal_map,
}


@given("a PNG of the seamless synthetic albedo")
def _passing_png(ctx: dict[str, Any]) -> None:
    image = make_seamless(synthetic_image(256))
    assert is_seamless(image)
    ctx["input"] = image
    ctx["png"] = save_png(image, ctx["tmp"] / "tile.png")


@given(parsers.parse('a PNG of the failing image "{image}"'))
def _failing_png(ctx: dict[str, Any], image: str) -> None:
    array = _FAILING_IMAGES[image]()
    assert not is_seamless(array)
    ctx["input"] = array
    ctx["png"] = save_png(array, ctx["tmp"] / "fail.png")


@when("python -m nmg_game_dev.texture seamless runs on it")
def _run_seamless(ctx: dict[str, Any], capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["seamless", str(ctx["png"])]) == 0
    ctx["json"] = json.loads(capsys.readouterr().out)
    ctx["output"] = _pixels(ctx["png"])


@then("the written pixels equal the input pixels")
def _unchanged(ctx: dict[str, Any]) -> None:
    np.testing.assert_array_equal(ctx["output"], ctx["input"])


@then("the printed JSON reports seamless true")
def _json_true(ctx: dict[str, Any]) -> None:
    assert ctx["json"] == {"path": str(ctx["png"]), "seamless": True}


@then("the written image passes is_seamless with the input's shape and dtype")
def _repaired(ctx: dict[str, Any]) -> None:
    output: np.ndarray = ctx["output"]
    assert is_seamless(output)
    assert output.shape == ctx["input"].shape and output.dtype == ctx["input"].dtype
    assert ctx["json"]["seamless"] is True


@then("on neither axis is its wrap larger than the input's")
def _not_worse(ctx: dict[str, Any]) -> None:
    for before, after in zip(seam_wraps(ctx["input"]), seam_wraps(ctx["output"]), strict=True):
        assert after <= before


# --- SCN005 ---------------------------------------------------------------------------------------

_EXISTING_TESTS = (
    "tests/unit/texture",
    "tests/bdd/test_texture_bdd.py",
    "tests/bdd/test_tiling_seam_check_bdd.py",
)


@given("the existing texture unit tests and texture BDD scenarios")
def _existing(ctx: dict[str, Any]) -> None:
    for target in _EXISTING_TESTS:
        assert (REPO_ROOT / target).exists(), target


@when("they run against the fixed package")
def _run_existing(ctx: dict[str, Any]) -> None:
    code = (
        "import sys, pytest; sys.exit(pytest.main(['-q', '-p', 'no:cacheprovider', *sys.argv[1:]]))"
    )
    ctx["process"] = subprocess.run(
        [sys.executable, "-c", code, *_EXISTING_TESTS],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


@then("they all pass")
def _all_pass(ctx: dict[str, Any]) -> None:
    process: subprocess.CompletedProcess[str] = ctx["process"]
    assert process.returncode == 0, process.stdout[-4000:] + process.stderr[-4000:]


# --- SCN006 ---------------------------------------------------------------------------------------

_DOCS = ("docs/onboarding/texture-models.md", "docs/skills/bake-materials.md")


@given("docs/onboarding/texture-models.md and docs/skills/bake-materials.md")
def _docs(ctx: dict[str, Any]) -> None:
    ctx["docs"] = {name: (REPO_ROOT / name).read_text(encoding="utf-8") for name in _DOCS}


@when("the seamless section and the not_seamless remediation are read")
def _sections(ctx: dict[str, Any]) -> None:
    onboarding = ctx["docs"][_DOCS[0]]
    section = onboarding.split("## Make a source texture seamless", 1)[1].split("\n## ", 1)[0]
    remediation = next(
        line for line in ctx["docs"][_DOCS[1]].splitlines() if line.startswith("| `not_seamless`")
    )
    ctx["sections"] = {
        name: " ".join(text.split())
        for name, text in zip(_DOCS, (section, remediation), strict=True)
    }


@then(
    "each says images packed into a .blend file must be reloaded or repacked from the fixed files"
)
def _says_reload(ctx: dict[str, Any]) -> None:
    for name, text in ctx["sections"].items():
        assert "packed into" in text and "`.blend`" in text, name
        assert "reloaded or repacked from the fixed files" in text, name
