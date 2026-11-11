"""End-to-end finalize (#69, AC5): a fixture crate through live Blender 5.2 and UE 5.8.

Runs only with ``pytest tests/e2e --runslow``.  It needs the live environment:
Blender with the MCP add-on and UE 5.8 with the Unreal MCP.  It imports into the open editor, so run
only in a dev project.  The fixture is a compliant standard_prop collection saved to
``tests/e2e/fixtures/crate.blend``, or to the path in ``NMG_FINALIZE_E2E_BLEND``. The multi-part
test builds its Gantry fixture headless, from ``fixtures/build_multipart_fixture.py`` (#145).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from nmg_game_dev.pipeline import STEP_ORDER, FinalizeRequest, finalize
from nmg_game_dev.pipeline.blender_proc import resolve_blender

pytestmark = pytest.mark.slow

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "crate.blend"
_GANTRY_BUILDER = Path(__file__).resolve().parent / "fixtures" / "build_multipart_fixture.py"


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


def test_finalize_multi_part_static_asset_keeps_size_pivots_and_names(tmp_path: Path) -> None:
    """AC7 (#145): a multi-part fixture finalizes into both variants with one static mesh per part.

    The Gantry fixture is built headless by ``fixtures/build_multipart_fixture.py``, so no manual
    step is needed. ``import_variant`` raises ``import_ue.pivot_mismatch`` on any pivot that is out
    of tolerance, so a finished import has passed the pivot check.
    """
    blend = tmp_path / "Gantry.blend"
    built = subprocess.run(
        [
            str(resolve_blender()),
            "--background",
            "--factory-startup",
            "--python",
            str(_GANTRY_BUILDER),
            "--",
            str(blend),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )
    assert built.returncode == 0, built.stderr[-2000:]
    request = FinalizeRequest(
        collection="Gantry",
        category="Props",
        asset_class="standard_prop",
        export_root=tmp_path / "export",
        blend=blend,
    )

    result = finalize(request, cache_dir=tmp_path / "cache", job_dir=tmp_path / "job")

    assert result.desktop_content_path == "/Game/Props/Gantry/Desktop"
    assert result.mobile_content_path == "/Game/Props/Gantry/Mobile"
    imports = next(step for step in result.steps if step.step == "import_ue").outputs["imports"]
    expected = ["SM_Gantry", "SM_Gantry_Hinge", "SM_Gantry_Trim"]
    for variant in ("Desktop", "Mobile"):
        assert imports[variant]["ok"] is True
        assert sorted(imports[variant]["static_meshes"]) == expected
