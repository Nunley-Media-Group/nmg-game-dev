"""AC5 and AC6: the generated Unreal code, the report lines, failures, and the backlog write.

The region code is also run against the fake ``unreal`` module in ``terrain_fakes``, with and
without an existing terrain level (AC5), and a region whose terrain names no entry is an
``design.unknown_reference`` line that does not stop the other items (AC6).
"""

from __future__ import annotations

import ast
import dataclasses
import io
import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import pytest

from nmg_game_dev.design import backlog
from nmg_game_dev.design.__main__ import main
from nmg_game_dev.design.paths import backlog_path
from nmg_game_dev.design.scaffold import ScaffoldReport, run_scaffold
from nmg_game_dev.pipeline.errors import PipelineError
from tests.unit.design.terrain_fakes import DEFAULT_LEVEL, PLANE, FakeUnreal

UNREACHABLE_CODE = "mcp.unreal.unreachable"
REGION_PATH = "/Game/Levels/OldTown/L_OldTown"
HARBOR_PATH = "/Game/Levels/Harbor/L_Harbor"
MISSION_PATH = "/Game/Missions/FindKey/DA_FindKey"
SYSTEM_PATH = "/Game/Systems/Inventory/BPC_Inventory"
HILLS_LEVEL = "/Game/Terrain/Hills/Desktop/L_Hills"

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


class FakeUnrealClient:
    """Records each code string and answers with one ``NMG_RESULT {json}`` line.

    ``results`` and ``raises`` are keyed by the path the code assigns to ``PATH``.
    """

    def __init__(
        self,
        results: Mapping[str, Mapping[str, Any]] | None = None,
        raises: Mapping[str, Exception] | None = None,
    ) -> None:
        self.codes: list[str] = []
        self._results = dict(results or {})
        self._raises = dict(raises or {})

    def execute_python_code(self, code: str, *, timeout: float | None = None) -> str:
        self.codes.append(code)
        path = _target_path(code)
        if path in self._raises:
            raise self._raises[path]
        default: dict[str, Any] = {"ok": True, "created": True, "path": path, "error": None}
        result = self._results.get(path, default)
        return f"NMG_RESULT {json.dumps(result)}\n"


def _target_path(code: str) -> str:
    match = re.search(r"^PATH = (.+)$", code, re.MULTILINE)
    assert match is not None, "generated code does not assign PATH"
    value: str = ast.literal_eval(match.group(1))
    return value


def _code_for(codes: list[str], path: str) -> str:
    matches = [code for code in codes if f"PATH = '{path}'" in code]
    assert len(matches) == 1, path
    return matches[0]


def _unreachable() -> PipelineError:
    return PipelineError(
        UNREACHABLE_CODE,
        "Unreal MCP is unreachable at http://127.0.0.1:55557/mcp",
        "Open the Unreal editor with the nmg-game-dev plugin, then rerun scaffold",
        "unreal_mcp",
    )


def _write(root: Path, relative: str, text: str) -> None:
    path = root / "docs" / "design" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _sync(root: Path) -> None:
    out, err = io.StringIO(), io.StringIO()
    assert main(["sync", "--project", str(root)], stdout=out, stderr=err) == 0, err.getvalue()


def _project(root: Path, docs: Mapping[str, str]) -> Path:
    for relative, text in docs.items():
        _write(root, relative, text)
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


def _run(root: Path, client: FakeUnrealClient) -> ScaffoldReport:
    report = ScaffoldReport()
    run_scaffold(client, root, report)
    return report


def _run_region(root: Path, existing: Iterable[str]) -> tuple[FakeUnreal, dict[str, Any]]:
    """Run the Old Town region code on the fake unreal module, with ``existing`` assets present."""
    fake = FakeUnreal(existing)
    result = fake.run(_code_for(_codes(root), REGION_PATH))
    return fake, result


def _codes(root: Path) -> list[str]:
    client = FakeUnrealClient()
    _run(root, client)
    return client.codes


def _texts(report: ScaffoldReport) -> list[str]:
    return [line.text() for line in report.lines]


def _statuses(root: Path) -> dict[str, str]:
    return {entry.asset_name: entry.status for entry in backlog.load(backlog_path(root))}


def test_region_code_builds_a_level_with_ground_player_start_and_lights(tmp_path: Path) -> None:
    code = _code_for(_codes(_full_project(tmp_path)), REGION_PATH)

    assert "/Engine/BasicShapes/Plane" in code
    assert "unreal.PlayerStart" in code
    assert "unreal.DirectionalLight" in code
    assert "unreal.SkyLight" in code


