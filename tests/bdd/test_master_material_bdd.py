"""pytest-bdd bindings for master_material.feature: SCN001-SCN003 of #101, SCN004-SCN006 of #204.

The steps reuse the AST, asset, and fake-UE helpers in ``tests/unit/test_build_master_material.py``,
so the scenarios and the unit tests check the same builder code and the same committed asset.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenario, then, when

from tests.unit.test_build_master_material import (
    DOGFOOD_PROJECT,
    MASKS_DEFAULT,
    NORMAL_DEFAULT,
    SHIPPED_ASSET,
    builder_tree,
    channel_wiring,
    guard_network,
    load_builder,
    make_fake_ue,
    name_entry,
    rebuild_clears_in_place,
    sampler_defaults,
    shipped_asset_bytes,
    skeletal_flag_before_recompile,
)

PARAMETER_NAMES = ("Tint", "BaseColor", "Normal", "ORM")


def graph_package_path(tree: ast.Module) -> str:
    """The package path the graph code builds from its PACKAGE_DIR and NAME constants."""
    constants = {
        target.id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name) and target.id in {"PACKAGE_DIR", "NAME"}
    }
    return f"{constants['PACKAGE_DIR']}/{constants['NAME']}"


@pytest.fixture()
def state() -> dict[str, Any]:
    return {}


@scenario(
    "master_material.feature",
    "The master material's samplers default to textures that match their sampler type",
)
def test_samplers_default_to_matching_textures() -> None:
    """SCN001 (AC1, FR1): typed sampler defaults in the builder and the shipped asset."""


@scenario("master_material.feature", "The master material is usable on skeletal meshes")
def test_master_material_is_usable_on_skeletal_meshes() -> None:
    """SCN002 (AC2, FR2): skeletal usage is set before recompile and recorded in the asset."""


@scenario(
    "master_material.feature",
    "Rebuilding keeps instances, parameter names, and channel wiring",
)
def test_rebuild_keeps_instances_parameter_names_and_wiring() -> None:
    """SCN003 (AC3): the in-place rebuild keeps parameter names and channel wiring."""


@given("the M_NmgORM builder code from scripts/unreal/build_master_material.py")
def builder_code(state: dict[str, Any]) -> None:
    state["tree"] = builder_tree()


@given("an existing M_NmgORM asset")
def existing_asset(state: dict[str, Any]) -> None:
    assert SHIPPED_ASSET.is_file(), "the shipped M_NmgORM.uasset must exist to be rebuilt"
    state["tree"] = builder_tree()


@when("it builds the BaseColor, Normal, and ORM sampler parameters")
def build_sampler_parameters(state: dict[str, Any]) -> None:
    state["defaults"] = sampler_defaults(state["tree"])


@when("it builds the material")
def build_material(state: dict[str, Any]) -> None:
    state["skeletal_before_recompile"] = skeletal_flag_before_recompile(state["tree"])


@when("the builder runs again")
def rebuild(state: dict[str, Any]) -> None:
    state["defaults"] = sampler_defaults(state["tree"])
    state["wiring"] = channel_wiring(state["tree"])
    state["rebuilds_in_place"] = rebuild_clears_in_place(state["tree"])


@then(parsers.parse("{parameter} defaults to {path}"))
def parameter_defaults_to(state: dict[str, Any], parameter: str, path: str) -> None:
    assert state["defaults"][parameter][1] == path


@then("the shipped M_NmgORM.uasset references both default textures")
def asset_references_default_textures() -> None:
    data = shipped_asset_bytes()
    assert NORMAL_DEFAULT.encode() in data
    assert MASKS_DEFAULT.encode() in data


@then("it enables used_with_skeletal_mesh before recompiling")
def enables_skeletal_usage_before_recompile(state: dict[str, Any]) -> None:
    assert state["skeletal_before_recompile"] is True


@then("the shipped M_NmgORM.uasset records bUsedWithSkeletalMesh")
def asset_records_skeletal_usage() -> None:
    assert b"bUsedWithSkeletalMesh" in shipped_asset_bytes()


@then("it loads and clears the existing material instead of recreating it")
def loads_and_clears_existing(state: dict[str, Any]) -> None:
    assert state["rebuilds_in_place"] is True


@then("the BaseColor, Normal, and ORM parameters keep their names")
def parameters_keep_names(state: dict[str, Any]) -> None:
    assert set(state["defaults"]) == {"BaseColor", "Normal", "ORM"}


@then("ORM R, G, and B still feed Ambient Occlusion, Roughness, and Metallic")
def orm_channels_unchanged(state: dict[str, Any]) -> None:
    assert [row for row in state["wiring"] if row[0] == "orm"] == [
        ("orm", "R", "unreal.MaterialProperty.MP_AMBIENT_OCCLUSION"),
        ("orm", "G", "unreal.MaterialProperty.MP_ROUGHNESS"),
        ("orm", "B", "unreal.MaterialProperty.MP_METALLIC"),
    ]


@scenario(
    "master_material.feature",
    "The master material is rebuilt by a separate headless UnrealEditor-Cmd process",
)
def test_master_material_is_rebuilt_headlessly() -> None:
    """SCN004 (AC1, FR1, FR4): --headless runs a separate UnrealEditor-Cmd, contacting no editor."""


@scenario("master_material.feature", "The committed master material carries the Tint parameter")
def test_committed_master_material_carries_tint() -> None:
    """SCN005 (AC2, FR2, FR3): the committed asset's name table holds all four parameters."""


