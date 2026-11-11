"""Host tests for material variants: the request, cache keys, UE import, listing, and CLI (#148).

The UE code never reaches an editor. A dict-backed fake ``unreal`` module runs the import and
listing templates in-process, so the stale-deletion and tag logic is exercised as written. The
fake keeps assets by object path, records the tags, parameters, and bindings each call sets, and
records deletions and creations. Tests that need no UE code stay plain.
"""

from __future__ import annotations

import ast
import contextlib
import io
import json
import struct
import sys
import zlib
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest import mock

import pytest

from nmg_game_dev.finalize import build_request, list_material_variants
from nmg_game_dev.finalize.__main__ import EXIT_FAILED, EXIT_OK, main
from nmg_game_dev.finalize.mcp_tools import list_material_variants as list_for_mcp
from nmg_game_dev.pipeline import FinalizeClients, FinalizeRequest, PipelineError, finalize
from nmg_game_dev.pipeline.steps import _STEP_VERSION, STEP_ORDER, settings_hash
from nmg_game_dev.unreal import build_import_code, import_variant
from nmg_game_dev.unreal import list_material_variants as list_rows
from tests.finalize_fakes import FakeBlenderSession, FakeStepRunner, FakeUnrealRunner

REPO_ROOT = Path(__file__).resolve().parents[2]
DESKTOP = "/Game/Props/Crate/Desktop"
MOBILE = "/Game/Props/Crate/Mobile"
MASTER = "/nmg-game-dev/Materials/M_NmgORM"
RED = {"name": "Red", "material": "M_Crate_Body", "base_color": "Red.png"}
BLUE_TINT = {"name": "Blue", "material": "M_Crate_Body", "parameters": {"Tint": [0.5, 0.25, 1.0]}}
BLUE_TEXTURE = {"name": "Blue", "material": "M_Crate_Body", "base_color": "Blue.png"}


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


def _ue_params(code: str) -> dict[str, Any]:
    line = next(line for line in code.splitlines() if line.startswith("PARAMS = json.loads("))
    decoded = ast.literal_eval(line[len("PARAMS = json.loads(") : -1])
    params: dict[str, Any] = json.loads(decoded)
    return params


def _report(variant: str = "desktop") -> dict[str, Any]:
    """A pre-export report with one mesh part, local bounds in Blender meters (Z-up)."""
    return {
        "kind": "contract",
        "asset": "Crate",
        "class": "standard_prop",
        "passed": True,
        "findings": [],
        "snapshot": {
            "SM_Crate": {
                "variant": variant,
                "type": "MESH",
                "local_bounds": {"min": [-0.5, 0.1, 0.0], "max": [0.5, 0.4, 1.0]},
            },
            "M_Crate_Body": {"variant": variant, "type": "MATERIAL"},
        },
    }


def _variant_dir(root: Path, variant: str, textures: list[str]) -> Path:
    """A variant folder with the FBX, the main textures, and the named variant textures."""
    directory = root / variant
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "SM_Crate.fbx").write_bytes(b"fbx")
    for name in ("T_Crate_Body_BC", "T_Crate_Body_N", "T_Crate_Body_ORM", *textures):
        (directory / f"{name}.png").write_bytes(b"png")
    return directory


# --- a dict-backed fake unreal module ---------------------------------------------------------


class _Obj:
    def __init__(self, **fields: Any) -> None:
        self.__dict__.update(fields)


class _Asset:
    def __init__(self, path: str) -> None:
        self.path = path
        self.dir, self.name = path.rsplit("/", 1)
        self.tags: dict[str, str] = {}
        self.props: dict[str, Any] = {}
        self.textures: dict[str, Any] = {}
        self.vectors: dict[str, Any] = {}
        self.parent: Any = None
        self.static_materials: list[_Obj] = []
        self.bound: dict[int, str] = {}

    def set_editor_property(self, name: str, value: Any) -> None:
        self.props[name] = value

    def get_bounding_box(self) -> _Obj:
        return _Obj(min=_Obj(x=-50.0, y=-40.0, z=0.0), max=_Obj(x=50.0, y=-10.0, z=100.0))

    def set_material(self, index: int, instance: _Asset) -> None:
        self.bound[index] = instance.path


