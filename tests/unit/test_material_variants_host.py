"""Host tests for material variants: the request, cache keys, Godot materials, listing, and CLI.

Material variants (#148) land in the Godot project as ``M_<Name>_<Part>_<Variant>.tres``
``StandardMaterial3D`` files that ``import_godot`` writes into each variant folder (#249). The
listing reads only ``nmg-variants.json`` and those files, so it never starts Godot: the listing
tests make resolving or starting Godot (or any process) fail.
"""

from __future__ import annotations

import io
import json
import struct
import zlib
from pathlib import Path
from typing import Any

import pytest

from nmg_game_dev.finalize import build_request, list_material_variants
from nmg_game_dev.finalize.__main__ import EXIT_FAILED, EXIT_OK, main
from nmg_game_dev.godot.material_variants import (
    list_material_variants as list_rows,
)
from nmg_game_dev.godot.material_variants import (
    render_material,
    resource_name,
    write_variant_materials,
)
from nmg_game_dev.pipeline import FinalizeClients, FinalizeRequest, PipelineError, finalize
from nmg_game_dev.pipeline.steps import _STEP_VERSION, STEP_ORDER, settings_hash
from tests.finalize_fakes import FakeStepRunner, FinalizeGodot
from tests.godot_fakes import forbid_godot

REPO_ROOT = Path(__file__).resolve().parents[2]
RED = {"name": "Red", "material": "M_Crate_Body", "base_color": "Red.png"}
BLUE_TINT = {"name": "Blue", "material": "M_Crate_Body", "parameters": {"Tint": [0.5, 0.25, 1.0]}}
BLUE_TEXTURE = {"name": "Blue", "material": "M_Crate_Body", "base_color": "Blue.png"}
# Sidecar entries, as the export step records them in nmg-variants.json.
RED_ENTRY = {
    "name": "Red",
    "material": "M_Crate_Body",
    "base_color": "T_Crate_Body_BC_Red.png",
    "parameters": {},
}
BLUE_ENTRY = {
    "name": "Blue",
    "material": "M_Crate_Body",
    "base_color": None,
    "parameters": {"Tint": [0.5, 0.25, 1.0, 1.0]},
}
LID_ENTRY = {
    "name": "Red",
    "material": "M_Crate_Lid",
    "base_color": None,
    "parameters": {"Tint": [1.0, 0.0, 0.0, 1.0]},
    "material_resource": "M_Crate_Lid_Red.tres",
}


# --- fixtures and small helpers ---------------------------------------------------------------


@pytest.fixture(autouse=True)
def _project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the project root at an empty directory, so no repository budget or backlog is read."""
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project))
    return project


def _png(path: Path, size: int, rgb: tuple[int, int, int] = (90, 90, 90)) -> Path:
    row = b"\x00" + bytes(rgb) * size
    raw = row * size

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    return path


def _declaration(directory: Path, entries: list[dict[str, Any]]) -> Path:
    path = directory / "Crate.material-variants.json"
    path.write_text(json.dumps({"schema": 1, "material_variants": entries}), encoding="utf-8")
    return path


def _request(
    blend: Path | None, export_root: Path, declaration: Path | None = None
) -> FinalizeRequest:
    return build_request(
        collection="Crate",
        category="Props",
        asset_class="standard_prop",
        export_root=export_root,
        blend=blend,
        material_variants_path=declaration,
    )


def _blend(directory: Path) -> Path:
    blend = directory / "crate.blend"
    blend.write_bytes(b"authored")
    return blend


def _game(root: Path) -> Path:
    """A Godot project at ``root`` (``project.godot``) with ``assets/`` as the export root."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "project.godot").write_text("config_version=5\n", encoding="utf-8")
    return root / "assets"


def _finalized(
    export_root: Path,
    desktop: list[dict[str, Any]],
    mobile: list[dict[str, Any]] | None = None,
    *,
    tres: tuple[str, ...] = (),
) -> Path:
    """An ``<export_root>/Props/Crate`` tree with nmg-variants.json and the named ``.tres`` files.

    ``tres`` names ``<Variant>/<file>`` paths to create.
    """
    asset = export_root / "Props" / "Crate"
    for variant in ("Desktop", "Mobile"):
        (asset / variant).mkdir(parents=True, exist_ok=True)
    payload = {
        "asset": "Crate",
        "material_variants": {
            "desktop": desktop,
            "mobile": desktop if mobile is None else mobile,
        },
    }
    (asset / "nmg-variants.json").write_text(json.dumps(payload), encoding="utf-8")
    for relative in tres:
        (asset / relative).write_text("[gd_resource]\n", encoding="utf-8")
    return asset


