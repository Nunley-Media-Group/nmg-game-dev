"""Godot scaffolding for region, mission, and system entries (#112, #249 FR7).

Each non-orphaned entry becomes one Godot text file under the project's ``game/`` folder. Nothing
runs Godot: the files are written directly, and an existing file is never touched.

Targets:

- region: scene ``game/levels/<Name>/<Name>.tscn`` with a ``Node3D`` root, a ``Marker3D``
  ``PlayerSpawn``, a ``DirectionalLight3D``, and a ``WorldEnvironment``. When the region's
  ``terrain`` names a terrain entry that has been finalized (its
  ``game/assets/<Category>/<Name>/Desktop/<Name>.tscn`` exists), the region gets an
  ``NmgVariantScene`` node whose ``scene_path`` is the variant-free
  ``res://assets/<Category>/<Name>/<Name>.tscn``, so each platform loads its own variant at run time
  and the scene never hard-links a ``Desktop/`` or ``Mobile/`` path the export presets drop.
  Otherwise it gets a 200 m ground: a ``PlaneMesh`` on a ``StaticBody3D`` with a ``BoxShape3D``.
- mission: ``NmgMissionDefinition`` resource ``game/missions/<Name>.tres``.
- system: component script ``game/systems/<Name>/<snake_name>.gd`` (``<Name>Component``). With
  ``template: audio`` the script extends ``NmgAudio`` and loads its name table, and
  ``game/systems/<Name>/audio_table.tres`` (an ``NmgAudioTable`` rendered from the imported sounds
  and the backlog's region music) is written beside it (#237).

An existing file is reported ``unchanged`` and is still marked ``scaffolded``. A region whose
``terrain`` names no terrain entry is a ``design.unknown_reference`` item; an entry whose asset name
is not PascalCase (it becomes a path and a class name) and an ``OSError`` on one entry are
``design.scaffold_failed`` items; none of them stops the others. A missing
``game/project.godot`` raises ``design.godot_project_missing`` before anything is written. The
backlog is written once, in a ``finally``, so the entries that did scaffold stay marked.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from nmg_game_dev.audio.tables import TABLE_NAME, render_table
from nmg_game_dev.godot.project import PROJECT_FILE, godot_string
from nmg_game_dev.pipeline.errors import PipelineError

from . import backlog
from .model import AUDIO_TEMPLATE, PASCAL_CASE, Entry
from .paths import backlog_path

SCAFFOLD_TYPES: Final = ("region", "mission", "system")
SCAFFOLD_FAILED: Final = "design.scaffold_failed"
UNKNOWN_REFERENCE: Final = "design.unknown_reference"
PROJECT_MISSING: Final = "design.godot_project_missing"
GAME_DIR: Final = "game"
MISSION_SCRIPT: Final = "res://addons/nmg_game_dev/nmg_mission_definition.gd"
VARIANT_SCENE_SCRIPT: Final = "res://addons/nmg_game_dev/nmg_variant_scene.gd"
GROUND_SIZE_M: Final = 200


@dataclass(frozen=True)
class ScaffoldLine:
    """One report line.  ``status`` is created, unchanged, skipped, or error.

    ``code`` is the ``design.*`` code an error line prints.  It defaults to
    ``design.scaffold_failed``.
    """

    status: str
    entry_type: str
    asset_name: str
    detail: str
    code: str = SCAFFOLD_FAILED

    def text(self) -> str:
        """Return the report line the command prints."""
        if self.status == "error":
            return f"error {self.code} {self.asset_name}: {self.detail}"
        return f"{self.status} {self.entry_type} {self.asset_name}: {self.detail}"


@dataclass
class ScaffoldReport:
    """The lines produced so far and whether any item failed."""

    lines: list[ScaffoldLine] = field(default_factory=list)
    failed: bool = False


@dataclass(frozen=True)
class Terrain:
    """A terrain entry a region can name: its category and asset name."""

    category: str
    asset_name: str

    def scene(self) -> Path:
        """The terrain's finalized Desktop scene, relative to the Godot project.

        Its existence marks the terrain as finalized; regions never reference it directly.
        """
        name = self.asset_name
        return Path("assets") / self.category / name / "Desktop" / f"{name}.tscn"

    def variant_free_path(self) -> str:
        """The ``res://`` path ``NmgAssets.resolve_variant_path`` routes to either variant."""
        name = self.asset_name
        return f"res://assets/{self.category}/{name}/{name}.tscn"


