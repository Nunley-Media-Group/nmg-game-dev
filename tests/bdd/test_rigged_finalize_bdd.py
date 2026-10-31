"""pytest-bdd bindings for rigged_finalize.feature: SCN001-SCN005 of #102.

The UE steps build the import code with ``build_import_code`` and check its text and parameters,
which needs no editor. The Blender steps each run one headless case that asserts the same
statement (tests/blender/test_variants_rigged.py or tests/blender/test_contract_reimport.py),
through scripts/run-blender-tests.sh. They skip when no Blender resolves, as the release-tooling
bindings do, so a plain CPython run reports them as skipped rather than passed.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, scenario, then, when

import nmg_game_dev.pipeline  # noqa: F401 - load the pipeline first; unreal imports it back
from nmg_game_dev.unreal import build_import_code
from tests.release_fakes import resolved_blender

REPO_ROOT = Path(__file__).resolve().parents[2]
_VARIANTS = "tests/blender/test_variants_rigged.py"
_REIMPORT = "tests/blender/test_contract_reimport.py"
_HERO_DESKTOP = "/Game/Characters/Hero/Desktop"
_HERO_MOBILE = "/Game/Characters/Hero/Mobile"
_CRATE_DESKTOP = "/Game/Props/Crate/Desktop"
_CRATE_MOBILE = "/Game/Props/Crate/Mobile"
_BOUNDS = {"min": [-0.5, 0.1, 0.0], "max": [0.5, 0.4, 1.0]}


@pytest.fixture()
def state() -> dict[str, Any]:
    return {}


def _report(asset: str, *, rigged: bool) -> dict[str, Any]:
    """A pre-export contract snapshot for one asset, with the rig's armature when rigged."""
    snapshot: dict[str, Any] = {
        f"SM_{asset}": {"variant": "desktop", "type": "MESH", "local_bounds": _BOUNDS},
        f"SM_{asset}_Mobile": {"variant": "mobile", "type": "MESH", "local_bounds": _BOUNDS},
    }
    if rigged:
        snapshot[f"SK_{asset}"] = {"variant": "desktop", "type": "ARMATURE", "local_bounds": None}
        for level in (1, 2):
            snapshot[f"SM_{asset}_Mobile_LOD{level}"] = {
                "variant": "mobile",
                "type": "MESH",
                "local_bounds": _BOUNDS,
            }
    return {
        "kind": "contract",
        "asset": asset,
        "class": "character" if rigged else "standard_prop",
        "passed": True,
        "findings": [],
        "snapshot": snapshot,
    }


def _params(code: str) -> dict[str, Any]:
    """The PARAMS literal build_import_code embeds, decoded."""
    import ast  # noqa: PLC0415
    import json  # noqa: PLC0415

    line = next(line for line in code.splitlines() if line.startswith("PARAMS = json.loads("))
    decoded = ast.literal_eval(line[len("PARAMS = json.loads(") : -1])
    params: dict[str, Any] = json.loads(decoded)
    return params


def _finalize_hero(state: dict[str, Any]) -> None:
    """Build the UE import code for both variants and check it against the Hero contract.

    The UE facts are checked here rather than in the Then steps: the Blender steps skip when no
    Blender resolves, and a skip would stop the scenario before its UE steps ran.
    """
    report = state["report"]
    state["desktop_code"] = build_import_code("/work/Hero/Desktop", _HERO_DESKTOP, "Hero", report)
    state["mobile_code"] = build_import_code(
        "/work/Hero/Mobile", _HERO_MOBILE, "Hero", report, skeleton_dest=_HERO_DESKTOP
    )
    _assert_desktop_skeletal(state["desktop_code"])
    _assert_mobile_onto_desktop(state["mobile_code"])


def _assert_desktop_skeletal(code: str) -> None:
    params = _params(code)
    assert params["rigged"] is True
    assert params["dest"] == _HERO_DESKTOP
    assert params["skeleton_dest"] == _HERO_DESKTOP
    assert "options.import_as_skeletal = True" in code
    assert "options.import_animations = False" in code
    assert "options.create_physics_asset = True" in code
    assert "MI_" in code


def _assert_mobile_onto_desktop(code: str) -> None:
    params = _params(code)
    assert params["rigged"] is True
    assert params["dest"] == _HERO_MOBILE
    assert params["skeleton_dest"] == _HERO_DESKTOP
    assert "options.create_physics_asset = False" in code
    assert "import_lod(mesh, level, lod_fbx)" in code
    assert "for level in (1, 2):" in code


