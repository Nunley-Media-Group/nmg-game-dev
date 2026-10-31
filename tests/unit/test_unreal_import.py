"""UE import code, NMG_RESULT parsing, and the pivot check for the finalize import step (#69, AC5).

A fake client stands in for UnrealMcpClient. It returns a canned tool output and records the
UE code it was given. The UE code itself runs only in the editor, so these tests check its
text, its embedded parameters, and the host-side result handling.
"""

from __future__ import annotations

import ast
import json
from typing import Any

import pytest

from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.unreal import (
    build_import_code,
    check_pivots,
    import_variant,
    parse_nmg_result,
)

DESKTOP_DEST = "/Game/Props/Crate/Desktop"
MOBILE_DEST = "/Game/Props/Crate/Mobile"
VARIANT_DIR = "/work/export/Props/Crate/Desktop"


class FakeUnreal:
    """Satisfies UnrealPythonClient. Returns ``output`` and remembers the code it received."""

    def __init__(self, output: str) -> None:
        self.output = output
        self.codes: list[str] = []

    def execute_python_code(self, code: str) -> str:
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
    return {
        "kind": "contract",
        "asset": "Crate",
        "class": "standard_prop",
        "passed": True,
        "findings": [],
        "snapshot": snapshot if snapshot is not None else _snapshot(variant),
    }


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
    assert "transform_vertex_to_absolute = False" in code
    assert "bake_pivot_in_vertex = False" in code


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
