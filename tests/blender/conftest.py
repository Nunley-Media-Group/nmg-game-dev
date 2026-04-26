"""Shared fixtures for Blender headless tests (run under blender --background)."""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "requires_host: skip test when ahujasid/blender-mcp is not installed",
    )


@pytest.fixture(scope="session")
def enabled_addon():
    # Session scope is deliberate — enabling/disabling per-test would leak
    # registered classes and confound AC1's idempotency assertion.
    try:
        import addon_utils  # noqa: PLC0415
    except ImportError:
        pytest.skip("Blender add-on tests require Blender's bundled Python runtime")

    module_id = "nmg_game_dev_blender_addon"
    addon_utils.enable(module_id, default_set=True, persistent=False)
    yield module_id
    addon_utils.disable(module_id, default_set=False)


@pytest.fixture()
def blender_context(enabled_addon: str):  # noqa: ARG001 — ordering dependency
    try:
        import bpy  # noqa: PLC0415
    except ImportError:
        pytest.skip("Blender add-on tests require Blender's bundled Python runtime")

    if not bpy.data.scenes:
        bpy.data.scenes.new("TestScene")
    return bpy.context
