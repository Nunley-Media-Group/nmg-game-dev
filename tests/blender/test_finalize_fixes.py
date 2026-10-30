"""Regression tests for three defects the finalize chain exposed (#69).

- validate with ``authored=True`` defers the material rules that only a bake satisfies, and the
  full contract still reports them (so the export gate enforces them after the bake).
- A scaled mobile texture copy survives a save and reload at its scaled size with its pixels.
- A mesh snapshot carries the object-local bounds that the UE pivot check compares against.

Run with scripts/run-blender-tests.sh.  Under plain CPython the module is skipped.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest

bpy = pytest.importorskip("bpy")

from .bake_fixtures import build_asset, procedural_material  # noqa: E402
from .contract_fixtures import clear_scene  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_scene(enabled_addon: str) -> Any:  # noqa: ARG001 - ordering dependency
    clear_scene()
    yield
    clear_scene()


@pytest.fixture()
def core(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.contract_core")


@pytest.fixture()
def validate_module(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.contract_core.validate")


@pytest.fixture()
def variants_textures(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.variants_core.textures")


def test_authored_validation_defers_material_rules_but_full_validation_reports_them(
    core: Any,
) -> None:
    # A procedural material is not an export-ready material, so the full contract flags it.
    build_asset("Crate", [procedural_material("Authored")])

    full = core.validate_asset("Crate", "standard_prop")
    authored = core.validate_asset("Crate", "standard_prop", authored=True)

    full_rules = {finding["rule"] for finding in full["findings"]}
    authored_rules = {finding["rule"] for finding in authored["findings"]}
    assert any(rule.startswith("material.") for rule in full_rules)
    assert not any(rule.startswith("material.") for rule in authored_rules)
    assert not any(rule.startswith("naming.material") for rule in authored_rules)


def test_mobile_copy_keeps_its_scaled_size_and_pixels_through_a_reload(
    variants_textures: Any, tmp_path: Path
) -> None:
    source = bpy.data.images.new("T_Crate_Body_BC", width=256, height=256, alpha=True)
    source.generated_color = (0.2, 0.4, 0.6, 1.0)
    copy = variants_textures.mobile_image_copy(source, 128)
    assert tuple(copy.size) == (128, 128)

    # Blender drops unreferenced datablocks on save, so a material uses the copy, as variants do.
    material = bpy.data.materials.new("M_Mobile_Probe")
    material.use_nodes = True
    material.node_tree.nodes.new("ShaderNodeTexImage").image = copy
    name = copy.name
    path = tmp_path / "variant.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(path))
    bpy.ops.wm.open_mainfile(filepath=str(path))

    reloaded = bpy.data.images[name]
    assert tuple(reloaded.size) == (128, 128)
    assert reloaded.packed_file is not None
    assert any(value > 0.0 for value in reloaded.pixels)


def test_mesh_snapshot_carries_object_local_bounds_in_meters(validate_module: Any) -> None:
    collection = build_asset("Crate", [procedural_material("Authored")])
    obj = collection.objects["SM_Crate"]

    snapshot = validate_module.object_snapshot(obj, "desktop", 12)

    corners = [tuple(corner) for corner in obj.bound_box]
    low = [min(corner[axis] for corner in corners) for axis in range(3)]
    high = [max(corner[axis] for corner in corners) for axis in range(3)]
    assert snapshot["local_bounds"]["min"] == pytest.approx(low, abs=1e-6)
    assert snapshot["local_bounds"]["max"] == pytest.approx(high, abs=1e-6)
