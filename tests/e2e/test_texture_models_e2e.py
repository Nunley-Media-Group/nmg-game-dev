"""Opt-in real-model test: one 256 px texture per pinned backend, with the real mflux weights (#7
FR19).

It runs only when ``TEXTURE_GEN_MODELS_DIR`` holds both ``<id>-q4`` folders and the ``texture-ai``
extra (mflux) is importable. Otherwise it skips, so CI and most laptops never load a model.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

from nmg_game_dev.texture import generate
from nmg_game_dev.texture.generate import TextureRequest
from nmg_game_dev.texture.paths import models_dir
from nmg_game_dev.texture.registry import REGISTRY


def _models_ready() -> bool:
    root = models_dir(dict(os.environ))
    if root is None:
        return False
    if not all((root / f"{spec.id}-q4").is_dir() for spec in REGISTRY.values()):
        return False
    return importlib.util.find_spec("mflux") is not None


pytestmark = pytest.mark.skipif(
    not _models_ready(),
    reason="needs TEXTURE_GEN_MODELS_DIR with both <id>-q4 folders and the texture-ai extra",
)


def test_each_pinned_backend_generates_a_256px_texture(tmp_path: Path) -> None:
    for backend in REGISTRY:
        result = generate.run(
            TextureRequest(
                prompt="burlap weave",
                backend=backend,
                seeds=[42],
                resolution=256,
                name=f"e2e-{backend}",
            ),
            output_root_override=tmp_path,
        )
        image = result.images[0]
        assert image.path.exists()
        assert image.backend == backend
        assert image.resolution == 256
