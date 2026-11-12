"""UE import code, NMG_RESULT parsing, and the pivot check for the finalize import step (#69, AC5).

A fake client stands in for UnrealMcpClient. It returns a canned tool output and records the
UE code it was given. The text tests check that code, its embedded parameters, and the host-side
result handling. The tests from the "generated code on the fake" section run the code itself
against ``tests/unit/fake_unreal.py`` (#145), an in-memory editor, so they check the assets it
makes. Nothing here contacts a running editor.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest

from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.unreal import (
    build_import_code,
    check_lod_counts,
    check_pivots,
    import_variant,
    parse_nmg_result,
)
from tests.unit.fake_unreal import (
    ASYM_HIGH,
    ASYM_LOW,
    BIG_HIGH,
    BIG_LOW,
    DESKTOP_DEST,
    MASTER_PATH,
    MOBILE_DEST,
    SMALL_HIGH,
    SMALL_LOW,
    FakeWorld,
    FbxNode,
    MaterialInstanceConstant,
    box,
    contract_report,
    dest_for,
    part,
    run_import,
    run_import_code,
    stage,
)

VARIANT_DIR = "/work/export/Props/Crate/Desktop"


class FakeUnreal:
    """Satisfies UnrealPythonClient. Returns ``output`` and remembers the code it received."""

    def __init__(self, output: str) -> None:
        self.output = output
        self.codes: list[str] = []

    def execute_python_code(self, code: str, *, timeout: float | None = None) -> str:
        self.codes.append(code)
        return self.output


def _snapshot(variant: str = "desktop") -> dict[str, Any]:
    """A contract snapshot with one MESH part, local bounds in Blender meters (Z-up)."""
    return {
        "SM_Crate": {
            "variant": variant,
            "type": "MESH",
            "local_bounds": {"min": [-0.5, 0.1, 0.0], "max": [0.5, 0.4, 1.0]},
        },
        "M_Crate_Body": {"variant": variant, "type": "MATERIAL"},
    }


def _report(variant: str = "desktop", snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    return contract_report(snapshot if snapshot is not None else _snapshot(variant))


def _ue_bounds(low: list[float], high: list[float]) -> dict[str, list[float]]:
    return {"min": low, "max": high}


def _matching_result(
    variant: str = "desktop",
    *,
    mesh: str = "SM_Crate",
    low: list[float] | None = None,
    high: list[float] | None = None,
) -> dict[str, Any]:
    # Blender meters → cm with Y negated: x 50, y (-40..-10), z 0..100.
    bounds = _ue_bounds(
        low if low is not None else [-50.0, -40.0, 0.0],
        high if high is not None else [50.0, -10.0, 100.0],
    )
    return {
        "ok": True,
        "variant": variant,
        "name": "Crate",
        "dest": DESKTOP_DEST if variant == "desktop" else MOBILE_DEST,
        "textures": [],
        "materials": {},
        "static_meshes": {mesh: {"path": f"/Game/Props/Crate/{variant}/{mesh}", "bounds": bounds}},
        "error": None,
    }


def _nmg_output(result: dict[str, Any]) -> str:
    return "UE log line\nNMG_RESULT " + json.dumps(result, sort_keys=True) + "\n"


def _embedded_params(code: str) -> dict[str, Any]:
    line = next(line for line in code.splitlines() if line.startswith("PARAMS = json.loads("))
    literal = line[len("PARAMS = json.loads(") : -1]
    decoded = ast.literal_eval(literal)
    assert isinstance(decoded, str)
    params: dict[str, Any] = json.loads(decoded)
    return params


# --- build_import_code ----------------------------------------------------------------------


def test_build_import_code_contains_the_texture_and_material_settings() -> None:
    code = build_import_code(VARIANT_DIR, DESKTOP_DEST, "Crate", _report())

    assert "TC_NORMALMAP" in code
    assert "TC_MASKS" in code
    assert "flip_green_channel" in code
    assert "/nmg-game-dev/Materials/M_NmgORM" in code
    assert "MI_" in code
    for parameter in ("BaseColor", "Normal", "ORM"):
        assert f'"{parameter}"' in code


def test_build_import_code_sets_the_fbx_options() -> None:
    code = build_import_code(VARIANT_DIR, DESKTOP_DEST, "Crate", _report())

    assert "FbxImportUI" in code
    assert "import_materials = False" in code
    assert "import_textures = False" in code
    assert "import_as_skeletal = False" in code
    assert "combine_meshes = False" in code
    # #145: the node transform is baked only for a single part, so a multi-part asset keeps pivots.
    assert 'transform_vertex_to_absolute = not PARAMS["multi_part"]' in code
    assert "transform_vertex_to_absolute = False" not in code
    assert "bake_pivot_in_vertex = False" in code


def test_build_import_code_scales_and_renames_static_parts_and_never_sets_feature_flags() -> None:
    # #145 FR5, FR9: the build scale and the rename run in the generated code, which never reads or
    # sets the Interchange FBX feature flag.
    code = build_import_code(VARIANT_DIR, DESKTOP_DEST, "Crate", _report())

    assert "build_scale3d = unreal.Vector(CM_PER_METER, CM_PER_METER, CM_PER_METER)" in code
    assert "get_lod_build_settings(mesh, lod)" in code
    assert "set_lod_build_settings(mesh, lod, settings)" in code
    assert "consolidate_assets(mesh, [_load(target)])" in code
    assert "rename_asset(object_path, target)" in code
    assert "Interchange" not in code
    assert "FeatureFlags" not in code


def test_build_import_code_embeds_parameters_and_prints_one_result_line() -> None:
    code = build_import_code(VARIANT_DIR, DESKTOP_DEST, "Crate", _report())
    params = _embedded_params(code)

    assert params["variant"] == "desktop"
    assert params["variant_dir"] == VARIANT_DIR
    assert params["dest"] == DESKTOP_DEST
    assert params["name"] == "Crate"
    assert params["expected_meshes"] == [["SM_Crate"]]
    assert code.count('print("NMG_RESULT "') == 1
    compile(code, "<ue-import>", "exec")


def test_build_import_code_lists_mobile_parts_by_their_export_name() -> None:
    snapshot = {
        "SM_Crate_Mobile": {"variant": "mobile", "type": "MESH", "local_bounds": {}},
    }
    code = build_import_code(VARIANT_DIR, MOBILE_DEST, "Crate", _report("mobile", snapshot))

    assert _embedded_params(code)["expected_meshes"] == [["SM_Crate", "SM_Crate_Mobile"]]


def test_build_import_code_expects_each_desktop_part_under_its_object_name() -> None:
    """#142: the FBX mesh carries its object's export name, so import_ue looks up no _001 name."""
    snapshot = {
        "SM_Crate": {"variant": "desktop", "type": "MESH", "local_bounds": {}},
        "SM_Crate_Seat": {"variant": "desktop", "type": "MESH", "local_bounds": {}},
    }
    code = build_import_code(VARIANT_DIR, DESKTOP_DEST, "Crate", _report("desktop", snapshot))

    assert _embedded_params(code)["expected_meshes"] == [["SM_Crate"], ["SM_Crate_Seat"]]


