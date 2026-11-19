"""Godot scaffolding of region, mission, and system entries (#112, #249 AC7, FR7).

Each entry becomes a Godot text file under ``game/``. The tests check the written text, the report
lines, that existing files are never touched, the per-entry failures that do not stop the run, the
``statuses`` filter, and the single backlog write.
"""

from __future__ import annotations

import dataclasses
import io
import re
from collections.abc import Mapping
from pathlib import Path

import pytest

from nmg_game_dev.design import backlog
from nmg_game_dev.design.__main__ import main
from nmg_game_dev.design.paths import backlog_path
from nmg_game_dev.design.scaffold import ScaffoldReport, run_scaffold, snake_case
from nmg_game_dev.pipeline.errors import PipelineError

REGION_FILE = "game/levels/OldTown/OldTown.tscn"
HARBOR_FILE = "game/levels/Harbor/Harbor.tscn"
MISSION_FILE = "game/missions/FindKey.tres"
SYSTEM_FILE = "game/systems/Inventory/inventory.gd"
HILLS_SCENE = "game/assets/Terrain/Hills/Desktop/Hills.tscn"

REGION = """\
---
type: region
name: Old Town
---
"""

CRATE = """\
---
type: prop
name: Crate
asset_class: standard_prop
category: Props
---
"""

MISSION = """\
---
type: mission
name: Find Key
act: 2
region: Old Town
depends_on: [Old Town, Crate]
---
"""

SYSTEM = """\
---
type: system
name: Inventory
---
"""

HILLS = """\
---
type: environment
name: Hills
asset_class: terrain
category: Terrain
---
"""

TERRAIN_REGION = """\
---
type: region
name: Old Town
terrain: Hills
---
"""

HARBOR = """\
---
type: region
name: Harbor
---
"""

MISSION_SCRIPT = "res://addons/nmg_game_dev/nmg_mission_definition.gd"

MISSION_TRES = f"""\
[gd_resource type="Resource" script_class="NmgMissionDefinition" format=3]

[ext_resource type="Script" path="{MISSION_SCRIPT}" id="1_script"]

[resource]
script = ExtResource("1_script")
mission_name = "Find Key"
act = 2
region = &"OldTown"
depends_on = Array[StringName]([&"OldTown", &"Crate"])
design_doc_path = "docs/design/missions/find-key.md"
"""

SYSTEM_GD = """\
## The Inventory system.
##
## Scaffolded by /design from docs/design/systems/inventory.md.
## Add it as a child of the node it serves.
class_name InventoryComponent
extends Node
"""

_HEADER = re.compile(r"^\[(?P<kind>\w+)(?P<attrs>[^\]]*)\]$", re.MULTILINE)
_ATTR = re.compile(r'(\w+)=("[^"]*"|\S+)')


def _write(root: Path, relative: str, text: str) -> None:
    path = root / "docs" / "design" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _sync(root: Path) -> None:
    out, err = io.StringIO(), io.StringIO()
    assert main(["sync", "--project", str(root)], stdout=out, stderr=err) == 0, err.getvalue()


def _project(root: Path, docs: Mapping[str, str]) -> Path:
    """Write the design docs and an empty ``game/project.godot``, then sync."""
    for relative, text in docs.items():
        _write(root, relative, text)
    (root / "game").mkdir(parents=True, exist_ok=True)
    (root / "game" / "project.godot").write_text("config_version=5\n", encoding="utf-8")
    _sync(root)
    return root


def _full_project(root: Path) -> Path:
    """A region, a prop the mission depends on, a mission, and a system, then synced."""
    return _project(
        root,
        {
            "regions/old-town.md": REGION,
            "props/crate.md": CRATE,
            "missions/find-key.md": MISSION,
            "systems/inventory.md": SYSTEM,
        },
    )


def _terrain_project(root: Path) -> Path:
    """A region that names the Hills terrain, and the Hills entry, then synced."""
    return _project(root, {"regions/old-town.md": TERRAIN_REGION, "environment/hills.md": HILLS})


def _set_terrain(root: Path, asset: str, terrain: str) -> None:
    """Point the region ``asset`` at ``terrain`` in the backlog.

    Sync rejects a region whose terrain names no entry, so such a backlog exists only when someone
    edits it by hand.  The test does that edit.
    """
    path = backlog_path(root)
    updated = [
        dataclasses.replace(entry, fields={**entry.fields, "terrain": terrain})
        if entry.asset_name == asset
        else entry
        for entry in backlog.load(path)
    ]
    backlog.write_atomic(path, backlog.dump(updated))


