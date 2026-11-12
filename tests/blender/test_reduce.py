"""reduce_core under Blender headless: AC1-AC14 and the reduce job envelope (#139).

Run with scripts/run-blender-tests.sh. The runner executes every test in one Blender process, and
the entry-script test runs finalize_entry.py in a fresh Blender subprocess, as production does.
Under plain CPython the module is skipped.
"""

from __future__ import annotations

import importlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

bpy = pytest.importorskip("bpy")

import numpy as np  # noqa: E402

from .contract_fixtures import clear_scene  # noqa: E402
from .reduce_fixtures import (  # noqa: E402
    PARTS,
    build_high_poly,
    object_name,
    reduce_budgets_file,
    scene_snapshot,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ENTRY = REPO_ROOT / "scripts" / "blender" / "finalize_entry.py"
_UNREDUCED_PART_TRIS = 6348
_HULL = object_name("Crate", "Hull")
_TURRET = object_name("Crate", "Turret")
_LID = object_name("Crate", "Lid")


@pytest.fixture(autouse=True)
def _isolated_scene(enabled_addon: str) -> Any:  # noqa: ARG001 - ordering dependency
    clear_scene()
    yield
    clear_scene()


@pytest.fixture()
def reduce_core(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.reduce_core")


@pytest.fixture()
def contract_uv(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.contract_core.uv")


def _triangles(mesh: bpy.types.Mesh) -> int:
    return sum(max(poly.loop_total - 2, 0) for poly in mesh.polygons)


def _part_meshes(collection_name: str) -> dict[str, bpy.types.Object]:
    collection = bpy.data.collections[collection_name]
    return {obj.name: obj for obj in collection.all_objects if obj.type == "MESH"}


def _reduce(reduce_core: Any, tmp_path: Path, **overrides: Any) -> dict[str, Any]:
    options: dict[str, Any] = {
        "device": "CPU",
        "out_dir": tmp_path / "out",
    }
    options.update(overrides)
    return reduce_core.reduce_asset(
        "Crate", "standard_prop", reduce_budgets_file(tmp_path), **options
    )


def test_over_budget_asset_reduces_into_budget_with_names_and_parents(
    reduce_core: Any, contract_uv: Any, tmp_path: Path
) -> None:
    """AC1, AC2, AC3, AC4, AC5, AC6, AC7, AC8, and the `_High` exclusion from hash and validate."""
    collection = build_high_poly("Crate", with_root=True)
    bpy.context.view_layer.update()
    originals = {
        name: (tuple(round(v, 5) for row in obj.matrix_world for v in row), obj.parent)
        for name, obj in _part_meshes("Crate").items()
    }
    root_name = collection.objects["Crate_Root"].name
    assert set(originals) == {object_name("Crate", part) for part, _, _ in PARTS}

    result = _reduce(
        reduce_core,
        tmp_path,
        cage_extrusion=0.05,
        parts={_HULL: {"share": 0.5}, _LID: {"max_ray_distance": 0.5}},
    )

    assert result["kind"] == "reduce"
    assert result["state"] == "reduced", result
    reduced = _part_meshes("Crate")
    # AC1: the same part names, transforms, and parents, within the Desktop budget.
    assert set(reduced) == set(originals)
    for name, obj in reduced.items():
        matrix = tuple(round(v, 5) for row in obj.matrix_world for v in row)
        assert matrix == originals[name][0], name
    assert reduced[_TURRET].parent is not None and reduced[_TURRET].parent.name == root_name
    assert reduced[_LID].parent is not None and reduced[_LID].parent.name == _HULL
    total = sum(_triangles(obj.data) for obj in reduced.values())
    assert total <= 3000
    assert total == result["total_tris"]

    # AC3 and AC4: the Hull override gives 1,500; the rest split the remaining 1,500 by area
    # (Turret 13.5 m2 against Lid 6 m2), and no part is above its target.
    parts = result["parts"]
    assert parts[_HULL]["target"] == 1500
    assert parts[_TURRET]["target"] == 1038
    assert parts[_LID]["target"] == 461
    for name, obj in reduced.items():
        assert parts[name]["final_tris"] == _triangles(obj.data)
        assert parts[name]["final_tris"] <= parts[name]["target"]
        assert parts[name]["source_tris"] == _UNREDUCED_PART_TRIS

    # AC7: asset-wide cage, and the per-part ray distance, are reported per part.
    assert parts[_HULL]["cage_extrusion"] == pytest.approx(0.05)
    assert parts[_HULL]["max_ray_distance"] == pytest.approx(0.10)
    assert parts[_LID]["max_ray_distance"] == pytest.approx(0.5)
    assert parts[_TURRET]["cage_extrusion"] == pytest.approx(0.05)

    # AC8: every part reports an unbaked share in 0..1, and the coverage is high.
    for name in reduced:
        share = parts[name]["unbaked_share"]
        assert 0.0 <= share <= 1.0
        assert share <= 0.01, name

    # AC2: the originals sit in a hidden top-level <Name>_High, unchanged, and not exported.
    high = bpy.data.collections.get("Crate_High")
    assert high is not None and high.name in bpy.context.scene.collection.children
    assert high.hide_viewport and high.hide_render
    assert {obj.name for obj in high.all_objects} == {f"{name}_High" for name in originals}
    for obj in high.all_objects:
        assert obj["nmg_source_name"] == obj.name.removesuffix("_High")
        assert _triangles(obj.data) == _UNREDUCED_PART_TRIS
        assert [slot.material.name for slot in obj.material_slots] == [
            f"M_Crate_{obj.name.removeprefix('SM_Crate_').removesuffix('_High')}_Authored"
        ]
    assert bpy.data.collections["Crate"]["nmg_reduced"] is True

    # AC2: the hash and the validation read only <Name>, so changing a _High object moves neither.
    before = reduce_core_hash(bpy.data.collections["Crate"])
    high.all_objects[0].location.x += 5.0
    assert reduce_core_hash(bpy.data.collections["Crate"]) == before
    report = _validate_crate(reduce_core)
    assert "_High" not in json.dumps(report["snapshot"])

    # AC5: one UVMap per part, every island in 0..1, and no overlap across the whole asset.
    faces: list[tuple[int, list[tuple[float, float]]]] = []
    for obj in reduced.values():
        assert [layer.name for layer in obj.data.uv_layers] == ["UVMap"]
        layer = obj.data.uv_layers[0].data
        for poly in obj.data.polygons:
            corners = [
                (layer[index].uv.x, layer[index].uv.y)
                for index in range(poly.loop_start, poly.loop_start + poly.loop_total)
            ]
            assert all(0.0 <= u <= 1.0 and 0.0 <= v <= 1.0 for u, v in corners)
            faces.append((len(faces), corners))
    assert contract_uv.polygon_overlap_fraction(faces) <= contract_uv.OVERLAP_LIMIT

    # AC6: one material on every reduced part, wired to 256 px BC, N, and ORM textures.
    for obj in reduced.values():
        assert [slot.material.name for slot in obj.material_slots] == ["M_Crate_Body"]
    assert result["texture_px"] == 256
    assert set(result["textures"]) == {"BC", "N", "ORM"}
    material = bpy.data.materials["M_Crate_Body"]
    images = {
        node.label: node.image for node in material.node_tree.nodes if node.type == "TEX_IMAGE"
    }
    assert set(images) == {"T_Crate_Body_BC", "T_Crate_Body_N", "T_Crate_Body_ORM"}
    for name, image in images.items():
        assert image.name == name
        assert tuple(image.size) == (256, 256)
        assert image.packed_file is not None, name
    base = np.array(images["T_Crate_Body_BC"].pixels[:])
    assert float(base.std()) > 1e-3, "the base colour bake is flat"
    for path in result["textures"].values():
        assert Path(path).is_file()


def reduce_core_hash(collection: bpy.types.Collection) -> str:
    """The content hash of <Name>, read through the finalize core the host uses."""
    core = importlib.import_module("nmg_game_dev_blender_addon.finalize_core")
    return core.content_hash(collection.name)


def _validate_crate(reduce_core: Any) -> dict[str, Any]:  # noqa: ARG001 - the add-on is loaded
    contract = importlib.import_module("nmg_game_dev_blender_addon.contract_core")
    return contract.validate_asset("Crate", "standard_prop", None, authored=True)


def test_rerun_rebuilds_from_high_and_never_duplicates_it_ac11(
    reduce_core: Any, tmp_path: Path
) -> None:
    build_high_poly("Crate")
    _reduce(reduce_core, tmp_path)
    high_names = {obj.name for obj in bpy.data.collections["Crate_High"].all_objects}

    result = _reduce(reduce_core, tmp_path, cage_extrusion=0.04, miss_threshold=0.05)

    assert result["state"] == "reduced"
    assert [c.name for c in bpy.data.collections if c.name.startswith("Crate_High")] == [
        "Crate_High"
    ]
    assert {obj.name for obj in bpy.data.collections["Crate_High"].all_objects} == high_names
    for obj in bpy.data.collections["Crate_High"].all_objects:
        assert _triangles(obj.data) == _UNREDUCED_PART_TRIS
    reduced = _part_meshes("Crate")
    assert set(reduced) == {object_name("Crate", part) for part, _, _ in PARTS}
    assert sum(_triangles(obj.data) for obj in reduced.values()) <= 3000
    assert result["parts"][_HULL]["cage_extrusion"] == pytest.approx(0.04)
    assert bpy.data.materials.get("M_Crate_Body") is not None
    assert [m.name for m in bpy.data.materials if m.name.startswith("M_Crate_Body")] == [
        "M_Crate_Body"
    ]


def test_ray_misses_fail_the_step_and_leave_the_scene_unchanged_ac9(
    reduce_core: Any, tmp_path: Path
) -> None:
    build_high_poly("Crate")
    before = scene_snapshot()

    result = reduce_core.run_for_mcp(
        collection="Crate",
        asset_class="standard_prop",
        budgets_path=reduce_budgets_file(tmp_path),
        device="CPU",
        max_ray_distance=0.0001,
        out_dir=str(tmp_path / "out"),
    )

    assert "error" in result, result
    error = result["error"]
    assert error["code"] == "reduce.bake_misses"
    assert error["target"] in {object_name("Crate", part) for part, _, _ in PARTS}
    assert "0.0001" in error["message"] and "%" in error["message"]
    assert scene_snapshot() == before
    assert bpy.data.collections.get("Crate_High") is None


def test_asset_already_in_budget_is_left_alone_ac12(reduce_core: Any, tmp_path: Path) -> None:
    build_high_poly("Crate", cuts=2)
    before = scene_snapshot()

    result = _reduce(reduce_core, tmp_path)

    assert result["state"] == "within_budget"
    assert result["textures"] == {}
    assert result["device"] is None
    assert scene_snapshot() == before
    assert bpy.data.collections.get("Crate_High") is None


def test_overrides_are_refused_before_any_change_ac4(reduce_core: Any, tmp_path: Path) -> None:
    build_high_poly("Crate")
    before = scene_snapshot()
    budgets = reduce_budgets_file(tmp_path)
    cases = {
        "reduce.overrides_exceed_budget": {
            _HULL: {"tris": 2000},
            _TURRET: {"tris": 2000},
        },
        "reduce.unknown_part": {"SM_Crate_Ghost": {"share": 0.2}},
        "reduce.invalid_override": {_HULL: {"share": 0.2, "tris": 100}},
    }
    for code, parts in cases.items():
        result = reduce_core.run_for_mcp(
            collection="Crate",
            asset_class="standard_prop",
            budgets_path=budgets,
            device="CPU",
            parts=parts,
            out_dir=str(tmp_path / "out"),
        )
        assert result["error"]["code"] == code, result
        assert scene_snapshot() == before


def test_rigged_asset_and_terrain_class_are_refused_ac13(reduce_core: Any, tmp_path: Path) -> None:
    build_high_poly("Crate", armature=True)
    before = scene_snapshot()
    rigged = reduce_core.run_for_mcp(
        collection="Crate",
        asset_class="standard_prop",
        budgets_path=reduce_budgets_file(tmp_path),
        device="CPU",
        out_dir=str(tmp_path / "out"),
    )
    assert rigged["error"]["code"] == "reduce.rigged"
    assert scene_snapshot() == before

    terrain = reduce_core.run_for_mcp(
        collection="Crate",
        asset_class="terrain",
        device="CPU",
        out_dir=str(tmp_path / "out"),
    )
    assert terrain["error"]["code"] == "reduce.class_unsupported"
    assert scene_snapshot() == before


def test_the_panel_operator_mcp_call_and_direct_call_share_one_result_shape_ac14(
    reduce_core: Any, tmp_path: Path
) -> None:
    build_high_poly("Crate", cuts=2)
    budgets = reduce_budgets_file(tmp_path)

    direct = reduce_core.reduce_asset("Crate", "standard_prop", budgets, device="CPU")
    via_mcp = reduce_core.run_for_mcp(
        collection="Crate", asset_class="standard_prop", budgets_path=budgets, device="CPU"
    )
    assert set(via_mcp) == set(direct)
    assert via_mcp["state"] == direct["state"] == "within_budget"

    outcome = bpy.ops.nmggamedev.reduce_to_budget(
        collection_name="Crate",
        asset_class="standard_prop",
        budgets_path=budgets,
        device="CPU",
    )
    assert outcome == {"FINISHED"}
    stored = json.loads(bpy.context.scene.nmg_game_dev.last_result)
    assert set(stored) == set(direct)
    assert stored["state"] == "within_budget"

    missing = reduce_core.run_for_mcp(collection="Missing", asset_class="standard_prop")
    assert missing["error"]["code"] == "reduce.collection_missing"


def test_reduce_job_writes_the_envelope_and_the_blend_ac14(
    enabled_addon: str, tmp_path: Path
) -> None:
    job_module = importlib.import_module(f"{enabled_addon}.finalize_core.reduce_job")
    build_high_poly("Crate", cuts=2)
    request = {
        "collection": "Crate",
        "asset_class": "standard_prop",
        "budgets_path": reduce_budgets_file(tmp_path),
        "device": "CPU",
        "cage_extrusion": None,
        "max_ray_distance": None,
        "miss_threshold": None,
        "parts": {},
    }
    job = tmp_path / "job"

    envelope = job_module.run_reduce(request, job)

    assert envelope["schemaVersion"] == 1
    assert envelope["step"] == "reduce"
    assert envelope["ok"] is True, envelope["error"]
    assert envelope["error"] is None
    assert envelope["outputs"]["result"]["state"] == "within_budget"
    assert Path(envelope["outputs"]["blend"]).is_file()

    refused = job_module.run_reduce({**request, "asset_class": "terrain"}, tmp_path / "job2")
    assert refused["ok"] is False
    assert refused["error"]["code"] == "reduce.class_unsupported"
    assert refused["outputs"] == {"result": {}, "blend": None}


def test_entry_script_runs_reduce_headless_and_writes_reduce_json(tmp_path: Path) -> None:
    build_high_poly("Crate", cuts=2)
    blend = tmp_path / "source.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend), copy=True)
    job = tmp_path / "job"
    job.mkdir()
    request = {
        "collection": "Crate",
        "asset_class": "standard_prop",
        "budgets_path": reduce_budgets_file(tmp_path),
        "device": "CPU",
        "cage_extrusion": None,
        "max_ray_distance": None,
        "miss_threshold": None,
        "parts": {},
    }
    (job / "request.json").write_text(json.dumps(request), encoding="utf-8")

    completed = subprocess.run(
        [
            bpy.app.binary_path,
            "--background",
            str(blend),
            "--python",
            str(ENTRY),
            "--",
            "reduce",
            "--job-dir",
            str(job),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
    )

    assert completed.returncode == 0, completed.stderr[-2000:]
    envelope = json.loads((job / "reduce.json").read_text(encoding="utf-8"))
    assert envelope["ok"] is True, envelope["error"]
    assert envelope["outputs"]["result"]["state"] == "within_budget"
    assert (job / "reduce.blend").is_file()
    assert "NMG_PROGRESS" in completed.stdout
