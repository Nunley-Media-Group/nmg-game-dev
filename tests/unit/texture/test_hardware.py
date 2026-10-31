"""Availability: platform, memory after the Blender reserve, and installed weights (#7 AC14,
AC15)."""

from __future__ import annotations

from pathlib import Path

import pytest

from nmg_game_dev.texture.errors import TextureGenError
from nmg_game_dev.texture.hardware import (
    DEFAULT_RESERVE_GB,
    availability,
    require_available,
    reserve_gb,
)
from nmg_game_dev.texture.registry import REGISTRY
from tests.texture_fakes import APPLE_SILICON_16GB, APPLE_SILICON_32GB, INTEL_LINUX, make_models

ZIMAGE = REGISTRY["z-image-turbo"]
FLUX = REGISTRY["flux2-klein-4b"]


def test_available_when_hardware_fits_and_weights_exist(models: Path) -> None:
    assert availability(ZIMAGE, APPLE_SILICON_32GB, models, DEFAULT_RESERVE_GB) == "available"


def test_x86_linux_is_unsupported(models: Path) -> None:
    assert availability(ZIMAGE, INTEL_LINUX, models, DEFAULT_RESERVE_GB) == "unsupported_platform"
    with pytest.raises(TextureGenError) as caught:
        require_available(ZIMAGE, INTEL_LINUX, models, DEFAULT_RESERVE_GB)
    assert caught.value.code == "texture.unsupported_platform"
    assert caught.value.remediation


def test_sixteen_gb_mac_has_insufficient_memory(models: Path) -> None:
    assert availability(ZIMAGE, APPLE_SILICON_16GB, models, 8.0) == "insufficient_memory"
    with pytest.raises(TextureGenError) as caught:
        require_available(ZIMAGE, APPLE_SILICON_16GB, models, 8.0)
    assert caught.value.code == "texture.insufficient_memory"
    assert "TEXTURE_GEN_BLENDER_RESERVE_GB" in caught.value.remediation


def test_missing_weights_point_at_onboarding(tmp_path: Path) -> None:
    models = make_models(tmp_path / "models", ids=("z-image-turbo",))
    assert availability(FLUX, APPLE_SILICON_32GB, models, DEFAULT_RESERVE_GB) == "not_installed"
    with pytest.raises(TextureGenError) as caught:
        require_available(FLUX, APPLE_SILICON_32GB, models, DEFAULT_RESERVE_GB)
    error = caught.value
    assert error.code == "texture.model_not_installed"
    assert "/onboard-consumer" in error.remediation
    expected_path = models / "flux2-klein-4b-q4"
    assert (
        f"mflux-save --model flux2-klein-4b --quantize 4 --path {expected_path}"
        in error.remediation
    )
    assert str(expected_path) in error.remediation


def test_unset_models_dir_is_not_installed() -> None:
    assert availability(FLUX, APPLE_SILICON_32GB, None, DEFAULT_RESERVE_GB) == "not_installed"


def test_empty_weights_folder_counts_as_missing(tmp_path: Path) -> None:
    (tmp_path / "flux2-klein-4b-q4").mkdir()
    assert availability(FLUX, APPLE_SILICON_32GB, tmp_path, DEFAULT_RESERVE_GB) == "not_installed"


def test_reserve_defaults_to_eight_and_reads_the_env() -> None:
    assert reserve_gb({}) == 8.0
    assert reserve_gb({"TEXTURE_GEN_BLENDER_RESERVE_GB": "4"}) == 4.0


def test_reserve_rejects_a_bad_value() -> None:
    with pytest.raises(TextureGenError) as caught:
        reserve_gb({"TEXTURE_GEN_BLENDER_RESERVE_GB": "lots"})
    assert caught.value.code == "texture.invalid_request"
