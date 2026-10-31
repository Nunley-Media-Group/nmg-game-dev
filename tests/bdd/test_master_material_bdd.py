"""pytest-bdd bindings for master_material.feature: SCN001-SCN003 of #101.

The steps reuse the AST and asset helpers in ``tests/unit/test_build_master_material.py``, so the
scenarios and the unit tests check the same builder code and the same committed asset.
"""

from __future__ import annotations

from typing import Any

import pytest
from pytest_bdd import given, parsers, scenario, then, when

from tests.unit.test_build_master_material import (
    MASKS_DEFAULT,
    NORMAL_DEFAULT,
    SHIPPED_ASSET,
    builder_tree,
    channel_wiring,
    rebuild_clears_in_place,
    sampler_defaults,
    shipped_asset_bytes,
    skeletal_flag_before_recompile,
)


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