def test_build_import_code_rejects_a_destination_that_is_not_a_variant() -> None:
    with pytest.raises(ValueError, match="Desktop or Mobile"):
        build_import_code(VARIANT_DIR, "/Game/Props/Crate", "Crate", _report())


# --- parse_nmg_result -----------------------------------------------------------------------


def test_parse_reads_the_last_nmg_result_line() -> None:
    output = 'NMG_RESULT {"ok": false}\nlater\nNMG_RESULT {"ok": true, "variant": "desktop"}'

    assert parse_nmg_result(output) == {"ok": True, "variant": "desktop"}


def test_parse_unwraps_the_vibeue_envelope() -> None:
    inner = 'ENGINE=5.8\nNMG_RESULT {"ok": true, "variant": "mobile"}\n'
    envelope = json.dumps({"success": True, "run_id": 7, "output": inner, "result": "None"})

    assert parse_nmg_result(envelope) == {"ok": True, "variant": "mobile"}


def test_parse_raises_when_vibeue_reports_failure() -> None:
    envelope = json.dumps({"success": False, "error_message": "Traceback: nope"})

    with pytest.raises(PipelineError) as raised:
        parse_nmg_result(envelope)

    assert raised.value.code == "import_ue.failed"
    assert raised.value.stage == "import_ue"


def test_parse_raises_when_no_result_line_is_printed() -> None:
    with pytest.raises(PipelineError) as raised:
        parse_nmg_result("ENGINE=5.8 but nothing else")

    assert raised.value.code == "import_ue.failed"
    assert "NMG_RESULT" in raised.value.message


def test_parse_raises_when_the_result_line_is_not_json() -> None:
    with pytest.raises(PipelineError) as raised:
        parse_nmg_result("NMG_RESULT {not json")

    assert raised.value.code == "import_ue.failed"


# --- check_pivots ---------------------------------------------------------------------------


def test_pivot_check_passes_when_bounds_match_after_unit_and_axis_conversion() -> None:
    check_pivots(_report(), _matching_result())


def test_pivot_check_passes_within_the_tolerance() -> None:
    result = _matching_result(low=[-50.0, -40.009, 0.0], high=[50.0, -10.0, 100.0])

    check_pivots(_report(), result)


def test_pivot_check_fails_when_y_is_not_negated() -> None:
    # Un-negated Y would put the box at (10..40) cm, which must not match.
    result = _matching_result(low=[-50.0, 10.0, 0.0], high=[50.0, 40.0, 100.0])

    with pytest.raises(PipelineError) as raised:
        check_pivots(_report(), result)

    assert raised.value.code == "import_ue.pivot_mismatch"
    assert raised.value.stage == "import_ue"


def test_pivot_check_fails_outside_the_tolerance() -> None:
    result = _matching_result(low=[-50.0, -40.0, 0.0], high=[50.0, -10.5, 100.0])

    with pytest.raises(PipelineError) as raised:
        check_pivots(_report(), result)

    assert raised.value.code == "import_ue.pivot_mismatch"
    assert "max on axis 1" in raised.value.message


def test_pivot_check_fails_when_a_part_has_no_static_mesh() -> None:
    result = _matching_result(mesh="SM_Other")

    with pytest.raises(PipelineError) as raised:
        check_pivots(_report(), result)

    assert raised.value.code == "import_ue.pivot_mismatch"
    assert "SM_Crate" in raised.value.message


def test_pivot_check_fails_closed_without_local_bounds() -> None:
    snapshot = {"SM_Crate": {"variant": "desktop", "type": "MESH"}}

    with pytest.raises(PipelineError) as raised:
        check_pivots(_report(snapshot=snapshot), _matching_result())

    assert raised.value.code == "import_ue.pivot_mismatch"
    assert "local_bounds" in raised.value.message


def test_pivot_check_matches_mobile_parts_by_export_name() -> None:
    snapshot = {
        "SM_Crate_Mobile": {
            "variant": "mobile",
            "type": "MESH",
            "local_bounds": {"min": [-0.5, 0.1, 0.0], "max": [0.5, 0.4, 1.0]},
        }
    }
    result = _matching_result("mobile", mesh="SM_Crate")

    check_pivots(_report("mobile", snapshot), result)


def test_pivot_check_ignores_the_other_variant_and_non_mesh_entries() -> None:
    snapshot = _snapshot("mobile")
    snapshot["SM_Crate"]["variant"] = "mobile"
    # The desktop result has no mesh that matches the mobile snapshot part, and that is fine.
    check_pivots(_report("mobile", snapshot), _matching_result("desktop", mesh="SM_Other"))


# --- import_variant -------------------------------------------------------------------------


def test_import_variant_returns_the_result_when_the_pivots_match() -> None:
    fake = FakeUnreal(_nmg_output(_matching_result()))

    result = import_variant(
        fake,
        variant_dir=VARIANT_DIR,
        dest=DESKTOP_DEST,
        name="Crate",
        report=_report(),
    )

    assert result["dest"] == DESKTOP_DEST
    assert result["variant"] == "desktop"
    assert len(fake.codes) == 1
    assert "NMG_RESULT" in fake.codes[0]


def test_import_variant_fails_when_ue_reports_not_ok() -> None:
    failed = _matching_result()
    failed["ok"] = False
    failed["error"] = "RuntimeError: texture missing: /Game/x/T_Crate_Body_BC"
    fake = FakeUnreal(_nmg_output(failed))

    with pytest.raises(PipelineError) as raised:
        import_variant(
            fake,
            variant_dir=VARIANT_DIR,
            dest=DESKTOP_DEST,
            name="Crate",
            report=_report(),
        )

    assert raised.value.code == "import_ue.failed"
    assert "texture missing" in raised.value.message


