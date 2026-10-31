"""Fixtures for the onboarding unit tests: a fake framework root, a fixture consumer, and stub
env."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.onboard_fakes import make_consumer, make_framework


@pytest.fixture
def framework(tmp_path: Path) -> Path:
    return make_framework(tmp_path / "framework")


@pytest.fixture
def consumer(tmp_path: Path) -> Path:
    return make_consumer(tmp_path)


@pytest.fixture
def volume(tmp_path: Path) -> Path:
    return tmp_path / "volume"


@pytest.fixture
def models(volume: Path) -> Path:
    return volume / "nmg-texture-models"


@pytest.fixture
def extensions(tmp_path: Path) -> Path:
    return tmp_path / "extensions" / "user_default"


@pytest.fixture
def env(extensions: Path, models: Path) -> dict[str, str]:
    return {
        "BLENDER_EXTENSIONS_DIR": str(extensions),
        "TEXTURE_GEN_MODELS_DIR": str(models),
    }
