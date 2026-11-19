"""Variant operators under Blender headless: AC1-AC8 and their BDD scenarios (SCN001-SCN008).

Run with scripts/run-blender-tests.sh. Under plain CPython the module is skipped.
"""

from __future__ import annotations

import importlib
import json
import socket
from pathlib import Path
from typing import Any

import pytest

bpy = pytest.importorskip("bpy")

_CATEGORY = "Props"
# Grid-filled cube from conftest.build_crate: 6 faces x 32 x 32 cells x 2 triangles.
CRATE_TRIS = 12 * 32 * 32


@pytest.fixture()
def core(enabled_addon: str):  # noqa: ANN201
    return importlib.import_module(f"{enabled_addon}.variants_core")


def _generate(export_root: Path, **overrides: Any) -> set[str]:
    arguments: dict[str, Any] = {
        "collection_name": "Crate",
        "category": _CATEGORY,
        "asset_class": "standard_prop",
        "export_root": str(export_root),
    }
    arguments.update(overrides)
    return bpy.ops.nmggamedev.generate_variants(**arguments)


def _last_result() -> dict[str, Any]:
    return json.loads(bpy.context.scene.nmg_game_dev.last_result)


def _triangles(mesh) -> int:  # noqa: ANN001
    return sum(max(len(polygon.vertices) - 2, 0) for polygon in mesh.polygons)


def _mobile_material_image_sizes() -> list[int]:
    sizes: list[int] = []
    for material in bpy.data.materials:
        if not material.name.endswith("_Mobile") or material.node_tree is None:
            continue
        for node in material.node_tree.nodes:
            if node.type == "TEX_IMAGE" and node.image is not None:
                sizes.append(max(node.image.size))
    return sizes


def _variant_root(export_root: Path) -> Path:
    return export_root / _CATEGORY / "Crate"


# ---------------------------------------------------------------------------
# AC1 / SCN001: separate variants with identical names
# ---------------------------------------------------------------------------


def test_ac1_variants_export_with_identical_names(build_crate, reset_scene, tmp_path: Path) -> None:  # noqa: ANN001
    build_crate()
    assert _generate(tmp_path) == {"FINISHED"}

    for variant in ("Desktop", "Mobile"):
        folder = _variant_root(tmp_path) / variant
        assert (folder / "Crate.glb").is_file()
        for suffix in ("BC", "N", "ORM"):
            assert (folder / f"T_Crate_Body_{suffix}.png").is_file()
    assert list(tmp_path.rglob("*.fbx")) == []
    assert [path for path in tmp_path.rglob("*") if "_LOD" in path.name] == []

    for variant in ("Desktop", "Mobile"):
        reset_scene()
        bpy.ops.import_scene.gltf(filepath=str(_variant_root(tmp_path) / variant / "Crate.glb"))
        object_names = {obj.name for obj in bpy.data.objects}
        material_names = {material.name for material in bpy.data.materials}
        image_names = {image.name for image in bpy.data.images}
        assert "SM_Crate" in object_names, f"{variant}: {sorted(object_names)}"
        assert "M_Crate_Body" in material_names, f"{variant}: {sorted(material_names)}"
        leaked = {name for name in object_names | material_names | image_names if "_Mobile" in name}
        assert not leaked, f"{variant} export leaked _Mobile names: {sorted(leaked)}"


# ---------------------------------------------------------------------------
# AC2 / SCN002: Desktop cleanup preserves quality
# ---------------------------------------------------------------------------