@scenario("master_material.feature", "The rebuilt master material keeps its path and package name")
def test_rebuilt_master_material_keeps_path_and_name() -> None:
    """SCN006 (AC3): the in-place rebuild keeps the package name and loads the existing material."""


@given("UE_ROOT holds a fake Build.sh and a fake UnrealEditor-Cmd that log their arguments")
def fake_unreal_engine(
    state: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = make_fake_ue(tmp_path)
    monkeypatch.setenv("UE_ROOT", str(fake.root))
    state["fake"] = fake


@given("the Unreal MCP client fails if it is constructed")
def mcp_client_forbidden(state: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    builder = load_builder()
    state["builder"] = builder
    state["attempts"] = guard_network(monkeypatch, builder)


@when("the builder runs with --headless")
def builder_runs_headless(state: dict[str, Any]) -> None:
    state["exit_code"] = state["builder"].main(["--headless"])


@then(
    "UnrealEditor-Cmd opens fixtures/dogfood.uproject with -ExecutePythonScript "
    "and the MCP plugins disabled"
)
def editor_opens_dogfood(state: dict[str, Any]) -> None:
    editor = state["fake"].editor_args()
    assert editor[0] == str(DOGFOOD_PROJECT)
    assert any(arg.startswith("-ExecutePythonScript=") for arg in editor)
    assert "-DisablePlugins=ModelContextProtocol,EditorToolset,VibeUE" in editor


@then("the script it runs is the builder's graph code")
def script_is_graph_code(state: dict[str, Any]) -> None:
    assert state["fake"].script_copy.read_text(encoding="utf-8") == state["builder"]._MATERIAL_CODE


@then("the builder exits 0 without contacting an editor")
def exits_zero_without_editor(state: dict[str, Any]) -> None:
    assert state["exit_code"] == 0
    assert state["attempts"] == []


@given("the committed M_NmgORM.uasset")
def committed_asset(state: dict[str, Any]) -> None:
    assert SHIPPED_ASSET.is_file(), "the shipped M_NmgORM.uasset must exist"
    state["data"] = shipped_asset_bytes()


@when("its name table is inspected")
def inspect_name_table(state: dict[str, Any]) -> None:
    state["missing"] = [name for name in PARAMETER_NAMES if name_entry(name) not in state["data"]]


@then("it holds the parameter names Tint, BaseColor, Normal, and ORM")
def holds_parameter_names(state: dict[str, Any]) -> None:
    assert state["missing"] == []


@given("the committed M_NmgORM.uasset and the builder's graph code")
def committed_asset_and_graph(state: dict[str, Any]) -> None:
    state["data"] = shipped_asset_bytes()
    state["tree"] = builder_tree()


@when("the master is rebuilt in place")
def master_rebuilt_in_place(state: dict[str, Any]) -> None:
    state["rebuilds_in_place"] = rebuild_clears_in_place(state["tree"])
    state["package"] = graph_package_path(state["tree"])


@then(parsers.parse("the asset's package name is {package}"))
def asset_package_name(state: dict[str, Any], package: str) -> None:
    assert state["package"] == package
    assert package.encode() in state["data"]


@then("the builder loads and clears the existing material instead of recreating it")
def builder_loads_and_clears(state: dict[str, Any]) -> None:
    assert state["rebuilds_in_place"] is True
