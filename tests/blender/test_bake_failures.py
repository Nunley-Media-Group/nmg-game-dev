"""Failure contract under Blender headless: AC6 (#67, SCN006).

Every unrepresentable input raises texture.bake_failed naming the target and reason, and the
original materials, UV maps, and render visibility are restored.

Run with scripts/run-blender-tests.sh. Under plain CPython the module is skipped.
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

bpy = pytest.importorskip("bpy")

from .bake_fixtures import (  # noqa: E402
    budgets_file,
    build_asset,
    build_failure,
    clear_scene,
    procedural_material,
)

_TARGETS = {
    "transparency": "M_Crate_Glass",
    "unsupported_shader": "M_Crate_Gloss",
    "emission": "M_Crate_Lamp",
    "volume_or_displacement": "M_Crate_Fog",
    "no_material": "SM_Crate",
    "uv_unwrap_failed": "SM_Crate",
}


@pytest.fixture(autouse=True)
def _isolated_scene() -> Iterator[None]:
    clear_scene()
    yield
    clear_scene()


@pytest.fixture()
def core(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.bake_core")


@pytest.fixture()
def budgets(tmp_path: Path) -> str:
    return budgets_file(tmp_path)


@pytest.mark.parametrize("reason", sorted(_TARGETS))
def test_ac6_each_reason_raises_bake_failed_naming_the_target(
    core: Any, tmp_path: Path, budgets: str, reason: str
) -> None:
    """AC6: each unrepresentable input raises texture.bake_failed with reason and target."""
    build_failure(reason)
    with pytest.raises(core.BakeError) as info:
        core.bake_asset("Crate", "standard_prop", tmp_path / "out", budgets, "CPU", 4)
    error = info.value
    assert error.code == "texture.bake_failed"
    assert error.reason == reason
    assert error.target == _TARGETS[reason]
    assert error.target in error.message
    assert error.remediation


def test_ac6_run_for_mcp_returns_the_error_dict(core: Any, tmp_path: Path, budgets: str) -> None:
    """AC5/AC6: run_for_mcp returns {"error": {...}} instead of raising."""
    build_failure("transparency")
    result = core.run_for_mcp(
        collection="Crate",
        asset_class="standard_prop",
        out_dir=str(tmp_path / "out"),
        budgets_path=budgets,
        device="CPU",
        samples=4,
    )
    assert set(result) == {"error"}
    assert result["error"]["code"] == "texture.bake_failed"
    assert result["error"]["reason"] == "transparency"
    assert result["error"]["target"] == "M_Crate_Glass"


def test_ac6_failure_after_mutation_restores_materials_uvs_and_visibility(
    enabled_addon: str, core: Any, tmp_path: Path, budgets: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC6: a failure after the file was changed restores the originals.

    Forces the proof gate to fail after rewiring, so the bake has already unwrapped, baked, and
    replaced the materials when it raises.
    """
    proof = importlib.import_module(f"{enabled_addon}.bake_core.proof")
    monkeypatch.setattr(proof, "within_tolerance", lambda metrics: False)
    overlapping = build_asset("Crate", [procedural_material("Authored")], packed=False)
    obj = overlapping.objects[0]
    uv_before = [tuple(item.uv) for item in obj.data.uv_layers["UVMap"].data]
    hidden_before = obj.hide_render
    sibling = bpy.data.objects.new("Set Dressing", bpy.data.meshes.new("Set Dressing"))
    bpy.context.scene.collection.objects.link(sibling)
    sibling_hidden = sibling.hide_render

    with pytest.raises(core.BakeError) as info:
        core.bake_asset("Crate", "standard_prop", tmp_path / "out", budgets, "CPU", 4)

    assert info.value.reason == "proof_mismatch"
    assert obj.data.materials[0].name == "Authored"
    assert "Authored_Authoring" not in bpy.data.materials
    assert "M_Crate_Body" not in bpy.data.materials
    assert [layer.name for layer in obj.data.uv_layers] == ["UVMap"]
    uv_after = [tuple(item.uv) for item in obj.data.uv_layers["UVMap"].data]
    assert uv_after == uv_before
    assert obj.hide_render == hidden_before
    assert sibling.hide_render == sibling_hidden