def _run(root: Path, statuses: set[str] | None = None) -> ScaffoldReport:
    report = ScaffoldReport()
    run_scaffold(root, report, statuses=statuses)
    return report


def _texts(report: ScaffoldReport) -> list[str]:
    return [line.text() for line in report.lines]


def _statuses(root: Path) -> dict[str, str]:
    return {entry.asset_name: entry.status for entry in backlog.load(backlog_path(root))}


def _game_files(root: Path) -> list[str]:
    game = root / "game"
    return sorted(p.relative_to(root).as_posix() for p in game.rglob("*") if p.is_file())


def _sections(text: str) -> list[tuple[str, dict[str, str]]]:
    """Return each ``[kind attr=value ...]`` header of a Godot text resource, in order."""
    return [
        (match["kind"], {key: value.strip('"') for key, value in _ATTR.findall(match["attrs"])})
        for match in _HEADER.finditer(text)
    ]


def _nodes(text: str) -> dict[str, dict[str, str]]:
    return {attrs["name"]: attrs for kind, attrs in _sections(text) if kind == "node"}


def _assert_well_formed_scene(text: str) -> None:
    """Resources come before nodes, and every reference names a resource declared before it."""
    sections = _sections(text)
    assert sections[0] == ("gd_scene", {"format": "3"})
    kinds = [kind for kind, _ in sections[1:]]
    first_node = kinds.index("node")
    assert all(kind == "node" for kind in kinds[first_node:])
    declared: set[str] = set()
    for block in re.split(r"\n\n(?=\[)", text):
        for ref in re.findall(r'(?:Sub|Ext)Resource\("([^"]+)"\)', block):
            assert ref in declared, f"{ref} is referenced before it is declared"
        header = _HEADER.match(block)
        if header and header["kind"] in {"ext_resource", "sub_resource"}:
            declared.add(dict(_ATTR.findall(header["attrs"]))["id"].strip('"'))


def test_every_entry_type_is_written_to_its_godot_path(tmp_path: Path) -> None:
    root = _full_project(tmp_path)

    report = _run(root)

    assert _texts(report) == [
        f"created mission FindKey: {MISSION_FILE}",
        f"created region OldTown: {REGION_FILE}",
        f"created system Inventory: {SYSTEM_FILE}",
    ]
    assert report.failed is False
    assert _game_files(root) == sorted(
        ["game/project.godot", MISSION_FILE, REGION_FILE, SYSTEM_FILE]
    )
    assert _statuses(root) == {
        "Crate": "planned",
        "FindKey": "scaffolded",
        "Inventory": "scaffolded",
        "OldTown": "scaffolded",
    }


def test_a_region_scene_has_a_spawn_light_environment_and_ground(tmp_path: Path) -> None:
    root = _full_project(tmp_path)
    _run(root)

    text = (root / REGION_FILE).read_text(encoding="utf-8")

    _assert_well_formed_scene(text)
    nodes = _nodes(text)
    assert nodes["OldTown"] == {"name": "OldTown", "type": "Node3D"}
    assert nodes["PlayerSpawn"]["type"] == "Marker3D"
    assert nodes["DirectionalLight3D"]["type"] == "DirectionalLight3D"
    assert nodes["WorldEnvironment"]["type"] == "WorldEnvironment"
    assert nodes["Ground"]["type"] == "StaticBody3D"
    assert nodes["Mesh"] == {"name": "Mesh", "type": "MeshInstance3D", "parent": "Ground"}
    assert nodes["Collision"] == {
        "name": "Collision",
        "type": "CollisionShape3D",
        "parent": "Ground",
    }
    assert 'environment = SubResource("Environment_world")' in text
    assert '[sub_resource type="Environment" id="Environment_world"]' in text
    assert '[sub_resource type="PlaneMesh" id="PlaneMesh_ground"]\nsize = Vector2(200, 200)' in text
    assert (
        '[sub_resource type="BoxShape3D" id="BoxShape3D_ground"]\nsize = Vector3(200, 1, 200)'
        in text
    )
    assert "ext_resource" not in text


def test_a_mission_is_an_nmg_mission_definition_resource(tmp_path: Path) -> None:
    root = _full_project(tmp_path)
    _run(root)

    assert (root / MISSION_FILE).read_text(encoding="utf-8") == MISSION_TRES


def test_a_mission_without_region_or_dependencies_writes_empty_values(tmp_path: Path) -> None:
    root = _project(tmp_path, {"missions/intro.md": "---\ntype: mission\nname: Intro\n---\n"})
    _run(root)

    text = (root / "game/missions/Intro.tres").read_text(encoding="utf-8")
    assert 'region = &""\n' in text
    assert "depends_on = Array[StringName]([])\n" in text
    assert "act = 0\n" in text


