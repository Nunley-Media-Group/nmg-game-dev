"""End-to-end finalize (#69, AC5): a fixture crate through live Blender 5.2 and UE 5.8.

Runs only with ``pytest tests/e2e --runslow``.  It needs the live environment:
Blender with the MCP add-on and UE 5.8 with the Unreal MCP.  It imports into the open editor, so run
only in a dev project.  The fixture is a compliant standard_prop collection saved to
``tests/e2e/fixtures/crate.blend``, or to the path in ``NMG_FINALIZE_E2E_BLEND``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from nmg_game_dev.pipeline import STEP_ORDER, FinalizeRequest, finalize

pytestmark = pytest.mark.slow

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "crate.blend"


def _fixture_blend() -> Path:
    override = os.environ.get("NMG_FINALIZE_E2E_BLEND")
    blend = Path(override) if override else _FIXTURE
    if not blend.is_file():
        pytest.skip(
            f"The e2e fixture is missing: {blend}. Save a compliant Crate collection there."
        )
    return blend


def test_finalize_imports_both_variants_with_identical_names(tmp_path: Path) -> None:
    blend = _fixture_blend()
    request = FinalizeRequest(
        collection="Crate",
        category="Props",
        asset_class="standard_prop",
        export_root=tmp_path / "export",
        blend=blend,
    )

    result = finalize(request, cache_dir=tmp_path / "cache", job_dir=tmp_path / "job")

    assert [step.step for step in result.steps] == list(STEP_ORDER)
    assert result.desktop_content_path == "/Game/Props/Crate/Desktop"
    assert result.mobile_content_path == "/Game/Props/Crate/Mobile"
    for variant in ("Desktop", "Mobile"):
        assert (tmp_path / "export" / "Props" / "Crate" / variant / "SM_Crate.fbx").is_file()
