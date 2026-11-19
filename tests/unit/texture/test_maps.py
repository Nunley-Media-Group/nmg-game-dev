"""Derived PBR maps: files, resolution, presets, and seams (#7 FR15, AC19)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image as PILImage

from nmg_game_dev.texture.errors import TextureGenError
from nmg_game_dev.texture.maps import PRESETS, derive, resolve_material
from nmg_game_dev.texture.seamless import is_seamless, make_seamless
from tests.texture_fakes import low_contrast_crop, periodic_crop, save_png, synthetic_image


def _seamless_albedo(tmp_path: Path, size: int = 128) -> Path:
    albedo = save_png(make_seamless(synthetic_image(size)), tmp_path / "albedo" / "tex_1_128.png")
    return albedo


def test_derive_writes_n_r_m_and_ao_at_albedo_resolution(tmp_path: Path) -> None:
    albedo = _seamless_albedo(tmp_path)
    roughness, metallic = PRESETS["stone"]
    maps = derive(albedo, roughness, metallic, ao=True)

    assert maps.normal == tmp_path / "albedo" / "tex_1_128_N.png"
    assert maps.ao == tmp_path / "albedo" / "tex_1_128_AO.png"
    for path in (maps.normal, maps.roughness, maps.metallic, maps.ao):
        assert path is not None and path.exists()
        with PILImage.open(path) as image:
            assert image.size == (128, 128)
        assert is_seamless(np.asarray(PILImage.open(path)))


def test_roughness_and_metallic_hold_the_preset_values(tmp_path: Path) -> None:
    albedo = _seamless_albedo(tmp_path)
    maps = derive(albedo, 0.85, 0.0)
    rough = np.asarray(PILImage.open(maps.roughness))
    metal = np.asarray(PILImage.open(maps.metallic))
    assert set(np.unique(rough).tolist()) == {round(0.85 * 255)}
    assert set(np.unique(metal).tolist()) == {0}
    assert maps.ao is None


def test_normal_map_is_a_unit_vector_encoding(tmp_path: Path) -> None:
    albedo = _seamless_albedo(tmp_path)
    maps = derive(albedo, 0.5, 0.0)
    normal = np.asarray(PILImage.open(maps.normal)).astype(float) / 255.0 * 2.0 - 1.0
    lengths = np.linalg.norm(normal, axis=-1)
    assert np.allclose(lengths, 1.0, atol=0.02)
    assert (normal[..., 2] > 0).all()


def test_presets_and_explicit_values_resolve() -> None:
    assert resolve_material("metal") == (0.35, 1.0)
    assert resolve_material((0.2, 0.7)) == (0.2, 0.7)


@pytest.mark.parametrize("bad", ["marble", (1.5, 0.0), (0.5, -0.1)])
def test_bad_material_is_refused(bad: str | tuple[float, float]) -> None:
    with pytest.raises(TextureGenError) as caught:
        resolve_material(bad)
    assert caught.value.code == "texture.invalid_request"


# --- #238: every derived map passes the bake seam rule ------------------------------------------


@pytest.mark.parametrize(
    "albedo",
    [make_seamless(synthetic_image(128)), make_seamless(low_contrast_crop())],
    ids=["seamless-synthetic", "seamless-low-contrast"],
)
def test_every_derived_map_passes_the_seam_rule(tmp_path: Path, albedo: np.ndarray) -> None:
    assert is_seamless(albedo)
    path = save_png(albedo, tmp_path / "albedo" / "tex_1.png")
    maps = derive(path, *PRESETS["stone"], ao=True)
    for written in (maps.normal, maps.roughness, maps.metallic, maps.ao):
        assert written is not None
        with PILImage.open(written) as image:
            assert is_seamless(np.asarray(image)), written.name


def test_a_band_repaired_normal_map_is_still_a_unit_vector_encoding(tmp_path: Path) -> None:
    # A smooth non-tiling albedo gives an N whose wrap fails until the band repair runs.
    smooth = np.rint(periodic_crop(128, seed=5, cutoff=0.08) * 255.0).astype(np.uint8)
    path = save_png(smooth, tmp_path / "albedo" / "tex_1.png")
    maps = derive(path, 0.5, 0.0)
    encoded = np.asarray(PILImage.open(maps.normal)).astype(np.float64)
    assert is_seamless(encoded.astype(np.uint8))
    np.testing.assert_array_equal(encoded[0], encoded[-1])
    np.testing.assert_array_equal(encoded[:, 0], encoded[:, -1])
    vectors = encoded / 255.0 * 2.0 - 1.0
    np.testing.assert_allclose(np.linalg.norm(vectors, axis=-1), 1.0, atol=0.02)
    assert (vectors[..., 2] > 0).all()