def test_mission_code_writes_the_data_asset_from_the_entry(tmp_path: Path) -> None:
    code = _code_for(_codes(_full_project(tmp_path)), MISSION_PATH)

    assert "NmgMissionDefinition" in code
    for field in ("mission_name", "act", "region", "depends_on", "design_doc_path"):
        assert f'set_editor_property("{field}"' in code
    assert "MISSION_NAME = 'Find Key'\n" in code
    assert "ACT = 2\n" in code
    assert "REGION = 'OldTown'\n" in code
    assert "DEPENDS_ON = ['OldTown', 'Crate']\n" in code
    assert "DESIGN_DOC_PATH = 'docs/design/missions/find-key.md'\n" in code


def test_system_code_creates_an_actor_component_blueprint(tmp_path: Path) -> None:
    code = _code_for(_codes(_full_project(tmp_path)), SYSTEM_PATH)

    assert "ActorComponent" in code
    assert "BlueprintFactory" in code


def test_every_scaffold_code_checks_existence_before_it_creates(tmp_path: Path) -> None:
    codes = _codes(_full_project(tmp_path))

    assert len(codes) == 3
    for code in codes:
        check = code.index("does_asset_exist(PATH)")
        creates = [
            code.index(token)
            for token in ("levels.new_level(", "tools.create_asset(")
            if token in code
        ]
        assert creates, code
        assert check < min(creates)


def test_report_lines_say_created_unchanged_or_skipped(tmp_path: Path) -> None:
    root = _full_project(tmp_path)
    (root / "docs" / "design" / "systems" / "inventory.md").unlink()
    _sync(root)
    mission_exists = {"ok": True, "created": False, "path": MISSION_PATH, "error": None}
    client = FakeUnrealClient(results={MISSION_PATH: mission_exists})

    report = _run(root, client)

    assert _texts(report) == [
        f"unchanged mission FindKey: {MISSION_PATH}",
        f"created region OldTown: {REGION_PATH}",
        "skipped system Inventory: docs/design/systems/inventory.md",
    ]
    assert report.failed is False
    assert _statuses(root) == {
        "Crate": "planned",
        "FindKey": "scaffolded",
        "Inventory": "orphaned",
        "OldTown": "scaffolded",
    }


def test_orphaned_entries_are_never_sent_to_unreal(tmp_path: Path) -> None:
    root = _full_project(tmp_path)
    (root / "docs" / "design" / "systems" / "inventory.md").unlink()
    _sync(root)
    client = FakeUnrealClient()

    _run(root, client)

    assert len(client.codes) == 2
    assert not any("BPC_Inventory" in code for code in client.codes)


def test_a_failed_item_is_reported_and_the_other_items_still_run(tmp_path: Path) -> None:
    root = _full_project(tmp_path)
    region_failed = {
        "ok": False,
        "created": False,
        "path": REGION_PATH,
        "error": "RuntimeError: could not save the level",
    }
    client = FakeUnrealClient(results={REGION_PATH: region_failed})

    report = _run(root, client)

    assert report.failed is True
    texts = _texts(report)
    assert "error design.scaffold_failed OldTown: RuntimeError: could not save the level" in texts
    assert f"created mission FindKey: {MISSION_PATH}" in texts
    assert f"created system Inventory: {SYSTEM_PATH}" in texts
    assert len(client.codes) == 3
    assert _statuses(root)["OldTown"] == "planned"


def test_a_pipeline_error_from_one_item_becomes_its_error_line(tmp_path: Path) -> None:
    root = _full_project(tmp_path)
    refused = PipelineError("import_ue.failed", "the editor refused the level", "rerun", "import")
    client = FakeUnrealClient(raises={REGION_PATH: refused})

    report = _run(root, client)

    assert report.failed is True
    assert "error design.scaffold_failed OldTown: the editor refused the level" in _texts(report)
    assert len(client.codes) == 3


def test_backlog_is_written_once_per_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _full_project(tmp_path)
    original = backlog.update_statuses
    calls: list[dict[str, str]] = []

    def counting(path: Path, statuses: Mapping[str, str]) -> list[str]:
        calls.append(dict(statuses))
        return original(path, statuses)

    monkeypatch.setattr(backlog, "update_statuses", counting)
    _run(root, FakeUnrealClient())

    assert len(calls) == 1
    assert calls[0] == {"FindKey": "scaffolded", "Inventory": "scaffolded", "OldTown": "scaffolded"}


