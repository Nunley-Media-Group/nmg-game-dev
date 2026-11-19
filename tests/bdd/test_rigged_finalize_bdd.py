"""pytest-bdd bindings for rigged_finalize.feature: SCN001-SCN005 of #102, on Godot (#249).

The Godot steps finalize the asset with ``FakeStepRunner`` and ``FinalizeGodot`` from
tests/finalize_fakes.py: ``import_godot`` runs one headless import and probes each variant's
``.glb`` against its ``nmg-asset.json``. The Blender steps each run one headless case that asserts
the same statement (tests/blender/test_variants_rigged.py or
tests/blender/test_contract_reimport.py) through scripts/run-blender-tests.sh. They skip when no
Blender resolves, so a plain CPython run reports them as skipped rather than passed.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, scenario, then, when

from nmg_game_dev.pipeline import FinalizeClients, FinalizeRequest, finalize
from tests.finalize_fakes import FakeStepRunner, FinalizeGodot, asset_meshes
from tests.release_fakes import resolved_blender

REPO_ROOT = Path(__file__).resolve().parents[2]
_VARIANTS = "tests/blender/test_variants_rigged.py"
_REIMPORT = "tests/blender/test_contract_reimport.py"


@pytest.fixture()
def state(tmp_path: Path) -> dict[str, Any]:
    return {"tmp": tmp_path}


def _finalize(state: dict[str, Any], name: str, category: str, asset_class: str) -> None:
    """Finalize ``name`` through import_godot and keep the result and the Godot fake.

    The Godot facts are checked here rather than only in the Then steps: the Blender steps skip
    when no Blender resolves, and a skip would stop the scenario before its Godot steps ran.
    """
    tmp: Path = state["tmp"]
    blend = tmp / f"{name.lower()}.blend"
    blend.write_bytes(b"authored")
    request = FinalizeRequest(
        collection=name,
        category=category,
        asset_class=asset_class,  # type: ignore[arg-type]
        export_root=tmp / "export",
        blend=blend,
    )
    godot = FinalizeGodot(tmp)
    result = finalize(
        request,
        steps=("import_godot",),
        cache_dir=tmp / "cache",
        runner=FakeStepRunner(request),
        job_dir=tmp / "job",
        clients=FinalizeClients(godot=godot),
    )
    state.update(request=request, godot=godot, result=result, name=name, category=category)
    assert godot.count("--import") == 1
    for variant in ("Desktop", "Mobile"):
        _assert_imported(state, variant)


def _assert_imported(state: dict[str, Any], variant: str) -> None:
    name, category = state["name"], state["category"]
    resource = f"res://export/{category}/{name}/{variant}/{name}.glb"
    assert {"glb": resource} in state["godot"].params
    imported = next(step for step in state["result"].steps if step.step == "import_godot")
    assert imported.outputs["imports"][variant]["resource_path"] == resource
    assert imported.outputs["imports"][variant]["meshes"] == asset_meshes(name, variant)


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


# --- SCN001: Desktop exports skinned and imports as a skinned scene ------------------------


@scenario("rigged_finalize.feature", "Desktop exports skinned and imports as a skinned scene")
def test_scn001_desktop_exports_skinned_and_imports_as_skinned() -> None:
    """SCN001 (AC1, FR2, FR4)."""


@given('a character collection "Hero" whose SK_Hero skins SM_Hero through an Armature modifier')
def _hero_collection() -> None:
    """The Blender cases build this collection themselves."""


@given("the same rigged Hero collection")
def _same_hero() -> None:
    """The Blender cases build this collection themselves."""


@when("the Hero asset is finalized")
def _finalize_hero_step(state: dict[str, Any]) -> None:
    _finalize(state, "Hero", "Characters", "character")


@then(
    "Desktop/Hero.glb holds an armature named Armature with 26 deform bones "
    "and SM_Hero skinned to it"
)
def _desktop_glb_skinned() -> None:
    _blender_case(f"{_VARIANTS}::test_scn001_desktop_glb_holds_the_skinned_armature")


@then(
    "res://export/Characters/Hero/Desktop/Hero.glb is imported and its probed meshes match "
    "Desktop/nmg-asset.json"
)
def _desktop_imported(state: dict[str, Any]) -> None:
    _assert_imported(state, "Desktop")


# --- SCN002: Mobile exports one skinned scene ---------------------------------------------


@scenario(
    "rigged_finalize.feature",
    "Mobile exports one skinned scene and imports beside the Desktop variant",
)
def test_scn002_mobile_exports_one_skinned_scene() -> None:
    """SCN002 (AC2, FR3, FR4)."""


@then("Mobile holds Hero.glb with the armature and one skinned mesh and no _LOD files")
def _mobile_glb() -> None:
    _blender_case(f"{_VARIANTS}::test_scn002_mobile_glb_holds_the_armature_and_one_skinned_mesh")
    _blender_case(f"{_VARIANTS}::test_scn002_mobile_is_one_skinned_mesh_parented_to_the_rig")


@then(
    "res://export/Characters/Hero/Mobile/Hero.glb is imported and its probed meshes match "
    "Mobile/nmg-asset.json"
)
def _mobile_imported(state: dict[str, Any]) -> None:
    _assert_imported(state, "Mobile")
    mobile = state["request"].export_root / "Characters" / "Hero" / "Mobile"
    assert not list(mobile.glob("*_LOD*"))


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
def _unrigged_crate() -> None:
    """The fake export writes an unrigged Crate."""


@when("the Crate asset is finalized")
def _finalize_crate(state: dict[str, Any]) -> None:
    _finalize(state, "Crate", "Props", "standard_prop")


@then("Desktop and Mobile each hold one static Crate.glb and both import into Godot")
def _unrigged_static(state: dict[str, Any]) -> None:
    for variant in ("Desktop", "Mobile"):
        _assert_imported(state, variant)
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


@then("it imports the skinned .glb and passes")
def _reimport_passes() -> None:
    _blender_case(f"{_REIMPORT}::test_scn005_reimport_imports_the_skinned_glb_and_passes")


@then("a mesh exported without its skin is reported as reimport.skin_missing")
def _skin_missing() -> None:
    _blender_case(f"{_REIMPORT}::test_scn005_mesh_exported_without_its_skin_is_reported")