def run_scaffold(
    root: Path,
    report: ScaffoldReport,
    *,
    statuses: Collection[str] | None = None,
) -> None:
    """Scaffold every non-orphaned region, mission, and system entry under ``root``.

    ``statuses`` limits the run to entries whose backlog status is in it (conversion passes
    ``{"scaffolded"}``); entries outside it produce no line. Raises ``FileNotFoundError`` when the
    backlog is missing, ``ValueError`` when it is unreadable, and ``PipelineError``
    (``design.godot_project_missing``) when ``game/project.godot`` is missing.
    """
    path = backlog_path(root)
    if not path.is_file():
        raise FileNotFoundError(path)
    entries = backlog.load(path)
    game = root / GAME_DIR
    if not (game / PROJECT_FILE).is_file():
        raise PipelineError(
            code=PROJECT_MISSING,
            message=f"No {PROJECT_FILE} was found at {game}.",
            remediation="Run /onboard-consumer to create game/project.godot, then rerun "
            "`python -m nmg_game_dev.design scaffold`.",
            stage="design",
        )
    names = _asset_names(entries)
    terrains = _terrains(entries)
    marked: dict[str, str] = {}
    try:
        for entry in entries:
            if entry.type not in SCAFFOLD_TYPES:
                continue
            if statuses is not None and entry.status not in statuses:
                continue
            if entry.status == "orphaned":
                report.lines.append(
                    ScaffoldLine("skipped", entry.type, entry.asset_name, entry.source)
                )
                continue
            if not PASCAL_CASE.fullmatch(entry.asset_name):
                _record_failure(
                    report,
                    entry,
                    f"asset_name {entry.asset_name!r} is not PascalCase, so it cannot name a "
                    "Godot file or class",
                )
                continue
            terrain = entry.fields.get("terrain")
            if entry.type == "region" and terrain is not None and str(terrain) not in terrains:
                _record_failure(
                    report,
                    entry,
                    f"terrain {terrain!r} names no environment entry with asset_class terrain",
                    UNKNOWN_REFERENCE,
                )
                continue
            shown = f"{GAME_DIR}/{target_path(entry).as_posix()}"
            try:
                created = _write_new(
                    game / target_path(entry), _render(entry, game, names, terrains)
                )
            except OSError as error:
                _record_failure(report, entry, f"{shown}: {error}")
                continue
            marked[entry.asset_name] = "scaffolded"
            report.lines.append(
                ScaffoldLine(
                    "created" if created else "unchanged", entry.type, entry.asset_name, shown
                )
            )
            if _is_audio_system(entry):
                _scaffold_audio_table(root, game, entry, report)
    finally:
        if marked:
            backlog.update_statuses(path, marked)


def target_path(entry: Entry) -> Path:
    """Return the file an entry scaffolds to, relative to the Godot project."""
    name = entry.asset_name
    if entry.type == "region":
        return Path("levels") / name / f"{name}.tscn"
    if entry.type == "mission":
        return Path("missions") / f"{name}.tres"
    return Path("systems") / name / f"{snake_case(name)}.gd"


def audio_table_path(entry: Entry) -> Path:
    """Return the Audio component's name table, relative to the Godot project (#237 FR7)."""
    return Path("systems") / entry.asset_name / TABLE_NAME