def test_import_variant_fails_when_no_result_line_is_printed() -> None:
    fake = FakeUnreal("the editor printed nothing useful")

    with pytest.raises(PipelineError) as raised:
        import_variant(
            fake,
            variant_dir=VARIANT_DIR,
            dest=DESKTOP_DEST,
            name="Crate",
            report=_report(),
        )

    assert raised.value.code == "import_ue.failed"


def test_import_variant_raises_pivot_mismatch_after_a_successful_import() -> None:
    fake = FakeUnreal(_nmg_output(_matching_result(low=[-99.0, -40.0, 0.0])))

    with pytest.raises(PipelineError) as raised:
        import_variant(
            fake,
            variant_dir=VARIANT_DIR,
            dest=DESKTOP_DEST,
            name="Crate",
            report=_report(),
        )

    assert raised.value.code == "import_ue.pivot_mismatch"


# --- rigged variants (#102) -----------------------------------------------------------------

_LOCAL_BOUNDS = {"min": [-0.5, 0.1, 0.0], "max": [0.5, 0.4, 1.0]}


def _rigged_desktop_snapshot() -> dict[str, Any]:
    """A rigged Desktop: the root mesh and the armature SK_Crate, which marks the asset rigged."""
    return {
        "SM_Crate": {"variant": "desktop", "type": "MESH", "local_bounds": _LOCAL_BOUNDS},
        "SK_Crate": {"variant": "desktop", "type": "ARMATURE", "local_bounds": None},
    }


def _rigged_mobile_snapshot() -> dict[str, Any]:
    """A rigged Mobile: the root and its two LODs, each a skinned mesh (no LodGroup Empty)."""
    return {
        "SK_Crate": {"variant": "desktop", "type": "ARMATURE", "local_bounds": None},
        "SM_Crate_Mobile": {"variant": "mobile", "type": "MESH", "local_bounds": _LOCAL_BOUNDS},
        "SM_Crate_Mobile_LOD1": {
            "variant": "mobile",
            "type": "MESH",
            "local_bounds": _LOCAL_BOUNDS,
        },
        "SM_Crate_Mobile_LOD2": {
            "variant": "mobile",
            "type": "MESH",
            "local_bounds": _LOCAL_BOUNDS,
        },
    }


def _skeletal_result(mesh: str = "SM_Crate", variant: str = "desktop") -> dict[str, Any]:
    return {
        "ok": True,
        "variant": variant,
        "name": "Crate",
        "dest": DESKTOP_DEST if variant == "desktop" else MOBILE_DEST,
        "textures": [],
        "materials": {},
        "static_meshes": {},
        "skeletal_meshes": {
            mesh: {
                "path": f"/Game/Props/Crate/{variant}/{mesh}",
                "bounds": _ue_bounds([-50.0, -40.0, 0.0], [50.0, -10.0, 100.0]),
                "lod_count": 3 if variant == "mobile" else 1,
                "skeleton": f"{DESKTOP_DEST}/SM_Crate_Skeleton",
                "physics_asset": f"{DESKTOP_DEST}/SM_Crate_PhysicsAsset",
            }
        },
        "error": None,
    }


def test_rigged_desktop_code_imports_a_skeletal_mesh_with_its_physics_asset() -> None:
    report = _report(snapshot=_rigged_desktop_snapshot())

    code = build_import_code(VARIANT_DIR, DESKTOP_DEST, "Crate", report)

    params = _embedded_params(code)
    assert params["rigged"] is True
    assert params["skeleton_dest"] == DESKTOP_DEST
    assert params["expected_meshes"] == [["SM_Crate"]]
    assert "FBXIT_SKELETAL_MESH" in code
    assert "options.import_as_skeletal = True" in code
    assert "options.import_animations = False" in code
    assert "options.create_physics_asset = True" in code
    compile(code, "<ue-import>", "exec")


def test_rigged_mobile_code_reuses_the_desktop_skeleton_and_imports_the_lods() -> None:
    report = _report("mobile", _rigged_mobile_snapshot())

    code = build_import_code(VARIANT_DIR, MOBILE_DEST, "Crate", report, skeleton_dest=DESKTOP_DEST)

    params = _embedded_params(code)
    assert params["rigged"] is True
    assert params["skeleton_dest"] == DESKTOP_DEST
    assert "SM_" in code and "_Skeleton" in code and "_PhysicsAsset" in code
    assert "options.create_physics_asset = False" in code
    assert "SkeletalMeshEditorSubsystem" in code
    assert "import_lod(mesh, level, lod_fbx)" in code
    assert params["expected_meshes"] == [["SM_Crate", "SM_Crate_Mobile"]]
    compile(code, "<ue-import>", "exec")


def test_rigged_mobile_code_needs_the_desktop_skeleton_destination() -> None:
    report = _report("mobile", _rigged_mobile_snapshot())

    with pytest.raises(ValueError, match="skeleton_dest"):
        build_import_code(VARIANT_DIR, MOBILE_DEST, "Crate", report)


def test_unrigged_report_keeps_the_static_path() -> None:
    code = build_import_code(VARIANT_DIR, DESKTOP_DEST, "Crate", _report())

    assert _embedded_params(code)["rigged"] is False
    assert "import_as_skeletal = False" in code


def test_pivot_check_matches_the_skeletal_root_and_skips_the_rigged_lods() -> None:
    report = _report("mobile", _rigged_mobile_snapshot())

    check_pivots(report, _skeletal_result("SM_Crate_Mobile", variant="mobile"))


def test_pivot_check_fails_when_a_rigged_root_has_no_skeletal_mesh() -> None:
    report = _report("mobile", _rigged_mobile_snapshot())
    result = _skeletal_result("SM_Other", variant="mobile")

    with pytest.raises(PipelineError) as raised:
        check_pivots(report, result)

    assert raised.value.code == "import_ue.pivot_mismatch"


def test_import_variant_hands_the_skeleton_destination_to_the_code() -> None:
    fake = FakeUnreal(_nmg_output(_skeletal_result("SM_Crate_Mobile", variant="mobile")))

    result = import_variant(
        fake,
        variant_dir=VARIANT_DIR,
        dest=MOBILE_DEST,
        name="Crate",
        report=_report("mobile", _rigged_mobile_snapshot()),
        skeleton_dest=DESKTOP_DEST,
    )

    assert result["ok"] is True
    assert _embedded_params(fake.codes[0])["skeleton_dest"] == DESKTOP_DEST


