"""Regression tests for the M_NmgORM master-material builder (#101).

Covers AC1-AC3 and FR1-FR3 of specs/101-*/requirements.md. The graph code in ``_MATERIAL_CODE``
runs inside the UE editor, so these tests read it as an AST and check the committed
``M_NmgORM.uasset`` bytes instead of executing it. The BDD bindings in
``tests/bdd/test_master_material_bdd.py`` reuse the helpers defined here.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

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


def test_normal_and_orm_wiring_is_unchanged_and_base_color_is_the_tinted_product() -> None:
    # Base Color now comes from the Multiply node (#148, FR6), so the BaseColor sampler feeds that
    # node instead of Base Color directly. Normal and ORM keep their channels.
    assert channel_wiring(builder_tree()) == [
        ("tinted", "", "unreal.MaterialProperty.MP_BASE_COLOR"),
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


# --- the builder's UE code, run against an in-memory fake `unreal` module (#148) ---------------

MASTER_PARAMETERS_PATH = (
    REPO_ROOT / "plugins" / "nmg-game-dev-blender-addon" / "utils" / "master_material.py"
)
VECTOR_EXPRESSION = "unreal.MaterialExpressionVectorParameter"
MULTIPLY_EXPRESSION = "unreal.MaterialExpressionMultiply"


class _Namespace:
    """Enum-like namespace whose attributes are their dotted names, as the builder reads them."""

    def __init__(self, prefix: str) -> None:
        self._prefix = prefix

    def __getattr__(self, name: str) -> str:
        return f"{self._prefix}.{name}"


class _Node:
    """A material expression the builder created, with the properties the builder set."""

    def __init__(self, kind: str) -> None:
        self.kind = kind
        self.properties: dict[str, Any] = {}

    def set_editor_property(self, name: str, value: Any) -> None:
        self.properties[name] = value


class _Record:
    """What the builder created and connected. Connections are (source, output, target, input)."""

    def __init__(self) -> None:
        self.nodes: list[_Node] = []
        self.connections: list[tuple[Any, str, Any, Any]] = []


class _Color:
    def __init__(self, r: float, g: float, b: float, a: float) -> None:
        self.values = (r, g, b, a)


def _fake_unreal(record: _Record) -> ModuleType:
    module = ModuleType("unreal")

    class Texture:
        pass

    class Material:
        def __init__(self, name: str) -> None:
            self.name = name

        def set_editor_property(self, name: str, value: Any) -> None:
            _ = (name, value)

    class MaterialEditingLibrary:
        @staticmethod
        def create_material_expression(material: Any, kind: str, x: float, y: float) -> _Node:
            _ = (material, x, y)
            node = _Node(kind)
            record.nodes.append(node)
            return node

        @staticmethod
        def connect_material_expressions(source: Any, output: str, target: Any, pin: str) -> None:
            record.connections.append((source, output, target, pin))

        @staticmethod
        def connect_material_property(source: Any, output: str, prop: str) -> None:
            record.connections.append((source, output, None, prop))

        @staticmethod
        def recompile_material(material: Any) -> None:
            _ = material

    class EditorAssetLibrary:
        @staticmethod
        def does_asset_exist(path: str) -> bool:
            _ = path
            return False

        @staticmethod
        def load_asset(path: str) -> Any:
            return Texture() if path.startswith("/Engine/") else None

        @staticmethod
        def save_loaded_asset(asset: Any) -> None:
            _ = asset

    class _AssetTools:
        @staticmethod
        def create_asset(name: str, package: str, kind: Any, factory: Any) -> Material:
            _ = (package, kind, factory)
            return Material(name)

    class AssetToolsHelpers:
        @staticmethod
        def get_asset_tools() -> _AssetTools:
            return _AssetTools()

    class LinearColor(_Color):
        pass

    module.Texture = Texture  # type: ignore[attr-defined]
    module.Material = Material  # type: ignore[attr-defined]
    module.MaterialEditingLibrary = MaterialEditingLibrary  # type: ignore[attr-defined]
    module.EditorAssetLibrary = EditorAssetLibrary  # type: ignore[attr-defined]
    module.AssetToolsHelpers = AssetToolsHelpers  # type: ignore[attr-defined]
    module.LinearColor = LinearColor  # type: ignore[attr-defined]
    module.MaterialSamplerType = _Namespace("unreal.MaterialSamplerType")  # type: ignore[attr-defined]
    module.MaterialProperty = _Namespace("unreal.MaterialProperty")  # type: ignore[attr-defined]
    # Every other unreal.<Name> the builder reads (expression classes) is its own name. The factory
    # is called, so it is a callable that returns a placeholder.
    module.__dict__["MaterialFactoryNew"] = lambda: "unreal.MaterialFactoryNew()"
    module.__dict__["__getattr__"] = lambda name: f"unreal.{name}"
    return module


def load_master_parameters() -> dict[str, str]:
    spec = importlib.util.spec_from_file_location("master_material_table", MASTER_PARAMETERS_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    table: dict[str, str] = module.MASTER_PARAMETERS
    return table


def run_builder_under_fake_unreal(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> tuple[dict[str, Any], _Record]:
    record = _Record()
    monkeypatch.setitem(sys.modules, "unreal", _fake_unreal(record))
    exec(  # noqa: S102 - the builder's own UE code, run against the fake module
        compile(load_builder()._MATERIAL_CODE, "<M_NmgORM builder>", "exec"),
        {"__name__": "m_nmg_orm_builder"},
    )
    printed = capsys.readouterr().out
    line = next(line for line in printed.splitlines() if line.startswith("NMG_RESULT "))
    result: dict[str, Any] = json.loads(line[len("NMG_RESULT ") :])
    return result, record


def _by_parameter(record: _Record, parameter: str) -> _Node:
    return next(node for node in record.nodes if node.properties.get("parameter_name") == parameter)


def _of_kind(record: _Record, kind: str) -> list[_Node]:
    return [node for node in record.nodes if node.kind == kind]


def test_builder_code_runs_under_the_fake_unreal_and_reports_success(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    result, _record = run_builder_under_fake_unreal(monkeypatch, capsys)

    assert result == {"ok": True, "asset": "/nmg-game-dev/Materials/M_NmgORM", "error": None}


def test_tint_is_the_vector_parameter_with_a_white_default(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _result, record = run_builder_under_fake_unreal(monkeypatch, capsys)

    tints = _of_kind(record, VECTOR_EXPRESSION)
    assert [node.properties["parameter_name"] for node in tints] == ["Tint"]
    assert tints[0].properties["default_value"].values == (1.0, 1.0, 1.0, 1.0)


def test_master_parameter_table_matches_the_vector_parameters_the_builder_creates(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _result, record = run_builder_under_fake_unreal(monkeypatch, capsys)

    recorded = {node.properties["parameter_name"] for node in _of_kind(record, VECTOR_EXPRESSION)}
    declared = {name for name, kind in load_master_parameters().items() if kind == "vector"}
    assert recorded == declared == {"Tint"}


def test_base_color_is_the_base_color_sampler_times_tint(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _result, record = run_builder_under_fake_unreal(monkeypatch, capsys)

    base = _by_parameter(record, "BaseColor")
    tint = _of_kind(record, VECTOR_EXPRESSION)[0]
    products = _of_kind(record, MULTIPLY_EXPRESSION)
    assert len(products) == 1
    product = products[0]
    assert (base, "RGB", product, "A") in record.connections
    assert (tint, "", product, "B") in record.connections
    assert (product, "", None, "unreal.MaterialProperty.MP_BASE_COLOR") in record.connections
    assert (base, "RGB", None, "unreal.MaterialProperty.MP_BASE_COLOR") not in record.connections


def test_normal_and_orm_channels_still_feed_their_material_properties(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _result, record = run_builder_under_fake_unreal(monkeypatch, capsys)

    normal = _by_parameter(record, "Normal")
    orm = _by_parameter(record, "ORM")
    assert (normal, "RGB", None, "unreal.MaterialProperty.MP_NORMAL") in record.connections
    assert (orm, "R", None, "unreal.MaterialProperty.MP_AMBIENT_OCCLUSION") in record.connections
    assert (orm, "G", None, "unreal.MaterialProperty.MP_ROUGHNESS") in record.connections
    assert (orm, "B", None, "unreal.MaterialProperty.MP_METALLIC") in record.connections