# --- AC1 and FR1: the request finds the declaration -------------------------------------------


def test_the_declaration_beside_the_blend_is_found_and_absolute(tmp_path: Path) -> None:
    blend = _blend(tmp_path)
    declaration = _declaration(tmp_path, [RED])

    request = _request(blend, tmp_path / "export")

    assert request.material_variants_path == declaration.resolve()
    assert Path(str(request.to_json_dict()["material_variants_path"])).is_absolute()


def test_an_explicit_declaration_wins_over_the_one_beside_the_blend(tmp_path: Path) -> None:
    blend = _blend(tmp_path)
    _declaration(tmp_path, [RED])
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    explicit = _declaration(elsewhere, [BLUE_TINT])

    request = _request(blend, tmp_path / "export", explicit)

    assert request.material_variants_path == explicit.resolve()


def test_a_missing_explicit_declaration_is_refused_with_its_code(tmp_path: Path) -> None:
    with pytest.raises(PipelineError) as raised:
        _request(_blend(tmp_path), tmp_path / "export", tmp_path / "absent.material-variants.json")

    assert raised.value.code == "finalize.material_variants_not_found"


def test_a_session_run_without_an_explicit_declaration_declares_none(tmp_path: Path) -> None:
    request = _request(None, tmp_path / "export")

    assert request.material_variants_path is None


def test_the_declaration_argument_reaches_the_request_as_given(tmp_path: Path) -> None:
    declaration = _declaration(tmp_path, [RED])
    request = build_request(
        collection="Crate",
        category="Props",
        asset_class="standard_prop",
        export_root=tmp_path / "export",
        material_variants_path=str(declaration),
    )

    assert request.material_variants_path == declaration.resolve()


# --- FR9: the cache keys of validate and export follow the declaration ------------------------


# export_anims and import_anims (#138) are per-clip steps with no whole-step settings hash.
_WHOLE_STEPS = tuple(step for step in STEP_ORDER if step not in ("export_anims", "import_anims"))


def _keys(request: FinalizeRequest) -> dict[str, str]:
    return {step: settings_hash(step, request, "budgets") for step in _WHOLE_STEPS}


def test_step_version_is_five() -> None:
    assert _STEP_VERSION == "5"


def test_a_declaration_change_moves_only_the_validate_and_export_keys(tmp_path: Path) -> None:
    _png(tmp_path / "Red.png", 512)
    blend = _blend(tmp_path)
    declaration = _declaration(tmp_path, [RED])
    before = _keys(_request(blend, tmp_path / "export", declaration))

    _declaration(tmp_path, [RED, BLUE_TINT])
    after = _keys(_request(blend, tmp_path / "export", declaration))

    assert {step for step in _WHOLE_STEPS if before[step] != after[step]} == {"validate", "export"}


def test_a_changed_texture_byte_moves_the_validate_and_export_keys(tmp_path: Path) -> None:
    _png(tmp_path / "Red.png", 512, (10, 10, 10))
    blend = _blend(tmp_path)
    declaration = _declaration(tmp_path, [RED])
    before = _keys(_request(blend, tmp_path / "export", declaration))

    _png(tmp_path / "Red.png", 512, (200, 10, 10))
    after = _keys(_request(blend, tmp_path / "export", declaration))

    assert {step for step in _WHOLE_STEPS if before[step] != after[step]} == {"validate", "export"}


def test_no_declaration_keys_match_each_other_across_runs(tmp_path: Path) -> None:
    first = _keys(_request(None, tmp_path / "export"))
    second = _keys(_request(None, tmp_path / "export"))

    assert first == second


# --- AC6 (#249): import_godot writes one StandardMaterial3D per declared variant -------------


