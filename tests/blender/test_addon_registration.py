"""Add-on registration, naming contract, and version sync (AC1, AC3, AC5, AC6)."""

from __future__ import annotations

import warnings
from pathlib import Path

# ---------------------------------------------------------------------------
# AC1: clean enable + idempotent re-register
# ---------------------------------------------------------------------------


def test_enable_succeeds(enabled_addon: str) -> None:
    """add-on enables cleanly (AC1)."""
    import addon_utils  # noqa: PLC0415

    loaded, _ = addon_utils.check(enabled_addon)
    assert loaded, f"addon_utils.check('{enabled_addon}') reported not loaded"


def test_unregister_register_is_idempotent(enabled_addon: str) -> None:
    """unregister() → register() twice raises nothing and leaks no classes (AC1)."""
    import sys  # noqa: PLC0415

    addon_module = sys.modules.get(enabled_addon)
    assert addon_module is not None, f"Module '{enabled_addon}' not in sys.modules"

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        # First cycle
        addon_module.unregister()
        addon_module.register()
        # Second cycle
        addon_module.unregister()
        addon_module.register()

    duplicate_warnings = [
        w
        for w in caught
        if "already registered" in str(w.message).lower() or "duplicate" in str(w.message).lower()
    ]
    assert not duplicate_warnings, f"Duplicate class warnings on re-register: {duplicate_warnings}"


# ---------------------------------------------------------------------------
# AC3: naming contract
# ---------------------------------------------------------------------------


def test_naming_contract_operators(enabled_addon: str) -> None:
    """Every nmg operator bl_idname starts with 'nmggamedev.' (AC3)."""
    import bpy  # noqa: PLC0415

    nmg_ops = [
        name
        for name in dir(bpy.types)
        if (
            (cls := getattr(bpy.types, name, None)) is not None
            and isinstance(getattr(cls, "bl_idname", None), str)
            and getattr(cls, "bl_idname", "").startswith("nmggamedev.")
        )
    ]
    assert len(nmg_ops) == 3, (
        f"Expected exactly 3 nmggamedev.* operators, found {len(nmg_ops)}: {nmg_ops}"
    )
    expected = {
        "nmggamedev.cleanup_desktop",
        "nmggamedev.optimize_mobile",
        "nmggamedev.generate_variants",
    }
    found_idnames = {getattr(bpy.types, name).bl_idname for name in nmg_ops}
    assert found_idnames == expected, (
        f"Operator idnames mismatch. Expected {expected}, got {found_idnames}"
    )


def test_naming_contract_panels(enabled_addon: str) -> None:
    """Every nmg panel class name starts with 'NMGGAMEDEV_PT_' (AC3)."""
    import bpy  # noqa: PLC0415

    nmg_panels = [
        name
        for name in dir(bpy.types)
        if (
            (cls := getattr(bpy.types, name, None)) is not None
            and isinstance(cls, type)
            and issubclass(cls, bpy.types.Panel)
            and name.startswith("NMGGAMEDEV_PT_")
        )
    ]
    assert nmg_panels, "No NMGGAMEDEV_PT_ panels found"
    for name in nmg_panels:
        assert name.startswith("NMGGAMEDEV_PT_"), (
            f"Panel '{name}' does not satisfy AC3 naming contract"
        )


def test_naming_contract_property_groups(enabled_addon: str) -> None:
    """Every nmg property group starts with 'NmgGameDev' and ends with 'Props' (AC3)."""
    import bpy  # noqa: PLC0415

    nmg_groups = [
        name
        for name in dir(bpy.types)
        if (
            (cls := getattr(bpy.types, name, None)) is not None
            and isinstance(cls, type)
            and issubclass(cls, bpy.types.PropertyGroup)
            and name.startswith("NmgGameDev")
        )
    ]
    assert nmg_groups, "No NmgGameDev* property groups found"
    for name in nmg_groups:
        assert name.startswith("NmgGameDev") and name.endswith("Props"), (
            f"PropertyGroup '{name}' violates AC3: "
            "must start with 'NmgGameDev' and end with 'Props'"
        )


# ---------------------------------------------------------------------------
# AC5: panel registers in background mode
# ---------------------------------------------------------------------------


def test_panel_registered_in_background(enabled_addon: str) -> None:
    """NMGGAMEDEV_PT_main_panel is in bpy.types in --background mode (AC5)."""
    import bpy  # noqa: PLC0415

    assert hasattr(bpy.types, "NMGGAMEDEV_PT_main_panel"), (
        "NMGGAMEDEV_PT_main_panel is not registered in bpy.types"
    )


# ---------------------------------------------------------------------------
# AC6: bl_info version matches VERSION
# ---------------------------------------------------------------------------


def test_bl_info_version_matches_version_file(enabled_addon: str) -> None:
    """bl_info['version'] tuple matches the repo VERSION file (AC6)."""
    import sys  # noqa: PLC0415

    addon_module = sys.modules.get(enabled_addon)
    assert addon_module is not None

    bl_info = getattr(addon_module, "bl_info", None)
    assert bl_info is not None, "bl_info not found on addon module"

    version_tuple = bl_info.get("version")
    assert isinstance(version_tuple, tuple), (
        f"bl_info['version'] should be a tuple, got {type(version_tuple)}"
    )
    assert len(version_tuple) == 3, (
        f"bl_info['version'] should have 3 components, got {version_tuple}"
    )

    # Walk up from this test file to find VERSION
    current = Path(__file__).resolve().parent
    version_file: Path | None = None
    for _ in range(20):
        candidate = current / "VERSION"
        if candidate.is_file():
            version_file = candidate
            break
        parent = current.parent
        if parent == current:
            break
        current = parent

    assert version_file is not None, "Could not locate VERSION file"
    raw = version_file.read_text(encoding="utf-8").strip()
    parts = raw.split(".")
    assert len(parts) == 3 and all(p.isdigit() for p in parts), (
        f"VERSION file contains invalid semver: '{raw}'"
    )
    expected = (int(parts[0]), int(parts[1]), int(parts[2]))
    assert version_tuple == expected, (
        f"bl_info['version'] {version_tuple!r} does not match VERSION {expected!r}"
    )
