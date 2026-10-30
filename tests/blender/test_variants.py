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
        assert (folder / "SM_Crate.fbx").is_file()
        for suffix in ("BC", "N", "ORM"):
            assert (folder / f"T_Crate_Body_{suffix}.png").is_file()

    for variant in ("Desktop", "Mobile"):
        reset_scene()
        bpy.ops.import_scene.fbx(filepath=str(_variant_root(tmp_path) / variant / "SM_Crate.fbx"))
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
# AC3 / SCN003: Mobile decimated to budget with two LODs
# ---------------------------------------------------------------------------


def test_ac3_mobile_is_decimated_with_two_lods(build_crate) -> None:  # noqa: ANN001
    build_crate()
    assert bpy.ops.nmggamedev.cleanup_desktop(collection_name="Crate") == {"FINISHED"}
    assert bpy.ops.nmggamedev.optimize_mobile(
        collection_name="Crate", asset_class="standard_prop"
    ) == {"FINISHED"}

    group = bpy.data.objects["SM_Crate_Mobile"]
    assert group.type == "EMPTY"
    assert group["fbx_type"] == "LodGroup"
    lod0, lod1, lod2 = (
        _triangles(bpy.data.objects[f"SM_Crate_Mobile_LOD{level}"].data) for level in range(3)
    )
    assert lod0 <= 3000
    assert lod1 <= 0.5 * lod0
    assert lod2 <= 0.25 * lod0
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
    assert variants["desktop"]["fbx"] == "Desktop/SM_Crate.fbx"
    assert variants["desktop"]["max_texture_px"] == 2048
    assert variants["mobile"]["fbx"] == "Mobile/SM_Crate.fbx"
    assert variants["mobile"]["lod_levels"] == 3
    assert len(variants["mobile"]["lod_tris"]) == 3
    assert variants["mobile"]["texture_bytes"] > 0
    assert variants["desktop"]["texture_bytes"] > 0

    asset = json.loads((root / "Mobile" / "nmg-asset.json").read_text(encoding="utf-8"))
    assert asset == {
        "class": "standard_prop",
        "tris": variants["mobile"]["lod_tris"][0],
        "max_texture_px": 1024,
        "materials": 1,
    }

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
    assert result["poly_count_mobile"] == asset["tris"]


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


def test_ac6_budget_override_raises_lod0_limit(build_crate, tmp_path: Path) -> None:  # noqa: ANN001
    build_crate()
    assert bpy.ops.nmggamedev.cleanup_desktop(collection_name="Crate") == {"FINISHED"}

    budgets = tmp_path / "nmg-budgets.json"
    budgets.write_text(json.dumps({"standard_prop": {"tris": 5000}}), encoding="utf-8")
    assert bpy.ops.nmggamedev.optimize_mobile(
        collection_name="Crate", asset_class="standard_prop", budgets_path=str(budgets)
    ) == {"FINISHED"}

    result = _last_result()
    assert result["budget"]["tris"] == 5000
    lod0 = result["lod_tris"][0]
    assert 3000 < lod0 <= 5000, f"LOD0 should use the 5000 budget, got {lod0}"


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
    assert list(tmp_path.rglob("*.fbx")) == []
    assert list(tmp_path.rglob("*.json")) == []
    assert _triangles(bpy.data.objects["SM_Crate"].data) == CRATE_TRIS + 1, "cleanup must not run"

    with pytest.raises(RuntimeError, match="variants.unbaked_material"):
        _generate(tmp_path)
    assert list(tmp_path.rglob("*.fbx")) == []


def test_ac7_too_many_materials_for_the_class(build_crate, core, tmp_path: Path) -> None:  # noqa: ANN001
    build_crate("two")
    with pytest.raises(core.VariantError) as info:
        core.generate_variants("Crate", _CATEGORY, "standard_prop", str(tmp_path))
    assert info.value.code == "variants.mobile_material_limit"
    assert list(tmp_path.rglob("*.fbx")) == []


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
# Child parts keep one LOD level (FR3: LOD0 only for assets with child parts)
# ---------------------------------------------------------------------------


def test_child_parts_export_as_single_lod_level(build_crate) -> None:  # noqa: ANN001
    build_crate(parts=True)
    assert bpy.ops.nmggamedev.cleanup_desktop(collection_name="Crate") == {"FINISHED"}
    assert bpy.ops.nmggamedev.optimize_mobile(
        collection_name="Crate", asset_class="standard_prop"
    ) == {"FINISHED"}

    result = _last_result()
    assert result["lod_levels"] == 1
    assert bpy.data.objects["SM_Crate_Mobile"].type == "MESH"
    assert "SM_Crate_Trim_Mobile" in bpy.data.objects
    assert "SM_Crate_Mobile" in bpy.data.objects