class StaticMesh(_Asset):
    pass


class SkeletalMesh(_Asset):
    pass


class MaterialInstanceConstant(_Asset):
    pass


class Material(_Asset):
    pass


class Texture2D(_Asset):
    pass


class _Store:
    """UE assets by object path, and what the code created and deleted."""

    def __init__(self) -> None:
        self.assets: dict[str, _Asset] = {}
        self.created: list[str] = []
        self.deleted: list[str] = []
        self.assets[MASTER] = Material(MASTER)


def _fake_unreal(store: _Store) -> ModuleType:
    module = ModuleType("unreal")

    class EditorAssetLibrary:
        @staticmethod
        def load_asset(path: str) -> _Asset | None:
            return store.assets.get(path)

        @staticmethod
        def does_asset_exist(path: str) -> bool:
            return path in store.assets

        @staticmethod
        def does_directory_exist(path: str) -> bool:
            return any(asset.dir == path for asset in store.assets.values())

        @staticmethod
        def list_assets(
            directory: str, recursive: bool = False, include_folder: bool = False
        ) -> list[str]:
            _ = (recursive, include_folder)
            return sorted(
                f"{asset.path}.{asset.name}"
                for asset in store.assets.values()
                if asset.dir == directory
            )

        @staticmethod
        def save_loaded_asset(asset: _Asset) -> bool:
            _ = asset
            return True

        @staticmethod
        def get_metadata_tag(asset: _Asset, key: str) -> str:
            return asset.tags.get(key, "")

        @staticmethod
        def set_metadata_tag(asset: _Asset, key: str, value: str) -> None:
            asset.tags[key] = value

        @staticmethod
        def delete_asset(path: str) -> bool:
            store.deleted.append(path)
            store.assets.pop(path, None)
            return True

    class _AssetTools:
        @staticmethod
        def import_asset_tasks(tasks: list[Any]) -> None:
            for task in tasks:
                if task.filename.endswith(".png"):
                    path = f"{task.destination_path}/{task.destination_name}"
                    store.assets[path] = Texture2D(path)
                else:
                    path = f"{task.destination_path}/SM_Crate"
                    mesh = StaticMesh(path)
                    mesh.static_materials = [_Obj(material_slot_name="M_Crate_Body")]
                    store.assets[path] = mesh
                    task.imported_object_paths = [f"{path}.SM_Crate"]

        @staticmethod
        def create_asset(name: str, dest: str, kind: Any, factory: Any) -> _Asset:
            _ = factory
            path = f"{dest}/{name}"
            asset: _Asset = kind(path)
            store.assets[path] = asset
            store.created.append(path)
            return asset

    class AssetToolsHelpers:
        @staticmethod
        def get_asset_tools() -> _AssetTools:
            return _AssetTools()

    class AssetImportTask:
        def __init__(self) -> None:
            self.imported_object_paths: list[str] = []

    class FbxImportUI:
        def __init__(self) -> None:
            self.static_mesh_import_data = _Obj()

    class LinearColor:
        def __init__(self, r: float, g: float, b: float, a: float) -> None:
            self.values = (r, g, b, a)

    class MaterialEditingLibrary:
        @staticmethod
        def set_material_instance_parent(instance: _Asset, parent: Any) -> None:
            instance.parent = parent

        @staticmethod
        def set_material_instance_texture_parameter_value(
            instance: _Asset, name: str, texture: Any
        ) -> None:
            instance.textures[name] = texture

        @staticmethod
        def set_material_instance_vector_parameter_value(
            instance: _Asset, name: str, value: Any
        ) -> None:
            instance.vectors[name] = value

    module.EditorAssetLibrary = EditorAssetLibrary  # type: ignore[attr-defined]
    module.AssetToolsHelpers = AssetToolsHelpers  # type: ignore[attr-defined]
    module.AssetImportTask = AssetImportTask  # type: ignore[attr-defined]
    module.FbxImportUI = FbxImportUI  # type: ignore[attr-defined]
    module.FBXImportType = _Obj(FBXIT_SKELETAL_MESH="skeletal")  # type: ignore[attr-defined]
    module.TextureCompressionSettings = _Obj(TC_NORMALMAP="normal", TC_MASKS="masks")  # type: ignore[attr-defined]
    module.MaterialEditingLibrary = MaterialEditingLibrary  # type: ignore[attr-defined]
    module.LinearColor = LinearColor  # type: ignore[attr-defined]
    module.StaticMesh = StaticMesh  # type: ignore[attr-defined]
    module.SkeletalMesh = SkeletalMesh  # type: ignore[attr-defined]
    module.MaterialInstanceConstant = MaterialInstanceConstant  # type: ignore[attr-defined]
    module.MaterialInstanceConstantFactoryNew = lambda: "factory"  # type: ignore[attr-defined]
    module.Material = Material  # type: ignore[attr-defined]
    module.Texture2D = Texture2D  # type: ignore[attr-defined]
    return module


