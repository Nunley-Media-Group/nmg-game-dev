"""The closed registry: exactly two pinned models and the allowlist (#7 AC12, AC13)."""

from __future__ import annotations

import pytest

from nmg_game_dev.texture.errors import TextureGenError
from nmg_game_dev.texture.registry import REGISTRY, resolve


def test_registry_holds_exactly_the_two_pinned_models() -> None:
    assert list(REGISTRY) == ["z-image-turbo", "flux2-klein-4b"]
    zimage = REGISTRY["z-image-turbo"]
    assert (zimage.repo, zimage.revision, zimage.license) == (
        "Tongyi-MAI/Z-Image-Turbo",
        "f332072aa78be7aecdf3ee76d5c247082da564a6",
        "apache-2.0",
    )
    assert (zimage.quantization, zimage.default_steps, zimage.peak_memory_gb) == (4, 9, 14.6)
    flux = REGISTRY["flux2-klein-4b"]
    assert (flux.repo, flux.revision, flux.license) == (
        "black-forest-labs/FLUX.2-klein-4B",
        "e7b7dc27f91deacad38e78976d1f2b499d76a294",
        "apache-2.0",
    )
    assert (flux.quantization, flux.default_steps, flux.peak_memory_gb) == (4, 4, 12.9)


def test_registry_cannot_be_extended_at_runtime() -> None:
    with pytest.raises(TypeError):
        REGISTRY["sdxl"] = REGISTRY["z-image-turbo"]  # type: ignore[index]


@pytest.mark.parametrize(
    "repo", ["black-forest-labs/FLUX.2-klein-9B", "black-forest-labs/FLUX.1-dev"]
)
def test_unpinned_repos_are_refused(repo: str) -> None:
    with pytest.raises(TextureGenError) as caught:
        resolve(repo)
    assert caught.value.code == "texture.model_not_allowed"
    assert "z-image-turbo" in caught.value.remediation
    assert "black-forest-labs/FLUX.2-klein-4B" in caught.value.remediation


def test_unknown_backend_id_is_refused() -> None:
    with pytest.raises(TextureGenError) as caught:
        resolve("sdxl")
    assert caught.value.code == "texture.unknown_backend"
    assert "flux2-klein-4b" in caught.value.remediation


def test_pinned_repo_resolves_to_its_backend() -> None:
    assert resolve("Tongyi-MAI/Z-Image-Turbo").id == "z-image-turbo"
    assert resolve("flux2-klein-4b").repo == "black-forest-labs/FLUX.2-klein-4B"


def test_model_ref_must_match_the_backend_repo() -> None:
    with pytest.raises(TextureGenError) as caught:
        resolve("flux2-klein-4b", model_ref="black-forest-labs/FLUX.2-klein-9B")
    assert caught.value.code == "texture.model_not_allowed"
