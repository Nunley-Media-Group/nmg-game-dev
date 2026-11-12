"""Regression tests for the M_NmgORM master-material builder (#101) and its headless rebuild (#204).

Covers AC1-AC3 and FR1-FR3 of specs/101-*/requirements.md, and AC1-AC3 and FR1-FR4 of
specs/204-*/requirements.md. The graph code in ``_MATERIAL_CODE`` runs inside the UE editor, so
these tests read it as an AST and check the committed ``M_NmgORM.uasset`` bytes instead of
executing it. The headless tests run the builder against fake ``Build.sh`` and
``UnrealEditor-Cmd`` stubs, never a real engine. The BDD bindings in
``tests/bdd/test_master_material_bdd.py`` reuse the helpers here.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import socket
import struct
import sys
from collections.abc import Callable
from dataclasses import dataclass
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


# --- the headless rebuild (#204): fake Build.sh and UnrealEditor-Cmd, no real engine -------------

DOGFOOD_PROJECT = REPO_ROOT / "fixtures" / "dogfood.uproject"
SUCCESS_LINE = (
    'LogPython: NMG_RESULT {"asset": "/nmg-game-dev/Materials/M_NmgORM", "error": null, "ok": true}'
)
FAILURE_LINE = (
    'LogPython: NMG_RESULT {"ok": false, "error": "RuntimeError: x", '
    '"asset": "/nmg-game-dev/Materials/M_NmgORM"}'
)
# Each stub is a POSIX shell script that records its argv, one argument per line.
_BUILD_STUB = r"""printf '%s\n' "$@" > "__LOG__"
exit __EXIT__
"""
_EDITOR_STUB = r"""printf '%s\n' "$@" > "__LOG__"
for arg in "$@"; do
  case "$arg" in
    -ExecutePythonScript=*) cp "${arg#-ExecutePythonScript=}" "__COPY__" ;;
  esac