# --- multi-part static import (#145) ------------------------------------------------


def test_build_import_code_passes_multi_part_and_the_datablock_export_names() -> None:
    snapshot = {
        "SM_Crate": {"variant": "desktop", "type": "MESH", "mesh": "SM_Crate", "local_bounds": {}},
        "SM_Crate_Lid": {
            "variant": "desktop",
            "type": "MESH",
            "mesh": "SM_Crate_Lid.001",
            "local_bounds": {},
        },
        # Two parts that share a datablock cannot be named after it, so neither is mapped.
        "SM_Crate_Clip": {
            "variant": "desktop",
            "type": "MESH",
            "mesh": "SM_Crate_Shared",
            "local_bounds": {},
        },
        "SM_Crate_Strap": {
            "variant": "desktop",
            "type": "MESH",
            "mesh": "SM_Crate_Shared",
            "local_bounds": {},
        },
    }

    params = _embedded_params(
        build_import_code(VARIANT_DIR, DESKTOP_DEST, "Crate", _report(snapshot=snapshot))
    )

    assert params["multi_part"] is True
    assert params["mesh_names"] == {"SM_Crate": "SM_Crate", "SM_Crate_Lid.001": "SM_Crate_Lid"}


def test_multi_part_counts_base_parts_not_their_lod_objects() -> None:
    # SM_Crate_LOD0 is a level of SM_Crate, so this is still one part.
    snapshot = {
        "SM_Crate": {"variant": "desktop", "type": "MESH", "mesh": "SM_Crate", "local_bounds": {}},
        "SM_Crate_LOD0": {
            "variant": "desktop",
            "type": "MESH",
            "mesh": "SM_Crate_LOD0",
            "local_bounds": {},
        },
    }

    params = _embedded_params(
        build_import_code(VARIANT_DIR, DESKTOP_DEST, "Crate", _report(snapshot=snapshot))
    )

    assert params["multi_part"] is False


@pytest.mark.parametrize("variant", ["desktop", "mobile"])
def test_single_part_static_mesh_imports_at_the_authored_size(tmp_path: Path, variant: str) -> None:
    # AC1: one part bakes the node transform, so the reported bounds are centimetres and need no
    # build scale.
    world, folder, report = stage(tmp_path, variant, part(variant, "SM_Crate", BIG_LOW, BIG_HIGH))

    result = run_import(world, folder, variant, report)

    assert result["static_meshes"]["SM_Crate"]["bounds"] == box(800.0)
    assert world.build_writes == []


@pytest.mark.parametrize("variant", ["desktop", "mobile"])
def test_multi_part_static_meshes_import_at_the_authored_size(tmp_path: Path, variant: str) -> None:
    # AC1 and AC5: every part of a multi-part asset is rebuilt at build scale 100 on each run, and
    # each reports its authored size and is saved at that size.
    world, folder, report = stage(
        tmp_path,
        variant,
        part(variant, "SM_Crate", BIG_LOW, BIG_HIGH),
        part(variant, "SM_Crate_Trim", SMALL_LOW, SMALL_HIGH),
    )
    dest = dest_for(variant)

    result = run_import(world, folder, variant, report)

    assert result["static_meshes"]["SM_Crate"]["bounds"] == box(800.0)
    assert result["static_meshes"]["SM_Crate_Trim"]["bounds"] == box(100.0)
    # The scale is written before the rename, so each write is under the datablock-based path.
    suffix = "" if variant == "desktop" else "_Mobile"
    assert sorted(path for path, _, _ in world.build_writes) == [
        dest + "/SM_Crate" + suffix,
        dest + "/SM_Crate_Trim" + suffix,
    ]
    assert {scale for _, _, scale in world.build_writes} == {(100.0, 100.0, 100.0)}
    assert world.saved[dest + "/SM_Crate"] == box(800.0)


def test_each_part_keeps_its_own_pivot_on_a_multi_part_asset(tmp_path: Path) -> None:
    # AC2: a part 5 m and 3 m from the asset origin keeps its bounds relative to its own origin, and
    # its translation is not baked into its vertices. Y is negated, so its bounds are -75..-25 in Y.
    world, folder, report = stage(
        tmp_path,
        "desktop",
        part("desktop", "SM_Crate", BIG_LOW, BIG_HIGH),
        part("desktop", "SM_Crate_Lid", ASYM_LOW, ASYM_HIGH, translation=(5.0, 3.0, 0.0)),
    )

    result = run_import(world, folder, "desktop", report)

    assert result["static_meshes"]["SM_Crate_Lid"]["bounds"] == {
        "min": [-100.0, -75.0, 0.0],
        "max": [100.0, -25.0, 200.0],
    }


@pytest.mark.parametrize("variant", ["desktop", "mobile"])
def test_a_static_mesh_is_named_after_its_part_object_not_its_datablock(
    tmp_path: Path, variant: str
) -> None:
    # AC3: the datablock SM_Crate_Lid.001 imports as SM_Crate_Lid, and on Mobile _Mobile is removed.
    world, folder, report = stage(
        tmp_path,
        variant,
        part(variant, "SM_Crate", BIG_LOW, BIG_HIGH),
        part(
            variant,
            "SM_Crate_Lid",
            SMALL_LOW,
            SMALL_HIGH,
            translation=(2.0, 0.0, 0.0),
            duplicate=True,
        ),
    )
    dest = dest_for(variant)

    result = run_import(world, folder, variant, report)

    assert sorted(result["static_meshes"]) == ["SM_Crate", "SM_Crate_Lid"]
    assert world.static_mesh_paths() == [dest + "/SM_Crate", dest + "/SM_Crate_Lid"]


