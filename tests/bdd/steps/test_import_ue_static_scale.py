"""pytest-bdd bindings for import_ue_static_scale.feature: SCN001-SCN008 of #145.

Each scenario runs the generated UE import code against tests/unit/fake_unreal.py through
import_variant, so the static meshes it makes are checked and not only its text. The fake reads
the part sizes in metres, so "a part 8 m wide" is a part 8 m from its origin on each axis, which
gives the -800/800 cm bounds the scenario states. SCN007 does not run the live e2e test: it checks
that the opt-in test is collected and skipped without --runslow, and that it asserts what the
scenario says.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, scenario, then, when

from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.unreal import PIVOT_TOLERANCE_CM
from tests.unit.fake_unreal import (
    ASYM_HIGH,
    ASYM_LOW,
    BIG_HIGH,
    BIG_LOW,
    DESKTOP_DEST,
    SMALL_HIGH,
    SMALL_LOW,
    FakeWorld,
    FbxNode,
    MaterialInstanceConstant,
    box,
    part,
    run_import,
    stage,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
_E2E_TEST = "tests/e2e/test_finalize_e2e.py"
_E2E_NAME = "test_finalize_multi_part_static_asset_keeps_size_pivots_and_names"
_E2E_FIXTURE = "tests/e2e/fixtures/build_multipart_fixture.py"
_TEXTURES = ("T_Crate_Body_BC", "T_Crate_Body_N", "T_Crate_Body_ORM")

Case = tuple[FakeWorld, Path, dict[str, Any]]


@pytest.fixture()
def state() -> dict[str, Any]:
    return {}


def _assert_bounds(actual: Any, expected: dict[str, list[float]]) -> None:
    for corner in ("min", "max"):
        assert actual[corner] == pytest.approx(expected[corner], abs=PIVOT_TOLERANCE_CM)


def _run(state: dict[str, Any], variant: str, skeleton_dest: str | None = None) -> None:
    """Run the generated import for one staged variant and keep its result for the Then steps."""
    world, folder, report = state["cases"][variant]
    state["results"][variant] = run_import(
        world, folder, variant, report, skeleton_dest=skeleton_dest
    )


# --- SCN001: a static mesh larger than a metre imports at the authored size -----------------


@scenario(
    "import_ue_static_scale.feature",
    "A static mesh larger than a metre imports at the authored size",
)
def test_scn001_a_static_mesh_larger_than_a_metre_imports_at_the_authored_size() -> None:
    """SCN001 (AC1, FR1, FR4)."""


@given("a non-rigged asset exported by finalize with a part 8 m wide")
def _eight_metre_part(state: dict[str, Any], tmp_path: Path) -> None:
    case = stage(tmp_path, "desktop", part("desktop", "SM_Crate", BIG_LOW, BIG_HIGH))
    state["cases"] = {"desktop": case}
    state["results"] = {}


@when("import_ue imports the Desktop variant on UE 5.8")
def _import_desktop(state: dict[str, Any]) -> None:
    _run(state, "desktop")


@when("import_ue imports the Desktop variant")
def _import_desktop_variant(state: dict[str, Any]) -> None:
    _run(state, "desktop")


@then("the part's static mesh bounds are -800 cm to 800 cm on that axis within 0.01 cm")
def _bounds_800(state: dict[str, Any]) -> None:
    _assert_bounds(state["results"]["desktop"]["static_meshes"]["SM_Crate"]["bounds"], box(800.0))


@then("the pivot check passes")
def _pivot_passes(state: dict[str, Any]) -> None:
    # run_import checks the pivots and raises import_ue.pivot_mismatch when one is off, so a
    # result that came back has passed. This checks every variant the scenario imported.
    assert state["results"]
    assert all(result["ok"] is True for result in state["results"].values())


# --- SCN002: each part keeps its own pivot -------------------------------------------------


@scenario("import_ue_static_scale.feature", "Each part keeps its own pivot")
def test_scn002_each_part_keeps_its_own_pivot() -> None:
    """SCN002 (AC2, FR2)."""


@given("a non-rigged asset with two parts whose origins are away from the asset origin")
def _two_offset_parts(state: dict[str, Any], tmp_path: Path) -> None:
    case = stage(
        tmp_path,
        "desktop",
        part("desktop", "SM_Crate", BIG_LOW, BIG_HIGH),
        part("desktop", "SM_Crate_Lid", ASYM_LOW, ASYM_HIGH, translation=(5.0, 3.0, 0.0)),
    )
    state["cases"] = {"desktop": case}
    state["results"] = {}


@then("each static mesh's bounds are relative to its own part origin")
def _bounds_relative_to_own_origin(state: dict[str, Any]) -> None:
    lid = state["results"]["desktop"]["static_meshes"]["SM_Crate_Lid"]["bounds"]
    _assert_bounds(lid, {"min": [-100.0, -75.0, 0.0], "max": [100.0, -25.0, 200.0]})


@then("no part's translation appears in its bounds")
def _no_translation(state: dict[str, Any]) -> None:
    # The translation is (5, 3, 0) m, which would show as 500 and 300 cm if it were baked in.
    lid = state["results"]["desktop"]["static_meshes"]["SM_Crate_Lid"]["bounds"]
    assert all(abs(value) <= 200.0 for corner in lid.values() for value in corner)


# --- SCN003: a static mesh is named after its part object, not its datablock ---------------


@scenario(
    "import_ue_static_scale.feature",
    "A static mesh is named after its part object, not its datablock",
)
def test_scn003_a_static_mesh_is_named_after_its_part_object() -> None:
    """SCN003 (AC3, FR3)."""


@given('a part object "SM_Crate_Lid" whose mesh datablock is "SM_Crate_Lid.001"')
def _datablock_part(state: dict[str, Any], tmp_path: Path) -> None:
    case = stage(
        tmp_path,
        "desktop",
        part("desktop", "SM_Crate", BIG_LOW, BIG_HIGH),
        part("desktop", "SM_Crate_Lid", SMALL_LOW, SMALL_HIGH, duplicate=True),
    )
    state["cases"] = {"desktop": case}
    state["results"] = {}


@when("import_ue imports the variant")
def _import_variant(state: dict[str, Any]) -> None:
    _run(state, "desktop")


@then('the result holds a static mesh named "SM_Crate_Lid"')
def _named_after_object(state: dict[str, Any]) -> None:
    assert "SM_Crate_Lid" in state["results"]["desktop"]["static_meshes"]


@then("every snapshot part has a static mesh")
def _every_part_has_a_mesh(state: dict[str, Any]) -> None:
    snapshot = state["cases"]["desktop"][2]["snapshot"]
    meshes = state["results"]["desktop"]["static_meshes"]
    for key, entry in snapshot.items():
        if entry.get("type") == "MESH":
            assert key.replace("_Mobile", "", 1) in meshes, key


# --- SCN004: a reimport reports the new geometry ------------------------------------------


@scenario("import_ue_static_scale.feature", "A reimport reports the new geometry")
def test_scn004_a_reimport_reports_the_new_geometry() -> None:
    """SCN004 (AC4, FR4)."""


@given('the destination already holds "SM_Crate_Lid" imported at 1/100 scale')
def _earlier_import(state: dict[str, Any], tmp_path: Path) -> None:
    world, folder, report = stage(
        tmp_path,
        "desktop",
        part("desktop", "SM_Crate", BIG_LOW, BIG_HIGH),
        part("desktop", "SM_Crate_Lid", SMALL_LOW, SMALL_HIGH, duplicate=True),
    )
    lid = FbxNode("SM_Crate_Lid", "SM_Crate_Lid.001", SMALL_LOW, SMALL_HIGH)
    world.seed_static_mesh(DESKTOP_DEST + "/SM_Crate_Lid", lid)
    world.seed_static_mesh(DESKTOP_DEST + "/SM_Crate_Lid_001", lid)
    state["cases"] = {"desktop": (world, folder, report)}
    state["results"] = {}


@when("import_ue imports the variant again")
def _reimport(state: dict[str, Any]) -> None:
    _run(state, "desktop")


@then("the reported and saved bounds are those of the new import at the authored size")
def _reported_and_saved(state: dict[str, Any]) -> None:
    world = state["cases"]["desktop"][0]
    reported = state["results"]["desktop"]["static_meshes"]["SM_Crate_Lid"]["bounds"]
    _assert_bounds(reported, box(100.0))
    _assert_bounds(world.saved[DESKTOP_DEST + "/SM_Crate_Lid"], box(100.0))


# --- SCN005: desktop and mobile variants both import correctly -----------------------------


@scenario("import_ue_static_scale.feature", "Desktop and Mobile variants both import correctly")
def test_scn005_desktop_and_mobile_variants_both_import_correctly() -> None:
    """SCN005 (AC5)."""


@given("a non-rigged multi-part asset")
def _multi_part_both_variants(state: dict[str, Any], tmp_path: Path) -> None:
    cases: dict[str, Case] = {}
    for variant in ("desktop", "mobile"):
        cases[variant] = stage(
            tmp_path,
            variant,
            part(variant, "SM_Crate", BIG_LOW, BIG_HIGH),
            part(variant, "SM_Crate_Trim", SMALL_LOW, SMALL_HIGH),
        )
    state["cases"] = cases
    state["results"] = {}


@when("finalize runs import_ue for the Desktop and Mobile variants")
def _import_both(state: dict[str, Any]) -> None:
    _run(state, "desktop")
    _run(state, "mobile")


@then(
    "each variant's static meshes are at the authored size, keep their pivots, "
    "and are named after their part export names"
)
def _both_variants_authored(state: dict[str, Any]) -> None:
    for variant in ("desktop", "mobile"):
        meshes = state["results"][variant]["static_meshes"]
        assert sorted(meshes) == ["SM_Crate", "SM_Crate_Trim"]
        _assert_bounds(meshes["SM_Crate"]["bounds"], box(800.0))
        _assert_bounds(meshes["SM_Crate_Trim"]["bounds"], box(100.0))


# --- SCN006: rigged imports are unchanged -------------------------------------------------


@scenario("import_ue_static_scale.feature", "Rigged imports are unchanged")
def test_scn006_rigged_imports_are_unchanged() -> None:
    """SCN006 (AC6, FR6)."""


@given("a rigged character report")
def _rigged_report(state: dict[str, Any], tmp_path: Path) -> None:
    desktop = stage(
        tmp_path,
        "desktop",
        part("desktop", "SM_Crate", BIG_LOW, BIG_HIGH, duplicate=True),
        armature=True,
    )
    mobile = stage(tmp_path, "mobile", part("mobile", "SM_Crate", BIG_LOW, BIG_HIGH), armature=True)
    # The Mobile skeletal import reuses the Desktop skeleton and physics asset, so both must exist.
    mobile[0].seed_asset(DESKTOP_DEST + "/SM_Crate_Skeleton")
    mobile[0].seed_asset(DESKTOP_DEST + "/SM_Crate_PhysicsAsset")
    state["cases"] = {"desktop": desktop, "mobile": mobile}
    state["results"] = {}


@when("import_ue imports its Desktop and Mobile variants")
def _import_rigged(state: dict[str, Any]) -> None:
    _run(state, "desktop")
    _run(state, "mobile", skeleton_dest=DESKTOP_DEST)


@then("the Skeletal Mesh import sets no build scale and renames nothing")
def _rigged_no_scale_no_rename(state: dict[str, Any]) -> None:
    for variant in ("desktop", "mobile"):
        world = state["cases"][variant][0]
        assert world.build_writes == []
        assert world.redirects == {}
        assert sorted(state["results"][variant]["skeletal_meshes"]) == ["SM_Crate"]


# --- SCN007: an opt-in end-to-end test covers a multi-part static asset ---------------------


@scenario(
    "import_ue_static_scale.feature",
    "An opt-in end-to-end test covers a multi-part static asset",
)
def test_scn007_an_opt_in_end_to_end_test_covers_a_multi_part_static_asset() -> None:
    """SCN007 (AC7, FR8)."""


@given("the multi-part Gantry fixture builder and the slow finalize test in tests/e2e")
def _e2e_files_exist() -> None:
    assert (REPO_ROOT / _E2E_FIXTURE).is_file()
    assert (REPO_ROOT / _E2E_TEST).is_file()


@when("pytest collects tests/e2e without --runslow")
def _collect_e2e(state: dict[str, Any]) -> None:
    state["e2e"] = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/e2e", "-v", "-p", "no:cacheprovider"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )


@then("the multi-part finalize test is collected and skipped")
def _e2e_skipped(state: dict[str, Any]) -> None:
    completed = state["e2e"]
    assert completed.returncode == 0, (completed.stdout + completed.stderr)[-3000:]
    lines = [line for line in completed.stdout.splitlines() if _E2E_NAME in line]
    assert lines, "the multi-part finalize test was not collected"
    assert "SKIPPED" in lines[0], lines[0]


@then(
    "the test asserts both variants import with one static mesh per part named after its object "
    "and a passing pivot check when run with --runslow"
)
def _e2e_asserts() -> None:
    source = (REPO_ROOT / _E2E_TEST).read_text(encoding="utf-8")
    body = source[source.index(f"def {_E2E_NAME}") :]
    assert "resolve_blender" in body
    assert "Desktop" in body and "Mobile" in body
    assert "static_meshes" in body
    assert "pivot" in body.lower()


# --- SCN008: other import behavior is preserved -------------------------------------------


@scenario("import_ue_static_scale.feature", "Other import behavior is preserved")
def test_scn008_other_import_behavior_is_preserved() -> None:
    """SCN008 (AC8, FR7)."""


@given("any static asset")
def _any_static_asset(state: dict[str, Any], tmp_path: Path) -> None:
    case = stage(
        tmp_path,
        "desktop",
        part("desktop", "SM_Crate", BIG_LOW, BIG_HIGH, materials=("M_Crate_Body",)),
        textures=_TEXTURES,
    )
    state["cases"] = {"desktop": case}
    state["results"] = {}


@when("import_ue imports it")
def _import_any(state: dict[str, Any]) -> None:
    _run(state, "desktop")


@then(
    "texture settings, MI_<Name>_<Part> binding, the NMG_RESULT schema, the error codes, "
    "and the 0.01 cm tolerance are unchanged"
)
def _behavior_preserved(state: dict[str, Any], tmp_path: Path) -> None:
    world = state["cases"]["desktop"][0]
    result = state["results"]["desktop"]
    assert set(result) == {
        "ok",
        "variant",
        "name",
        "dest",
        "textures",
        "materials",
        "static_meshes",
        "skeletal_meshes",
        "error",
    }
    assert world.assets[DESKTOP_DEST + "/T_Crate_Body_N"].properties["compression_settings"] == (
        "TC_NORMALMAP"
    )
    assert world.assets[DESKTOP_DEST + "/T_Crate_Body_ORM"].properties["compression_settings"] == (
        "TC_MASKS"
    )
    instance = world.assets[DESKTOP_DEST + "/MI_Crate_Body"]
    assert isinstance(instance, MaterialInstanceConstant)
    assert instance.texture_params["BaseColor"] == DESKTOP_DEST + "/T_Crate_Body_BC"
    assert PIVOT_TOLERANCE_CM == 0.01
    # Without the master material the import fails with the import_ue.failed code.
    no_master, folder, report = stage(
        tmp_path / "no_master",
        "desktop",
        part("desktop", "SM_Crate", BIG_LOW, BIG_HIGH, materials=("M_Crate_Body",)),
        textures=_TEXTURES,
        seed_master=False,
    )
    with pytest.raises(PipelineError) as raised:
        run_import(no_master, folder, "desktop", report)
    assert raised.value.code == "import_ue.failed"
