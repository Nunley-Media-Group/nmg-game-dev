"""Fixtures for the texture unit tests: a fake worker, model folders, and an output root."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.texture_fakes import make_models, write_fake_worker


@pytest.fixture
def worker(tmp_path: Path) -> Path:
    return write_fake_worker(tmp_path / "worker")


@pytest.fixture
def log(tmp_path: Path) -> Path:
    return tmp_path / "worker.log"


@pytest.fixture
def models(tmp_path: Path) -> Path:
    return make_models(tmp_path / "models")


@pytest.fixture
def out_root(tmp_path: Path) -> Path:
    return tmp_path / "out"


@pytest.fixture
def env(models: Path, out_root: Path) -> dict[str, str]:
    return {
        "TEXTURE_GEN_MODELS_DIR": str(models),
        "NMG_GAME_DEV_TEXTURE_DIR": str(out_root),
    }
