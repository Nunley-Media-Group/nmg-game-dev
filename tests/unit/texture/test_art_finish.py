"""Finishing a picked art take into game images from synthetic takes (#253 AC5-AC7, FR4, FR5)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image as PILImage

from nmg_game_dev.texture import art_finish
from nmg_game_dev.texture.errors import TextureGenError
from tests.texture_fakes import save_png, synthetic_disc

BG = (200, 200, 200)
DISC = (180, 40, 40)
ICONS = Path("game/assets/UI/Icons")
PANELS = Path("game/assets/UI/Panels")
PAINTINGS = Path("game/assets/UI/Paintings")


def _take(root: Path, kind: str, name: str, pick: int, rgb: np.ndarray) -> Path:
    return save_png(rgb, root / "SourceArt" / "Art" / "raw" / kind / f"{name}-{pick}.png")


def _alpha_bbox(path: Path) -> tuple[int, int, int, int]:
    with PILImage.open(path) as image:
        bbox = image.getchannel("A").getbbox()
    assert bbox is not None
    return bbox


def test_icon_writes_512_and_64_pngs_with_transparent_corners_and_a_feathered_edge(
    tmp_path: Path,
) -> None:
    _take(tmp_path, "icon", "HealthPotion", 2, synthetic_disc())
    result = art_finish.finish(tmp_path, "icon", "HealthPotion", 2)
    full = tmp_path / ICONS / "HealthPotion.png"
    small = tmp_path / ICONS / "HealthPotion_small.png"
    with PILImage.open(full) as image:
        assert image.size == (512, 512)
        assert image.mode == "RGBA"
        alpha = np.asarray(image)[..., 3]
    assert alpha[0, 0] == 0 and alpha[0, -1] == 0
    assert alpha[-1, 0] == 0 and alpha[-1, -1] == 0
    assert alpha[256, 256] == 255
    row = alpha[256]
    first_visible = int(np.flatnonzero(row)[0])
    first_solid = int(np.flatnonzero(row == 255)[0])
    ramp = [int(value) for value in row[first_visible:first_solid]]
    partial = [value for value in ramp if 0 < value < 255]
    # Two 3 x 3 box passes ramp the cut-out edge over about 2 px either side of the mask edge,
    # and the resize adds about a pixel, so the partial values form a short ramp, not a hard step.
    assert partial, "the cut-out edge must carry partial alpha values"
    assert len(ramp) <= 8, f"the feather is too wide: {ramp}"
    with PILImage.open(small) as image:
        assert image.size == (64, 64)
    assert {entry["path"] for entry in result["files"]} == {str(full), str(small)}


def test_the_subject_is_centred_with_an_eight_percent_margin_and_its_bottom_on_the_baseline(
    tmp_path: Path,
) -> None:
    _take(tmp_path, "icon", "HealthPotion", 2, synthetic_disc())
    art_finish.finish(tmp_path, "icon", "HealthPotion", 2)
    left, top, right, bottom = _alpha_bbox(tmp_path / ICONS / "HealthPotion.png")
    # A square subject fills the long side: 512 * (1 - 2 * 0.08) = 430 px, centred, on baseline 471.
    assert abs((left + right) / 2 - 256) <= 1
    assert abs(bottom - 471) <= 1
    assert abs((bottom - top) - 430) <= 2


def test_two_subjects_share_the_same_baseline(tmp_path: Path) -> None:
    rectangle = np.full((512, 512, 3), BG, dtype=np.uint8)
    rectangle[60:460, 200:312] = DISC
    _take(tmp_path, "icon", "Disc", 1, synthetic_disc())
    _take(tmp_path, "icon", "Tall", 1, rectangle)
    art_finish.finish(tmp_path, "icon", "Disc", 1)
    art_finish.finish(tmp_path, "icon", "Tall", 1)
    disc_bottom = _alpha_bbox(tmp_path / ICONS / "Disc.png")[3]
    tall_bottom = _alpha_bbox(tmp_path / ICONS / "Tall.png")[3]
    assert abs(disc_bottom - tall_bottom) <= 1


def test_a_rerun_gives_byte_identical_icon_files(tmp_path: Path) -> None:
    _take(tmp_path, "icon", "HealthPotion", 2, synthetic_disc())
    art_finish.finish(tmp_path, "icon", "HealthPotion", 2)
    full = tmp_path / ICONS / "HealthPotion.png"
    small = tmp_path / ICONS / "HealthPotion_small.png"
    first = (full.read_bytes(), small.read_bytes())
    art_finish.finish(tmp_path, "icon", "HealthPotion", 2)
    assert (full.read_bytes(), small.read_bytes()) == first


def test_ui_art_writes_only_the_1024_panel(tmp_path: Path) -> None:
    _take(tmp_path, "ui", "Frame", 1, synthetic_disc())
    result = art_finish.finish(tmp_path, "ui", "Frame", 1)
    panel = tmp_path / PANELS / "Frame.png"
    with PILImage.open(panel) as image:
        assert image.size == (1024, 1024)
    assert not (tmp_path / PANELS / "Frame_small.png").exists()
    assert [entry["path"] for entry in result["files"]] == [str(panel)]


def test_a_background_whose_corners_differ_is_rejected_and_nothing_is_written(
    tmp_path: Path,
) -> None:
    gradient = np.zeros((512, 512, 3), dtype=np.uint8)
    gradient[..., 0] = np.linspace(0, 255, 512, dtype=np.uint8)[None, :]
    _take(tmp_path, "icon", "Blurred", 1, gradient)
    with pytest.raises(TextureGenError) as caught:
        art_finish.finish(tmp_path, "icon", "Blurred", 1)
    assert caught.value.code == "art.background_not_flat"
    assert caught.value.remediation
    assert not (tmp_path / ICONS).exists()


def test_a_subject_touching_the_edge_is_rejected_and_nothing_is_written(tmp_path: Path) -> None:
    _take(tmp_path, "icon", "Clipped", 1, synthetic_disc(center_x=40, radius=60))
    with pytest.raises(TextureGenError) as caught:
        art_finish.finish(tmp_path, "icon", "Clipped", 1)
    assert caught.value.code == "art.subject_cropped"
    assert not (tmp_path / ICONS).exists()


def test_a_take_with_no_subject_is_rejected_as_cropped(tmp_path: Path) -> None:
    _take(tmp_path, "icon", "Empty", 1, np.full((512, 512, 3), BG, dtype=np.uint8))
    with pytest.raises(TextureGenError) as caught:
        art_finish.finish(tmp_path, "icon", "Empty", 1)
    assert caught.value.code == "art.subject_cropped"


def test_a_painting_is_resized_to_1920_wide_as_rgb_without_alpha(tmp_path: Path) -> None:
    yy, xx = np.mgrid[0:576, 0:1024]
    rgb = np.stack([xx % 256, yy % 256, (xx + yy) % 256], axis=-1).astype(np.uint8)
    _take(tmp_path, "painting", "Dawn", 1, rgb)
    result = art_finish.finish(tmp_path, "painting", "Dawn", 1, width=1920)
    target = tmp_path / PAINTINGS / "Dawn.png"
    with PILImage.open(target) as image:
        assert image.size == (1920, 1080)
        assert image.mode == "RGB"
    assert [entry["path"] for entry in result["files"]] == [str(target)]


def test_a_painting_without_a_width_uses_1920_and_a_rerun_is_byte_identical(
    tmp_path: Path,
) -> None:
    _take(tmp_path, "painting", "Dawn", 1, np.full((576, 1024, 3), 90, dtype=np.uint8))
    art_finish.finish(tmp_path, "painting", "Dawn", 1)
    target = tmp_path / PAINTINGS / "Dawn.png"
    with PILImage.open(target) as image:
        assert image.size == (1920, 1080)
    first = target.read_bytes()
    art_finish.finish(tmp_path, "painting", "Dawn", 1)
    assert target.read_bytes() == first


def test_a_missing_take_raises_take_not_found(tmp_path: Path) -> None:
    with pytest.raises(TextureGenError) as caught:
        art_finish.finish(tmp_path, "icon", "HealthPotion", 9)
    assert caught.value.code == "art.take_not_found"
    assert "HealthPotion-9.png" in caught.value.message


def test_width_applies_to_paintings_only(tmp_path: Path) -> None:
    _take(tmp_path, "icon", "HealthPotion", 1, synthetic_disc())
    with pytest.raises(TextureGenError) as caught:
        art_finish.finish(tmp_path, "icon", "HealthPotion", 1, width=1920)
    assert caught.value.code == "texture.invalid_request"