def test_a_system_is_a_component_script(tmp_path: Path) -> None:
    root = _full_project(tmp_path)
    _run(root)

    assert (root / SYSTEM_FILE).read_text(encoding="utf-8") == SYSTEM_GD


@pytest.mark.parametrize(
    ("name", "snake"),
    [
        ("Inventory", "inventory"),
        ("OldTown", "old_town"),
        ("HUDOverlay", "hud_overlay"),
        ("Act2Boss", "act2_boss"),
    ],
)
def test_snake_case(name: str, snake: str) -> None:
    assert snake_case(name) == snake


def test_a_second_run_leaves_every_file_byte_identical_and_reports_unchanged(
    tmp_path: Path,
) -> None:
    root = _full_project(tmp_path)
    _run(root)
    edited = root / REGION_FILE
    edited.write_text(edited.read_text(encoding="utf-8") + "# hand edit\n", encoding="utf-8")
    before = {path: (root / path).read_bytes() for path in _game_files(root)}

    report = _run(root)

    assert _texts(report) == [
        f"unchanged mission FindKey: {MISSION_FILE}",
        f"unchanged region OldTown: {REGION_FILE}",
        f"unchanged system Inventory: {SYSTEM_FILE}",
    ]
    assert {path: (root / path).read_bytes() for path in _game_files(root)} == before
    assert _statuses(root)["OldTown"] == "scaffolded"


def test_an_existing_file_from_before_the_backlog_is_marked_scaffolded(tmp_path: Path) -> None:
    root = _full_project(tmp_path)
    existing = root / SYSTEM_FILE
    existing.parent.mkdir(parents=True)
    existing.write_text("extends Node\n", encoding="utf-8")

    report = _run(root)

    assert f"unchanged system Inventory: {SYSTEM_FILE}" in _texts(report)
    assert existing.read_text(encoding="utf-8") == "extends Node\n"
    assert _statuses(root)["Inventory"] == "scaffolded"


def test_orphaned_entries_are_skipped_and_not_written(tmp_path: Path) -> None:
    root = _full_project(tmp_path)
    (root / "docs" / "design" / "systems" / "inventory.md").unlink()
    _sync(root)

    report = _run(root)

    assert "skipped system Inventory: docs/design/systems/inventory.md" in _texts(report)
    assert not (root / SYSTEM_FILE).exists()
    assert _statuses(root)["Inventory"] == "orphaned"


def test_a_region_instances_its_finalized_terrain_scene(tmp_path: Path) -> None:
    root = _terrain_project(tmp_path)
    scene = root / HILLS_SCENE
    scene.parent.mkdir(parents=True)
    scene.write_text("[gd_scene format=3]\n", encoding="utf-8")

    report = _run(root)

    assert _texts(report) == [f"created region OldTown: {REGION_FILE}"], "terrain is not scaffolded"
    text = (root / REGION_FILE).read_text(encoding="utf-8")
    _assert_well_formed_scene(text)
    # The region names the terrain variant-free and loads it through NmgVariantScene, so the
    # Mobile/Web presets (which drop every Desktop/ folder) never leave a dangling reference.
    assert (
        '[ext_resource type="Script" path="res://addons/nmg_game_dev/nmg_variant_scene.gd" '
        'id="1_terrain"]'
    ) in text
    assert (
        '[node name="Hills" type="Node3D" parent="."]\n'
        'script = ExtResource("1_terrain")\n'
        'scene_path = "res://assets/Terrain/Hills/Hills.tscn"'
    ) in text
    assert "/Desktop/" not in text and "/Mobile/" not in text
    assert "PlaneMesh" not in text
    assert "StaticBody3D" not in text
    assert {"PlayerSpawn", "DirectionalLight3D", "WorldEnvironment"} <= set(_nodes(text))


def test_a_region_gets_a_ground_when_its_terrain_scene_does_not_exist(tmp_path: Path) -> None:
    root = _terrain_project(tmp_path)

    _run(root)

    text = (root / REGION_FILE).read_text(encoding="utf-8")
    assert "ext_resource" not in text
    assert '[sub_resource type="PlaneMesh" id="PlaneMesh_ground"]' in text


