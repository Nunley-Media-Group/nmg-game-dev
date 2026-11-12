"""Material variants under Blender headless: the declaration, its contract rules, and export (#148).

Run with scripts/run-blender-tests.sh. The Crate is the compliant baked-style asset from
contract_fixtures, so the declarations name its M_Crate_Body material and its 512 px base colour.
Under plain CPython the module is skipped.
"""

from __future__ import annotations

import importlib
import json
import struct
from pathlib import Path
from typing import Any

import pytest

bpy = pytest.importorskip("bpy")

from .contract_fixtures import (  # noqa: E402
    _box_mesh,
    build_crate,
    clear_scene,
    write_declaration,
    write_png_file,
)

RED = {"name": "Red", "material": "M_Crate_Body", "base_color": "Red.png"}
BLUE_TINT = {"name": "Blue", "material": "M_Crate_Body", "parameters": {"Tint": [0.5, 0.25, 1.0]}}
BLUE_TEXTURE = {"name": "Blue", "material": "M_Crate_Body", "base_color": "Blue.png"}
METRICS: dict[str, Any] = {
    "desktop": {"tris": 12, "max_texture_px": 512, "materials": 1},
    "mobile": {
        "tris": 12,
        "lod_tris": {},
        "lod_levels": 0,
        "max_texture_px": 512,
        "materials": 1,
    },
}


@pytest.fixture(autouse=True)
def _isolated_scene(enabled_addon: str) -> Any:  # noqa: ARG001 - ordering dependency
    clear_scene()
    yield
    clear_scene()


