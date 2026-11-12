"""End-to-end finalize (#69, AC5): a fixture crate through live Blender 5.2 and UE 5.8.

Runs only with ``pytest tests/e2e --runslow``.  It needs the live environment:
Blender with the MCP add-on and UE 5.8 with the Unreal MCP.  It imports into the open editor, so run
only in a dev project.  The fixture is a compliant standard_prop collection saved to
``tests/e2e/fixtures/crate.blend``, or to the path in ``NMG_FINALIZE_E2E_BLEND``. The multi-part
test builds its Gantry fixture headless, from ``fixtures/build_multipart_fixture.py`` (#145). The
static LOD group test builds a single-mesh Crate headless from ``fixtures/build_crate_fixture.py``
when no Crate fixture is set up (#146).
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from nmg_game_dev.pipeline import STEP_ORDER, FinalizeRequest, finalize
from nmg_game_dev.pipeline.blender_proc import resolve_blender
from nmg_game_dev.pipeline.clients.unreal_mcp import UnrealMcpClient
from nmg_game_dev.unreal import import_variant, parse_nmg_result

pytestmark = pytest.mark.slow

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "crate.blend"
_GANTRY_BUILDER = Path(__file__).resolve().parent / "fixtures" / "build_multipart_fixture.py"
_CRATE_BUILDER = Path(__file__).resolve().parent / "fixtures" / "build_crate_fixture.py"
_MOBILE_FOLDER = "/Game/Props/Crate/Mobile"

#: Reads the imported Mobile Static Mesh back from the editor. It prints one NMG_RESULT line.
#: ``get_num_triangles`` is the BlueprintPure ``UStaticMesh::GetNumTriangles`` (UE 5.8).
_STATIC_MOBILE_QUERY = """
import json
import unreal

FOLDER = "/Game/Props/Crate/Mobile"
mesh = unreal.EditorAssetLibrary.load_asset(FOLDER + "/SM_Crate")
is_static = isinstance(mesh, unreal.StaticMesh)
lod_count = mesh.get_num_lods() if is_static else None
lod_triangles = [mesh.get_num_triangles(lod) for lod in range(lod_count)] if is_static else []
per_lod_assets = [
    path
    for path in unreal.EditorAssetLibrary.list_assets(FOLDER, recursive=False, include_folder=False)
    if "SM_Crate_LOD" in path
]
print("NMG_RESULT " + json.dumps({
    "is_static_mesh": is_static,
    "lod_count": lod_count,
    "lod_triangles": lod_triangles,
    "per_lod_assets": per_lod_assets,
}, sort_keys=True))
"""


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


def _static_crate_blend(tmp_path: Path) -> Path:
    """The Crate for the static LOD test: crate.blend when it is set up, else a headless build.

    The build writes a single-mesh, non-rigged Crate with no manual step (#146).
    """
    override = os.environ.get("NMG_FINALIZE_E2E_BLEND")
    if override and Path(override).is_file():
        return Path(override)
    if _FIXTURE.is_file():
        return _FIXTURE
    blend = tmp_path / "Crate.blend"
    built = subprocess.run(
        [
            str(resolve_blender()),
            "--background",
            "--factory-startup",
            "--python",
            str(_CRATE_BUILDER),
            "--",
            str(blend),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )
    assert built.returncode == 0, built.stderr[-2000:]
    return blend


def test_finalize_static_mobile_lod_group_imports_as_one_static_mesh(tmp_path: Path) -> None:
    """AC1, AC5, AC6, AC8 (#146): a static Mobile LOD group imports as one Static Mesh with 3 LODs.

    The Mobile variant of a single-mesh Crate exports as an LOD group. The import must give one
    Static Mesh SM_Crate in the Mobile folder with three LODs and no per-LOD asset, with each LOD's
    triangle count equal to the variants step's record. A second Mobile import over it must pass
    the LOD count check again.
    """
    blend = _static_crate_blend(tmp_path)
    request = FinalizeRequest(
        collection="Crate",
        category="Props",
        asset_class="standard_prop",
        export_root=tmp_path / "export",
        blend=blend,
    )

    result = finalize(request, cache_dir=tmp_path / "cache", job_dir=tmp_path / "job")

    assert result.desktop_content_path == "/Game/Props/Crate/Desktop"
    assert result.mobile_content_path == _MOBILE_FOLDER
    steps = {step.step: step for step in result.steps}
    imports = steps["import_ue"].outputs["imports"]
    assert imports["Mobile"]["ok"] is True
    assert sorted(imports["Mobile"]["static_meshes"]) == ["SM_Crate"]
    assert imports["Mobile"]["static_meshes"]["SM_Crate"]["lod_count"] == 3
    assert imports["Mobile"]["materials"] == {"M_Crate_Body": _MOBILE_FOLDER + "/MI_Crate_Body"}

    lod_tris = steps["variants"].outputs["tris"]["Mobile"]["lod_tris"]
    assert len(lod_tris) == 3
    assert lod_tris[0] > lod_tris[1] > lod_tris[2]
    with UnrealMcpClient() as client:
        facts = parse_nmg_result(client.execute_python_code(_STATIC_MOBILE_QUERY))
    assert facts["is_static_mesh"] is True
    assert facts["lod_count"] == 3
    assert facts["per_lod_assets"] == []
    assert facts["lod_triangles"] == lod_tris

    export = steps["export"].outputs["variants"]["Mobile"]
    report = json.loads(Path(str(export["pre_report"])).read_text(encoding="utf-8"))
    with UnrealMcpClient() as client:
        again = import_variant(
            client,
            variant_dir=str(export["dir"]),
            dest=_MOBILE_FOLDER,
            name="Crate",
            report=report,
        )
    assert again["static_meshes"]["SM_Crate"]["lod_count"] == 3
