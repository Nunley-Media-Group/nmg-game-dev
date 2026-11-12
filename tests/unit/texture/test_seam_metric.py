"""The bake seam measure and texture-gen's is_seamless agree (#147 AC1 to AC7, FR1 to FR5).

bake_core/seam_metric.py and bake_core/errors.py are loaded by file path (tests.texture_fakes.
load_bake_core): the add-on is a Blender package that cannot be imported under plain CPython.
"""

from __future__ import annotations

import numpy as np

from nmg_game_dev.texture.seamless import SEAM_FLOOR, SEAM_RATIO, is_seamless, make_seamless
from tests.texture_fakes import (
    load_bake_core,
    near_flat_u8,
    periodic_crop,
    periodic_noise,
    seam_corpus,
    smooth_ramp,
    synthetic_image,
    white_noise_u8,
)

seam_metric = load_bake_core("seam_metric.py")
bake_errors = load_bake_core("errors.py")


def test_ac1_exactly_tileable_busy_texture_passes_both_checks() -> None:
    img = periodic_noise(256, seed=0, cutoff=0.25)
    assert min(seam.interior for seam in seam_metric.measure(img)) > 0.04
    assert seam_metric.passes(img)
    assert is_seamless(img)


def test_ac2_wrap_discontinuity_on_busy_noise_fails_and_names_the_channel() -> None:
    img = periodic_crop(256, seed=0, cutoff=0.08)
    seams = seam_metric.measure(img)
    for seam in seams:
        assert seam.wrap >= 3 * seam.interior
    assert not seam_metric.passes(img)
    assert not is_seamless(img)
    detail = seam_metric.failure_detail("BC", seams)
    assert detail.startswith("BC wrap ")
    assert " vs interior " in detail


def test_ac3_visible_seam_on_a_smooth_texture_fails() -> None:
    img = smooth_ramp()
    seam = seam_metric.measure(img)[0]
    assert seam.wrap < 0.04
    assert seam.wrap >= 10 * seam.interior
    assert not seam_metric.passes(img)
    assert not is_seamless(img)


def test_ac4_constant_and_near_flat_textures_pass_without_division() -> None:
    constant = np.full((256, 256, 3), 0.5)
    for img in (constant, near_flat_u8()):
        with np.errstate(divide="raise", invalid="raise"):
            seams = seam_metric.measure(img)
        assert all(seam.allowed >= SEAM_FLOOR for seam in seams)
        assert seam_metric.passes(img)
        assert is_seamless(img)


def test_ac5_make_seamless_output_passes_the_bake_metric() -> None:
    for img in (synthetic_image(256), white_noise_u8(256, seed=0)):
        out = make_seamless(img)
        assert out.shape == img.shape
        assert seam_metric.passes(out)
        assert is_seamless(out)


def test_ac6_bake_metric_and_is_seamless_agree_on_every_corpus_image() -> None:
    assert seam_metric.SEAM_RATIO == SEAM_RATIO
    assert seam_metric.SEAM_FLOOR == SEAM_FLOOR
    verdicts: list[bool] = []
    for name, img in seam_corpus():
        bake_verdict = seam_metric.passes(img)
        assert bake_verdict == is_seamless(img), name
        verdicts.append(bake_verdict)
    # The corpus is only meaningful if it holds both outcomes.
    assert any(verdicts) and not all(verdicts)


def test_ac7_not_seamless_remediation_names_the_seamless_subcommand() -> None:
    assert "python -m nmg_game_dev.texture seamless" in bake_errors.REASONS["not_seamless"]