def run_ue_text(code: str, store: _Store) -> str:
    """Run UE Python against the fake module and return what it printed."""
    buffer = io.StringIO()
    with (
        mock.patch.dict(sys.modules, {"unreal": _fake_unreal(store)}),
        contextlib.redirect_stdout(buffer),
    ):
        exec(compile(code, "<ue>", "exec"), {"__name__": "ue_code"})  # noqa: S102
    return buffer.getvalue()


class FakeEditor:
    """Satisfies UnrealPythonClient: each call runs the code against the shared store."""

    def __init__(self, store: _Store) -> None:
        self.store = store
        self.codes: list[str] = []

    def execute_python_code(self, code: str) -> str:
        self.codes.append(code)
        return run_ue_text(code, self.store)


def _result_of(output: str) -> dict[str, Any]:
    line = next(line for line in output.splitlines() if line.startswith("NMG_RESULT "))
    result: dict[str, Any] = json.loads(line[len("NMG_RESULT ") :])
    return result


def _import(
    store: _Store,
    variant_dir: Path,
    dest: str,
    entries: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    return import_variant(
        FakeEditor(store),
        variant_dir=str(variant_dir),
        dest=dest,
        name="Crate",
        report=_report("mobile" if dest.endswith("Mobile") else "desktop"),
        material_variants=entries,
    )


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


def _keys(request: FinalizeRequest) -> dict[str, str]:
    return {step: settings_hash(step, request, "budgets") for step in STEP_ORDER}


def test_step_version_is_four() -> None:
    assert _STEP_VERSION == "4"


def test_a_declaration_change_moves_only_the_validate_and_export_keys(tmp_path: Path) -> None:
    _png(tmp_path / "Red.png", 512)
    blend = _blend(tmp_path)
    declaration = _declaration(tmp_path, [RED])
    before = _keys(_request(blend, tmp_path / "export", declaration))

    _declaration(tmp_path, [RED, BLUE_TINT])
    after = _keys(_request(blend, tmp_path / "export", declaration))

    assert {step for step in STEP_ORDER if before[step] != after[step]} == {"validate", "export"}


def test_a_changed_texture_byte_moves_the_validate_and_export_keys(tmp_path: Path) -> None:
    _png(tmp_path / "Red.png", 512, (10, 10, 10))
    blend = _blend(tmp_path)
    declaration = _declaration(tmp_path, [RED])
    before = _keys(_request(blend, tmp_path / "export", declaration))

    _png(tmp_path / "Red.png", 512, (200, 10, 10))
    after = _keys(_request(blend, tmp_path / "export", declaration))

    assert {step for step in STEP_ORDER if before[step] != after[step]} == {"validate", "export"}


def test_no_declaration_keys_match_each_other_across_runs(tmp_path: Path) -> None:
    first = _keys(_request(None, tmp_path / "export"))
    second = _keys(_request(None, tmp_path / "export"))

    assert first == second


# --- AC2, AC3, AC9: the UE import creates, tags, reuses, and deletes variant assets ----------


def test_a_texture_variant_is_created_beside_the_main_set_with_its_textures(tmp_path: Path) -> None:
    store = _Store()
    desktop = _variant_dir(tmp_path, "Desktop", ["T_Crate_Body_BC_Red"])

    entry = {
        "name": "Red",
        "material": "M_Crate_Body",
        "base_color": "T_Crate_Body_BC_Red.png",
        "parameters": {},
        "material_instance": "MI_Crate_Body_Red",
    }

    result = _import(store, desktop, DESKTOP, [entry])

    instance = store.assets[f"{DESKTOP}/MI_Crate_Body_Red"]
    assert isinstance(instance, MaterialInstanceConstant)
    assert instance.parent.path == MASTER
    assert instance.textures["BaseColor"].path == f"{DESKTOP}/T_Crate_Body_BC_Red"
    assert instance.textures["Normal"].path == f"{DESKTOP}/T_Crate_Body_N"
    assert instance.textures["ORM"].path == f"{DESKTOP}/T_Crate_Body_ORM"
    assert store.assets[f"{DESKTOP}/T_Crate_Body_BC_Red"].props["srgb"] is True
    assert result["material_variants"] == {
        "Red": {
            "material": "M_Crate_Body",
            "instance": f"{DESKTOP}/MI_Crate_Body_Red",
            "texture": f"{DESKTOP}/T_Crate_Body_BC_Red",
        }
    }


def test_variant_instances_are_tagged_and_never_bound_to_the_mesh_slot(tmp_path: Path) -> None:
    store = _Store()
    desktop = _variant_dir(tmp_path, "Desktop", ["T_Crate_Body_BC_Red"])
    entry = {
        "name": "Red",
        "material": "M_Crate_Body",
        "base_color": "T_Crate_Body_BC_Red.png",
        "parameters": {},
        "material_instance": "MI_Crate_Body_Red",
    }

    _import(store, desktop, DESKTOP, [entry])

    instance = store.assets[f"{DESKTOP}/MI_Crate_Body_Red"]
    assert instance.tags == {
        "nmg.asset": "Crate",
        "nmg.material_variant": "Red",
        "nmg.material_slot": "M_Crate_Body",
    }
    mesh = store.assets[f"{DESKTOP}/SM_Crate"]
    assert mesh.bound == {0: f"{DESKTOP}/MI_Crate_Body"}


def test_a_parameter_variant_sets_tint_and_keeps_the_main_textures(tmp_path: Path) -> None:
    store = _Store()
    desktop = _variant_dir(tmp_path, "Desktop", [])
    entry = {
        "name": "Blue",
        "material": "M_Crate_Body",
        "base_color": None,
        "parameters": {"Tint": [0.5, 0.25, 1.0, 1.0]},
        "material_instance": "MI_Crate_Body_Blue",
    }

    result = _import(store, desktop, DESKTOP, [entry])

    instance = store.assets[f"{DESKTOP}/MI_Crate_Body_Blue"]
    assert instance.vectors["Tint"].values == (0.5, 0.25, 1.0, 1.0)
    assert instance.textures["BaseColor"].path == f"{DESKTOP}/T_Crate_Body_BC"
    assert not any(path.endswith("_BC_Blue") for path in store.assets)
    assert result["material_variants"]["Blue"]["texture"] is None


def test_the_variant_texture_is_imported_in_both_folders_with_the_same_names(
    tmp_path: Path,
) -> None:
    store = _Store()
    entry = {
        "name": "Red",
        "material": "M_Crate_Body",
        "base_color": "T_Crate_Body_BC_Red.png",
        "parameters": {},
        "material_instance": "MI_Crate_Body_Red",
    }
    _import(store, _variant_dir(tmp_path, "Desktop", ["T_Crate_Body_BC_Red"]), DESKTOP, [entry])
    _import(store, _variant_dir(tmp_path, "Mobile", ["T_Crate_Body_BC_Red"]), MOBILE, [entry])

    assert f"{DESKTOP}/MI_Crate_Body_Red" in store.assets
    assert f"{MOBILE}/MI_Crate_Body_Red" in store.assets
    assert store.assets[f"{MOBILE}/T_Crate_Body_BC_Red"].props["srgb"] is True


def test_removing_a_variant_deletes_its_tagged_assets_and_reports_them(tmp_path: Path) -> None:
    store = _Store()
    red = {
        "name": "Red",
        "material": "M_Crate_Body",
        "base_color": "T_Crate_Body_BC_Red.png",
        "parameters": {},
        "material_instance": "MI_Crate_Body_Red",
    }
    blue = {
        "name": "Blue",
        "material": "M_Crate_Body",
        "base_color": "T_Crate_Body_BC_Blue.png",
        "parameters": {},
        "material_instance": "MI_Crate_Body_Blue",
    }
    _import(
        store,
        _variant_dir(tmp_path, "Desktop", ["T_Crate_Body_BC_Red", "T_Crate_Body_BC_Blue"]),
        DESKTOP,
        [red, blue],
    )
    red_created = store.created.count(f"{DESKTOP}/MI_Crate_Body_Red")

    # The author removed Blue, and the export deleted its texture from the folder.
    (tmp_path / "Desktop" / "T_Crate_Body_BC_Blue.png").unlink()
    result = _import(store, tmp_path / "Desktop", DESKTOP, [red])

    assert result["removed"] == [
        f"{DESKTOP}/MI_Crate_Body_Blue",
        f"{DESKTOP}/T_Crate_Body_BC_Blue",
    ]
    assert f"{DESKTOP}/MI_Crate_Body_Blue" not in store.assets
    assert f"{DESKTOP}/T_Crate_Body_BC_Blue" not in store.assets
    assert f"{DESKTOP}/T_Crate_Body_BC_Red" in store.assets
    assert store.created.count(f"{DESKTOP}/MI_Crate_Body_Red") == red_created == 1


def test_reimporting_the_same_declaration_reuses_every_variant_asset(tmp_path: Path) -> None:
    store = _Store()
    entry = {
        "name": "Red",
        "material": "M_Crate_Body",
        "base_color": "T_Crate_Body_BC_Red.png",
        "parameters": {},
        "material_instance": "MI_Crate_Body_Red",
    }
    desktop = _variant_dir(tmp_path, "Desktop", ["T_Crate_Body_BC_Red"])
    _import(store, desktop, DESKTOP, [entry])

    result = _import(store, desktop, DESKTOP, [entry])

    assert result["removed"] == []
    assert store.created.count(f"{DESKTOP}/MI_Crate_Body_Red") == 1


def test_without_material_variants_the_bindings_are_unchanged(tmp_path: Path) -> None:
    store = _Store()
    desktop = _variant_dir(tmp_path, "Desktop", [])

    result = _import(store, desktop, DESKTOP, None)

    assert result["ok"] is True
    assert result["materials"] == {"M_Crate_Body": f"{DESKTOP}/MI_Crate_Body"}
    assert result["material_variants"] == {}
    assert result["removed"] == []
    assert store.assets[f"{DESKTOP}/SM_Crate"].bound == {0: f"{DESKTOP}/MI_Crate_Body"}


def test_build_import_code_embeds_each_declared_entry_for_the_template() -> None:
    entries = [
        {
            "name": "Red",
            "material": "M_Crate_Body",
            "base_color": "T_Crate_Body_BC_Red.png",
            "parameters": {},
            "material_instance": "MI_Crate_Body_Red",
        }
    ]

    code = build_import_code(
        "/work/Desktop", DESKTOP, "Crate", _report(), material_variants=entries
    )

    assert _ue_params(code)["material_variants"] == entries
    assert "_BC_" in code  # the template treats a variant base colour as sRGB


def test_the_import_step_passes_each_variants_sidecar_list_to_unreal(tmp_path: Path) -> None:
    class _DeclaringRunner(FakeStepRunner):
        def _export_outputs(self, job_dir: Path) -> dict[str, Any]:
            outputs = super()._export_outputs(job_dir)
            entry = {
                "name": "Red",
                "material": "M_Crate_Body",
                "base_color": "T_Crate_Body_BC_Red.png",
                "parameters": {},
                "material_instance": "MI_Crate_Body_Red",
            }
            Path(outputs["sidecar"]).write_text(
                json.dumps(
                    {"asset": "Crate", "material_variants": {"desktop": [entry], "mobile": [entry]}}
                ),
                encoding="utf-8",
            )
            return outputs

    blend = _blend(tmp_path)
    request = FinalizeRequest(
        collection="Crate",
        category="Props",
        asset_class="standard_prop",
        export_root=tmp_path / "export",
        blend=blend,
    )
    unreal = FakeUnrealRunner()

    finalize(
        request,
        steps=STEP_ORDER,
        force=False,
        cache_dir=tmp_path / "cache",
        runner=_DeclaringRunner(request),
        job_dir=tmp_path / "job",
        clients=FinalizeClients(blender=FakeBlenderSession(), unreal=unreal),
    )

    params = [_ue_params(code) for code in unreal.codes]
    assert [item["material_variants"][0]["name"] for item in params] == ["Red", "Red"]


def test_a_sidecar_without_material_variants_imports_with_none(tmp_path: Path) -> None:
    blend = _blend(tmp_path)
    request = FinalizeRequest(
        collection="Crate",
        category="Props",
        asset_class="standard_prop",
        export_root=tmp_path / "export",
        blend=blend,
    )
    unreal = FakeUnrealRunner()

    finalize(
        request,
        steps=STEP_ORDER,
        force=False,
        cache_dir=tmp_path / "cache",
        runner=FakeStepRunner(request),
        job_dir=tmp_path / "job",
        clients=FinalizeClients(blender=FakeBlenderSession(), unreal=unreal),
    )

    assert [_ue_params(code)["material_variants"] for code in unreal.codes] == [[], []]


# --- AC8 and FR8: listing from the tags -----------------------------------------------------


def _import_both_folders(store: _Store, tmp_path: Path) -> None:
    red = {
        "name": "Red",
        "material": "M_Crate_Body",
        "base_color": "T_Crate_Body_BC_Red.png",
        "parameters": {},
        "material_instance": "MI_Crate_Body_Red",
    }
    blue = {
        "name": "Blue",
        "material": "M_Crate_Body",
        "base_color": None,
        "parameters": {"Tint": [0.5, 0.25, 1.0, 1.0]},
        "material_instance": "MI_Crate_Body_Blue",
    }
    _import(store, _variant_dir(tmp_path, "Desktop", ["T_Crate_Body_BC_Red"]), DESKTOP, [red, blue])
    _import(store, _variant_dir(tmp_path, "Mobile", ["T_Crate_Body_BC_Red"]), MOBILE, [red, blue])


def test_listing_returns_each_variant_with_its_instance_in_both_folders(tmp_path: Path) -> None:
    store = _Store()
    _import_both_folders(store, tmp_path)

    rows = list_rows(FakeEditor(store), "Props", "Crate")

    assert rows == [
        {
            "name": "Blue",
            "material": "M_Crate_Body",
            "desktop": f"{DESKTOP}/MI_Crate_Body_Blue",
            "mobile": f"{MOBILE}/MI_Crate_Body_Blue",
        },
        {
            "name": "Red",
            "material": "M_Crate_Body",
            "desktop": f"{DESKTOP}/MI_Crate_Body_Red",
            "mobile": f"{MOBILE}/MI_Crate_Body_Red",
        },
    ]


def test_listing_returns_an_empty_list_when_nothing_is_tagged_or_the_folders_are_missing() -> None:
    assert list_rows(FakeEditor(_Store()), "Props", "Crate") == []


def test_listing_ignores_untagged_instances_of_other_assets(tmp_path: Path) -> None:
    store = _Store()
    other = MaterialInstanceConstant(f"{DESKTOP}/MI_Crate_Body")
    other.tags = {"nmg.asset": "Chest"}
    store.assets[other.path] = other

    assert list_rows(FakeEditor(store), "Props", "Crate") == []


def test_listing_reports_a_ue_failure_with_the_finalize_code() -> None:
    class _Broken:
        def execute_python_code(self, code: str) -> str:
            _ = code
            return 'NMG_RESULT {"error": "KeyError: x", "instances": [], "ok": false}'

    with pytest.raises(PipelineError) as raised:
        list_rows(_Broken(), "Props", "Crate")

    assert raised.value.code == "finalize.material_variants_failed"


def test_the_mcp_tool_returns_the_same_rows_as_the_listing(tmp_path: Path) -> None:
    store = _Store()
    _import_both_folders(store, tmp_path)

    rows = list_material_variants(category="Props", collection="Crate", client=FakeEditor(store))

    assert rows == list_rows(FakeEditor(store), "Props", "Crate")
    assert list_for_mcp(category="Props", collection="Crate", client=FakeEditor(_Store())) == []


def test_the_mcp_tool_returns_the_unreachable_error_structured() -> None:
    class _Unreachable:
        def execute_python_code(self, code: str) -> str:
            _ = code
            raise PipelineError(
                code="mcp.unreal.unreachable",
                message="no Unreal MCP endpoint",
                remediation="Run scripts/start-unreal-mcp.sh.",
                stage="import_ue",
            )

    result = list_for_mcp(category="Props", collection="Crate", client=_Unreachable())

    assert result == {
        "error": {
            "code": "mcp.unreal.unreachable",
            "message": "no Unreal MCP endpoint",
            "remediation": "Run scripts/start-unreal-mcp.sh.",
            "stage": "import_ue",
        }
    }


def test_the_mcp_tool_refuses_a_name_that_is_not_pascal_case() -> None:
    result = list_for_mcp(category="props", collection="Crate", client=FakeEditor(_Store()))

    assert isinstance(result, dict)
    assert result["error"]["code"] == "finalize.invalid_request"


def test_the_cli_lists_the_rows_as_json(tmp_path: Path) -> None:
    store = _Store()
    _import_both_folders(store, tmp_path)
    stdout, stderr = io.StringIO(), io.StringIO()

    code = main(
        ["material-variants", "--category", "Props", "--collection", "Crate", "--json"],
        stdout=stdout,
        stderr=stderr,
        unreal_client=FakeEditor(store),
    )

    assert code == EXIT_OK
    assert [row["name"] for row in json.loads(stdout.getvalue())] == ["Blue", "Red"]


def test_the_cli_prints_one_line_per_variant_and_says_when_there_are_none() -> None:
    stdout = io.StringIO()
    main(
        ["material-variants", "--category", "Props", "--collection", "Crate"],
        stdout=stdout,
        stderr=io.StringIO(),
        unreal_client=FakeEditor(_Store()),
    )

    assert stdout.getvalue() == "Crate has no material variants in Unreal.\n"


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
        "MI_<Name>_<Part>_<Variant>",
        "material_variant.material_merged",
        "Tint",
    ):
        assert needle in contract, needle
    assert ".material-variants.json" in skill
    assert "material-variants" in skill
    for needle in ("list_material_variants", "material_variants_path"):
        assert needle in mcp, needle