def test_ac2_cleanup_removes_only_degenerate_geometry(build_crate) -> None:  # noqa: ANN001
    build_crate()
    assert bpy.ops.nmggamedev.cleanup_desktop(collection_name="Crate") == {"FINISHED"}

    report = _last_result()
    assert report["tris_before"] == CRATE_TRIS + 1  # the injected zero-area face
    assert report["tris_after"] == CRATE_TRIS, "no decimation: only the zero-area face goes"

    mesh = bpy.data.objects["SM_Crate"].data
    used_vertices: set[int] = set()
    for edge in mesh.edges:
        used_vertices.update(edge.vertices)
    assert len(used_vertices) == len(mesh.vertices), "loose or duplicate vertices remain"
    assert all(polygon.area > 1e-10 for polygon in mesh.polygons), "zero-area face remains"
    assert all(polygon.normal.dot(polygon.center) > 0 for polygon in mesh.polygons), (
        "normals point inward on part of the mesh"
    )
    assert all(
        tuple(image.size) == (2048, 2048)
        for image in bpy.data.images
        if image.name.startswith("T_Crate")
    )


# ---------------------------------------------------------------------------
# AC3 / SCN003: Mobile decimated to budget as one mesh (the engine generates LODs on import)
# ---------------------------------------------------------------------------


def test_ac3_mobile_is_decimated_to_budget_without_lod_meshes(build_crate) -> None:  # noqa: ANN001
    build_crate()
    assert bpy.ops.nmggamedev.cleanup_desktop(collection_name="Crate") == {"FINISHED"}
    assert bpy.ops.nmggamedev.optimize_mobile(
        collection_name="Crate", asset_class="standard_prop"
    ) == {"FINISHED"}

    mobile = bpy.data.objects["SM_Crate_Mobile"]
    assert mobile.type == "MESH"
    assert [obj.name for obj in bpy.data.collections["Crate_Mobile"].all_objects] == [
        "SM_Crate_Mobile"
    ]
    assert not [obj for obj in bpy.data.objects if "_LOD" in obj.name]
    tris = _triangles(mobile.data)
    assert 0 < tris <= 3000
    assert _last_result()["tris"] == tris
    assert _mobile_material_image_sizes() and max(_mobile_material_image_sizes()) == 1024


# ---------------------------------------------------------------------------
# AC4 / SCN004: sidecars record metrics and budget settings
# ---------------------------------------------------------------------------


def test_ac4_sidecars_and_result_keys(build_crate, tmp_path: Path) -> None:  # noqa: ANN001
    build_crate()
    assert _generate(tmp_path) == {"FINISHED"}

    root = _variant_root(tmp_path)
    variants = json.loads((root / "nmg-variants.json").read_text(encoding="utf-8"))
    assert variants["class"] == "standard_prop"
    assert variants["budget"] == {"tris": 3000, "max_texture_px": 1024, "materials": 1}
    assert variants["desktop"]["glb"] == "Desktop/Crate.glb"
    assert variants["desktop"]["max_texture_px"] == 2048
    assert variants["mobile"]["glb"] == "Mobile/Crate.glb"
    assert "lod_tris" not in variants["mobile"]
    assert "meshes" not in variants["mobile"]
    assert variants["mobile"]["texture_bytes"] > 0
    assert variants["desktop"]["texture_bytes"] > 0

    for variant, max_px in (("Desktop", 2048), ("Mobile", 1024)):
        asset = json.loads((root / variant / "nmg-asset.json").read_text(encoding="utf-8"))
        tris = variants[variant.lower()]["tris"]
        assert set(asset) == {"class", "tris", "max_texture_px", "materials", "meshes"}
        assert asset["class"] == "standard_prop"
        assert asset["tris"] == tris
        assert asset["max_texture_px"] == max_px
        assert asset["materials"] == 1
        (mesh,) = asset["meshes"]
        assert mesh["name"] == "SM_Crate"
        assert mesh["tris"] == tris
        assert mesh["material_slots"] == 1
        assert set(mesh["bounds"]) == {"min", "max"}

    result = _last_result()
    for key in (
        "desktop_path",
        "mobile_path",
        "poly_count_desktop",
        "poly_count_mobile",
        "texture_bytes_desktop",
        "texture_bytes_mobile",
    ):
        assert key in result, key
    assert result["poly_count_mobile"] == variants["mobile"]["tris"]


# ---------------------------------------------------------------------------
# AC5 / SCN005: results are deterministic
# ---------------------------------------------------------------------------