def _blender_case(node: str) -> None:
    """Run one headless Blender case by node ID; skip when no Blender resolves."""
    blender = resolved_blender()
    if blender is None:
        pytest.skip("Blender does not resolve (set BLENDER_BIN or BLENDER_APP); case not run")
    completed = subprocess.run(
        [str(REPO_ROOT / "scripts" / "run-blender-tests.sh"), node],
        cwd=REPO_ROOT,
        env={**os.environ, "BLENDER_BIN": blender},
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, (completed.stdout + completed.stderr)[-3000:]


# --- SCN001: Desktop exports skinned and imports as a Skeletal Mesh --------------------------


@scenario("rigged_finalize.feature", "Desktop exports skinned and imports as a Skeletal Mesh")
def test_scn001_desktop_exports_skinned_and_imports_as_skeletal() -> None:
    """SCN001 (AC1, FR2, FR4)."""


@given('a character collection "Hero" whose SK_Hero skins SM_Hero through an Armature modifier')
def _hero_collection(state: dict[str, Any]) -> None:
    # The Blender cases build this collection themselves; the UE steps need its pre-export report.
    state["report"] = _report("Hero", rigged=True)


@given("the same rigged Hero collection")
def _same_hero(state: dict[str, Any]) -> None:
    state["report"] = _report("Hero", rigged=True)


@when("the Hero asset is finalized")
def _finalize_hero_step(state: dict[str, Any]) -> None:
    _finalize_hero(state)


@then(
    "Desktop/SM_Hero.fbx holds an armature named Armature with 26 deform bones "
    "and SM_Hero skinned to it"
)
def _desktop_fbx_skinned() -> None:
    _blender_case(f"{_VARIANTS}::test_scn001_desktop_fbx_holds_the_skinned_armature")


@then(
    "/Game/Characters/Hero/Desktop/SM_Hero is a Skeletal Mesh with SM_Hero_Skeleton, "
    "SM_Hero_PhysicsAsset, and MI_Hero_<Part> on every slot"
)
def _desktop_imports_skeletal(state: dict[str, Any]) -> None:
    _assert_desktop_skeletal(state["desktop_code"])


# --- SCN002: Mobile exports three skinned LODs and imports onto the Desktop skeleton ---------


@scenario(
    "rigged_finalize.feature",
    "Mobile exports three skinned LODs and imports onto the Desktop skeleton",
)
def test_scn002_mobile_exports_three_skinned_lods() -> None:
    """SCN002 (AC2, FR3, FR4)."""


@then(
    "Mobile holds SM_Hero.fbx, SM_Hero_LOD1.fbx, and SM_Hero_LOD2.fbx, "
    "each with the armature and one skinned mesh"
)
def _mobile_fbx_per_lod() -> None:
    _blender_case(
        f"{_VARIANTS}::test_scn002_mobile_fbx_per_lod_each_holds_the_armature_and_a_skinned_mesh"
    )


@then("LOD1 and LOD2 are at most 50% and 25% of LOD0's triangles")
def _lod_ratios() -> None:
    _blender_case(f"{_VARIANTS}::test_scn002_lod_ratios_stay_within_the_mobile_budget")


@then(
    "/Game/Characters/Hero/Mobile/SM_Hero is a Skeletal Mesh with 3 LODs "
    "using the Desktop skeleton and physics asset"
)
def _mobile_imports_onto_desktop_skeleton(state: dict[str, Any]) -> None:
    _assert_mobile_onto_desktop(state["mobile_code"])


# --- SCN003: Cleanup keeps the Armature modifier and vertex groups -------------------------


@scenario("rigged_finalize.feature", "Cleanup keeps the Armature modifier and vertex groups")
def test_scn003_cleanup_keeps_the_armature_modifier_and_vertex_groups() -> None:
    """SCN003 (AC3, FR1). The Blender cases in the Then steps set up and run the cleanup."""


@given("a rigged Hero mesh that also has a non-Armature modifier")
def _rigged_mesh_with_modifier() -> None:
    """The Blender case adds the modifier before it runs the cleanup."""


@when("the variants cleanup runs")
def _cleanup_runs() -> None:
    """The Blender case runs cleanup_desktop in each Then step."""


@then("the non-Armature modifier is applied")
def _non_armature_applied() -> None:
    _blender_case(f"{_VARIANTS}::test_scn003_cleanup_applies_the_non_armature_modifier")


@then("the Armature modifier targeting SK_Hero and the vertex groups remain")
def _armature_kept() -> None:
    _blender_case(f"{_VARIANTS}::test_scn003_cleanup_keeps_the_armature_modifier_and_vertex_groups")


# --- SCN004: Unrigged assets keep the static path ------------------------------------------


@scenario("rigged_finalize.feature", "Unrigged assets keep the static path")
def test_scn004_unrigged_assets_keep_the_static_path() -> None:
    """SCN004 (AC4)."""


@given('a collection "Crate" with no SK_Crate')
def _unrigged_crate(state: dict[str, Any]) -> None:
    state["report"] = _report("Crate", rigged=False)


@when("the Crate asset is finalized")
def _finalize_crate(state: dict[str, Any]) -> None:
    report = state["report"]
    state["desktop_code"] = build_import_code(
        "/work/Crate/Desktop", _CRATE_DESKTOP, "Crate", report
    )
    state["mobile_code"] = build_import_code("/work/Crate/Mobile", _CRATE_MOBILE, "Crate", report)
    for code in (state["desktop_code"], state["mobile_code"]):
        assert _params(code)["rigged"] is False
        assert "import_as_skeletal = False" in code


@then("Desktop and Mobile import as Static Meshes and Mobile keeps its single-FBX LodGroup layout")
def _unrigged_static() -> None:
    _blender_case(f"{_VARIANTS}::test_scn004_unrigged_asset_keeps_the_static_layout")


# --- SCN005: The re-import check covers rigged variants ------------------------------------


@scenario("rigged_finalize.feature", "The re-import check covers rigged variants")
def test_scn005_the_reimport_check_covers_rigged_variants() -> None:
    """SCN005 (AC5, FR5)."""


@given("exported rigged Hero variants")
def _exported_rigged() -> None:
    """The Blender cases export the rigged Hero variants they check."""


@when("the re-import check runs on the Mobile folder")
def _reimport_runs() -> None:
    """The Blender cases run the re-import check in a fresh Blender process."""


@then("it imports all three LOD files and passes")
def _reimport_passes() -> None:
    _blender_case(f"{_REIMPORT}::test_scn005_reimport_imports_every_lod_file_and_passes")


@then("a mesh exported without its skin is reported as reimport.skin_missing")
def _skin_missing() -> None:
    _blender_case(f"{_REIMPORT}::test_scn005_mesh_exported_without_its_skin_is_reported")
