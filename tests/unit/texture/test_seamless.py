"""The seamless post-process: AC18 seam threshold and dimensions."""

from __future__ import annotations

import numpy as np
import pytest

from nmg_game_dev.texture import seamless
from nmg_game_dev.texture.seamless import (
    EDGE_BAND_WIDTH,
    GROSS_SEAM_RATIO,
    edge_band,
    fix_seam,
    interior_mad,
    is_seamless,
    make_seamless,
    repair_seam,
    seam_mad,
    seam_ratios,
    seam_wraps,
)
from tests.texture_fakes import narrow_seam_albedo, stepped_normal_map, synthetic_image


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


# --- #238: edge-band repair and severity-based fix ---------------------------------------------


def _inputs() -> list[np.ndarray]:
    rgb = synthetic_image(128)
    as_float = rgb.astype(np.float64) / 255.0
    return [rgb, rgb[..., 0], as_float, as_float[..., 0]]


@pytest.mark.parametrize("img", _inputs(), ids=["u8-rgb", "u8-gray", "float-rgb", "float-gray"])
def test_edge_band_makes_the_wrap_lines_identical_and_leaves_the_middle(img: np.ndarray) -> None:
    for axis in (0, 1):
        out = edge_band(img, axis)
        assert out.shape == img.shape and out.dtype == np.float64
        np.testing.assert_allclose(np.take(out, 0, axis=axis), np.take(out, -1, axis=axis))
        middle = slice(EDGE_BAND_WIDTH, img.shape[axis] - EDGE_BAND_WIDTH)
        index: list[slice] = [slice(None)] * img.ndim
        index[axis] = middle
        np.testing.assert_array_equal(out[tuple(index)], img.astype(np.float64)[tuple(index)])


def test_edge_band_narrows_to_half_a_short_axis() -> None:
    img = synthetic_image(6)
    out = edge_band(img, 0)
    np.testing.assert_allclose(out[0], out[-1])
    assert out.shape == img.shape


@pytest.mark.parametrize("img", _inputs(), ids=["u8-rgb", "u8-gray", "float-rgb", "float-gray"])
def test_repair_seam_passes_and_keeps_shape_and_dtype(img: np.ndarray) -> None:
    assert not is_seamless(img)
    out = repair_seam(img)
    assert out.shape == img.shape and out.dtype == img.dtype
    assert is_seamless(out)


def test_repair_seam_leaves_a_passing_image_unchanged() -> None:
    img = make_seamless(synthetic_image(128))
    np.testing.assert_array_equal(repair_seam(img), img)


def _pushed_over_image() -> np.ndarray:
    """Axis 0 fails and axis 1 passes, but the axis-0 band smooths the noisy edge rows, which
    lowers the axis-1 interior until the fixed last-column step fails it."""
    rng = np.random.default_rng(0)
    img = np.full((32, 64), 0.5)
    img[:3] += rng.uniform(-0.2, 0.2, (3, 64))
    img[-3:] += rng.uniform(-0.2, 0.2, (3, 64))
    img[3:-3, -1] += 0.028
    img[-1] += 0.05
    return img


def test_repair_seam_repairs_an_axis_the_first_pass_pushed_over(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    img = _pushed_over_image()
    assert seamless.failing_axes(img) == (0,)
    assert seamless.failing_axes(edge_band(img, 0)) == (1,)
    calls: list[int] = []
    original = seamless.edge_band

    def recording(image: np.ndarray, axis: int, width: int = EDGE_BAND_WIDTH) -> np.ndarray:
        calls.append(axis)
        return original(image, axis, width)

    monkeypatch.setattr(seamless, "edge_band", recording)
    out = repair_seam(img)
    assert calls == [0, 1]
    assert is_seamless(out)


def test_fix_seam_returns_a_passing_image_unchanged() -> None:
    img = make_seamless(synthetic_image(256))
    assert is_seamless(img)
    assert fix_seam(img) is img


def test_fix_seam_band_repairs_a_narrow_failure_without_make_seamless(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    img = narrow_seam_albedo()
    assert not is_seamless(img) and max(seam_ratios(img)) <= GROSS_SEAM_RATIO

    def refuse(_: np.ndarray) -> np.ndarray:
        raise AssertionError("make_seamless must not run on a narrow failure")

    monkeypatch.setattr(seamless, "make_seamless", refuse)
    out = fix_seam(img)
    assert is_seamless(out) and out.shape == img.shape and out.dtype == img.dtype
    # Only the edge band changed: the interior rows are untouched.
    np.testing.assert_array_equal(
        out[EDGE_BAND_WIDTH:-EDGE_BAND_WIDTH], img[EDGE_BAND_WIDTH:-EDGE_BAND_WIDTH]
    )
    for before, after in zip(seam_wraps(img), seam_wraps(out), strict=True):
        assert after <= before


def test_fix_seam_cross_fades_then_bands_a_gross_failure() -> None:
    img = synthetic_image(256)
    assert max(seam_ratios(img)) > GROSS_SEAM_RATIO
    out = fix_seam(img)
    assert is_seamless(out) and out.shape == img.shape and out.dtype == img.dtype
    assert not np.array_equal(out, repair_seam(img, reference=img))
    for before, after in zip(seam_wraps(img), seam_wraps(out), strict=True):
        assert after <= before


def test_fix_seam_repairs_a_stepped_normal_map() -> None:
    img = stepped_normal_map()
    assert not is_seamless(img)
    out = fix_seam(img)
    assert is_seamless(out)
    for before, after in zip(seam_wraps(img), seam_wraps(out), strict=True):
        assert after <= before


def test_seam_ratios_match_is_seamless() -> None:
    for img in (synthetic_image(128), make_seamless(synthetic_image(128)), narrow_seam_albedo()):
        assert is_seamless(img) == (max(seam_ratios(img)) <= 1.0)