@pytest.fixture()
def contract(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.contract_core")


@pytest.fixture()
def steps(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.finalize_core")


@pytest.fixture()
def textures(tmp_path: Path) -> Path:
    """Replacement base colours beside the declaration: a 512 px Red and Blue, and bad files."""
    write_png_file(tmp_path / "Red.png", 512, (200, 40, 40))
    write_png_file(tmp_path / "Blue.png", 512, (40, 40, 200))
    write_png_file(tmp_path / "Small.png", 256)
    write_png_file(tmp_path / "Odd.png", 300)
    (tmp_path / "Notes.txt").write_text("not a texture", encoding="utf-8")
    return tmp_path


def _add_material_part(material_name: str) -> None:
    """Add a Desktop part with its own material, parented to the root, as an authored asset has."""
    material = bpy.data.materials.new(material_name)
    material.use_nodes = True
    part_name = f"SM_Crate_{material_name.removeprefix('M_Crate_')}"
    part = bpy.data.objects.new(part_name, _box_mesh(part_name, material))
    bpy.data.collections["Crate"].objects.link(part)
    part.parent = bpy.data.objects["SM_Crate"]


def _declare(tmp_path: Path, entries: list[dict[str, Any]]) -> Path:
    return write_declaration(tmp_path / "Crate.material-variants.json", entries)


def _validate(
    contract: Any, declaration: Path, asset_class: str = "standard_prop"
) -> dict[str, Any]:
    return contract.validate_asset(
        "Crate",
        asset_class,
        authored=True,
        material_variants_path=str(declaration),
    )


def _rules(report: dict[str, Any]) -> set[str]:
    return {item["rule"] for item in report["findings"]}


def _finding(report: dict[str, Any], rule: str) -> dict[str, str]:
    return next(item for item in report["findings"] if item["rule"] == rule)


def _png_dimensions(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:24]
    width, height = struct.unpack(">II", header[16:24])
    return width, height


def _export(steps: Any, tmp_path: Path, declaration: Path | None, name: str = "job") -> Path:
    """Run the finalize export step on the Crate and return <export>/Props/Crate."""
    request = {
        "collection": "Crate",
        "category": "Props",
        "asset_class": "standard_prop",
        "export_root": str(tmp_path / "export"),
        "blend": None,
        "budgets_path": None,
        "device": "CPU",
        "samples": 4,
        "material_variants_path": str(declaration) if declaration is not None else None,
    }
    job = tmp_path / name
    job.mkdir(parents=True, exist_ok=True)
    envelope = steps.run_step("export", request, job, {"metrics": METRICS})
    assert envelope["ok"] is True, envelope["error"]
    return tmp_path / "export" / "Props" / "Crate"


def _sidecar(root: Path) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads((root / "nmg-variants.json").read_text(encoding="utf-8"))
    return payload


# --- AC1: the declaration is read and listed --------------------------------------------------


def test_scn001_the_declaration_is_read_and_each_variant_is_listed(
    contract: Any, textures: Path
) -> None:
    build_crate()
    report = _validate(contract, _declare(textures, [RED, BLUE_TINT]))

    assert report["passed"] is True, report["findings"]
    listed = {entry["name"]: entry for entry in report["material_variants"]}
    assert listed["Red"]["material"] == "M_Crate_Body"
    assert listed["Red"]["base_color"] == str(textures / "Red.png")
    assert listed["Blue"]["base_color"] is None
    assert listed["Blue"]["parameters"] == {"Tint": [0.5, 0.25, 1.0, 1.0]}


def test_without_a_declaration_the_report_has_no_material_variants(contract: Any) -> None:
    build_crate()

    report = contract.validate_asset("Crate", "standard_prop", authored=True)

    assert "material_variants" not in report


def test_a_malformed_declaration_raises_declaration_invalid(contract: Any, tmp_path: Path) -> None:
    build_crate()
    declaration = tmp_path / "Crate.material-variants.json"
    declaration.write_text("{not json", encoding="utf-8")

    with pytest.raises(contract.ContractError) as raised:
        _validate(contract, declaration)

    assert raised.value.code == "material_variant.declaration_invalid"


# --- AC5: every material_variant rule produces a finding naming the asset and the variant ----

RULE_CASES: list[tuple[str, str, str | None, list[dict[str, Any]]]] = [
    (
        "material_variant.name",
        "standard_prop",
        None,
        [{"name": "red", "material": "M_Crate_Body", "base_color": "Red.png"}],
    ),
    # Body plus _Red names the part M_Crate_Body_Red, so the MI would collide with that part's.
    ("material_variant.name", "hero_prop", "M_Crate_Body_Red", [RED]),
    ("material_variant.duplicate", "standard_prop", None, [RED, dict(RED)]),
    (
        "material_variant.material_missing",
        "standard_prop",
        None,
        [{"name": "Red", "material": "M_Crate_Trim", "base_color": "Red.png"}],
    ),
    (
        "material_variant.texture_missing",
        "standard_prop",
        None,
        [{"name": "Red", "material": "M_Crate_Body", "base_color": "Missing.png"}],
    ),
    (
        "material_variant.texture_missing",
        "standard_prop",
        None,
        [{"name": "Red", "material": "M_Crate_Body", "base_color": "Notes.txt"}],
    ),
    (
        "material_variant.texture_size",
        "standard_prop",
        None,
        [{"name": "Red", "material": "M_Crate_Body", "base_color": "Odd.png"}],
    ),
    (
        "material_variant.texture_size",
        "standard_prop",
        None,
        [{"name": "Red", "material": "M_Crate_Body", "base_color": "Small.png"}],
    ),
    (
        "material_variant.parameter",
        "standard_prop",
        None,
        [{"name": "Blue", "material": "M_Crate_Body", "parameters": {"Glow": [1, 1, 1]}}],
    ),
    (
        "material_variant.parameter",
        "standard_prop",
        None,
        [{"name": "Blue", "material": "M_Crate_Body", "parameters": {"Tint": [1, 1]}}],
    ),
    (
        "material_variant.parameter",
        "standard_prop",
        None,
        [{"name": "Blue", "material": "M_Crate_Body", "parameters": {"Tint": [-1, 0, 0]}}],
    ),
    (
        "material_variant.empty",
        "standard_prop",
        None,
        [{"name": "Red", "material": "M_Crate_Body"}],
    ),
]


@pytest.mark.parametrize(
    ("rule", "asset_class", "extra_part", "entries"),
    RULE_CASES,
    ids=[f"{case[0].split('.')[-1]}-{index}" for index, case in enumerate(RULE_CASES)],
)
def test_scn005_each_rule_yields_a_finding_naming_the_asset_and_variant(
    contract: Any,
    textures: Path,
    rule: str,
    asset_class: str,
    extra_part: str | None,
    entries: list[dict[str, Any]],
) -> None:
    build_crate()
    if extra_part is not None:
        _add_material_part(extra_part)

    report = _validate(contract, _declare(textures, entries), asset_class)

    assert report["passed"] is False
    assert rule in _rules(report), sorted(_rules(report))
    message = _finding(report, rule)["message"]
    assert "Crate" in message
    assert entries[0]["name"] in message
    assert rule in message


# --- AC6: merged authored materials ------------------------------------------------------------


def test_scn006_a_variant_on_a_merged_authored_material_is_rejected(
    contract: Any, textures: Path
) -> None:
    build_crate()
    # Two authored materials exceed the Mobile limit of one, so the bake merges them into Body.
    _add_material_part("M_Crate_Trim")

    report = _validate(
        contract,
        _declare(
            textures,
            [{"name": "Red", "material": "M_Crate_Trim", "base_color": "Red.png"}],
        ),
    )

    merged = _finding(report, "material_variant.material_merged")
    assert "M_Crate_Body" in merged["message"]


def test_a_variant_on_the_merged_body_material_is_accepted(contract: Any, textures: Path) -> None:
    build_crate()
    _add_material_part("M_Crate_Trim")

    report = _validate(contract, _declare(textures, [RED]))

    assert not _rules(report) & {
        "material_variant.material_merged",
        "material_variant.material_missing",
    }
    assert report["material_variants"][0]["material"] == "M_Crate_Body"


# --- AC2, AC3, AC7: export writes the variant textures and records them ----------------------


def test_scn002_a_texture_variant_is_written_at_each_folders_base_colour_size(
    steps: Any, textures: Path
) -> None:
    build_crate()
    root = _export(steps, textures, _declare(textures, [RED]))

    assert _png_dimensions(root / "Desktop" / "T_Crate_Body_BC_Red.png") == (512, 512)
    assert _png_dimensions(root / "Mobile" / "T_Crate_Body_BC_Red.png") == _png_dimensions(
        root / "Mobile" / "T_Crate_Body_BC.png"
    )


def test_the_mobile_variant_is_scaled_to_the_mobile_base_colour(steps: Any, textures: Path) -> None:
    build_crate()
    bpy.data.images["T_Crate_Body_BC_Mobile"].scale(256, 256)

    root = _export(steps, textures, _declare(textures, [RED]))

    assert _png_dimensions(root / "Mobile" / "T_Crate_Body_BC.png") == (256, 256)
    assert _png_dimensions(root / "Mobile" / "T_Crate_Body_BC_Red.png") == (256, 256)
    assert _png_dimensions(root / "Desktop" / "T_Crate_Body_BC_Red.png") == (512, 512)


def test_scn003_a_parameter_variant_writes_no_texture_and_lists_its_tint(
    steps: Any, textures: Path
) -> None:
    build_crate()
    root = _export(steps, textures, _declare(textures, [BLUE_TINT]))

    assert not list((root / "Desktop").glob("T_Crate_*_BC_Blue.png"))
    assert not list((root / "Mobile").glob("T_Crate_*_BC_Blue.png"))
    variants = _sidecar(root)["material_variants"]
    assert variants["desktop"] == [
        {
            "name": "Blue",
            "material": "M_Crate_Body",
            "base_color": None,
            "parameters": {"Tint": [0.5, 0.25, 1.0, 1.0]},
            "material_instance": "MI_Crate_Body_Blue",
        }
    ]
    assert variants["mobile"] == variants["desktop"]


def test_scn007_the_sidecar_lists_each_texture_variant_for_both_folders(
    steps: Any, textures: Path
) -> None:
    build_crate()
    root = _export(steps, textures, _declare(textures, [RED]))

    variants = _sidecar(root)["material_variants"]
    expected = {
        "name": "Red",
        "material": "M_Crate_Body",
        "base_color": "T_Crate_Body_BC_Red.png",
        "parameters": {},
        "material_instance": "MI_Crate_Body_Red",
    }
    assert variants == {"desktop": [expected], "mobile": [expected]}


def test_scn004_without_a_declaration_the_export_matches_the_unfeatured_export(
    steps: Any, textures: Path
) -> None:
    build_crate()
    root = _export(steps, textures, None)

    assert "material_variants" not in _sidecar(root)
    assert {path.name for path in (root / "Desktop").iterdir()} == {
        "SM_Crate.fbx",
        "T_Crate_Body_BC.png",
        "T_Crate_Body_N.png",
        "T_Crate_Body_ORM.png",
    }
    assert {path.name for path in (root / "Mobile").iterdir()} == {
        "SM_Crate.fbx",
        "T_Crate_Body_BC.png",
        "T_Crate_Body_N.png",
        "T_Crate_Body_ORM.png",
        "nmg-asset.json",
    }


# --- AC9: removing a variant deletes its texture from both folders ----------------------------


def test_scn009_removing_a_variant_deletes_its_texture_from_both_folders(
    steps: Any, textures: Path
) -> None:
    build_crate()
    first = _export(steps, textures, _declare(textures, [RED, BLUE_TEXTURE]), name="first")
    assert (first / "Desktop" / "T_Crate_Body_BC_Blue.png").is_file()
    assert (first / "Mobile" / "T_Crate_Body_BC_Blue.png").is_file()

    second = _export(steps, textures, _declare(textures, [RED]), name="second")

    assert not (second / "Desktop" / "T_Crate_Body_BC_Blue.png").exists()
    assert not (second / "Mobile" / "T_Crate_Body_BC_Blue.png").exists()
    assert (second / "Desktop" / "T_Crate_Body_BC_Red.png").is_file()
    assert [entry["name"] for entry in _sidecar(second)["material_variants"]["desktop"]] == ["Red"]