def test_ac5_two_runs_produce_identical_sidecars(build_crate, tmp_path: Path) -> None:  # noqa: ANN001
    first_root, second_root = tmp_path / "first", tmp_path / "second"

    build_crate()
    assert _generate(first_root) == {"FINISHED"}
    first = (_variant_root(first_root) / "nmg-variants.json").read_text(encoding="utf-8")

    build_crate()
    assert _generate(second_root) == {"FINISHED"}
    second = (_variant_root(second_root) / "nmg-variants.json").read_text(encoding="utf-8")

    assert first == second


# ---------------------------------------------------------------------------
# AC6 / SCN006: budget overrides apply
# ---------------------------------------------------------------------------


def test_ac6_budget_override_raises_the_mobile_limit(build_crate, tmp_path: Path) -> None:  # noqa: ANN001
    build_crate()
    assert bpy.ops.nmggamedev.cleanup_desktop(collection_name="Crate") == {"FINISHED"}

    budgets = tmp_path / "nmg-budgets.json"
    budgets.write_text(json.dumps({"standard_prop": {"tris": 5000}}), encoding="utf-8")
    assert bpy.ops.nmggamedev.optimize_mobile(
        collection_name="Crate", asset_class="standard_prop", budgets_path=str(budgets)
    ) == {"FINISHED"}

    result = _last_result()
    assert result["budget"]["tris"] == 5000
    tris = result["tris"]
    assert 3000 < tris <= 5000, f"Mobile should use the 5000 budget, got {tris}"


# ---------------------------------------------------------------------------
# AC7 / SCN007: unsupported inputs fail with a remediation and write nothing
# ---------------------------------------------------------------------------


def test_ac7_unbaked_material_fails_before_any_write(build_crate, core, tmp_path: Path) -> None:  # noqa: ANN001
    build_crate("unbaked")
    with pytest.raises(core.VariantError) as info:
        core.generate_variants("Crate", _CATEGORY, "standard_prop", str(tmp_path))

    assert info.value.code == "variants.unbaked_material"
    assert "M_Crate_Body" in info.value.message
    assert info.value.remediation
    assert list(tmp_path.rglob("*.glb")) == []
    assert list(tmp_path.rglob("*.json")) == []
    assert _triangles(bpy.data.objects["SM_Crate"].data) == CRATE_TRIS + 1, "cleanup must not run"

    with pytest.raises(RuntimeError, match="variants.unbaked_material"):
        _generate(tmp_path)
    assert list(tmp_path.rglob("*.glb")) == []


def test_ac7_too_many_materials_for_the_class(build_crate, core, tmp_path: Path) -> None:  # noqa: ANN001
    build_crate("two")
    with pytest.raises(core.VariantError) as info:
        core.generate_variants("Crate", _CATEGORY, "standard_prop", str(tmp_path))
    assert info.value.code == "variants.mobile_material_limit"
    assert list(tmp_path.rglob("*.glb")) == []


def test_ac7_missing_asset_is_reported(reset_scene, core, tmp_path: Path) -> None:  # noqa: ANN001
    reset_scene()
    with pytest.raises(core.VariantError) as info:
        core.generate_variants("Crate", _CATEGORY, "standard_prop", str(tmp_path))
    assert info.value.code == "variants.asset_not_found"
    assert "SM_Crate" in info.value.message


# ---------------------------------------------------------------------------
# AC8 / SCN008: processing is local
# ---------------------------------------------------------------------------