def test_a_texture_variant_uses_its_own_base_colour_and_the_part_normal_and_orm(
    tmp_path: Path,
) -> None:
    folder = _game(tmp_path / "game") / "Props" / "Crate" / "Desktop"
    folder.mkdir(parents=True)

    (path,) = write_variant_materials(tmp_path / "game", folder, "Crate", [RED_ENTRY])

    assert path == folder / "M_Crate_Body_Red.tres"
    text = path.read_text(encoding="utf-8")
    base = "res://assets/Props/Crate/Desktop"
    assert text.startswith('[gd_resource type="StandardMaterial3D"')
    assert "format=3" in text.splitlines()[0]
    assert f'path="{base}/T_Crate_Body_BC_Red.png" id="1_albedo"' in text
    assert f'path="{base}/T_Crate_Body_N.png" id="2_normal"' in text
    assert f'path="{base}/T_Crate_Body_ORM.png" id="3_orm"' in text
    assert 'albedo_texture = ExtResource("1_albedo")' in text
    assert 'normal_texture = ExtResource("2_normal")' in text
    assert "normal_enabled = true" in text
    # ORM: occlusion in red, roughness in green, metallic in blue.
    assert 'ao_texture = ExtResource("3_orm")' in text
    assert "ao_texture_channel = 0" in text
    assert 'roughness_texture = ExtResource("3_orm")' in text
    assert "roughness_texture_channel = 1" in text
    assert 'metallic_texture = ExtResource("3_orm")' in text
    assert "metallic_texture_channel = 2" in text
    # No Tint declared: the albedo colour is white.
    assert "albedo_color = Color(1, 1, 1, 1)" in text
    assert 'resource_name = "M_Crate_Body_Red"' in text


def test_a_parameter_variant_sets_the_tint_and_keeps_the_part_base_colour(
    tmp_path: Path,
) -> None:
    folder = _game(tmp_path / "game") / "Props" / "Crate" / "Mobile"
    folder.mkdir(parents=True)

    (path,) = write_variant_materials(tmp_path / "game", folder, "Crate", [BLUE_ENTRY])

    text = path.read_text(encoding="utf-8")
    assert 'path="res://assets/Props/Crate/Mobile/T_Crate_Body_BC.png" id="1_albedo"' in text
    assert "albedo_color = Color(0.5, 0.25, 1, 1)" in text


def test_a_three_component_tint_gets_full_alpha(tmp_path: Path) -> None:
    folder = _game(tmp_path / "game") / "Props" / "Crate" / "Desktop"
    folder.mkdir(parents=True)
    entry = {**BLUE_ENTRY, "parameters": {"Tint": [0.5, 0.25, 1.0]}}

    text = render_material(tmp_path / "game", folder, "Crate", entry)

    assert "albedo_color = Color(0.5, 0.25, 1, 1)" in text


def test_the_recorded_material_resource_names_the_file(tmp_path: Path) -> None:
    assert resource_name(LID_ENTRY) == "M_Crate_Lid_Red.tres"
    assert resource_name({**LID_ENTRY, "material_resource": "Desktop/M_Crate_Lid_Red.tres"}) == (
        "M_Crate_Lid_Red.tres"
    )
    assert resource_name(RED_ENTRY) == "M_Crate_Body_Red.tres"


def test_removing_a_variant_deletes_only_its_stale_material(tmp_path: Path) -> None:
    folder = _game(tmp_path / "game") / "Props" / "Crate" / "Desktop"
    folder.mkdir(parents=True)
    write_variant_materials(tmp_path / "game", folder, "Crate", [RED_ENTRY, BLUE_ENTRY])
    (folder / "Crate.glb").write_bytes(b"glb")
    (folder / "M_Other_Body_Red.tres").write_text("other asset", encoding="utf-8")

    written = write_variant_materials(tmp_path / "game", folder, "Crate", [RED_ENTRY])

    assert written == [folder / "M_Crate_Body_Red.tres"]
    assert not (folder / "M_Crate_Body_Blue.tres").exists()
    assert (folder / "M_Crate_Body_Red.tres").is_file()
    assert (folder / "Crate.glb").is_file()
    assert (folder / "M_Other_Body_Red.tres").is_file()


def test_a_hand_made_material_in_the_folder_is_never_removed(tmp_path: Path) -> None:
    """Review F20: only .tres files finalize wrote (its manifest) are stale candidates."""
    folder = _game(tmp_path / "game") / "Props" / "Crate" / "Desktop"
    folder.mkdir(parents=True)
    hand_made = folder / "M_Crate_Body_Custom.tres"
    hand_made.write_text("made in the Godot editor", encoding="utf-8")
    write_variant_materials(tmp_path / "game", folder, "Crate", [RED_ENTRY, BLUE_ENTRY])

    write_variant_materials(tmp_path / "game", folder, "Crate", [])

    assert hand_made.read_text(encoding="utf-8") == "made in the Godot editor"
    assert not (folder / "M_Crate_Body_Red.tres").exists()
    assert not (folder / "M_Crate_Body_Blue.tres").exists()


