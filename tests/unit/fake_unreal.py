"""A fake ``unreal`` module that runs UE Python from ``build_terrain_code`` in CPython (#154).

The generated code imports ``unreal`` and calls the editor APIs it needs: asset import tasks,
asset library, texture properties, the level subsystems, and ``NmgLandscapeLibrary``. ``FakeEditor``
records every call in order and holds the level and asset state. Tests set ``fail_on`` to make a
named call raise, and ``sampled_cm`` to set what ``sample_heights`` returns for each point.

``run_generated_code`` installs the fake as ``sys.modules["unreal"]``, executes the code, and
returns the text it printed. The generated code prints one ``NMG_RESULT`` line, so tests parse
that with ``import_asset.parse_nmg_result``.
"""

from __future__ import annotations

import contextlib
import io
import sys
from collections.abc import Iterator, Mapping
from types import ModuleType
from typing import Any

MAIN_MAP = "/Game/Maps/Main"


class FakeTexture:
    """A texture imported by an ``AssetImportTask``. Property writes are recorded."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.properties: dict[str, Any] = {}

    def set_editor_property(self, name: str, value: Any) -> None:
        self.properties[name] = value


class FakeAsset:
    """Any other asset the generated code creates: a material, a layer info, or a landscape."""

    def __init__(self, path: str, **attributes: Any) -> None:
        self.path = path
        self.attributes = attributes


class FakeLandscape:
    """The Landscape actor that ``import_landscape`` returns."""

    def __init__(self, level: str, arguments: Mapping[str, Any]) -> None:
        self.level = level
        self.arguments = dict(arguments)


class FakeEditor:
    """Editor state and call log shared by every fake API in one run.

    Attributes:
        levels: Existing level paths. ``MAIN_MAP`` starts open and exists.
        open_level: The level that ``get_editor_world`` reports.
        assets: Textures and other assets by path.
        calls: Every fake call in order, as ``name`` or ``name:detail`` strings.
        import_files: The file of each ``AssetImportTask``, in order.
        import_tasks: The flags of each ``AssetImportTask``, for the texture settings checks.
        material_args: The last ``build_layered_material`` arguments, by name.
        layer_info_args: The ``create_layer_info`` arguments, in call order.
        landscape_args: The last ``import_landscape`` arguments, by name.
        saved: Levels saved by ``save_current_level``.
        loaded: Levels passed to ``load_level``.
        sampled_cm: The height ``sample_heights`` returns for each ``(x, y)`` point, in cm.
        sample_offset_cm: Added to every sampled height, to inject an error.
        fail_on: Call names that raise ``RuntimeError`` when reached.
    """

    def __init__(self) -> None:
        self.levels: set[str] = {MAIN_MAP}
        self.open_level: str | None = MAIN_MAP
        self.assets: dict[str, Any] = {}
        self.calls: list[str] = []
        self.import_files: list[str] = []
        self.import_tasks: list[dict[str, Any]] = []
        self.material_args: dict[str, Any] = {}
        self.layer_info_args: list[dict[str, Any]] = []
        self.landscape_args: dict[str, Any] = {}
        self.saved: list[str] = []
        self.loaded: list[str] = []
        self.sampled_cm: dict[tuple[float, float], float] = {}
        self.sample_offset_cm: float = 0.0
        self.fail_on: set[str] = set()

    def record(self, call: str) -> None:
        self.calls.append(call)

    def check(self, name: str) -> None:
        self.record(name)
        if name in self.fail_on:
            raise RuntimeError(f"fake failure in {name}")


class _Vector:
    def __init__(self, x: float = 0.0, y: float = 0.0, z: float = 0.0) -> None:
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)


class _Vector2D:
    def __init__(self, x: float = 0.0, y: float = 0.0) -> None:
        self.x = float(x)
        self.y = float(y)


class AssetImportTask:
    """Plain attributes, as the generated code sets them. ``import_asset_tasks`` reads them."""

    def __init__(self) -> None:
        self.filename = ""
        self.destination_path = ""
        self.destination_name = ""
        self.automated = False
        self.replace_existing = False
        self.save = False


class TextureCompressionSettings:
    TC_NORMALMAP = "TC_NORMALMAP"
    TC_MASKS = "TC_MASKS"


class LevelEditorSubsystem:
    """Marker class: the generated code passes it to ``get_editor_subsystem``."""


class UnrealEditorSubsystem:
    """Marker class: the generated code passes it to ``get_editor_subsystem``."""


class _AssetTools:
    def __init__(self, editor: FakeEditor) -> None:
        self._editor = editor

    def import_asset_tasks(self, tasks: list[AssetImportTask]) -> None:
        editor = self._editor
        editor.check("import_asset_tasks")
        for task in tasks:
            editor.import_files.append(task.filename)
            editor.import_tasks.append(
                {
                    "filename": task.filename,
                    "destination_path": task.destination_path,
                    "destination_name": task.destination_name,
                    "automated": task.automated,
                    "replace_existing": task.replace_existing,
                    "save": task.save,
                }
            )
            path = task.destination_path + "/" + task.destination_name
            editor.assets[path] = FakeTexture(path)


class _AssetToolsHelpers:
    def __init__(self, editor: FakeEditor) -> None:
        self._editor = editor

    def get_asset_tools(self) -> _AssetTools:
        return _AssetTools(self._editor)


class _EditorAssetLibrary:
    def __init__(self, editor: FakeEditor) -> None:
        self._editor = editor

    def load_asset(self, path: str) -> Any:
        return self._editor.assets.get(path)

    def save_loaded_asset(self, asset: Any) -> bool:
        self._editor.record(f"save_asset:{asset.path}")
        return True

    def does_asset_exist(self, path: str) -> bool:
        return path in self._editor.levels or path in self._editor.assets

    def delete_asset(self, path: str) -> bool:
        editor = self._editor
        editor.check(f"delete_asset:{path}")
        editor.levels.discard(path)
        editor.assets.pop(path, None)
        return True


class _FakeWorld:
    def __init__(self, level: str) -> None:
        self._level = level

    def get_path_name(self) -> str:
        return f"{self._level}.{self._level.rsplit('/', 1)[-1]}"


class _UnrealEditorSubsystem:
    def __init__(self, editor: FakeEditor) -> None:
        self._editor = editor

    def get_editor_world(self) -> _FakeWorld | None:
        level = self._editor.open_level
        return None if level is None else _FakeWorld(level)


class _LevelEditorSubsystem:
    def __init__(self, editor: FakeEditor) -> None:
        self._editor = editor

    def new_level(self, path: str) -> bool:
        editor = self._editor
        editor.check(f"new_level:{path}")
        if path in editor.levels:
            return False
        editor.levels.add(path)
        editor.open_level = path
        return True

    def load_level(self, path: str) -> bool:
        editor = self._editor
        editor.check(f"load_level:{path}")
        editor.loaded.append(path)
        if path not in editor.levels:
            return False
        editor.open_level = path
        return True

    def save_current_level(self) -> bool:
        editor = self._editor
        editor.check(f"save_current_level:{editor.open_level}")
        editor.saved.append(str(editor.open_level))
        return True


class _NmgLandscapeLibrary:
    """Stands in for the C++ ``UNmgLandscapeLibrary`` static functions."""

    def __init__(self, editor: FakeEditor) -> None:
        self._editor = editor

    def build_layered_material(
        self,
        dest: str,
        name: str,
        layers: list[str],
        bc: list[FakeTexture],
        n: list[FakeTexture],
        orm: list[FakeTexture],
        mapping_scale: float,
    ) -> FakeAsset:
        editor = self._editor
        editor.check("build_layered_material")
        editor.material_args = {
            "dest": dest,
            "name": name,
            "layers": list(layers),
            "bc": [texture.path for texture in bc],
            "n": [texture.path for texture in n],
            "orm": [texture.path for texture in orm],
            "mapping_scale": mapping_scale,
        }
        material = FakeAsset(dest + "/" + name)
        editor.assets[material.path] = material
        return material

    def create_layer_info(self, dest: str, name: str, layer: str) -> FakeAsset:
        editor = self._editor
        editor.check(f"create_layer_info:{name}")
        editor.layer_info_args.append({"dest": dest, "name": name, "layer": layer})
        info = FakeAsset(dest + "/" + name, layer=layer)
        editor.assets[info.path] = info
        return info

    def import_landscape(
        self,
        world: _FakeWorld,
        heightmap: str,
        weightmaps: list[str],
        layer_infos: list[FakeAsset],
        material: FakeAsset,
        n: int,
        location: _Vector,
        scale: _Vector,
    ) -> FakeLandscape:
        editor = self._editor
        editor.check("import_landscape")
        editor.landscape_args = {
            "level": world._level,
            "heightmap": heightmap,
            "weightmaps": list(weightmaps),
            "layer_infos": [info.path for info in layer_infos],
            "material": material.path,
            "n": n,
            "location": (location.x, location.y, location.z),
            "scale": (scale.x, scale.y, scale.z),
        }
        return FakeLandscape(world._level, editor.landscape_args)

    def sample_heights(self, landscape: FakeLandscape, points: list[_Vector2D]) -> list[float]:
        editor = self._editor
        editor.check("sample_heights")
        heights: list[float] = []
        for point in points:
            key = (point.x, point.y)
            if key not in editor.sampled_cm:
                raise RuntimeError(f"fake sample_heights has no height for {key}")
            heights.append(editor.sampled_cm[key] + editor.sample_offset_cm)
        return heights


def make_unreal_module(editor: FakeEditor) -> ModuleType:
    """Return a module object that stands in for ``unreal``, backed by ``editor``."""
    module = ModuleType("unreal")
    attributes: dict[str, Any] = {
        "AssetImportTask": AssetImportTask,
        "TextureCompressionSettings": TextureCompressionSettings,
        "LevelEditorSubsystem": LevelEditorSubsystem,
        "UnrealEditorSubsystem": UnrealEditorSubsystem,
        "Vector": _Vector,
        "Vector2D": _Vector2D,
        "AssetToolsHelpers": _AssetToolsHelpers(editor),
        "EditorAssetLibrary": _EditorAssetLibrary(editor),
        "NmgLandscapeLibrary": _NmgLandscapeLibrary(editor),
        "get_editor_subsystem": _subsystem_getter(editor),
    }
    vars(module).update(attributes)
    return module


def _subsystem_getter(editor: FakeEditor) -> Any:
    subsystems: dict[type, Any] = {
        LevelEditorSubsystem: _LevelEditorSubsystem(editor),
        UnrealEditorSubsystem: _UnrealEditorSubsystem(editor),
    }

    def get_editor_subsystem(cls: type) -> Any:
        if cls not in subsystems:
            raise RuntimeError(f"fake unreal has no editor subsystem {cls.__name__}")
        return subsystems[cls]

    return get_editor_subsystem


@contextlib.contextmanager
def installed(editor: FakeEditor) -> Iterator[ModuleType]:
    """Install the fake ``unreal`` as ``sys.modules["unreal"]`` for the ``with`` block."""
    module = make_unreal_module(editor)
    previous = sys.modules.get("unreal")
    sys.modules["unreal"] = module
    try:
        yield module
    finally:
        if previous is None:
            sys.modules.pop("unreal", None)
        else:
            sys.modules["unreal"] = previous


def run_generated_code(code: str, editor: FakeEditor) -> str:
    """Execute UE Python ``code`` against ``editor`` and return what it printed."""
    output = io.StringIO()
    namespace: dict[str, Any] = {"__name__": "__ue_generated__"}
    with installed(editor), contextlib.redirect_stdout(output):
        exec(compile(code, "<ue-terrain>", "exec"), namespace)
    return output.getvalue()