def test_unreachable_editor_raises_and_keeps_statuses_of_items_already_scaffolded(
    tmp_path: Path,
) -> None:
    root = _full_project(tmp_path)
    client = FakeUnrealClient(raises={SYSTEM_PATH: _unreachable()})
    report = ScaffoldReport()

    with pytest.raises(PipelineError) as caught:
        run_scaffold(client, root, report)

    assert caught.value.code == UNREACHABLE_CODE
    assert _texts(report) == [
        f"created mission FindKey: {MISSION_PATH}",
        f"created region OldTown: {REGION_PATH}",
    ]
    assert len(client.codes) == 3
    assert _statuses(root) == {
        "Crate": "planned",
        "FindKey": "scaffolded",
        "Inventory": "planned",
        "OldTown": "scaffolded",
    }


def test_missing_backlog_raises_before_any_editor_call(tmp_path: Path) -> None:
    _write(tmp_path, "regions/old-town.md", REGION)
    client = FakeUnrealClient()

    with pytest.raises(FileNotFoundError):
        _run(tmp_path, client)

    assert client.codes == []


def test_region_code_names_the_desktop_terrain_level_of_its_terrain(tmp_path: Path) -> None:
    codes = _codes(_terrain_project(tmp_path))

    assert len(codes) == 1, "the terrain entry itself is not scaffolded"
    assert f"TERRAIN_LEVEL = '{HILLS_LEVEL}'\n" in _code_for(codes, REGION_PATH)


def test_region_code_has_no_terrain_level_when_the_region_names_no_terrain(tmp_path: Path) -> None:
    code = _code_for(_codes(_full_project(tmp_path)), REGION_PATH)

    assert "TERRAIN_LEVEL = None\n" in code


def test_region_streams_an_existing_terrain_level_and_spawns_no_plane(tmp_path: Path) -> None:
    fake, result = _run_region(_terrain_project(tmp_path), existing={HILLS_LEVEL})

    assert result == {
        "ok": True,
        "created": True,
        "path": REGION_PATH,
        "error": None,
        "terrain": HILLS_LEVEL,
    }
    streamed = ("add_level_to_world", REGION_PATH, HILLS_LEVEL, "LevelStreamingAlwaysLoaded")
    assert streamed in fake.calls
    assert fake.calls.index(("new_level", REGION_PATH)) < fake.calls.index(streamed)
    assert "StaticMeshActor" not in fake.spawned()
    assert ("load_asset", PLANE) not in fake.calls
    assert {"PlayerStart", "DirectionalLight", "SkyLight"} <= set(fake.spawned())
    assert fake.open_level == DEFAULT_LEVEL, "the editor returns to the level it had open"


def test_region_spawns_the_plane_when_its_terrain_level_does_not_exist(tmp_path: Path) -> None:
    fake, result = _run_region(_terrain_project(tmp_path), existing=())

    assert result == {
        "ok": True,
        "created": True,
        "path": REGION_PATH,
        "error": None,
        "terrain": None,
    }
    assert not any(call[0] == "add_level_to_world" for call in fake.calls)
    assert "StaticMeshActor" in fake.spawned()
    assert ("load_asset", PLANE) in fake.calls
    assert ("scale", (100, 100, 1)) in fake.calls
    assert {"PlayerStart", "DirectionalLight", "SkyLight"} <= set(fake.spawned())


def test_region_without_a_terrain_field_spawns_the_plane(tmp_path: Path) -> None:
    fake, result = _run_region(_full_project(tmp_path), existing={HILLS_LEVEL})

    assert result["terrain"] is None
    assert not any(call[0] == "add_level_to_world" for call in fake.calls)
    assert ("load_asset", PLANE) in fake.calls


def test_region_naming_no_terrain_entry_is_an_unknown_reference_and_the_others_still_run(
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
    client = FakeUnrealClient()

    report = _run(root, client)

    assert report.failed is True
    texts = _texts(report)
    assert (
        "error design.unknown_reference OldTown: "
        "terrain 'Ghost' names no environment entry with asset_class terrain"
    ) in texts
    assert f"created region Harbor: {HARBOR_PATH}" in texts
    assert f"created system Inventory: {SYSTEM_PATH}" in texts
    assert len(client.codes) == 2, "no Unreal call is made for the region that names no terrain"
    assert all(REGION_PATH not in code for code in client.codes)
    assert _statuses(root) == {
        "Harbor": "scaffolded",
        "Hills": "planned",
        "Inventory": "scaffolded",
        "OldTown": "planned",
    }
