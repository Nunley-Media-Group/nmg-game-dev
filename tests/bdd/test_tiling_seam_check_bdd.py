"""pytest-bdd bindings for tiling_seam_check.feature: SCN001-SCN004, SCN006, SCN007 (#147).

The bake seam check is judged through bake_core/seam_metric.py, loaded by file path, because
tiling.py imports bpy. The not_seamless remediation comes from bake_core/errors.py, and the
seamless CLI output is checked in SCN007. SCN005 (texture-gen output baked in Blender) runs in
tests/blender/test_bake_tiling.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pytest_bdd import given, scenario, then, when

from nmg_game_dev.texture.__main__ import main
from nmg_game_dev.texture.seamless import is_seamless
from tests.texture_fakes import (
    load_bake_core,
    near_flat_u8,
    periodic_crop,
    periodic_noise,
    save_png,
    seam_corpus,
    smooth_ramp,
)

FEATURE = "tiling_seam_check.feature"
seam_metric = load_bake_core("seam_metric.py")
bake_errors = load_bake_core("errors.py")


def _run_bake_check(ctx: dict[str, Any]) -> None:
    ctx["bake"] = [seam_metric.passes(img) for _, img in ctx["images"]]
    ctx["details"] = [
        seam_metric.failure_detail(name, seam_metric.measure(img))
        for name, img in ctx["images"]
        if not seam_metric.passes(img)
    ]


# --- SCN001 ------------------------------


@scenario(FEATURE, "An exactly tileable busy texture passes")
def test_scn001_exactly_tileable_busy_texture_passes() -> None:
    """SCN001: an exactly periodic fine-noise texture raises no not_seamless."""


@given(
    "an exactly periodic fine-noise texture whose interior adjacent-row difference is above 0.04",
    target_fixture="ctx",
)
def _periodic_busy(tmp_path: Path) -> dict[str, Any]:
    img = periodic_noise(256, seed=0, cutoff=0.25)
    assert min(seam.interior for seam in seam_metric.measure(img)) > 0.04
    return {"tmp": tmp_path, "images": [("BC", img)]}


@when("the tiling seam check runs on it")
def _check_one(ctx: dict[str, Any]) -> None:
    _run_bake_check(ctx)


@then("no not_seamless error is raised")
def _no_error(ctx: dict[str, Any]) -> None:
    assert all(ctx["bake"]), ctx["details"]


# --- SCN002 ------------------------------


@scenario(FEATURE, "A real wrap discontinuity on a busy texture fails")
def test_scn002_wrap_discontinuity_on_busy_texture_fails() -> None:
    """SCN002: a non-periodic busy texture raises not_seamless and names the channel."""


@given(
    "a non-periodic noise texture whose wrap difference is at least 3 times its interior "
    "difference",
    target_fixture="ctx",
)
def _non_periodic_busy(tmp_path: Path) -> dict[str, Any]:
    img = periodic_crop(256, seed=0, cutoff=0.08)
    for seam in seam_metric.measure(img):
        assert seam.wrap >= 3 * seam.interior
    return {"tmp": tmp_path, "images": [("BC", img)]}


@then("not_seamless is raised and the message names the failing channel")
def _fails_and_names_channel(ctx: dict[str, Any]) -> None:
    assert not all(ctx["bake"])
    assert any(detail.startswith("BC wrap ") for detail in ctx["details"])


# --- SCN003 ------------------------------


@scenario(FEATURE, "A visible seam on a smooth texture fails")
def test_scn003_visible_seam_on_smooth_texture_fails() -> None:
    """SCN003: a smooth texture with a visible wrap step raises not_seamless."""


@given(
    "a smooth gradient whose wrap step is under 0.04 but at least 10 times its interior difference",
    target_fixture="ctx",
)
def _smooth_step(tmp_path: Path) -> dict[str, Any]:
    img = smooth_ramp()
    seam = seam_metric.measure(img)[0]
    assert seam.wrap < 0.04 and seam.wrap >= 10 * seam.interior
    return {"tmp": tmp_path, "images": [("BC", img)]}


@then("not_seamless is raised")
def _raised(ctx: dict[str, Any]) -> None:
    assert not all(ctx["bake"])


# --- SCN004 ------------------------------


@scenario(FEATURE, "Flat and near-flat textures pass")
def test_scn004_flat_and_near_flat_textures_pass() -> None:
    """SCN004: a constant and a one-level 8-bit texture raise no not_seamless."""


@given(
    "a constant texture and a near-flat 8-bit texture with one level of noise",
    target_fixture="ctx",
)
def _flat_pair(tmp_path: Path) -> dict[str, Any]:
    return {
        "tmp": tmp_path,
        "images": [("constant", np.full((256, 256, 3), 0.5)), ("near-flat", near_flat_u8())],
    }


@when("the tiling seam check runs on each")
def _check_each(ctx: dict[str, Any]) -> None:
    _run_bake_check(ctx)


# --- SCN006 ------------------------------


@scenario(FEATURE, "Bake and texture-gen agree on what seamless means")
def test_scn006_bake_and_texture_gen_agree() -> None:
    """SCN006: the bake seam check and is_seamless give the same result on every image."""


@given(
    "the seam test corpus in 8-bit and float, RGB and single-channel forms",
    target_fixture="ctx",
)
def _corpus(tmp_path: Path) -> dict[str, Any]:
    return {"tmp": tmp_path, "images": seam_corpus()}


@when("each image is judged by the bake seam check and by is_seamless")
def _judge_corpus(ctx: dict[str, Any]) -> None:
    ctx["pairs"] = [
        (name, seam_metric.passes(img), is_seamless(img)) for name, img in ctx["images"]
    ]


@then("both give the same result for every image")
def _same_result(ctx: dict[str, Any]) -> None:
    mismatched = [name for name, bake, texgen in ctx["pairs"] if bake != texgen]
    assert mismatched == []
    verdicts = [bake for _, bake, _ in ctx["pairs"]]
    assert any(verdicts) and not all(verdicts)


# --- SCN007 ------------------------------


@scenario(FEATURE, "The error and docs describe the measure and a fix")
def test_scn007_error_and_docs_describe_the_measure_and_fix() -> None:
    """SCN007: the failure message names wrap and interior; the remediation runs the CLI."""


@given("a not_seamless failure on a non-periodic texture", target_fixture="ctx")
def _failure(tmp_path: Path) -> dict[str, Any]:
    return {"tmp": tmp_path, "images": [("BC", periodic_crop(256, seed=0, cutoff=0.08))]}


@when("the author reads the message and its remediation")
def _read_message(ctx: dict[str, Any]) -> None:
    _run_bake_check(ctx)
    ctx["remediation"] = bake_errors.REASONS["not_seamless"]
    ctx["png"] = save_png(
        np.rint(ctx["images"][0][1] * 255.0).astype(np.uint8), ctx["tmp"] / "source" / "BC.png"
    )


@then("the message reports the wrap and interior values for the failing channel")
def _reports_values(ctx: dict[str, Any]) -> None:
    assert ctx["details"], "the failing texture must produce a failure detail"
    detail = ctx["details"][0]
    assert detail.startswith("BC wrap ")
    assert " vs interior " in detail


@then("the remediation names python -m nmg_game_dev.texture seamless")
def _remediation_runs(ctx: dict[str, Any], capsys: pytest.CaptureFixture[str]) -> None:
    assert "python -m nmg_game_dev.texture seamless" in ctx["remediation"]
    target = ctx["tmp"] / "tile" / "BC.png"
    assert main(["seamless", str(ctx["png"]), "--out", str(target)]) == 0
    assert json.loads(capsys.readouterr().out) == {"path": str(target), "seamless": True}
