"""Unreal scaffolding for region, mission, and system entries (#112 FR6, FR7).

Each non-orphaned entry becomes one ``execute_python_code`` call through the Unreal MCP.  Each call
checks ``EditorAssetLibrary.does_asset_exist`` first and returns without touching an existing
asset.  The UE result comes back as one ``NMG_RESULT {json}`` line, parsed by
``nmg_game_dev.unreal.import_asset.parse_nmg_result``.

Targets:

- region: level ``/Game/Levels/<Name>/L_<Name>`` with a ground plane, PlayerStart, DirectionalLight,
  and SkyLight.  The editor returns to the level it had open.
- mission: ``UNmgMissionDefinition`` data asset ``/Game/Missions/<Name>/DA_<Name>``.
- system: Actor Component Blueprint ``/Game/Systems/<Name>/BPC_<Name>``.

A ``design.scaffold_failed`` item does not stop the others.  An unreachable editor raises
``PipelineError`` (``mcp.unreal.unreachable``), and the caller exits 2.  The backlog is written
once, in a ``finally``, so the entries that did scaffold stay marked.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.unreal.import_asset import UnrealPythonClient, parse_nmg_result

from . import backlog
from .model import Entry
from .paths import backlog_path

SCAFFOLD_TYPES: Final = ("region", "mission", "system")
UNREACHABLE: Final = "mcp.unreal.unreachable"
SCAFFOLD_FAILED: Final = "design.scaffold_failed"


@dataclass(frozen=True)
class ScaffoldLine:
    """One report line.  ``status`` is created, unchanged, skipped, or error."""

    status: str
    entry_type: str
    asset_name: str
    detail: str

    def text(self) -> str:
        """Return the report line the command prints."""
        if self.status == "error":
            return f"error {SCAFFOLD_FAILED} {self.asset_name}: {self.detail}"
        return f"{self.status} {self.entry_type} {self.asset_name}: {self.detail}"


@dataclass
class ScaffoldReport:
    """The lines produced so far and whether any item failed."""

    lines: list[ScaffoldLine] = field(default_factory=list)
    failed: bool = False


def run_scaffold(client: UnrealPythonClient, root: Path, report: ScaffoldReport) -> None:
    """Scaffold every non-orphaned region, mission, and system entry under ``root``.

    Lines are appended to ``report`` as they are produced, so the caller still has them if the
    editor becomes unreachable.  Raises ``PipelineError`` for an unreachable editor, and
    ``FileNotFoundError`` when the backlog is missing.
    """
    path = backlog_path(root)
    if not path.is_file():
        raise FileNotFoundError(path)
    entries = backlog.load(path)
    names = _asset_names(entries)
    statuses: dict[str, str] = {}
    try:
        for entry in entries:
            if entry.type not in SCAFFOLD_TYPES:
                continue
            if entry.status == "orphaned":
                report.lines.append(
                    ScaffoldLine("skipped", entry.type, entry.asset_name, entry.source)
                )
                continue
            try:
                result = parse_nmg_result(
                    client.execute_python_code(build_scaffold_code(entry, names))
                )
            except PipelineError as error:
                if error.code == UNREACHABLE:
                    raise
                _record_failure(report, entry, error.message)
                continue
            if result.get("ok") is not True:
                _record_failure(report, entry, str(result.get("error") or "unknown UE error"))
                continue
            created = result.get("created") is True
            statuses[entry.asset_name] = "scaffolded"
            report.lines.append(
                ScaffoldLine(
                    "created" if created else "unchanged",
                    entry.type,
                    entry.asset_name,
                    str(result.get("path") or ""),
                )
            )
    finally:
        if statuses:
            backlog.update_statuses(path, statuses)


def build_scaffold_code(entry: Entry, names: Mapping[str, str]) -> str:
    """Return the UE Python that scaffolds one entry and prints one ``NMG_RESULT`` line.

    ``names`` maps each entry's name and asset name to its asset name, so a mission's region and
    dependencies are written as asset names, as the mission data asset expects.
    """
    constants = _constants(entry, names)
    assignments = "".join(f"{key} = {value!r}\n" for key, value in constants.items())
    return assignments + _PRELUDE + _BODIES[entry.type] + _EPILOGUE


def _constants(entry: Entry, names: Mapping[str, str]) -> dict[str, object]:
    name = entry.asset_name
    if entry.type == "region":
        return {"PATH": f"/Game/Levels/{name}/L_{name}"}
    if entry.type == "mission":
        region = entry.fields.get("region")
        return {
            "PATH": f"/Game/Missions/{name}/DA_{name}",
            "PACKAGE_PATH": f"/Game/Missions/{name}",
            "ASSET_NAME": f"DA_{name}",
            "MISSION_NAME": entry.name,
            "ACT": int(entry.fields.get("act", 0)),
            "REGION": names.get(str(region)) if region is not None else None,
            "DEPENDS_ON": [
                names.get(str(item), str(item)) for item in entry.fields.get("depends_on", [])
            ],
            "DESIGN_DOC_PATH": entry.source,
        }
    return {
        "PATH": f"/Game/Systems/{name}/BPC_{name}",
        "PACKAGE_PATH": f"/Game/Systems/{name}",
        "ASSET_NAME": f"BPC_{name}",
    }


def _asset_names(entries: list[Entry]) -> dict[str, str]:
    names: dict[str, str] = {}
    for entry in entries:
        names[entry.name] = entry.asset_name
        names[entry.asset_name] = entry.asset_name
    return names


def _record_failure(report: ScaffoldReport, entry: Entry, detail: str) -> None:
    report.failed = True
    report.lines.append(ScaffoldLine("error", entry.type, entry.asset_name, detail))


_PRELUDE: Final = """import json