def _is_audio_system(entry: Entry) -> bool:
    return entry.type == "system" and entry.fields.get("template") == AUDIO_TEMPLATE


def _scaffold_audio_table(root: Path, game: Path, entry: Entry, report: ScaffoldReport) -> None:
    """Write the Audio component's name table beside its script, as a line of its own (#237)."""
    shown = f"{GAME_DIR}/{audio_table_path(entry).as_posix()}"
    try:
        created = _write_new(game / audio_table_path(entry), render_table(root))
    except OSError as error:
        _record_failure(report, entry, f"{shown}: {error}")
        return
    report.lines.append(
        ScaffoldLine("created" if created else "unchanged", entry.type, entry.asset_name, shown)
    )


def snake_case(name: str) -> str:
    """Return ``OldTown`` as ``old_town`` and ``HUDOverlay`` as ``hud_overlay``."""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", "_", name).lower()


def _write_new(path: Path, text: str) -> bool:
    """Create ``path`` with ``text``; return False, writing nothing, when it already exists."""
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    except FileExistsError:
        return False
    return True


def _render(
    entry: Entry, game: Path, names: Mapping[str, str], terrains: Mapping[str, Terrain]
) -> str:
    if entry.type == "region":
        terrain = entry.fields.get("terrain")
        scene = None
        if terrain is not None:
            candidate = terrains[str(terrain)]
            if (game / candidate.scene()).is_file():
                scene = candidate
        return region_scene(entry.asset_name, scene)
    if entry.type == "mission":
        return mission_resource(entry, names)
    if _is_audio_system(entry):
        return audio_system_script(entry)
    return system_script(entry)


def region_scene(name: str, terrain: Terrain | None) -> str:
    """Return the ``.tscn`` text for region ``name``, loading ``terrain``'s variant when given."""
    blocks = ["[gd_scene format=3]"]
    if terrain is not None:
        script = godot_string(VARIANT_SCENE_SCRIPT)
        blocks.append(f'[ext_resource type="Script" path={script} id="1_terrain"]')
    blocks.extend(
        [
            '[sub_resource type="ProceduralSkyMaterial" id="ProceduralSkyMaterial_sky"]',
            '[sub_resource type="Sky" id="Sky_sky"]\n'
            'sky_material = SubResource("ProceduralSkyMaterial_sky")',
            '[sub_resource type="Environment" id="Environment_world"]\n'
            "background_mode = 2\n"
            'sky = SubResource("Sky_sky")\n'
            "tonemap_mode = 2",
        ]
    )
    if terrain is None:
        size = GROUND_SIZE_M
        blocks.extend(
            [
                '[sub_resource type="PlaneMesh" id="PlaneMesh_ground"]\n'
                f"size = Vector2({size}, {size})",
                '[sub_resource type="BoxShape3D" id="BoxShape3D_ground"]\n'
                f"size = Vector3({size}, 1, {size})",
            ]
        )
    blocks.extend(
        [
            f'[node name="{name}" type="Node3D"]',
            '[node name="PlayerSpawn" type="Marker3D" parent="."]\n'
            "transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 1, 0)",
            # Pitched 45 degrees down about X, so the light falls on the scene at an angle.
            '[node name="DirectionalLight3D" type="DirectionalLight3D" parent="."]\n'
            "transform = Transform3D(1, 0, 0, 0, 0.707107, 0.707107, 0, -0.707107, 0.707107, "
            "0, 10, 0)\n"
            "shadow_enabled = true",
            '[node name="WorldEnvironment" type="WorldEnvironment" parent="."]\n'
            'environment = SubResource("Environment_world")',
        ]
    )
    if terrain is not None:
        blocks.append(
            f'[node name="{terrain.asset_name}" type="Node3D" parent="."]\n'
            'script = ExtResource("1_terrain")\n'
            f"scene_path = {godot_string(terrain.variant_free_path())}"
        )
    else:
        blocks.extend(
            [
                '[node name="Ground" type="StaticBody3D" parent="."]',
                '[node name="Mesh" type="MeshInstance3D" parent="Ground"]\n'
                'mesh = SubResource("PlaneMesh_ground")',
                # The 1 m thick box sits under the plane, so its top face is the ground at y=0.
                '[node name="Collision" type="CollisionShape3D" parent="Ground"]\n'
                "transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 0, -0.5, 0)\n"
                'shape = SubResource("BoxShape3D_ground")',
            ]
        )
    return "\n\n".join(blocks) + "\n"