done
cat "__OUTPUT__"
exit __EXIT__
"""


@dataclass(frozen=True)
class FakeUe:
    """A temporary UE_ROOT whose Build.sh and UnrealEditor-Cmd log their arguments."""

    root: Path
    build_log: Path
    editor_log: Path
    script_copy: Path

    def build_args(self) -> list[str]:
        return self.build_log.read_text(encoding="utf-8").splitlines()

    def editor_args(self) -> list[str]:
        return self.editor_log.read_text(encoding="utf-8").splitlines()


def _write_stub(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(0o755)


def make_fake_ue(
    tmp_path: Path,
    *,
    build_exit: int = 0,
    editor_exit: int = 0,
    editor_output: str = SUCCESS_LINE,
    with_editor: bool = True,
) -> FakeUe:
    fake = FakeUe(
        root=tmp_path / "UE_5.8",
        build_log=tmp_path / "build-argv.txt",
        editor_log=tmp_path / "editor-argv.txt",
        script_copy=tmp_path / "copied-script.py",
    )
    output = tmp_path / "editor-output.txt"
    output.write_text(editor_output + "\n", encoding="utf-8")
    build_body = _BUILD_STUB.replace("__LOG__", str(fake.build_log)).replace(
        "__EXIT__", str(build_exit)
    )
    _write_stub(fake.root / "Engine" / "Build" / "BatchFiles" / "Mac" / "Build.sh", build_body)
    if with_editor:
        editor_body = (
            _EDITOR_STUB.replace("__LOG__", str(fake.editor_log))
            .replace("__COPY__", str(fake.script_copy))
            .replace("__OUTPUT__", str(output))
            .replace("__EXIT__", str(editor_exit))
        )
        _write_stub(fake.root / "Engine" / "Binaries" / "Mac" / "UnrealEditor-Cmd", editor_body)
    return fake


def guard_network(monkeypatch: pytest.MonkeyPatch, builder: ModuleType) -> list[str]:
    """Make any MCP client construction or socket connect fail; return the list of attempts."""
    attempts: list[str] = []

    class RefusingClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            attempts.append("UnrealMcpClient")
            raise AssertionError("headless mode constructed UnrealMcpClient")

    def refuse_connect(*args: object, **kwargs: object) -> None:
        attempts.append("socket.connect")
        raise AssertionError("headless mode opened a network connection")

    monkeypatch.setattr(builder, "UnrealMcpClient", RefusingClient)
    monkeypatch.setattr(socket.socket, "connect", refuse_connect)
    return attempts


def name_entry(name: str) -> bytes:
    """A serialized name-table entry: int32 length counting the NUL, the ASCII bytes, then a NUL."""
    return struct.pack("<i", len(name) + 1) + name.encode("ascii") + b"\0"


def test_headless_builds_dogfood_then_runs_the_graph_in_a_separate_editor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = make_fake_ue(tmp_path)
    monkeypatch.setenv("UE_ROOT", str(fake.root))
    builder = load_builder()
    attempts = guard_network(monkeypatch, builder)

    assert builder.main(["--headless"]) == 0

    assert attempts == []
    assert fake.build_args() == [
        "DogfoodEditor",
        "Mac",
        "Development",
        f"-Project={DOGFOOD_PROJECT}",
        "-WaitMutex",
        "-NoUBA",
    ]
    editor = fake.editor_args()
    assert editor[0] == str(DOGFOOD_PROJECT)
    assert Path(editor[0]).is_absolute()
    assert "-DisablePlugins=ModelContextProtocol,EditorToolset,VibeUE" in editor
    assert "-EnablePlugins=PythonScriptPlugin" in editor
    for flag in ("-unattended", "-nopause", "-nosplash", "-nullrhi", "-stdout"):
        assert flag in editor
    assert "-FullStdOutLogOutput" in editor
    assert "Built /nmg-game-dev/Materials/M_NmgORM" in capsys.readouterr().out


def test_headless_runs_the_builder_graph_and_removes_its_temporary_script(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = make_fake_ue(tmp_path)
    monkeypatch.setenv("UE_ROOT", str(fake.root))
    builder = load_builder()
    guard_network(monkeypatch, builder)

    assert builder.main(["--headless"]) == 0

    script_arg = next(arg for arg in fake.editor_args() if arg.startswith("-ExecutePythonScript="))
    script_path = Path(script_arg.removeprefix("-ExecutePythonScript="))
    assert fake.script_copy.read_text(encoding="utf-8") == builder._MATERIAL_CODE
    assert not script_path.exists()


def test_headless_ue_error_exits_1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = make_fake_ue(tmp_path, editor_output=FAILURE_LINE)
    monkeypatch.setenv("UE_ROOT", str(fake.root))
    builder = load_builder()
    guard_network(monkeypatch, builder)

    assert builder.main(["--headless"]) == 1
    assert "ERROR [import_ue.failed] RuntimeError: x" in capsys.readouterr().err


def test_headless_without_a_result_line_exits_1_and_names_the_editor_status(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = make_fake_ue(tmp_path, editor_exit=5, editor_output="LogPython: booting")
    monkeypatch.setenv("UE_ROOT", str(fake.root))
    builder = load_builder()
    guard_network(monkeypatch, builder)

    assert builder.main(["--headless"]) == 1
    assert "exited 5" in capsys.readouterr().err


def test_missing_unreal_editor_cmd_exits_3_before_building(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = make_fake_ue(tmp_path, with_editor=False)
    monkeypatch.setenv("UE_ROOT", str(fake.root))
    builder = load_builder()
    guard_network(monkeypatch, builder)

    assert builder.main(["--headless"]) == 3

    err = capsys.readouterr().err
    assert "[master_material.headless_unavailable]" in err
    assert str(fake.root / "Engine" / "Binaries" / "Mac" / "UnrealEditor-Cmd") in err
    assert "UE_ROOT" in err
    assert not fake.build_log.exists()


def test_failed_dogfood_build_exits_3_and_never_runs_the_editor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = make_fake_ue(tmp_path, build_exit=2)
    monkeypatch.setenv("UE_ROOT", str(fake.root))
    builder = load_builder()
    guard_network(monkeypatch, builder)

    assert builder.main(["--headless"]) == 3

    assert "[master_material.build_failed] Build.sh exited 2" in capsys.readouterr().err
    assert not fake.editor_log.exists()


def test_headless_and_url_are_mutually_exclusive() -> None:
    builder = load_builder()

    with pytest.raises(SystemExit) as exit_info:
        builder.main(["--headless", "--url", "http://127.0.0.1:8000/mcp"])

    assert exit_info.value.code == 2


def test_mcp_mode_still_exits_2_when_the_endpoint_is_unreachable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    builder = load_builder()

    class UnreachableClient:
        def __init__(self, url: object) -> None:
            _ = url
            raise builder.PipelineError(
                code="mcp.unreal.unreachable",
                message="no Unreal MCP endpoint",
                remediation="start the editor",
                stage="import_ue",
            )

    monkeypatch.setattr(builder, "UnrealMcpClient", UnreachableClient)

    assert builder.main([]) == 2
    assert "[mcp.unreal.unreachable]" in capsys.readouterr().err


def test_committed_asset_carries_every_parameter_the_builder_defines() -> None:
    data = shipped_asset_bytes()

    missing = [
        name for name in ("Tint", "BaseColor", "Normal", "ORM") if name_entry(name) not in data
    ]

    assert missing == []


def test_committed_asset_keeps_the_master_package_path_and_name() -> None:
    data = shipped_asset_bytes()

    assert b"/nmg-game-dev/Materials/M_NmgORM" in data
    assert name_entry("M_NmgORM") in data
