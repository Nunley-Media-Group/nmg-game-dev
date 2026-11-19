"""End-to-end terrain finalize (#154, #249): a grid terrain through headless Blender and Godot.

Runs only with ``pytest tests/e2e --runslow``. It needs Blender and Godot 4 resolvable as for the
finalize e2e suite. It writes a throwaway Godot project under ``tmp_path/game`` and finalizes into
``game/assets``. The fixture is a valid terrain collection saved to
``tests/e2e/fixtures/terrain.blend``, or to the path in ``NMG_TERRAIN_E2E_BLEND``. The collection
holds one SM_Ground grid at 127 with two Layer attributes and their M_Ground_<Layer> materials.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from nmg_game_dev.pipeline import STEP_ORDER, FinalizeRequest, finalize

pytestmark = pytest.mark.slow

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "terrain.blend"


def _fixture_blend() -> Path:
    override = os.environ.get("NMG_TERRAIN_E2E_BLEND")
    blend = Path(override) if override else _FIXTURE
    if not blend.is_file():
        pytest.skip(
            f"The terrain e2e fixture is missing: {blend}. Save a valid Ground terrain there."
        )
    return blend


def test_terrain_finalize_exports_both_variants_and_builds_their_scenes(tmp_path: Path) -> None:
    blend = _fixture_blend()
    game = tmp_path / "game"
    game.mkdir()
    (game / "project.godot").write_text("config_version=5\n", encoding="utf-8")
    request = FinalizeRequest(
        collection="Ground",
        category="Terrain",
        asset_class="terrain",
        export_root=game / "assets",
        blend=blend,
    )

    result = finalize(request, cache_dir=tmp_path / "cache", job_dir=tmp_path / "job")

    assert [step.step for step in result.steps] == list(STEP_ORDER)
    assert result.desktop_resource_path == "res://assets/Terrain/Ground/Desktop/Ground.tscn"
    root = request.export_root / "Terrain" / "Ground"
    for variant in ("Desktop", "Mobile"):
        assert (root / variant / "T_Ground_Height.png").is_file()
        assert (root / variant / "T_Ground_Splat.png").is_file()
        assert (root / variant / "Ground_Chunk_0_0.glb").is_file()
        scene = (root / variant / "Ground.tscn").read_text(encoding="utf-8")
        assert "HeightMapShape3D" in scene
        assert (root / variant / "nmg-asset.json").is_file()
    assert (root / "nmg-variants.json").is_file()
