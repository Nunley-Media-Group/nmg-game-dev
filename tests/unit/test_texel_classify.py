"""Per-slot texel density: classification, the density arithmetic, and report entries (#151).

contract_core/texel.py is loaded by file path under plain CPython, as test_blender_budgets.py
loads budgets.py, so its pure helpers are tested without Blender. SCN001-SCN009 run under
Blender headless in tests/blender/ (test_contract_validate.py, test_bake_tiling.py,
test_variants_mobile.py).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEXEL_PATH = _REPO_ROOT / "plugins" / "nmg-game-dev-blender-addon" / "contract_core" / "texel.py"


def _load_texel() -> ModuleType:
    name = "nmg_texel_under_test"
    spec = importlib.util.spec_from_file_location(name, _TEXEL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclasses looks the module up in sys.modules while it builds SlotArea.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


texel = _load_texel()


class _Material:
    """Stands in for a bpy material: a name and ID properties read through get()."""

    def __init__(self, name: str = "M_Piece_Part", props: dict[str, Any] | None = None) -> None:
        self.name = name
        self._props = props or {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._props.get(key, default)


def test_constants_match_the_contract() -> None:
    """FR3, FR4, FR13: the marker name, the cut-off, and the unchanged minimums."""
    assert texel.TRIM_ATLAS_PROPERTY == "nmg_trim_atlas"
    assert texel.FLAT_COLOUR_UV_AREA == 1e-8
    assert texel.DESKTOP_MIN == 256.0
    assert texel.MOBILE_MIN == 128.0


def test_the_pure_module_does_not_import_bpy() -> None:
    """The unit suite can load texel.py only because bpy is reached lazily, never at import."""
    assert "bpy" not in vars(texel)


def test_classify_checks_the_marker_first() -> None:
    """AC5: a marked slot is trim_atlas whatever its UV and world areas are."""
    assert texel.classify(0.0, 0.0, True) == "trim_atlas"
    assert texel.classify(0.0, 1.0, True) == "trim_atlas"
    assert texel.classify(5.0, 1.0, True) == "trim_atlas"


def test_classify_flat_colour_cut_off_is_inclusive() -> None:
    """AC4, FR3: UV area at or below the cut-off is flat_colour; just above it is measured."""
    assert texel.classify(0.0, 1.0, False) == "flat_colour"
    assert texel.classify(1e-8, 1.0, False) == "flat_colour"
    assert texel.classify(2e-8, 1.0, False) == "measured"


def test_classify_zero_world_area_is_skipped_not_measured() -> None:
    """A slot with UV area but no world area has nothing to measure."""
    assert texel.classify(1.0, 0.0, False) == "skipped"


def test_classify_measures_an_undeclared_tiling_slot() -> None:
    """AC6, AC9: an unmarked slot with real UV area is measured."""
    assert texel.classify(0.5, 1.0, False) == "measured"


def test_density_is_px_times_the_square_root_of_uv_over_world() -> None:
    """FR1-FR2: the measure is px * sqrt(UV area / world area)."""
    assert texel.density(256, 1.0, 1.0) == pytest.approx(256.0)
    assert texel.density(256, 0.25, 1.0) == pytest.approx(128.0)
    assert texel.density(256, 4.0, 1.0) == pytest.approx(512.0)
    assert texel.density(128, 1e-4, 1.0) == pytest.approx(1.28)


def test_slot_kind_follows_classify() -> None:
    """The SlotArea property and the function agree, so validation and bake cannot diverge."""
    slot = texel.SlotArea(
        slot=0, material=_Material(), uv_area=0.25, world_area=1.0, trim_atlas=False
    )
    assert slot.kind == texel.classify(0.25, 1.0, False) == "measured"


def test_slot_name_falls_back_for_a_slot_without_material() -> None:
    slot = texel.SlotArea(slot=3, material=None, uv_area=0.25, world_area=1.0, trim_atlas=False)
    assert slot.name == "slot 3"


def test_slot_entry_lists_each_variant_density_when_measured() -> None:
    """AC7: a measured slot lists its px/m for each variant, rounded to one place."""
    slot = texel.SlotArea(
        slot=1, material=_Material("M_Piece_Tile"), uv_area=0.25, world_area=1.0, trim_atlas=False
    )
    entry = texel.slot_entry(slot, {"desktop": 256, "mobile": 128})
    assert entry == {
        "slot": 1,
        "material": "M_Piece_Tile",
        "desktop": 128.0,
        "mobile": 64.0,
    }


def test_slot_entry_gives_none_for_a_variant_without_an_image() -> None:
    """A measured slot whose material has no image gives no px/m, as validation always has."""
    slot = texel.SlotArea(
        slot=0, material=_Material("M_Piece_Tile"), uv_area=0.25, world_area=1.0, trim_atlas=False
    )
    assert texel.slot_entry(slot, {"desktop": None})["desktop"] is None


@pytest.mark.parametrize(
    ("uv_area", "trim_atlas", "reason"),
    [(0.5, True, "trim_atlas"), (0.0, False, "flat_colour")],
)
def test_slot_entry_names_the_exemption_reason(
    uv_area: float, trim_atlas: bool, reason: str
) -> None:
    """AC7: an exempt slot is listed with its reason, `trim_atlas` or `flat_colour`."""
    slot = texel.SlotArea(
        slot=2,
        material=_Material("M_Piece_Atlas"),
        uv_area=uv_area,
        world_area=1.0,
        trim_atlas=trim_atlas,
    )
    assert texel.slot_entry(slot, {"desktop": 256, "mobile": 128}) == {
        "slot": 2,
        "material": "M_Piece_Atlas",
        "exempt": reason,
    }


def test_skipped_slot_has_no_report_entry() -> None:
    slot = texel.SlotArea(
        slot=0, material=_Material(), uv_area=1.0, world_area=0.0, trim_atlas=False
    )
    assert texel.slot_entry(slot, {"desktop": 256, "mobile": 128}) is None


def test_is_trim_atlas_reads_only_a_truthy_marker() -> None:
    """AC5: the marker is a custom property; absent or False means not a trim atlas."""
    assert texel.is_trim_atlas(None) is False
    assert texel.is_trim_atlas(_Material()) is False
    assert texel.is_trim_atlas(_Material(props={"nmg_trim_atlas": False})) is False
    assert texel.is_trim_atlas(_Material(props={"nmg_trim_atlas": True})) is True