def test_a_reimport_reports_the_new_bounds_over_a_mesh_at_one_hundredth_scale(
    tmp_path: Path,
) -> None:
    # AC4: an earlier import left SM_Crate_Lid at 1/100 scale, and a datablock-named duplicate
    # beside it. The reimport reports and saves the authored size, keeps one asset per part, and
    # consolidates the old asset into the new one.
    dest = DESKTOP_DEST
    world, folder, report = stage(
        tmp_path,
        "desktop",
        part("desktop", "SM_Crate", BIG_LOW, BIG_HIGH),
        part("desktop", "SM_Crate_Lid", SMALL_LOW, SMALL_HIGH, duplicate=True),
    )
    lid = FbxNode("SM_Crate_Lid", "SM_Crate_Lid.001", SMALL_LOW, SMALL_HIGH)
    world.seed_static_mesh(dest + "/SM_Crate_Lid", lid)
    world.seed_static_mesh(dest + "/SM_Crate_Lid_001", lid)
    assert world.static_mesh(dest + "/SM_Crate_Lid").bounds == box(1.0)

    result = run_import(world, folder, "desktop", report)

    assert result["static_meshes"]["SM_Crate_Lid"]["bounds"] == box(100.0)
    assert world.saved[dest + "/SM_Crate_Lid"] == box(100.0)
    assert world.static_mesh_paths() == [dest + "/SM_Crate", dest + "/SM_Crate_Lid"]
    assert list(world.redirects) == [dest + "/SM_Crate_Lid"]


def test_a_rigged_import_keeps_its_size_and_sets_no_build_scale_or_name(tmp_path: Path) -> None:
    # AC6: the skeletal path runs neither the build scale nor the rename, even when its node's
    # datablock differs from its name.
    world, folder, report = stage(
        tmp_path,
        "desktop",
        part("desktop", "SM_Crate", BIG_LOW, BIG_HIGH, duplicate=True),
        armature=True,
    )
    dest = DESKTOP_DEST

    result = run_import(world, folder, "desktop", report)

    assert result["skeletal_meshes"]["SM_Crate"]["bounds"] == box(800.0)
    assert world.build_writes == []
    assert world.redirects == {}
    # The rig assets are the only additions: the skeleton the import made and the physics asset the
    # code created (#141). Nothing is renamed or added beside them.
    rig = [dest + "/SM_Crate_Skeleton", dest + "/SM_Crate_PhysicsAsset"]
    assert sorted(world.assets) == sorted([MASTER_PATH, dest + "/SM_Crate", *rig])


def test_texture_settings_material_binding_and_result_keys_are_unchanged(tmp_path: Path) -> None:
    # AC8: the textures, the MI_ binding, the result keys, and the error codes match before #145.
    dest = DESKTOP_DEST
    world, folder, report = stage(
        tmp_path,
        "desktop",
        part("desktop", "SM_Crate", BIG_LOW, BIG_HIGH, materials=("M_Crate_Body",)),
        textures=("T_Crate_Body_BC", "T_Crate_Body_N", "T_Crate_Body_ORM"),
    )

    result = run_import(world, folder, "desktop", report)

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
        "attempts",
    }
    assert result["textures"] == [
        dest + "/T_Crate_Body_BC",
        dest + "/T_Crate_Body_N",
        dest + "/T_Crate_Body_ORM",
    ]
    assert world.assets[dest + "/T_Crate_Body_BC"].properties == {"srgb": True}
    assert world.assets[dest + "/T_Crate_Body_N"].properties == {
        "flip_green_channel": True,
        "compression_settings": "TC_NORMALMAP",
        "srgb": False,
    }
    assert world.assets[dest + "/T_Crate_Body_ORM"].properties == {
        "srgb": False,
        "compression_settings": "TC_MASKS",
    }
    instance = world.assets[dest + "/MI_Crate_Body"]
    assert isinstance(instance, MaterialInstanceConstant)
    assert instance.parent is world.assets[MASTER_PATH]
    assert instance.texture_params == {
        "BaseColor": dest + "/T_Crate_Body_BC",
        "Normal": dest + "/T_Crate_Body_N",
        "ORM": dest + "/T_Crate_Body_ORM",
    }
    assert world.static_mesh(dest + "/SM_Crate").static_materials[0].material_interface is instance
    assert result["materials"] == {"M_Crate_Body": dest + "/MI_Crate_Body"}


def test_a_missing_master_material_fails_with_the_import_ue_failed_code(tmp_path: Path) -> None:
    # AC8: the error code and remediation path are unchanged.
    world, folder, report = stage(
        tmp_path,
        "desktop",
        part("desktop", "SM_Crate", BIG_LOW, BIG_HIGH, materials=("M_Crate_Body",)),
        seed_master=False,
    )

    with pytest.raises(PipelineError) as raised:
        run_import(world, folder, "desktop", report)

    assert raised.value.code == "import_ue.failed"
    assert "M_NmgORM is missing" in raised.value.message


# --- static Mobile LOD group (#146) -----------------------------------------------------------


def _lod_group_snapshot() -> dict[str, Any]:
    """A static Mobile LOD group as variants_core exports it: the Empty and its three LOD meshes."""
    snapshot: dict[str, Any] = {
        "SM_Crate_Mobile": {
            "variant": "mobile",
            "type": "EMPTY",
            "mesh": None,
            "local_bounds": None,
        },
    }
    for level in range(3):
        key = f"SM_Crate_Mobile_LOD{level}"
        snapshot[key] = {
            "variant": "mobile",
            "type": "MESH",
            "mesh": key,
            "local_bounds": _LOCAL_BOUNDS,
        }
    return snapshot


def _static_lod_result(entry_fields: dict[str, Any]) -> dict[str, Any]:
    """The UE result for a static LOD group: one Static Mesh SM_Crate with ``entry_fields`` set."""
    result = _matching_result("mobile")
    result["static_meshes"]["SM_Crate"].update(entry_fields)
    return result


def test_static_lod_group_expects_one_static_mesh_named_after_its_empty() -> None:
    # AC1, FR3: the _LOD0 entry is the Static Mesh SM_Crate, and _LOD1 and _LOD2 expect no mesh.
    code = build_import_code(
        VARIANT_DIR, MOBILE_DEST, "Crate", _report("mobile", _lod_group_snapshot())
    )

    params = _embedded_params(code)
    assert params["expected_meshes"] == [
        ["SM_Crate", "SM_Crate_LOD0", "SM_Crate_Mobile", "SM_Crate_Mobile_LOD0"]
    ]
    assert params["rigged"] is False
    assert params["multi_part"] is False
    assert "get_num_lods()" in code
    assert '"lod_count"' in code
    compile(code, "<ue-import>", "exec")


def test_import_variant_accepts_a_static_lod_group_that_reports_three_lods() -> None:
    # AC1, AC4: one Static Mesh SM_Crate with three LODs passes the LOD count and pivot checks.
    fake = FakeUnreal(_nmg_output(_static_lod_result({"lod_count": 3})))

    result = import_variant(
        fake,
        variant_dir=VARIANT_DIR,
        dest=MOBILE_DEST,
        name="Crate",
        report=_report("mobile", _lod_group_snapshot()),
    )

    assert sorted(result["static_meshes"]) == ["SM_Crate"]
    assert result["static_meshes"]["SM_Crate"]["lod_count"] == 3