import unreal

RESULT = {"ok": False, "created": False, "path": PATH, "error": None}


"""

_EPILOGUE: Final = """

try:
    _scaffold()
except Exception as error:
    RESULT.update(ok=False, created=False, error=type(error).__name__ + ": " + str(error))
print("NMG_RESULT " + json.dumps(RESULT))
"""

_REGION_BODY: Final = """def _scaffold():
    if unreal.EditorAssetLibrary.does_asset_exist(PATH):
        RESULT.update(ok=True, created=False)
        return
    editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    previous = editor.get_editor_world().get_outermost().get_path_name()
    try:
        if not levels.new_level(PATH):
            raise RuntimeError("LevelEditorSubsystem.new_level failed for " + PATH)
        ground = actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0, 0, 0))
        ground.static_mesh_component.set_editor_property(
            "static_mesh", unreal.EditorAssetLibrary.load_asset("/Engine/BasicShapes/Plane")
        )
        ground.set_actor_scale3d(unreal.Vector(100, 100, 1))
        actors.spawn_actor_from_class(unreal.PlayerStart, unreal.Vector(0, 0, 100))
        actors.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0, 0, 0))
        actors.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0, 0, 0))
        if not levels.save_current_level():
            raise RuntimeError("could not save the level " + PATH)
        RESULT.update(ok=True, created=True)
    finally:
        levels.load_level(previous)
"""

_MISSION_BODY: Final = """def _scaffold():
    if unreal.EditorAssetLibrary.does_asset_exist(PATH):
        RESULT.update(ok=True, created=False)
        return
    if not hasattr(unreal, "NmgMissionDefinition"):
        raise RuntimeError(
            "unreal.NmgMissionDefinition is not loaded; build the nmg-game-dev UE plugin and "
            "restart the editor"
        )
    factory = unreal.DataAssetFactory()
    factory.set_editor_property("data_asset_class", unreal.NmgMissionDefinition)
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    asset = tools.create_asset(ASSET_NAME, PACKAGE_PATH, unreal.NmgMissionDefinition, factory)
    if asset is None:
        raise RuntimeError("AssetTools.create_asset returned nothing for " + PATH)
    asset.set_editor_property("mission_name", MISSION_NAME)
    asset.set_editor_property("act", ACT)
    asset.set_editor_property("region", unreal.Name(REGION or "None"))
    asset.set_editor_property("depends_on", [unreal.Name(item) for item in DEPENDS_ON])
    asset.set_editor_property("design_doc_path", DESIGN_DOC_PATH)
    unreal.EditorAssetLibrary.save_loaded_asset(asset)
    RESULT.update(ok=True, created=True)
"""

_SYSTEM_BODY: Final = """def _scaffold():
    if unreal.EditorAssetLibrary.does_asset_exist(PATH):
        RESULT.update(ok=True, created=False)
        return
    factory = unreal.BlueprintFactory()
    factory.set_editor_property("parent_class", unreal.ActorComponent)
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    blueprint = tools.create_asset(ASSET_NAME, PACKAGE_PATH, unreal.Blueprint, factory)
    if blueprint is None:
        raise RuntimeError("AssetTools.create_asset returned nothing for " + PATH)
    unreal.EditorAssetLibrary.save_loaded_asset(blueprint)
    RESULT.update(ok=True, created=True)
"""

_BODIES: Final = {"region": _REGION_BODY, "mission": _MISSION_BODY, "system": _SYSTEM_BODY}
