"""Coexistence tests against ahujasid/blender-mcp (AC2).

Skipped module-wide when the host add-on is not installed in this Blender's
add-on paths.
"""

from __future__ import annotations

import os
import platform
import subprocess

import pytest

_HOST_CANDIDATES = (
    "bl_ext.user_default.blender_mcp",
    "bl_ext.user_default.blender-mcp",
    "blender_mcp",
    "blender-mcp",
)


def _detect_host_addon() -> str | None:
    # addon_utils.modules() returns discovered add-on modules without enabling
    # them — unlike enable(), which writes tracebacks to stderr on misses.
    try:
        import addon_utils  # noqa: PLC0415
    except ImportError:
        return None
    known = {mod.__name__ for mod in addon_utils.modules()}
    for candidate in _HOST_CANDIDATES:
        if candidate in known:
            return candidate
    return None


_HOST_ADDON_ID = _detect_host_addon()

pytestmark = [
    pytest.mark.requires_host,
    pytest.mark.skipif(
        _HOST_ADDON_ID is None,
        reason=(
            "ahujasid/blender-mcp is not installed in this Blender's add-on paths. "
            "Install it (uvx blender-mcp or pip install blender-mcp) and enable it "
            "in Blender before running the coexistence suite."
        ),
    ),
]


def test_both_addons_load(enabled_addon: str) -> None:
    import addon_utils  # noqa: PLC0415

    assert _HOST_ADDON_ID is not None  # guaranteed by skipif
    addon_utils.enable(_HOST_ADDON_ID, default_set=False, persistent=False)

    nmg_loaded, _ = addon_utils.check(enabled_addon)
    host_loaded, _ = addon_utils.check(_HOST_ADDON_ID)
    assert nmg_loaded, f"nmg add-on '{enabled_addon}' is not loaded"
    assert host_loaded, f"blender-mcp host '{_HOST_ADDON_ID}' is not loaded"


@pytest.mark.skipif(
    platform.system() == "Windows",
    reason="lsof is not available on Windows",
)
def test_no_second_port_bound() -> None:
    blender_mcp_port = int(os.environ.get("BLENDER_MCP_PORT", "9876"))
    blender_pid = os.getpid()

    result = subprocess.run(
        ["lsof", "-nP", f"-p{blender_pid}", "-iTCP", "-sTCP:LISTEN"],
        capture_output=True,
        text=True,
    )
    unexpected: list[int] = []
    for line in result.stdout.strip().splitlines():
        parts = line.split()
        if not parts:
            continue
        name_col = parts[-1]  # host:port (LISTEN)
        if ":" not in name_col:
            continue
        try:
            port = int(name_col.split(":")[-1].split("(")[0])
        except ValueError:
            continue
        if port != blender_mcp_port:
            unexpected.append(port)

    assert not unexpected, (
        f"Blender process {blender_pid} is listening on unexpected ports: {unexpected}. "
        f"Only BLENDER_MCP_PORT ({blender_mcp_port}) is permitted."
    )


def test_disabling_nmg_leaves_host_functional(enabled_addon: str) -> None:
    import addon_utils  # noqa: PLC0415

    assert _HOST_ADDON_ID is not None
    addon_utils.enable(_HOST_ADDON_ID, default_set=False, persistent=False)
    addon_utils.disable(enabled_addon, default_set=False)
    try:
        host_loaded, _ = addon_utils.check(_HOST_ADDON_ID)
        assert host_loaded, f"host '{_HOST_ADDON_ID}' unavailable after disabling nmg add-on"
    finally:
        addon_utils.enable(enabled_addon, default_set=True, persistent=False)


def test_disabling_host_leaves_nmg_functional(enabled_addon: str) -> None:  # noqa: ARG001
    import addon_utils  # noqa: PLC0415
    import bpy  # noqa: PLC0415

    assert _HOST_ADDON_ID is not None
    addon_utils.enable(_HOST_ADDON_ID, default_set=False, persistent=False)
    addon_utils.disable(_HOST_ADDON_ID, default_set=False)
    try:
        result = bpy.ops.nmggamedev.cleanup_desktop()
        assert result == {"FINISHED"}, f"cleanup_desktop returned {result!r} after disabling host"
    finally:
        addon_utils.enable(_HOST_ADDON_ID, default_set=False, persistent=False)