@pytest.mark.parametrize(
    ("entry_fields", "actual"),
    [({"lod_count": 1}, "1"), ({}, "missing")],
)
def test_static_lod_group_fails_when_the_lod_count_differs_or_is_missing(
    entry_fields: dict[str, Any], actual: str
) -> None:
    # AC2, FR4: the message names the mesh, the expected count of 3, and the actual count.
    fake = FakeUnreal(_nmg_output(_static_lod_result(entry_fields)))

    with pytest.raises(PipelineError) as raised:
        import_variant(
            fake,
            variant_dir=VARIANT_DIR,
            dest=MOBILE_DEST,
            name="Crate",
            report=_report("mobile", _lod_group_snapshot()),
        )

    assert raised.value.code == "import_ue.failed"
    assert "SM_Crate" in raised.value.message
    assert "3" in raised.value.message
    assert actual in raised.value.message


def test_static_lod_group_pivot_is_checked_against_lod0_alone() -> None:
    # AC3, FR5: SM_Crate is compared with SM_Crate_Mobile_LOD0. The passing check also shows that
    # _LOD1 and _LOD2 are not looked up as meshes, because no mesh of theirs exists.
    report = _report("mobile", _lod_group_snapshot())

    check_pivots(report, _matching_result("mobile", mesh="SM_Crate"))

    off = _matching_result("mobile", mesh="SM_Crate", high=[50.0, -10.5, 100.0])
    with pytest.raises(PipelineError) as raised:
        check_pivots(report, off)
    assert raised.value.code == "import_ue.pivot_mismatch"
    assert "SM_Crate_Mobile_LOD0" in raised.value.message


def test_static_lod_group_reimport_passes_the_lod_count_and_pivot_checks_again() -> None:
    # AC6: the Mobile import code replaces existing assets, and a second UE result that again
    # reports SM_Crate with three LODs and matching bounds passes both checks.
    report = _report("mobile", _lod_group_snapshot())
    fake = FakeUnreal(_nmg_output(_static_lod_result({"lod_count": 3})))

    first = import_variant(
        fake, variant_dir=VARIANT_DIR, dest=MOBILE_DEST, name="Crate", report=report
    )
    second = import_variant(
        fake, variant_dir=VARIANT_DIR, dest=MOBILE_DEST, name="Crate", report=report
    )

    assert first == second
    assert "task.replace_existing = True" in fake.codes[0]


def test_check_lod_counts_passes_for_a_multi_part_mobile_with_no_lod_count() -> None:
    # AC7, FR8: a multi-part static Mobile expects one mesh per part and gets no LOD count check.
    snapshot = {
        "SM_Crate_Mobile": {"variant": "mobile", "type": "MESH", "local_bounds": _LOCAL_BOUNDS},
        "SM_Crate_Lid_Mobile": {"variant": "mobile", "type": "MESH", "local_bounds": _LOCAL_BOUNDS},
    }
    report = _report("mobile", snapshot)

    params = _embedded_params(build_import_code(VARIANT_DIR, MOBILE_DEST, "Crate", report))
    assert params["multi_part"] is True
    assert params["expected_meshes"] == [
        ["SM_Crate_Lid", "SM_Crate_Lid_Mobile"],
        ["SM_Crate", "SM_Crate_Mobile"],
    ]

    result = _matching_result("mobile", mesh="SM_Crate")
    result["static_meshes"]["SM_Crate_Lid"] = {
        "path": f"{MOBILE_DEST}/SM_Crate_Lid",
        "bounds": {"min": [0.0, 0.0, 0.0], "max": [1.0, 1.0, 1.0]},
    }
    check_lod_counts(report, result)


def test_check_lod_counts_does_nothing_for_desktop_or_rigged_results() -> None:
    # AC7, FR8: a static Desktop and a rigged variant have no LOD group, so they pass unchecked.
    check_lod_counts(_report(), _matching_result())
    check_lod_counts(
        _report("mobile", _rigged_mobile_snapshot()),
        _skeletal_result("SM_Crate_Mobile", variant="mobile"),
    )


def _stage_static_lod_group(
    tmp_path: Path, lods: int = 3
) -> tuple[FakeWorld, Path, dict[str, Any]]:
    """Stage the Mobile variant of a static LOD group on the fake editor.

    The FBX holds one node, SM_Crate, with ``lods`` LODs, which is what Interchange reads from the
    LOD-group FBX. The snapshot holds the Empty SM_Crate_Mobile and its three LOD meshes.
    """
    bounds = {"min": list(ASYM_LOW), "max": list(ASYM_HIGH)}
    node = FbxNode(
        "SM_Crate",
        "SM_Crate_Mobile_LOD0",
        ASYM_LOW,
        ASYM_HIGH,
        materials=("M_Crate_Body",),
        lods=lods,
    )
    entry = {
        "variant": "mobile",
        "type": "MESH",
        "mesh": "SM_Crate_Mobile_LOD0",
        "local_bounds": bounds,
    }
    textures = ("T_Crate_Body_BC", "T_Crate_Body_N", "T_Crate_Body_ORM")
    world, folder, report = stage(
        tmp_path, "mobile", (node, "SM_Crate_Mobile_LOD0", entry), textures=textures
    )
    snapshot = report["snapshot"]
    snapshot["SM_Crate_Mobile"] = {
        "variant": "mobile",
        "type": "EMPTY",
        "mesh": None,
        "local_bounds": None,
    }
    for level in (1, 2):
        key = f"SM_Crate_Mobile_LOD{level}"
        snapshot[key] = {"variant": "mobile", "type": "MESH", "mesh": key, "local_bounds": bounds}
    return world, folder, report


