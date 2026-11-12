"""End-to-end terrain finalize (#154): a grid terrain through live Blender 5.2 and UE 5.8.

Runs only with ``pytest tests/e2e --runslow``. It needs the live environment: Blender with the MCP
add-on, and UE 5.8 with the Unreal MCP and a dev project. It imports a Landscape level into the open
editor, so run it only in a dev project and never as a required gate. The fixture is a valid
terrain collection saved to ``tests/e2e/fixtures/terrain.blend``, or to the path in
``NMG_TERRAIN_E2E_BLEND``. The collection holds one SM_Ground grid at 127 with two Layer attributes
and their M_Ground_<Layer> materials.
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


def test_terrain_finalize_exports_both_variants_and_builds_their_levels(tmp_path: Path) -> None:
    blend = _fixture_blend()
    request = FinalizeRequest(
        collection="Ground",
        category="Terrain",
        asset_class="terrain",
        export_root=tmp_path / "export",
        blend=blend,
    )

    result = finalize(request, cache_dir=tmp_path / "cache", job_dir=tmp_path / "job")

    assert [step.step for step in result.steps] == list(STEP_ORDER)
    root = tmp_path / "export" / "Terrain" / "Ground"
    for variant in ("Desktop", "Mobile"):
        assert (root / variant / "T_Ground_Height.png").is_file()
        assert (root / variant / "T_Ground_Layer_Grass.png").is_file()
    assert (root / "nmg-variants.json").is_file()
    assert (root / "Mobile" / "nmg-asset.json").is_file()
