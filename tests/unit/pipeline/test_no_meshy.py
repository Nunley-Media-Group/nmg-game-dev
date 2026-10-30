"""AC3 (#64): the Meshy client types and generate route are gone from the pipeline."""

from __future__ import annotations

import dataclasses
import typing

from nmg_game_dev.pipeline import Source
from nmg_game_dev.pipeline.stages import _base, _mcp, generate
from nmg_game_dev.pipeline.stages._base import McpClients


def test_mcp_clients_has_no_meshy_field() -> None:
    field_names = {f.name for f in dataclasses.fields(McpClients)}
    assert "meshy" not in field_names
    assert field_names == {"blender", "unreal"}


def test_meshy_mcp_protocol_is_removed() -> None:
    assert not hasattr(_base, "MeshyMcp")


def test_generate_meshy_is_removed() -> None:
    assert not hasattr(generate, "generate_meshy")


def test_server_literal_is_blender_and_unreal() -> None:
    assert typing.get_args(_mcp.Server) == ("blender", "unreal")


def test_source_literal_is_blender_only() -> None:
    assert typing.get_args(Source) == ("blender",)