def test_static_lod_group_imports_one_static_mesh_on_the_fake(tmp_path: Path) -> None:
    # AC1, AC4, AC5, FR1, FR2, FR7: the generated code imports SM_Crate.fbx once, reports three
    # LODs, binds the slot's material, and makes no per-LOD asset and no build-scale write.
    world, folder, report = _stage_static_lod_group(tmp_path)

    result = run_import(world, folder, "mobile", report)

    assert sorted(result["static_meshes"]) == ["SM_Crate"]
    assert result["static_meshes"]["SM_Crate"]["lod_count"] == 3
    assert result["static_meshes"]["SM_Crate"]["bounds"] == {
        "min": [-100.0, -75.0, 0.0],
        "max": [100.0, -25.0, 200.0],
    }
    assert result["materials"] == {"M_Crate_Body": MOBILE_DEST + "/MI_Crate_Body"}
    instance = world.assets[MOBILE_DEST + "/MI_Crate_Body"]
    assert world.static_mesh(MOBILE_DEST + "/SM_Crate").static_materials[0].material_interface is (
        instance
    )
    assert world.imported_fbx == [str(folder / "SM_Crate.fbx")]
    assert world.static_mesh_paths() == [MOBILE_DEST + "/SM_Crate"]
    assert world.build_writes == []


def test_static_lod_group_fails_on_the_fake_when_the_mesh_lost_lods(tmp_path: Path) -> None:
    # AC2: the UE mesh has one LOD where the snapshot has three, so the import fails.
    world, folder, report = _stage_static_lod_group(tmp_path, lods=1)

    with pytest.raises(PipelineError) as raised:
        run_import(world, folder, "mobile", report)

    assert raised.value.code == "import_ue.failed"
    assert "SM_Crate has 1 LODs" in raised.value.message
    assert "3 LOD objects" in raised.value.message


def test_a_repeated_static_lod_group_import_gives_the_same_result(tmp_path: Path) -> None:
    # AC6: a second Mobile import over the first replaces it and passes both checks.
    world, folder, report = _stage_static_lod_group(tmp_path)

    first = run_import(world, folder, "mobile", report)
    second = run_import(world, folder, "mobile", report)

    assert second == first
    assert second["static_meshes"]["SM_Crate"]["lod_count"] == 3


def test_a_single_part_static_mesh_reports_one_lod(tmp_path: Path) -> None:
    # AC4: any static mesh that is not a LOD group reports a lod_count of 1.
    world, folder, report = stage(
        tmp_path, "desktop", part("desktop", "SM_Crate", BIG_LOW, BIG_HIGH)
    )

    result = run_import(world, folder, "desktop", report)

    assert result["static_meshes"]["SM_Crate"]["lod_count"] == 1


# --- folder resolution and rig assets on the fake (#141) ---------------------------------------

_CVAR = "Interchange.FeatureFlags.Import.FBX"
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _only_first_mesh(created: list[str]) -> list[str]:
    """What UE 5.8 reports for a multi-part FBX: the first mesh alone, in imported_object_paths."""
    return created[:1]


def test_a_multi_part_static_import_returns_every_part(tmp_path: Path) -> None:
    # AC1, SCN001: three parts, all reported by the task, and each one comes back.
    world, folder, report = stage(
        tmp_path,
        "desktop",
        part("desktop", "SM_Crate", BIG_LOW, BIG_HIGH),
        part("desktop", "SM_Crate_Body", SMALL_LOW, SMALL_HIGH),
        part("desktop", "SM_Crate_Lid", SMALL_LOW, SMALL_HIGH),
    )

    result = run_import(world, folder, "desktop", report)

    assert result["ok"] is True
    assert sorted(result["static_meshes"]) == ["SM_Crate", "SM_Crate_Body", "SM_Crate_Lid"]
    assert world.static_mesh_paths() == [
        DESKTOP_DEST + "/SM_Crate",
        DESKTOP_DEST + "/SM_Crate_Body",
        DESKTOP_DEST + "/SM_Crate_Lid",
    ]


def test_a_two_part_static_import_returns_both_parts_when_the_task_lists_only_the_first(
    tmp_path: Path,
) -> None:
    # AC7, FR1: both parts are in the folder, but the task lists only SM_Crate.
    world, folder, report = stage(
        tmp_path,
        "desktop",
        part("desktop", "SM_Crate", BIG_LOW, BIG_HIGH),
        part("desktop", "SM_Crate_Lid", SMALL_LOW, SMALL_HIGH),
    )
    world.reported_paths = _only_first_mesh

    result = run_import(world, folder, "desktop", report)

    assert result["ok"] is True
    assert sorted(result["static_meshes"]) == ["SM_Crate", "SM_Crate_Lid"]
    assert result["static_meshes"]["SM_Crate"]["bounds"] == box(800.0)
    assert result["static_meshes"]["SM_Crate_Lid"]["bounds"] == box(100.0)


def test_expected_meshes_are_resolved_by_name_and_an_unrelated_mesh_is_ignored(
    tmp_path: Path,
) -> None:
    # AC2, SCN002: an unrelated Static Mesh in the folder is neither bound nor reported.
    world, folder, report = stage(
        tmp_path,
        "desktop",
        part("desktop", "SM_Crate", BIG_LOW, BIG_HIGH),
        part("desktop", "SM_Crate_Lid", SMALL_LOW, SMALL_HIGH),
    )
    unrelated = FbxNode("SM_Other", "SM_Other", SMALL_LOW, SMALL_HIGH, materials=("M_Crate_Extra",))
    world.seed_static_mesh(DESKTOP_DEST + "/SM_Other", unrelated, transform=True)
    world.reported_paths = _only_first_mesh

    result = run_import(world, folder, "desktop", report)

    assert sorted(result["static_meshes"]) == ["SM_Crate", "SM_Crate_Lid"]
    assert "M_Crate_Extra" not in result["materials"]
    other = world.static_mesh(DESKTOP_DEST + "/SM_Other")
    assert other.static_materials[0].material_interface is None
    assert all("SM_Other" not in path for path, _, _ in world.build_writes)


def test_a_rigged_desktop_import_creates_the_missing_physics_asset(tmp_path: Path) -> None:
    # AC3, SCN003, FR3: the import makes the skeleton but no physics asset, so the code makes it.
    dest = DESKTOP_DEST
    world, folder, report = stage(
        tmp_path, "desktop", part("desktop", "SM_Crate", BIG_LOW, BIG_HIGH), armature=True
    )

    result = run_import(world, folder, "desktop", report)

    assert result["ok"] is True
    assert world.create_physics_calls == [dest + "/SM_Crate"]
    physics = world.assets[dest + "/SM_Crate_PhysicsAsset"]
    assert world.assets[dest + "/SM_Crate"].get_editor_property("physics_asset") is physics
    assert {dest + "/SM_Crate", dest + "/SM_Crate_PhysicsAsset"} <= set(world.saved)
    skeletal = result["skeletal_meshes"]["SM_Crate"]
    assert skeletal["skeleton"] == dest + "/SM_Crate_Skeleton"
    assert skeletal["physics_asset"] == dest + "/SM_Crate_PhysicsAsset"


