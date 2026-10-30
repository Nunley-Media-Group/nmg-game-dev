"""Idempotent bake under Blender headless: AC7 (#67, SCN007).

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
    checker_image,
    clear_scene,
    image_material,
    procedural_material,
)


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


def _texture_mtimes(result: dict[str, Any]) -> dict[str, int]:
    return {path: Path(path).stat().st_mtime_ns for path in result["desktop_textures"]}


def test_ac7_unchanged_second_bake_is_a_cache_hit(core: Any, tmp_path: Path, budgets: str) -> None:
    """AC7: the second run reports cache_hit true and leaves every PNG untouched (SCN007)."""
    build_asset("Crate", [procedural_material("Authored")])
    first = core.bake_asset("Crate", "standard_prop", tmp_path / "out", budgets, "CPU", 4)
    assert first["cache_hit"] is False
    mtimes = _texture_mtimes(first)

    second = core.bake_asset("Crate", "standard_prop", tmp_path / "out", budgets, "CPU", 4)

    assert second["cache_hit"] is True
    assert second["desktop_textures"] == first["desktop_textures"]
    assert _texture_mtimes(second) == mtimes


def test_ac7_edited_material_causes_a_rebake(core: Any, tmp_path: Path, budgets: str) -> None:
    """AC7: a change to the baked material's settings is not a cache hit."""
    build_asset("Crate", [procedural_material("Authored")])
    core.bake_asset("Crate", "standard_prop", tmp_path / "out", budgets, "CPU", 4)

    material = bpy.data.materials["M_Crate_Body"]
    bsdf = next(node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Specular IOR Level"].default_value = 0.8

    rebaked = core.bake_asset("Crate", "standard_prop", tmp_path / "out", budgets, "CPU", 4)

    assert rebaked["cache_hit"] is False


def test_ac7_missing_texture_is_never_a_cache_hit(core: Any, tmp_path: Path, budgets: str) -> None:
    """AC7: a recorded PNG that no longer exists is not a cache hit.

    The rebake starts from already-baked materials whose texture is gone, so it cannot reproduce
    the look and fails the proof loudly. The failed run removes its outputs and the manifest, so
    the next run cannot hit a stale cache entry.
    """
    build_asset("Crate", [procedural_material("Authored")])
    first = core.bake_asset("Crate", "standard_prop", tmp_path / "out", budgets, "CPU", 4)
    Path(first["desktop_textures"][0]).unlink()

    with pytest.raises(core.BakeError) as info:
        core.bake_asset("Crate", "standard_prop", tmp_path / "out", budgets, "CPU", 4)

    assert info.value.reason == "proof_mismatch"
    assert not (tmp_path / "out" / "bake.json").exists()
    assert not any(Path(path).exists() for path in first["desktop_textures"])


def test_ac7_image_material_is_idempotent_too(core: Any, tmp_path: Path, budgets: str) -> None:
    """AC7: an image-texture asset is a cache hit on the second run as well."""
    image = checker_image("Authored_src", periodic=True)
    build_asset("Crate", [image_material("Authored", image)])
    core.bake_asset("Crate", "standard_prop", tmp_path / "out", budgets, "CPU", 4)
    again = core.bake_asset("Crate", "standard_prop", tmp_path / "out", budgets, "CPU", 4)
    assert again["cache_hit"] is True