def test_ac8_generate_completes_with_sockets_blocked(
    build_crate, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # noqa: ANN001
    build_crate()

    def _blocked(*args: object, **kwargs: object) -> None:
        raise OSError("network sockets are blocked for this test")

    monkeypatch.setattr(socket, "socket", _blocked)
    assert _generate(tmp_path) == {"FINISHED"}


# ---------------------------------------------------------------------------
# Child parts are fitted together and keep their names
# ---------------------------------------------------------------------------


def test_child_parts_are_fitted_together_under_their_names(build_crate) -> None:  # noqa: ANN001
    build_crate(parts=True)
    assert bpy.ops.nmggamedev.cleanup_desktop(collection_name="Crate") == {"FINISHED"}
    assert bpy.ops.nmggamedev.optimize_mobile(
        collection_name="Crate", asset_class="standard_prop"
    ) == {"FINISHED"}

    result = _last_result()
    assert result["tris"] <= result["budget"]["tris"]
    assert bpy.data.objects["SM_Crate_Mobile"].type == "MESH"
    assert "SM_Crate_Trim_Mobile" in bpy.data.objects
    assert "SM_Crate_Mobile" in bpy.data.objects


def test_issue142_mesh_datablocks_export_under_their_object_names(
    build_crate, reset_scene, tmp_path: Path
) -> None:  # noqa: ANN001
    """#142 AC4: a part whose mesh data is SM_Crate_Trim.001 exports with its object's name, and
    the session's object and mesh names are the same after the export as before it."""
    build_crate(parts=True)
    bpy.data.objects["SM_Crate_Trim"].data.name = "SM_Crate_Trim.001"
    session_before = {obj.name: obj.data.name for obj in bpy.data.objects if obj.type == "MESH"}

    assert _generate(tmp_path) == {"FINISHED"}

    session_after = {name: bpy.data.objects[name].data.name for name in session_before}
    assert session_after == session_before
    for variant in ("Desktop", "Mobile"):
        reset_scene()
        bpy.ops.import_scene.gltf(filepath=str(_variant_root(tmp_path) / variant / "Crate.glb"))
        meshes = [obj for obj in bpy.data.objects if obj.type == "MESH"]
        assert "SM_Crate_Trim" in {obj.name for obj in meshes}, f"{variant}: {meshes}"
        for obj in meshes:
            assert obj.data.name == obj.name, f"{variant}: {obj.name} carries {obj.data.name}"


# ---------------------------------------------------------------------------
# #249: nmg-asset.json meshes match the written GLB (names, triangles, surfaces, engine bounds)
# ---------------------------------------------------------------------------


def test_asset_sidecar_meshes_match_the_written_glb(
    build_crate, reset_scene, tmp_path: Path
) -> None:  # noqa: ANN001
    build_crate(parts=True)
    assert _generate(tmp_path) == {"FINISHED"}

    for variant in ("Desktop", "Mobile"):
        folder = _variant_root(tmp_path) / variant
        asset = json.loads((folder / "nmg-asset.json").read_text(encoding="utf-8"))
        recorded = {mesh["name"]: mesh for mesh in asset["meshes"]}
        assert sorted(recorded) == ["SM_Crate", "SM_Crate_Trim"], variant
        assert sum(mesh["tris"] for mesh in recorded.values()) == asset["tris"]

        reset_scene()
        bpy.ops.import_scene.gltf(filepath=str(folder / "Crate.glb"))
        imported = {obj.name: obj for obj in bpy.data.objects if obj.type == "MESH"}
        assert sorted(imported) == sorted(recorded), variant
        for name, obj in imported.items():
            entry = recorded[name]
            assert entry["tris"] == _triangles(obj.data), name
            used = {polygon.material_index for polygon in obj.data.polygons}
            assert entry["material_slots"] == len(used), name
            corners = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
            # Blender (x, y, z) is engine (x, z, -y).
            low = [
                min(c.x for c in corners),
                min(c.z for c in corners),
                -max(c.y for c in corners),
            ]
            high = [
                max(c.x for c in corners),
                max(c.z for c in corners),
                -min(c.y for c in corners),
            ]
            assert entry["bounds"]["min"] == pytest.approx(low, abs=1e-4), name
            assert entry["bounds"]["max"] == pytest.approx(high, abs=1e-4), name
        lowest = min(mesh["bounds"]["min"][1] for mesh in recorded.values())
        if variant == "Mobile":
            assert lowest == pytest.approx(0.0, abs=1e-4), "the Mobile bottom sits on the origin"