def test_rewriting_the_same_declaration_leaves_the_file_unchanged(tmp_path: Path) -> None:
    folder = _game(tmp_path / "game") / "Props" / "Crate" / "Desktop"
    folder.mkdir(parents=True)
    (path,) = write_variant_materials(tmp_path / "game", folder, "Crate", [RED_ENTRY])
    before = path.read_bytes()

    write_variant_materials(tmp_path / "game", folder, "Crate", [RED_ENTRY])

    assert path.read_bytes() == before


def test_a_material_outside_the_asset_naming_is_a_mismatch(tmp_path: Path) -> None:
    folder = _game(tmp_path / "game") / "Props" / "Crate" / "Desktop"
    folder.mkdir(parents=True)

    with pytest.raises(PipelineError) as raised:
        write_variant_materials(
            tmp_path / "game", folder, "Crate", [{**RED_ENTRY, "material": "M_Barrel_Body"}]
        )

    assert raised.value.code == "import_godot.mismatch"
    assert raised.value.remediation


class _VariantStepRunner(FakeStepRunner):
    """The Blender fake, with an export sidecar that lists material variants."""

    def __init__(self, request: FinalizeRequest, entries: list[dict[str, Any]]) -> None:
        super().__init__(request)
        self.entries = entries

    def _sidecar(self) -> dict[str, Any]:
        payload = super()._sidecar()
        if self.entries:
            payload["material_variants"] = {
                "desktop": self.entries,
                "mobile": [dict(entry) for entry in self.entries],
            }
        return payload


def _finalize(tmp_path: Path, entries: list[dict[str, Any]]) -> tuple[Any, FinalizeGodot]:
    export_root = _game(tmp_path / "game")
    request = _request(_blend(tmp_path), export_root)
    godot = FinalizeGodot(tmp_path / "game")
    result = finalize(
        request,
        cache_dir=tmp_path / "cache",
        runner=_VariantStepRunner(request, entries),
        job_dir=tmp_path / "job",
        clients=FinalizeClients(godot=godot),
    )
    return result, godot


def test_import_godot_writes_each_variants_materials_in_both_folders(tmp_path: Path) -> None:
    result, godot = _finalize(tmp_path, [RED_ENTRY, BLUE_ENTRY, LID_ENTRY])

    asset = tmp_path / "game" / "assets" / "Props" / "Crate"
    for variant in ("Desktop", "Mobile"):
        for name in ("M_Crate_Body_Red.tres", "M_Crate_Body_Blue.tres", "M_Crate_Lid_Red.tres"):
            assert (asset / variant / name).is_file(), f"{variant}/{name}"
    imported = next(step for step in result.steps if step.step == "import_godot")
    assert imported.outputs["imports"]["Desktop"]["material_variants"] == [
        "res://assets/Props/Crate/Desktop/M_Crate_Body_Red.tres",
        "res://assets/Props/Crate/Desktop/M_Crate_Body_Blue.tres",
        "res://assets/Props/Crate/Desktop/M_Crate_Lid_Red.tres",
    ]
    # The materials are written before the one headless import, which picks them up.
    assert godot.count("--import") == 1


def test_a_sidecar_without_material_variants_writes_no_material(tmp_path: Path) -> None:
    result, _godot = _finalize(tmp_path, [])

    asset = tmp_path / "game" / "assets" / "Props" / "Crate"
    assert list(asset.rglob("*.tres")) == []
    imported = next(step for step in result.steps if step.step == "import_godot")
    assert imported.outputs["imports"]["Mobile"]["material_variants"] == []


