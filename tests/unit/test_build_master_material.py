"""Regression tests for the M_NmgORM master-material builder (#101).

Covers AC1-AC3 and FR1-FR3 of specs/101-*/requirements.md. The graph code in ``_MATERIAL_CODE``
runs inside the UE editor, so these tests read it as an AST and check the committed
``M_NmgORM.uasset`` bytes instead of executing it. The BDD bindings in
``tests/bdd/test_master_material_bdd.py`` reuse the helpers defined here.
"""

from __future__ import annotations

import ast
import importlib.util
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILDER_PATH = REPO_ROOT / "scripts" / "unreal" / "build_master_material.py"
SHIPPED_ASSET = (
    REPO_ROOT / "plugins" / "nmg-game-dev-ue-plugin" / "Content" / "Materials" / "M_NmgORM.uasset"
)

COLOR_DEFAULT = "/Engine/EngineResources/DefaultTexture"
NORMAL_DEFAULT = "/Engine/EngineMaterials/DefaultNormal"
MASKS_DEFAULT = "/Engine/EngineMaterials/DefaultDiffuse_TC_Masks"


def load_builder() -> ModuleType:
    spec = importlib.util.spec_from_file_location("build_master_material", BUILDER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def builder_tree() -> ast.Module:
    """AST of the UE-side graph code the builder sends through execute_python_code."""
    source: str = load_builder()._MATERIAL_CODE
    return ast.parse(source)


def function(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"M_NmgORM code has no function {name}")


def calls(nodes: ast.AST | list[ast.stmt], callee: str) -> list[ast.Call]:
    """Calls under ``nodes`` whose callee text ends with ``callee``, in source order."""
    roots = nodes if isinstance(nodes, list) else [nodes]
    found = [
        node
        for root in roots
        for node in ast.walk(root)
        if isinstance(node, ast.Call) and ast.unparse(node.func).endswith(callee)
    ]
    return sorted(found, key=lambda call: (call.lineno, call.col_offset))


def _const(node: ast.expr) -> Any:
    return node.value if isinstance(node, ast.Constant) else None


def index_of(body: list[ast.stmt], predicate: Callable[[ast.stmt], bool]) -> int:
    for index, statement in enumerate(body):
        if predicate(statement):
            return index
    return -1


def sampler_defaults(tree: ast.Module) -> dict[str, tuple[str, str | None]]:
    """Map each sampler parameter to (sampler type, default texture) as ``_build`` passes them."""
    defaults: dict[str, tuple[str, str | None]] = {}
    for call in calls(function(tree, "_build"), "_sampler"):
        parameter = _const(call.args[1])
        sampler_type = ast.unparse(call.args[3])
        default = _const(call.args[4]) if len(call.args) > 4 else None
        defaults[parameter] = (sampler_type, default)
    return defaults


def sampler_sets_texture(tree: ast.Module) -> bool:
    """True when ``_sampler`` sets the texture and names the path when it will not load."""
    sampler = function(tree, "_sampler")
    properties = {
        _const(call.args[0]) for call in calls(sampler, "set_editor_property") if call.args
    }
    return (
        "texture" in properties
        and bool(calls(sampler, "load_asset"))
        and "could not load default texture " in ast.unparse(sampler)
    )


def _sets_skeletal_flag(statement: ast.stmt) -> bool:
    return any(
        len(call.args) == 2
        and _const(call.args[0]) == "used_with_skeletal_mesh"
        and _const(call.args[1]) is True
        for call in calls(statement, "set_editor_property")
    )


def skeletal_flag_before_recompile(tree: ast.Module) -> bool:
    body = function(tree, "_build").body
    flag = index_of(body, _sets_skeletal_flag)
    recompile = index_of(body, lambda statement: bool(calls(statement, "recompile_material")))
    return flag != -1 and recompile != -1 and flag < recompile


def channel_wiring(tree: ast.Module) -> list[tuple[str, str, str]]:
    """(sampler variable, source channel, material property) for each connection in ``_build``."""
    return [
        (ast.unparse(call.args[0]), _const(call.args[1]), ast.unparse(call.args[2]))
        for call in calls(function(tree, "_build"), "connect_material_property")
    ]


def rebuild_clears_in_place(tree: ast.Module) -> bool:
    """True when an existing M_NmgORM is loaded and cleared, and only a missing one is created."""
    run = function(tree, "_run")
    branches = [node for node in run.body if isinstance(node, ast.If)]
    if not branches:
        return False
    branch = branches[0]
    return bool(
        calls(branch.test, "does_asset_exist")
        and calls(branch.body, "load_asset")
        and calls(branch.body, "_clear")
        and not calls(branch.body, "create_asset")
        and calls(branch.orelse, "create_asset")
        and not calls(tree, "delete_asset")
        and not calls(tree, "delete_loaded_asset")
    )


def shipped_asset_bytes() -> bytes:
    return SHIPPED_ASSET.read_bytes()


def test_each_sampler_defaults_to_a_texture_of_its_sampler_type() -> None:
    assert sampler_defaults(builder_tree()) == {
        "BaseColor": ("unreal.MaterialSamplerType.SAMPLERTYPE_COLOR", COLOR_DEFAULT),
        "Normal": ("unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL", NORMAL_DEFAULT),
        "ORM": ("unreal.MaterialSamplerType.SAMPLERTYPE_MASKS", MASKS_DEFAULT),
    }


def test_sampler_sets_its_texture_and_names_the_path_when_the_default_does_not_load() -> None:
    assert sampler_sets_texture(builder_tree())


def test_skeletal_mesh_usage_is_enabled_before_recompile() -> None:
    assert skeletal_flag_before_recompile(builder_tree())


def test_channel_wiring_and_parameter_names_are_unchanged() -> None:
    assert channel_wiring(builder_tree()) == [
        ("base", "RGB", "unreal.MaterialProperty.MP_BASE_COLOR"),
        ("normal", "RGB", "unreal.MaterialProperty.MP_NORMAL"),
        ("orm", "R", "unreal.MaterialProperty.MP_AMBIENT_OCCLUSION"),
        ("orm", "G", "unreal.MaterialProperty.MP_ROUGHNESS"),
        ("orm", "B", "unreal.MaterialProperty.MP_METALLIC"),
    ]


def test_rebuild_loads_and_clears_the_existing_material_instead_of_recreating_it() -> None:
    assert rebuild_clears_in_place(builder_tree())


def test_shipped_asset_references_default_textures_and_skeletal_usage() -> None:
    data = shipped_asset_bytes()
    for needle in (NORMAL_DEFAULT, MASKS_DEFAULT, "bUsedWithSkeletalMesh"):
        assert needle.encode() in data, f"{needle} missing from M_NmgORM.uasset"
