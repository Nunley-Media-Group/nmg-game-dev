"""The seamless post-process: AC18 seam threshold and dimensions."""

from __future__ import annotations

import numpy as np

from nmg_game_dev.texture.seamless import interior_mad, is_seamless, make_seamless, seam_mad
from tests.texture_fakes import synthetic_image


def test_input_seam_is_far_worse_than_the_interior() -> None:
    img = synthetic_image(256)
    for axis in (0, 1):
        assert seam_mad(img, axis) > 5 * interior_mad(img, axis)
    assert not is_seamless(img)


def test_make_seamless_passes_the_seam_check_and_keeps_dimensions() -> None:
    img = synthetic_image(256)
    out = make_seamless(img)
    assert out.shape == img.shape
    assert out.dtype == np.uint8
    for axis in (0, 1):
        assert seam_mad(out, axis) <= 1.5 * interior_mad(out, axis)
    assert is_seamless(out)


def test_make_seamless_handles_single_channel() -> None:
    gray = synthetic_image(128)[..., 0]
    out = make_seamless(gray)
    assert out.shape == gray.shape
    assert is_seamless(out)