def test_listing_after_finalize_returns_the_written_materials(tmp_path: Path) -> None:
    _finalize(tmp_path, [RED_ENTRY, BLUE_ENTRY])

    rows = list_material_variants(
        category="Props", collection="Crate", export_root=str(tmp_path / "game" / "assets")
    )

    assert rows == [
        {
            "name": "Blue",
            "material": "M_Crate_Body",
            "desktop": "res://assets/Props/Crate/Desktop/M_Crate_Body_Blue.tres",
            "mobile": "res://assets/Props/Crate/Mobile/M_Crate_Body_Blue.tres",
        },
        {
            "name": "Red",
            "material": "M_Crate_Body",
            "desktop": "res://assets/Props/Crate/Desktop/M_Crate_Body_Red.tres",
            "mobile": "res://assets/Props/Crate/Mobile/M_Crate_Body_Red.tres",
        },
    ]


# --- AC6 and FR6: listing from the files finalize wrote, without Godot ------------------------


def test_listing_returns_sorted_rows_with_paths_only_for_existing_materials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    export_root = _game(tmp_path / "game")
    _finalized(
        export_root,
        [RED_ENTRY, BLUE_ENTRY, LID_ENTRY],
        [RED_ENTRY, LID_ENTRY],
        tres=(
            "Desktop/M_Crate_Body_Red.tres",
            "Desktop/M_Crate_Lid_Red.tres",
            "Mobile/M_Crate_Lid_Red.tres",
        ),
    )
    forbid_godot(monkeypatch)

    rows = list_material_variants(
        category="Props", collection="Crate", export_root=str(export_root)
    )

    assert rows == [
        {"name": "Blue", "material": "M_Crate_Body", "desktop": None, "mobile": None},
        {
            "name": "Red",
            "material": "M_Crate_Body",
            "desktop": "res://assets/Props/Crate/Desktop/M_Crate_Body_Red.tres",
            "mobile": None,
        },
        {
            "name": "Red",
            "material": "M_Crate_Lid",
            "desktop": "res://assets/Props/Crate/Desktop/M_Crate_Lid_Red.tres",
            "mobile": "res://assets/Props/Crate/Mobile/M_Crate_Lid_Red.tres",
        },
    ]


def test_listing_an_asset_without_material_variants_is_empty(tmp_path: Path) -> None:
    export_root = _game(tmp_path / "game")
    asset = export_root / "Props" / "Crate"
    asset.mkdir(parents=True)
    (asset / "nmg-variants.json").write_text('{"asset": "Crate"}', encoding="utf-8")

    assert list_rows(export_root, "Props", "Crate") == []


def test_listing_defaults_to_the_project_game_assets(tmp_path: Path, _project: Path) -> None:
    export_root = _game(_project / "game")
    _finalized(export_root, [RED_ENTRY], tres=("Desktop/M_Crate_Body_Red.tres",))

    rows = list_material_variants(category="Props", collection="Crate")

    assert rows == [
        {
            "name": "Red",
            "material": "M_Crate_Body",
            "desktop": "res://assets/Props/Crate/Desktop/M_Crate_Body_Red.tres",
            "mobile": None,
        }
    ]


def test_a_missing_sidecar_is_material_variants_failed(tmp_path: Path) -> None:
    response = list_material_variants(
        category="Props", collection="Crate", export_root=str(_game(tmp_path / "game"))
    )

    assert isinstance(response, dict)
    assert response["error"]["code"] == "finalize.material_variants_failed"
    assert "nmg-variants.json" in response["error"]["message"]
    assert response["error"]["remediation"]


@pytest.mark.parametrize("text", ["{not json", "[1, 2]"])
def test_an_invalid_sidecar_is_material_variants_failed(tmp_path: Path, text: str) -> None:
    export_root = _game(tmp_path / "game")
    asset = export_root / "Props" / "Crate"
    asset.mkdir(parents=True)
    (asset / "nmg-variants.json").write_text(text, encoding="utf-8")

    with pytest.raises(PipelineError) as raised:
        list_rows(export_root, "Props", "Crate")

    assert raised.value.code == "finalize.material_variants_failed"


def test_an_entry_without_a_name_is_material_variants_failed(tmp_path: Path) -> None:
    export_root = _game(tmp_path / "game")
    _finalized(export_root, [{"material": "M_Crate_Body"}])

    with pytest.raises(PipelineError) as raised:
        list_rows(export_root, "Props", "Crate")

    assert raised.value.code == "finalize.material_variants_failed"