def test_a_created_physics_asset_is_moved_into_the_destination_folder(tmp_path: Path) -> None:
    # FR3: UE places the new physics asset beside the Desktop folder, so the code moves it to dest.
    dest = DESKTOP_DEST
    world, folder, report = stage(
        tmp_path, "desktop", part("desktop", "SM_Crate", BIG_LOW, BIG_HIGH), armature=True
    )
    world.physics_folder = dest + "/Physics"

    run_import(world, folder, "desktop", report)

    assert dest + "/Physics/SM_Crate_PhysicsAsset" not in world.assets
    physics = world.assets[dest + "/SM_Crate_PhysicsAsset"]
    assert world.assets[dest + "/SM_Crate"].get_editor_property("physics_asset") is physics


def test_a_rigged_desktop_import_without_a_skeleton_fails_naming_it(tmp_path: Path) -> None:
    # AC3: a missing skeleton fails the import, naming the skeleton path, before any physics asset.
    world, folder, report = stage(
        tmp_path, "desktop", part("desktop", "SM_Crate", BIG_LOW, BIG_HIGH), armature=True
    )
    world.skeleton_on_import = False
    code = build_import_code(str(folder), DESKTOP_DEST, "Crate", report)

    result = run_import_code(code, world)

    assert result["ok"] is False
    assert result["error"] == (
        "RuntimeError: skeleton missing after import: " + DESKTOP_DEST + "/SM_Crate_Skeleton"
    )
    assert world.create_physics_calls == []


def test_a_rigged_mobile_import_reuses_the_desktop_skeleton_and_physics_asset(
    tmp_path: Path,
) -> None:
    # AC4, SCN004: the Mobile import in the same editor reuses the Desktop rig and imports LOD1/2.
    world, desktop_folder, desktop_report = stage(
        tmp_path, "desktop", part("desktop", "SM_Crate", BIG_LOW, BIG_HIGH), armature=True
    )
    run_import(world, desktop_folder, "desktop", desktop_report)
    mobile_folder = tmp_path / "export" / "Props" / "Crate" / "Mobile"
    mobile_folder.mkdir(parents=True)
    for name in ("SM_Crate.fbx", "SM_Crate_LOD1.fbx", "SM_Crate_LOD2.fbx"):
        (mobile_folder / name).write_bytes(b"")
    mobile_node, _, _ = part("mobile", "SM_Crate", (-0.5, 0.1, 0.0), (0.5, 0.4, 1.0))
    world.add_fbx(str(mobile_folder / "SM_Crate.fbx"), [mobile_node])

    result = run_import(
        world,
        mobile_folder,
        "mobile",
        _report("mobile", _rigged_mobile_snapshot()),
        skeleton_dest=DESKTOP_DEST,
    )

    assert result["ok"] is True
    options = world.import_options[-1]
    assert options.skeleton is world.assets[DESKTOP_DEST + "/SM_Crate_Skeleton"]
    assert options.physics_asset is world.assets[DESKTOP_DEST + "/SM_Crate_PhysicsAsset"]
    assert options.create_physics_asset is False
    assert [(mesh, level) for mesh, level, _ in world.lod_imports] == [
        (MOBILE_DEST + "/SM_Crate", 1),
        (MOBILE_DEST + "/SM_Crate", 2),
    ]
    skeletal = result["skeletal_meshes"]["SM_Crate"]
    assert skeletal["lod_count"] == 3
    assert skeletal["physics_asset"] == DESKTOP_DEST + "/SM_Crate_PhysicsAsset"


def test_a_reimport_reports_the_new_bounds_and_passes_the_pivot_check(tmp_path: Path) -> None:
    # AC5, SCN005: the folder already holds SM_Crate at the old size, and the import replaces it.
    dest = DESKTOP_DEST
    world, folder, report = stage(
        tmp_path, "desktop", part("desktop", "SM_Crate", BIG_LOW, BIG_HIGH)
    )
    old = FbxNode("SM_Crate", "SM_Crate", SMALL_LOW, SMALL_HIGH)
    world.seed_static_mesh(dest + "/SM_Crate", old, transform=True)
    assert world.static_mesh(dest + "/SM_Crate").bounds == box(100.0)

    result = run_import(world, folder, "desktop", report)

    assert result["static_meshes"]["SM_Crate"]["bounds"] == box(800.0)
    assert world.saved[dest + "/SM_Crate"] == box(800.0)
    check_pivots(report, result)


def test_two_missing_parts_fail_the_import_and_name_both(tmp_path: Path) -> None:
    # AC6, SCN006, FR5: the snapshot lists two parts the import never made, and both are named.
    world, folder, report = stage(
        tmp_path, "desktop", part("desktop", "SM_Crate", BIG_LOW, BIG_HIGH)
    )
    for export in ("SM_Crate_Body", "SM_Crate_Lid"):
        _, key, entry = part("desktop", export, SMALL_LOW, SMALL_HIGH)
        report["snapshot"][key] = entry

    with pytest.raises(PipelineError) as raised:
        run_import(world, folder, "desktop", report)

    assert raised.value.code == "import_ue.failed"
    assert "no static mesh for snapshot part: SM_Crate_Body, SM_Crate_Lid" in raised.value.message


def test_no_shipped_file_offers_the_interchange_cvar_as_a_workaround() -> None:
    # AC9, SCN009, FR6: nothing the repository ships names the cvar, and neither does the code.
    offenders = []
    for directory in ("src", "skills", "docs", "scripts", "templates"):
        root = _REPO_ROOT / directory
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if "__pycache__" in path.parts or not path.is_file():
                continue
            if _CVAR.encode() in path.read_bytes():
                offenders.append(str(path.relative_to(_REPO_ROOT)))
    assert offenders == []
    code = build_import_code(VARIANT_DIR, DESKTOP_DEST, "Crate", _report())
    rigged = build_import_code(
        VARIANT_DIR, DESKTOP_DEST, "Crate", _report(snapshot=_rigged_desktop_snapshot())
    )
    assert "Interchange.FeatureFlags" not in code
    assert "Interchange.FeatureFlags" not in rigged