def mission_resource(entry: Entry, names: Mapping[str, str]) -> str:
    """Return the ``NmgMissionDefinition`` ``.tres`` text for a mission entry.

    ``names`` maps each entry's name and asset name to its asset name, so the region and the
    dependencies are written as asset names.
    """
    region = entry.fields.get("region")
    region_name = names.get(str(region), str(region)) if region is not None else ""
    depends = [names.get(str(item), str(item)) for item in entry.fields.get("depends_on", [])]
    depends_literal = ", ".join(_string_name(item) for item in depends)
    blocks = [
        '[gd_resource type="Resource" script_class="NmgMissionDefinition" format=3]',
        f'[ext_resource type="Script" path={godot_string(MISSION_SCRIPT)} id="1_script"]',
        "[resource]\n"
        'script = ExtResource("1_script")\n'
        f"mission_name = {godot_string(entry.name)}\n"
        f"act = {int(entry.fields.get('act', 0))}\n"
        f"region = {_string_name(region_name)}\n"
        f"depends_on = Array[StringName]([{depends_literal}])\n"
        f"design_doc_path = {godot_string(entry.source)}",
    ]
    return "\n\n".join(blocks) + "\n"


def system_script(entry: Entry) -> str:
    """Return the component script for a system entry."""
    return (
        f"## The {entry.name} system.\n"
        "##\n"
        f"## Scaffolded by /design from {entry.source}.\n"
        "## Add it as a child of the node it serves.\n"
        f"class_name {entry.asset_name}Component\n"
        "extends Node\n"
    )


def audio_system_script(entry: Entry) -> str:
    """Return the NmgAudio component script for a system entry with ``template: audio`` (#237 FR7).

    The script loads the component's name table in ``_init``, so sounds that ``import_audio``
    adds reach the component through the table with no edit to this file.
    """
    return (
        f"## The {entry.name} system: plays sounds and music by name.\n"
        "##\n"
        f"## Scaffolded by /design from {entry.source}.\n"
        f"class_name {entry.asset_name}Component\n"
        "extends NmgAudio\n"
        "\n"
        "\n"
        "func _init() -> void:\n"
        f'\ttable = load("res://systems/{entry.asset_name}/{TABLE_NAME}") as NmgAudioTable\n'
    )


def _string_name(value: str) -> str:
    return "&" + godot_string(value)


def _asset_names(entries: list[Entry]) -> dict[str, str]:
    names: dict[str, str] = {}
    for entry in entries:
        names[entry.name] = entry.asset_name
        names[entry.asset_name] = entry.asset_name
    return names


def _terrains(entries: list[Entry]) -> dict[str, Terrain]:
    """Map each terrain entry's name and asset name to its category and asset name."""
    terrains: dict[str, Terrain] = {}
    for entry in entries:
        if entry.type != "environment" or entry.fields.get("asset_class") != "terrain":
            continue
        terrain = Terrain(str(entry.fields["category"]), entry.asset_name)
        terrains[entry.name] = terrain
        terrains[entry.asset_name] = terrain
    return terrains


def _record_failure(
    report: ScaffoldReport, entry: Entry, detail: str, code: str = SCAFFOLD_FAILED
) -> None:
    report.failed = True
    report.lines.append(ScaffoldLine("error", entry.type, entry.asset_name, detail, code))
