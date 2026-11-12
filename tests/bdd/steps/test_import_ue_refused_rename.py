"""pytest-bdd bindings for import_ue_refused_rename.feature: SCN001-SCN004 of #203.

Each scenario runs the generated UE import code against tests/unit/fake_unreal.py through
import_variant, with the refusal knobs set where the scenario refuses a rename or consolidation.
The failure scenarios read back the PipelineError that import_variant raises, which carries the
NMG_RESULT error text. SCN004 is the success path, and it keeps the #145 re-import behavior.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, scenario, then, when

from nmg_game_dev.pipeline.errors import PipelineError
from tests.unit.fake_unreal import (
    BIG_HIGH,
    BIG_LOW,
    DESKTOP_DEST,
    SMALL_HIGH,
    SMALL_LOW,
    FbxNode,
    part,
    run_import,
    stage,
)

_FEATURE = "import_ue_refused_rename.feature"


@pytest.fixture()
def state() -> dict[str, Any]:
    return {}


def _error(state: dict[str, Any]) -> PipelineError:
    error = state.get("error")
    assert isinstance(error, PipelineError), "the import did not fail"
    return error


def _lid_import(state: dict[str, Any], tmp_path: Path) -> None:
    """A Desktop import whose part SM_Crate_Lid imports as SM_Crate_Lid_001, as #145 stages it."""
    state["case"] = stage(
        tmp_path,
        "desktop",
        part("desktop", "SM_Crate", BIG_LOW, BIG_HIGH),
        part("desktop", "SM_Crate_Lid", SMALL_LOW, SMALL_HIGH, duplicate=True),
    )


def _lid_reimport(state: dict[str, Any], tmp_path: Path) -> None:
    """The same import, into a folder where SM_Crate_Lid already exists beside SM_Crate_Lid_001."""
    _lid_import(state, tmp_path)
    world = state["case"][0]
    lid = FbxNode("SM_Crate_Lid", "SM_Crate_Lid.001", SMALL_LOW, SMALL_HIGH)
    world.seed_static_mesh(DESKTOP_DEST + "/SM_Crate_Lid", lid)
    world.seed_static_mesh(DESKTOP_DEST + "/SM_Crate_Lid_001", lid)


@when("import_ue imports the variant")
def _import_variant(state: dict[str, Any]) -> None:
    world, folder, report = state["case"]
    try:
        state["result"] = run_import(world, folder, "desktop", report)
    except PipelineError as error:
        state["error"] = error


@then('the import fails with "import_ue.failed"')
def _fails_with_code(state: dict[str, Any]) -> None:
    assert _error(state).code == "import_ue.failed"


# --- SCN001: a refused part rename fails the import ----------------------------------------


@scenario(_FEATURE, "A refused part rename fails the import")
def test_scn001_a_refused_part_rename_fails_the_import() -> None:
    """SCN001 (AC1, FR1)."""


@given('a Desktop multi-part static import whose part "SM_Crate_Lid" imports as "SM_Crate_Lid_001"')
def _scn001_import(state: dict[str, Any], tmp_path: Path) -> None:
    _lid_import(state, tmp_path)


@given('Unreal refuses to rename "SM_Crate_Lid_001"')
def _refuse_lid_rename(state: dict[str, Any]) -> None:
    state["case"][0].refused_renames.add(DESKTOP_DEST + "/SM_Crate_Lid_001")


@then('the error names "SM_Crate_Lid_001" and the target "SM_Crate_Lid"')
def _names_part_and_target(state: dict[str, Any]) -> None:
    expected = (
        f"RuntimeError: rename_asset refused to rename "
        f"{DESKTOP_DEST}/SM_Crate_Lid_001 to {DESKTOP_DEST}/SM_Crate_Lid"
    )
    assert _error(state).message == f"UE import of {DESKTOP_DEST} failed: {expected}"


# --- SCN002: a refused consolidation fails the import --------------------------------------


@scenario(_FEATURE, "A refused consolidation fails the import")
def test_scn002_a_refused_consolidation_fails_the_import() -> None:
    """SCN002 (AC2, FR1)."""


@given('a Desktop re-import where "SM_Crate_Lid" already exists beside the new "SM_Crate_Lid_001"')
def _scn002_reimport(state: dict[str, Any], tmp_path: Path) -> None:
    _lid_reimport(state, tmp_path)


@given('Unreal refuses to consolidate "SM_Crate_Lid"')
def _refuse_lid_consolidation(state: dict[str, Any]) -> None:
    state["case"][0].refused_consolidations.add(DESKTOP_DEST + "/SM_Crate_Lid")


@then('the error names the mesh "SM_Crate_Lid_001" and the target "SM_Crate_Lid"')
def _names_mesh_and_target(state: dict[str, Any]) -> None:
    expected = (
        f"RuntimeError: consolidate_assets refused to merge {DESKTOP_DEST}/SM_Crate_Lid "
        f"into {DESKTOP_DEST}/SM_Crate_Lid_001"
    )
    assert _error(state).message == f"UE import of {DESKTOP_DEST} failed: {expected}"


# --- SCN003: a refused physics-asset rename names both paths -------------------------------


@scenario(_FEATURE, "A refused physics-asset rename names both paths")
def test_scn003_a_refused_physics_asset_rename_names_both_paths() -> None:
    """SCN003 (AC3, FR1)."""


@given('a rigged Desktop import whose physics asset is created in a "Physics" subfolder')
def _scn003_rigged(state: dict[str, Any], tmp_path: Path) -> None:
    world, folder, report = stage(
        tmp_path, "desktop", part("desktop", "SM_Crate", BIG_LOW, BIG_HIGH), armature=True
    )
    world.physics_folder = DESKTOP_DEST + "/Physics"
    state["case"] = (world, folder, report)


@given("Unreal refuses to rename the created physics asset")
def _refuse_physics_rename(state: dict[str, Any]) -> None:
    state["case"][0].refused_renames.add(DESKTOP_DEST + "/Physics/SM_Crate_PhysicsAsset")


@then(
    'the error names the created physics asset path and the expected "SM_Crate_PhysicsAsset" path'
)
def _names_physics_paths(state: dict[str, Any]) -> None:
    expected = (
        f"RuntimeError: rename_asset refused to rename "
        f"{DESKTOP_DEST}/Physics/SM_Crate_PhysicsAsset to {DESKTOP_DEST}/SM_Crate_PhysicsAsset"
    )
    assert _error(state).message == f"UE import of {DESKTOP_DEST} failed: {expected}"


# --- SCN004: successful renames and consolidations are unchanged ---------------------------


@scenario(_FEATURE, "Successful renames and consolidations are unchanged")
def test_scn004_successful_renames_and_consolidations_are_unchanged() -> None:
    """SCN004 (AC4, FR1)."""


@given("a Desktop re-import where every rename and consolidation succeeds")
def _scn004_reimport(state: dict[str, Any], tmp_path: Path) -> None:
    _lid_reimport(state, tmp_path)


@then("the import succeeds with a static mesh for every part")
def _succeeds_for_every_part(state: dict[str, Any]) -> None:
    assert "error" not in state
    result = state["result"]
    assert result["ok"] is True
    assert sorted(result["static_meshes"]) == ["SM_Crate", "SM_Crate_Lid"]


@then('the old "SM_Crate_Lid" is consolidated into the new mesh')
def _old_lid_consolidated(state: dict[str, Any]) -> None:
    world = state["case"][0]
    assert world.redirects == {DESKTOP_DEST + "/SM_Crate_Lid": DESKTOP_DEST + "/SM_Crate_Lid_001"}