def test_a_material_outside_any_godot_project_is_material_variants_failed(
    tmp_path: Path,
) -> None:
    export_root = tmp_path / "loose"
    _finalized(export_root, [RED_ENTRY], tres=("Desktop/M_Crate_Body_Red.tres",))

    with pytest.raises(PipelineError) as raised:
        list_rows(export_root, "Props", "Crate")

    assert raised.value.code == "finalize.material_variants_failed"


def test_the_mcp_tool_refuses_a_name_that_is_not_pascal_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    forbid_godot(monkeypatch)
    response = list_material_variants(category="props", collection="Crate")

    assert isinstance(response, dict)
    assert response["error"]["code"] == "finalize.invalid_request"


def test_the_cli_lists_the_rows_as_json(tmp_path: Path) -> None:
    export_root = _game(tmp_path / "game")
    _finalized(export_root, [RED_ENTRY], tres=("Mobile/M_Crate_Body_Red.tres",))
    stdout = io.StringIO()

    code = main(
        [
            "material-variants",
            "--category",
            "Props",
            "--collection",
            "Crate",
            "--export-root",
            str(export_root),
            "--json",
        ],
        stdout=stdout,
        stderr=io.StringIO(),
    )

    assert code == EXIT_OK
    assert json.loads(stdout.getvalue()) == [
        {
            "name": "Red",
            "material": "M_Crate_Body",
            "desktop": None,
            "mobile": "res://assets/Props/Crate/Mobile/M_Crate_Body_Red.tres",
        }
    ]


def test_the_cli_prints_one_line_per_variant_and_says_when_there_are_none(
    tmp_path: Path,
) -> None:
    export_root = _game(tmp_path / "game")
    _finalized(export_root, [RED_ENTRY], tres=("Desktop/M_Crate_Body_Red.tres",))
    args = ["material-variants", "--category", "Props", "--collection", "Crate"]
    stdout = io.StringIO()

    assert main([*args, "--export-root", str(export_root)], stdout=stdout) == EXIT_OK
    assert stdout.getvalue() == (
        "Red  M_Crate_Body  Desktop: res://assets/Props/Crate/Desktop/M_Crate_Body_Red.tres  "
        "Mobile: -\n"
    )

    _finalized(export_root, [])
    stdout = io.StringIO()
    assert main([*args, "--export-root", str(export_root)], stdout=stdout) == EXIT_OK
    assert stdout.getvalue() == "Crate has no material variants.\n"


def test_the_cli_reports_a_missing_sidecar_with_exit_one(tmp_path: Path) -> None:
    stderr = io.StringIO()

    code = main(
        [
            "material-variants",
            "--category",
            "Props",
            "--collection",
            "Crate",
            "--export-root",
            str(tmp_path / "nowhere"),
        ],
        stdout=io.StringIO(),
        stderr=stderr,
    )

    assert code == EXIT_FAILED
    assert "ERROR [finalize.material_variants_failed]" in stderr.getvalue()


def test_the_cli_refuses_a_missing_declaration_with_exit_one(tmp_path: Path) -> None:
    stderr = io.StringIO()

    code = main(
        [
            "validate",
            "--collection",
            "Crate",
            "--category",
            "Props",
            "--class",
            "standard_prop",
            "--export-root",
            str(tmp_path / "export"),
            "--material-variants",
            str(tmp_path / "absent.material-variants.json"),
        ],
        stdout=io.StringIO(),
        stderr=stderr,
    )

    assert code == EXIT_FAILED
    assert "ERROR [finalize.material_variants_not_found]" in stderr.getvalue()


# --- AC10: the documents name the feature's contract ----------------------------------------


def test_the_documents_name_the_declaration_naming_rules_and_listing() -> None:
    contract = (REPO_ROOT / "docs" / "asset-contract.md").read_text(encoding="utf-8")
    skill = (REPO_ROOT / "skills" / "finalize-asset" / "SKILL.md").read_text(encoding="utf-8")
    mcp = (REPO_ROOT / "docs" / "mcp" / "finalize.md").read_text(encoding="utf-8")

    for needle in (
        ".material-variants.json",
        "T_<Name>_<Part>_BC_<Variant>",
        "M_<Name>_<Part>_<Variant>.tres",
        "material_variant.material_merged",
        "Tint",
    ):
        assert needle in contract, needle
    assert ".material-variants.json" in skill
    assert "material-variants" in skill
    for needle in ("list_material_variants", "material_variants_path"):
        assert needle in mcp, needle