def test_a_region_naming_no_terrain_entry_is_an_unknown_reference_and_the_others_still_run(
    tmp_path: Path,
) -> None:
    root = _project(
        tmp_path,
        {
            "regions/old-town.md": REGION,
            "regions/harbor.md": HARBOR,
            "environment/hills.md": HILLS,
            "systems/inventory.md": SYSTEM,
        },
    )
    _set_terrain(root, "OldTown", "Ghost")

    report = _run(root)

    assert report.failed is True
    texts = _texts(report)
    assert (
        "error design.unknown_reference OldTown: "
        "terrain 'Ghost' names no environment entry with asset_class terrain"
    ) in texts
    assert f"created region Harbor: {HARBOR_FILE}" in texts
    assert f"created system Inventory: {SYSTEM_FILE}" in texts
    assert not (root / REGION_FILE).exists()
    assert _statuses(root) == {
        "Harbor": "scaffolded",
        "Hills": "planned",
        "Inventory": "scaffolded",
        "OldTown": "planned",
    }


def test_a_write_failure_is_reported_and_the_other_items_still_run(tmp_path: Path) -> None:
    root = _full_project(tmp_path)
    blocker = root / "game" / "levels"
    blocker.write_text("a file where the levels folder should be", encoding="utf-8")

    report = _run(root)

    assert report.failed is True
    [error] = [line for line in report.lines if line.status == "error"]
    assert error.code == "design.scaffold_failed"
    assert error.text().startswith(f"error design.scaffold_failed OldTown: {REGION_FILE}: ")
    texts = _texts(report)
    assert f"created mission FindKey: {MISSION_FILE}" in texts
    assert f"created system Inventory: {SYSTEM_FILE}" in texts
    assert _statuses(root)["OldTown"] == "planned"


def test_statuses_limits_the_run_to_entries_with_those_statuses(tmp_path: Path) -> None:
    root = _full_project(tmp_path)
    backlog.update_statuses(backlog_path(root), {"OldTown": "scaffolded"})

    report = _run(root, statuses={"scaffolded"})

    assert _texts(report) == [f"created region OldTown: {REGION_FILE}"]
    assert _game_files(root) == sorted(["game/project.godot", REGION_FILE])
    assert _statuses(root)["FindKey"] == "planned"


def test_backlog_is_written_once_per_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _full_project(tmp_path)
    original = backlog.update_statuses
    calls: list[dict[str, str]] = []

    def counting(path: Path, statuses: Mapping[str, str]) -> list[str]:
        calls.append(dict(statuses))
        return original(path, statuses)

    monkeypatch.setattr(backlog, "update_statuses", counting)
    _run(root)

    assert calls == [{"FindKey": "scaffolded", "Inventory": "scaffolded", "OldTown": "scaffolded"}]


def test_a_missing_godot_project_raises_before_anything_is_written(tmp_path: Path) -> None:
    root = _full_project(tmp_path)
    (root / "game" / "project.godot").unlink()
    before = backlog_path(root).read_bytes()
    report = ScaffoldReport()

    with pytest.raises(PipelineError) as caught:
        run_scaffold(root, report)

    assert caught.value.code == "design.godot_project_missing"
    assert "/onboard-consumer" in caught.value.remediation
    assert report.lines == []
    assert _game_files(root) == []
    assert backlog_path(root).read_bytes() == before


def test_missing_backlog_raises_before_anything_is_written(tmp_path: Path) -> None:
    _write(tmp_path, "regions/old-town.md", REGION)

    with pytest.raises(FileNotFoundError):
        _run(tmp_path)

    assert not (tmp_path / "game").exists()


@pytest.mark.parametrize("bad", ["../../../escaped", "lower", "Old Town", "Old/Town", "OldTown\n"])
def test_an_asset_name_that_is_not_pascal_case_fails_that_entry_and_writes_nothing_outside(
    tmp_path: Path, bad: str
) -> None:
    """Review F7: asset_name becomes a path and a class name, so it must be PascalCase."""
    root = _full_project(tmp_path)
    path = backlog_path(root)
    updated = [
        dataclasses.replace(entry, asset_name=bad) if entry.asset_name == "Inventory" else entry
        for entry in backlog.load(path)
    ]
    backlog.write_atomic(path, backlog.dump(updated))
    before = {item for item in tmp_path.rglob("*") if "game" not in item.parts}

    report = _run(root)

    assert report.failed is True
    errors = [line for line in report.lines if line.status == "error"]
    assert [line.code for line in errors] == ["design.scaffold_failed"]
    assert "is not PascalCase" in errors[0].detail
    assert {item for item in tmp_path.rglob("*") if "game" not in item.parts} == before
    assert not list((root / "game" / "systems").rglob("*.gd"))
    # The other entries still scaffold.
    assert any(line.status == "created" for line in report.lines)
