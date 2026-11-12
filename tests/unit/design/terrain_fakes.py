"""A fake ``unreal`` module for running the generated region scaffold code (#154 AC5).

The region code is Python text that runs inside the Unreal editor.  ``FakeUnreal`` stands in for the
``unreal`` module it imports.  It keeps the open level, reports the package paths it was given as
existing, and appends every editor call to ``calls`` in order.  ``run`` executes generated code
against the fake and returns the ``NMG_RESULT`` payload the code printed.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
from collections.abc import Iterable
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest import mock

PLANE = "/Engine/BasicShapes/Plane"
DEFAULT_LEVEL = "/Game/Untitled"
_RESULT_PREFIX = "NMG_RESULT "


class UnrealEditorSubsystem:
    """Marker class passed to ``get_editor_subsystem``."""


class LevelEditorSubsystem:
    """Marker class passed to ``get_editor_subsystem``."""


class EditorActorSubsystem:
    """Marker class passed to ``get_editor_subsystem``."""


class StaticMeshActor:
    """Marker class passed to ``spawn_actor_from_class``."""


class PlayerStart:
    """Marker class passed to ``spawn_actor_from_class``."""


class DirectionalLight:
    """Marker class passed to ``spawn_actor_from_class``."""


class SkyLight:
    """Marker class passed to ``spawn_actor_from_class``."""


class LevelStreamingAlwaysLoaded:
    """Marker class passed to ``add_level_to_world``."""


class _Level:
    """The world the editor has open: ``get_editor_world().get_outermost().get_path_name()``."""

    def __init__(self, path: str) -> None:
        self.path = path

    def get_outermost(self) -> _Level:
        return self

    def get_path_name(self) -> str:
        return self.path


class _Actor:
    def __init__(self, fake: FakeUnreal) -> None:
        self._fake = fake
        self.static_mesh_component = SimpleNamespace(set_editor_property=self._set_property)

    def _set_property(self, name: str, value: object) -> None:
        self._fake.calls.append(("set_property", name, value))

    def set_actor_scale3d(self, scale: tuple[float, float, float]) -> None:
        self._fake.calls.append(("scale", scale))


def _vector(x: float, y: float, z: float) -> tuple[float, float, float]:
    return (x, y, z)


class FakeUnreal:
    """Stands in for the ``unreal`` module.  ``existing_assets`` are the package paths present."""

    def __init__(self, existing_assets: Iterable[str] = ()) -> None:
        self.existing_assets = set(existing_assets)
        self.calls: list[tuple[Any, ...]] = []
        self.open_level = DEFAULT_LEVEL
        self.module = self._module()

    def run(self, code: str) -> dict[str, Any]:
        """Execute generated region code against this fake and return its ``NMG_RESULT`` payload."""
        output = io.StringIO()
        with mock.patch.dict(sys.modules, {"unreal": self.module}):
            with contextlib.redirect_stdout(output):
                exec(compile(code, "<region scaffold>", "exec"), {})
        line = output.getvalue().strip().splitlines()[-1]
        assert line.startswith(_RESULT_PREFIX), line
        payload: dict[str, Any] = json.loads(line[len(_RESULT_PREFIX) :])
        return payload

    def spawned(self) -> list[str]:
        """The class names passed to ``spawn_actor_from_class``, in order."""
        return [call[1] for call in self.calls if call[0] == "spawn"]

    def _module(self) -> ModuleType:
        module = ModuleType("unreal")
        vars(module).update(
            UnrealEditorSubsystem=UnrealEditorSubsystem,
            LevelEditorSubsystem=LevelEditorSubsystem,
            EditorActorSubsystem=EditorActorSubsystem,
            StaticMeshActor=StaticMeshActor,
            PlayerStart=PlayerStart,
            DirectionalLight=DirectionalLight,
            SkyLight=SkyLight,
            LevelStreamingAlwaysLoaded=LevelStreamingAlwaysLoaded,
            Vector=_vector,
            get_editor_subsystem=self._subsystem,
            EditorAssetLibrary=SimpleNamespace(
                does_asset_exist=self._does_asset_exist,
                load_asset=self._load_asset,
            ),
            EditorLevelUtils=SimpleNamespace(add_level_to_world=self._add_level_to_world),
        )
        return module

    def _subsystem(self, cls: type) -> SimpleNamespace:
        if cls is UnrealEditorSubsystem:
            return SimpleNamespace(get_editor_world=self._editor_world)
        if cls is LevelEditorSubsystem:
            return SimpleNamespace(
                new_level=self._new_level,
                save_current_level=self._save_current_level,
                load_level=self._load_level,
            )
        if cls is EditorActorSubsystem:
            return SimpleNamespace(spawn_actor_from_class=self._spawn)
        raise AssertionError(f"no fake subsystem for {cls!r}")

    def _editor_world(self) -> _Level:
        return _Level(self.open_level)

    def _new_level(self, path: str) -> bool:
        self.calls.append(("new_level", path))
        self.open_level = path
        return True

    def _load_level(self, path: str) -> bool:
        self.calls.append(("load_level", path))
        self.open_level = path
        return True

    def _save_current_level(self) -> bool:
        self.calls.append(("save_current_level", self.open_level))
        return True

    def _spawn(self, cls: type, location: tuple[float, float, float]) -> _Actor:
        self.calls.append(("spawn", cls.__name__))
        return _Actor(self)

    def _does_asset_exist(self, path: str) -> bool:
        return path in self.existing_assets

    def _load_asset(self, path: str) -> str:
        self.calls.append(("load_asset", path))
        return path

    def _add_level_to_world(self, world: _Level, package: str, streaming: type) -> str:
        self.calls.append(("add_level_to_world", world.path, package, streaming.__name__))
        return package
