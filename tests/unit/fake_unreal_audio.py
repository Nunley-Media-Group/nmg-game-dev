"""Fakes for the audio import tests (#155, FR9): a stand-in ``unreal`` module and a client.

``FakeUnrealPythonClient`` runs the UE code that ``build_audio_import_code`` builds, with ``exec``,
against ``fake_unreal_module``. The code therefore runs as the editor would run it, but nothing
touches a live editor. ``reachable=False`` makes the client raise ``mcp.unreal.unreachable`` the way
``UnrealMcpClient`` does when no endpoint answers. No ElevenLabs call is made anywhere in this file.
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
import types
from collections.abc import Callable
from typing import Any
from unittest import mock

from nmg_game_dev.pipeline.errors import PipelineError

UNREACHABLE_URL = "http://127.0.0.1:8000/mcp"


class FakeSoundWave:
    """A SoundWave the fake editor holds. Its properties are the ones the UE code sets."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.properties: dict[str, Any] = {"looping": False}

    def set_editor_property(self, name: str, value: Any) -> None:
        self.properties[name] = value

    def get_editor_property(self, name: str) -> Any:
        return self.properties[name]


class FakeOtherAsset:
    """An asset of another class, so the ``isinstance(..., unreal.SoundWave)`` check fails."""

    def __init__(self, path: str) -> None:
        self.path = path


class FakeImportTask:
    """Mirrors the attributes ``unreal.AssetImportTask`` exposes to the UE code."""

    def __init__(self) -> None:
        self.filename = ""
        self.destination_path = ""
        self.destination_name = ""
        self.automated = False
        self.replace_existing = False
        self.save = False
        self.imported_object_paths: list[str] = []


class FakeEditor:
    """The fake project state: its assets, the import tasks it received, and what it saved."""

    def __init__(self, produces: Callable[[str], object] = FakeSoundWave) -> None:
        self.produces = produces
        self.assets: dict[str, Any] = {}
        self.tasks: list[FakeImportTask] = []
        self.saved: list[str] = []

    def sound_wave(self, path: str) -> FakeSoundWave | None:
        asset = self.assets.get(path)
        return asset if isinstance(asset, FakeSoundWave) else None


def fake_unreal_module(editor: FakeEditor) -> types.ModuleType:
    """Return a module named ``unreal`` whose calls act on ``editor``."""
    module = types.ModuleType("unreal")

    class _Tools:
        def import_asset_tasks(self, tasks: list[FakeImportTask]) -> None:
            for task in tasks:
                editor.tasks.append(task)
                if not os.path.isfile(task.filename):
                    raise RuntimeError(f"cannot import {task.filename}: no such file")
                path = f"{task.destination_path}/{task.destination_name}"
                if path in editor.assets and not task.replace_existing:
                    continue
                editor.assets[path] = editor.produces(path)
                task.imported_object_paths = [f"{path}.{task.destination_name}"]

    class AssetToolsHelpers:
        @staticmethod
        def get_asset_tools() -> _Tools:
            return _Tools()

    class EditorAssetLibrary:
        @staticmethod
        def does_asset_exist(path: str) -> bool:
            return path in editor.assets

        @staticmethod
        def load_asset(path: str) -> Any:
            return editor.assets.get(path)

        @staticmethod
        def save_loaded_asset(asset: Any) -> bool:
            editor.saved.append(asset.path)
            return True

    module.SoundWave = FakeSoundWave  # type: ignore[attr-defined]
    module.AssetImportTask = FakeImportTask  # type: ignore[attr-defined]
    module.AssetToolsHelpers = AssetToolsHelpers  # type: ignore[attr-defined]
    module.EditorAssetLibrary = EditorAssetLibrary  # type: ignore[attr-defined]
    return module


class FakeUnrealPythonClient:
    """Satisfies ``UnrealPythonClient``. Runs each code string against a ``FakeEditor``."""

    def __init__(self, editor: FakeEditor | None = None, *, reachable: bool = True) -> None:
        self.editor = editor if editor is not None else FakeEditor()
        self.reachable = reachable
        self.codes: list[str] = []

    def execute_python_code(self, code: str) -> str:
        self.codes.append(code)
        if not self.reachable:
            raise PipelineError(
                code="mcp.unreal.unreachable",
                message=f"Unreal MCP is unreachable at {UNREACHABLE_URL}: connection refused",
                remediation="Run scripts/start-unreal-mcp.sh, wait for the UE 5.8 editor to "
                "finish loading, and confirm UE_MCP_PORT matches the port the editor serves.",
                stage="import_ue",
            )
        output = io.StringIO()
        module = fake_unreal_module(self.editor)
        with (
            mock.patch.dict(sys.modules, {"unreal": module}),
            contextlib.redirect_stdout(output),
        ):
            exec(compile(code, "<ue-python>", "exec"), {"__name__": "__ue_fake__"})
        return output.getvalue()
