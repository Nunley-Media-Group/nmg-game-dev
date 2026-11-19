# ruff: noqa: E501  -- step decorators repeat the Gherkin text verbatim, so they run long.
"""pytest-bdd bindings for design.feature: SCN001-SCN007 of #112.

The steps share one ``state`` dict per scenario.  The project root is a temp directory with an
empty ``game/project.godot``, and ``CLAUDE_PROJECT_DIR`` points at it, so nothing touches the real
repository.  Scaffolding writes Godot text files directly, so no engine runs.
"""

from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, scenario, then, when

from nmg_game_dev.design import backlog
from nmg_game_dev.design.__main__ import main as design_main
from nmg_game_dev.design.model import Entry
from nmg_game_dev.design.paths import backlog_path
from nmg_game_dev.finalize import FinalizeService, finalize_asset
from nmg_game_dev.pipeline import FinalizeClients, FinalizeRequest, jobs
from tests.bdd.test_onboard_bdd import _fresh, _install
from tests.finalize_fakes import FakeBlenderSession, FakeStepRunner, FinalizeGodot

FEATURE = "design.feature"
REPO_ROOT = Path(__file__).resolve().parents[2]
DESIGN_CONTRACT = REPO_ROOT / "docs" / "design-contract.md"


REGION_FILE = "game/levels/OldTown/OldTown.tscn"
MISSION_FILE = "game/missions/FirstLight.tres"
SYSTEM_FILE = "game/systems/Stamina/stamina.gd"


def _game_files(root: Path) -> dict[str, bytes]:
    game = root / "game"
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in game.rglob("*") if p.is_file()}


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    root = tmp_path / "project"
    (root / "game").mkdir(parents=True)
    (root / "game" / "project.godot").write_text("config_version=5\n", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    return {"root": root, "tmp": tmp_path, "out": "", "exit": None, "before": None}


def _write(root: Path, relative: str, text: str) -> None:
    path = root / "docs" / "design" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _crate(category: str = "Props", asset_class: str = "standard_prop") -> str:
    return f"---\ntype: prop\nname: Crate\ncategory: {category}\nasset_class: {asset_class}\n---\n"


REGION = "---\ntype: region\nname: Old Town\n---\n"
MISSION = "---\ntype: mission\nname: First Light\nregion: Old Town\n---\n"
SYSTEM = "---\ntype: system\nname: Stamina\n---\n"


def _sync(state: dict[str, Any]) -> int:
    out, err = io.StringIO(), io.StringIO()
    code = design_main(["sync", "--project", str(state["root"])], stdout=out, stderr=err)
    state["out"], state["exit"] = out.getvalue(), code
    state["err"] = err.getvalue()
    return code


def _scaffold(state: dict[str, Any]) -> int:
    out, err = io.StringIO(), io.StringIO()
    code = design_main(["scaffold", "--project", str(state["root"])], stdout=out, stderr=err)
    state["out"], state["exit"] = out.getvalue(), code
    state["err"] = err.getvalue()
    return code


def _statuses(root: Path) -> dict[str, str]:
    return {entry.asset_name: entry.status for entry in backlog.load(backlog_path(root))}


def _entry(root: Path, asset_name: str) -> Entry:
    return next(e for e in backlog.load(backlog_path(root)) if e.asset_name == asset_name)


# --- SCN001 ------------------------------


@scenario(FEATURE, "Design docs parse into a sorted backlog")
def test_design_docs_parse_into_a_sorted_backlog() -> None:
    """AC1: one planned entry per file, sorted by type then asset name, one line each."""


@given(
    'a project whose docs/design holds a prop "Crate", a region "Old Town", and a mission "First Light"'
)
def _three_docs(state: dict[str, Any]) -> None:
    _write(state["root"], "props/crate.md", _crate())
    _write(state["root"], "regions/old-town.md", REGION)
    _write(state["root"], "regions/first-light.md", MISSION)


@when("design sync runs")
def _sync_runs(state: dict[str, Any]) -> None:
    _sync(state)


@then(
    "docs/design/backlog.json lists Crate, OldTown, and FirstLight sorted by type then asset name with status planned"
)
def _sorted_planned(state: dict[str, Any]) -> None:
    assert state["exit"] == 0, state["err"]
    listed = [(e.type, e.asset_name, e.status) for e in backlog.load(backlog_path(state["root"]))]
    assert listed == [
        ("mission", "FirstLight", "planned"),
        ("prop", "Crate", "planned"),
        ("region", "OldTown", "planned"),
    ]


@then("one planned line is printed per entry")
def _one_line_each(state: dict[str, Any]) -> None:
    lines = state["out"].splitlines()
    assert len(lines) == 3
    assert all(line.startswith("planned ") for line in lines)


# --- SCN002 ------------------------------


@scenario(FEATURE, "Re-sync keeps progress and marks removed docs orphaned")
def test_resync_keeps_progress_and_marks_removed_docs_orphaned() -> None:
    """AC2: status kept, fields updated, new planned, removed orphaned, byte-stable re-sync."""


@given("a backlog where Crate is finalized and OldTown is scaffolded")
def _progressed_backlog(state: dict[str, Any]) -> None:
    _write(state["root"], "props/crate.md", _crate())
    _write(state["root"], "regions/old-town.md", REGION)
    _write(state["root"], "regions/first-light.md", MISSION)
    assert _sync(state) == 0
    backlog.update_statuses(
        backlog_path(state["root"]), {"Crate": "finalized", "OldTown": "scaffolded"}
    )


@when(
    'the Crate doc is edited, a system doc "Stamina" is added, and the First Light doc is deleted, and sync runs'
)
def _edit_add_delete(state: dict[str, Any]) -> None:
    root = state["root"]
    _write(root, "props/crate.md", _crate(asset_class="hero_prop"))
    _write(root, "systems/stamina.md", SYSTEM)
    (root / "docs" / "design" / "regions" / "first-light.md").unlink()
    _sync(state)


@then(
    "Crate stays finalized with its new fields, OldTown stays scaffolded, Stamina is planned, and FirstLight is orphaned"
)
def _statuses_after_resync(state: dict[str, Any]) -> None:
    assert state["exit"] == 0, state["err"]
    root = state["root"]
    assert _statuses(root) == {
        "Crate": "finalized",
        "OldTown": "scaffolded",
        "Stamina": "planned",
        "FirstLight": "orphaned",
    }
    assert _entry(root, "Crate").fields["asset_class"] == "hero_prop"


@then("syncing again without changes writes a byte-identical backlog")
def _byte_identical(state: dict[str, Any]) -> None:
    path = backlog_path(state["root"])
    before = path.read_bytes()
    assert _sync(state) == 0
    assert path.read_bytes() == before


# --- SCN003 ------------------------------


@scenario(FEATURE, "Invalid design docs are reported and the backlog is kept")
def test_invalid_design_docs_are_reported_and_the_backlog_is_kept() -> None:
    """AC3: each problem reported with its file and field; the existing backlog is untouched."""


@given(
    "a doc with no frontmatter, a prop with no asset_class, and a mission whose region names no entry"
)
def _invalid_docs(state: dict[str, Any]) -> None:
    root = state["root"]
    _write(root, "props/crate.md", _crate())
    assert _sync(state) == 0
    state["before"] = backlog_path(root).read_bytes()
    _write(root, "notes/loose.md", "No frontmatter here.\n")
    _write(root, "props/bare.md", "---\ntype: prop\nname: Bare\ncategory: Props\n---\n")
    _write(root, "missions/lost.md", "---\ntype: mission\nname: Lost\nregion: Nowhere\n---\n")


@then(
    "it reports design.frontmatter_missing, design.missing_field, and design.unknown_reference with each file and field"
)
def _reports_each_code(state: dict[str, Any]) -> None:
    out = state["out"]
    assert "error design.frontmatter_missing docs/design/notes/loose.md: frontmatter" in out
    assert "error design.missing_field docs/design/props/bare.md: asset_class" in out
    assert "error design.unknown_reference docs/design/missions/lost.md: region" in out


@then("it exits 1 and the existing backlog is unchanged")
def _exits_and_keeps_backlog(state: dict[str, Any]) -> None:
    assert state["exit"] == 1
    assert backlog_path(state["root"]).read_bytes() == state["before"]


# --- SCN004 ------------------------------


@scenario(FEATURE, "finalize_asset takes category and class from the backlog")
def test_finalize_asset_takes_category_and_class_from_the_backlog() -> None:
    """AC4: the request uses the backlog values, and a successful job marks the entry finalized."""


@given("a backlog prop entry Crate with category Props and asset_class standard_prop")
def _prop_entry(state: dict[str, Any]) -> None:
    _write(state["root"], "props/crate.md", _crate())
    assert _sync(state) == 0


@when(
    "finalize_asset is called for collection Crate without category or asset_class and the job succeeds"
)
def _finalize_without_arguments(state: dict[str, Any]) -> None:
    blend = state["tmp"] / "crate.blend"
    blend.write_bytes(b"authored")
    cache = state["tmp"] / "cache"
    service = FinalizeService(cache, launcher=lambda job_dir: os.getpid())
    response = finalize_asset(
        collection="Crate",
        export_root=str(state["tmp"] / "game" / "assets"),
        blend=str(blend),
        service=service,
    )
    job_dir = cache / "jobs" / str(response["job_id"])
    request = FinalizeRequest.model_validate_json(
        (job_dir / "request.json").read_text(encoding="utf-8")
    )
    jobs.run_job(
        job_dir,
        clients=FinalizeClients(
            blender=FakeBlenderSession(), godot=FinalizeGodot(state["tmp"] / "game")
        ),
        runner=FakeStepRunner(request),
    )
    state["request"] = request
    state["job_state"] = service.status(str(response["job_id"]))["state"]


@then("the request used Props and standard_prop")
def _request_used_backlog_values(state: dict[str, Any]) -> None:
    assert state["job_state"] == "succeeded"
    assert state["request"].category == "Props"
    assert state["request"].asset_class == "standard_prop"


@then("the Crate entry's status is finalized")
def _crate_finalized(state: dict[str, Any]) -> None:
    assert _statuses(state["root"])["Crate"] == "finalized"


# --- SCN005 ------------------------------


@scenario(FEATURE, "Regions, missions, and systems are scaffolded as Godot files")
def test_regions_missions_and_systems_are_scaffolded_as_godot_files() -> None:
    """#249 AC7: each non-asset entry gets its Godot file and is marked scaffolded."""


@given("planned entries OldTown (region), FirstLight (mission in OldTown), and Stamina (system)")
def _planned_non_assets(state: dict[str, Any]) -> None:
    root = state["root"]
    _write(root, "regions/old-town.md", REGION)
    _write(root, "missions/first-light.md", MISSION)
    _write(root, "systems/stamina.md", SYSTEM)
    assert _sync(state) == 0


@when("design scaffold runs against the Godot project")
def _scaffold_against_project(state: dict[str, Any]) -> None:
    _scaffold(state)


@then(
    "it creates game/levels/OldTown/OldTown.tscn, game/missions/FirstLight.tres, and game/systems/Stamina/stamina.gd"
)
def _creates_three_files(state: dict[str, Any]) -> None:
    assert state["exit"] == 0, state["err"]
    root = state["root"]
    assert set(_game_files(root)) == {"game/project.godot", REGION_FILE, MISSION_FILE, SYSTEM_FILE}
    scene = (root / REGION_FILE).read_text(encoding="utf-8")
    for node in ('type="Marker3D"', 'type="DirectionalLight3D"', 'type="WorldEnvironment"'):
        assert node in scene
    mission = (root / MISSION_FILE).read_text(encoding="utf-8")
    assert 'script_class="NmgMissionDefinition"' in mission
    for field in ("mission_name", "act", "region", "depends_on", "design_doc_path"):
        assert f"\n{field} = " in mission
    assert "class_name StaminaComponent\nextends Node\n" in (root / SYSTEM_FILE).read_text("utf-8")


@then("the three entries are scaffolded")
def _three_scaffolded(state: dict[str, Any]) -> None:
    statuses = _statuses(state["root"])
    assert statuses["OldTown"] == statuses["FirstLight"] == statuses["Stamina"] == "scaffolded"


@then("a second scaffold leaves every file unchanged")
def _second_scaffold_unchanged(state: dict[str, Any]) -> None:
    before = _game_files(state["root"])
    assert _scaffold(state) == 0, state["err"]
    assert _game_files(state["root"]) == before
    assert all(line.startswith("unchanged ") for line in state["out"].splitlines())


# --- SCN006 ------------------------------


@scenario(FEATURE, "Existing scaffold targets are left alone")
def test_existing_scaffold_targets_are_left_alone() -> None:
    """AC6: an existing target prints unchanged and is not modified; the others still scaffold."""


@given("game/levels/OldTown/OldTown.tscn already exists")
def _level_exists(state: dict[str, Any]) -> None:
    root = state["root"]
    _write(root, "regions/old-town.md", REGION)
    _write(root, "missions/first-light.md", MISSION)
    _write(root, "systems/stamina.md", SYSTEM)
    assert _sync(state) == 0
    level = root / REGION_FILE
    level.parent.mkdir(parents=True)
    level.write_text("[gd_scene format=3]\n# hand-made\n", encoding="utf-8")
    state["before"] = level.read_bytes()


@when("design scaffold runs")
def _scaffold_runs(state: dict[str, Any]) -> None:
    _scaffold(state)


@then("it prints unchanged for OldTown without modifying the level")
def _unchanged_level(state: dict[str, Any]) -> None:
    assert state["exit"] == 0, state["err"]
    assert f"unchanged region OldTown: {REGION_FILE}" in state["out"]
    assert (state["root"] / REGION_FILE).read_bytes() == state["before"]


@then("the other entries still scaffold")
def _others_scaffold(state: dict[str, Any]) -> None:
    assert f"created mission FirstLight: {MISSION_FILE}" in state["out"]
    assert f"created system Stamina: {SYSTEM_FILE}" in state["out"]
    assert _statuses(state["root"])["OldTown"] == "scaffolded"


# --- SCN007 ------------------------------


@scenario(FEATURE, "Onboarding installs the design contract")
def test_onboarding_installs_the_design_contract() -> None:
    """AC7: the contract is installed, docs/design/ keeps its file, and the block links it."""


@given(
    "a consumer project with a docs/design folder that already holds a file", target_fixture="ctx"
)
def _consumer_with_design_file(tmp_path: Path) -> dict[str, Any]:
    ctx = _fresh(tmp_path)
    design = ctx["consumer"] / "docs" / "design"
    design.mkdir(parents=True)
    (design / "crate.md").write_text("keep me\n", encoding="utf-8")
    return ctx


@when("onboard-consumer runs")
def _onboard_runs(ctx: dict[str, Any]) -> None:
    _install(ctx)
    assert ctx["error"] is None, ctx["error"]


@then(
    "docs/nmg-game-dev/design-contract.md is installed and the existing docs/design file is untouched"
)
def _contract_installed(ctx: dict[str, Any]) -> None:
    installed = ctx["consumer"] / "docs" / "nmg-game-dev" / "design-contract.md"
    assert installed.read_bytes() == DESIGN_CONTRACT.read_bytes()
    assert (ctx["consumer"] / "docs" / "design" / "crate.md").read_text(encoding="utf-8") == (
        "keep me\n"
    )


@then("the CLAUDE.md nmg-game-dev block links the design contract")
def _block_links_contract(ctx: dict[str, Any]) -> None:
    claude_md = (ctx["consumer"] / "CLAUDE.md").read_text(encoding="utf-8")
    assert claude_md.count("docs/nmg-game-dev/design-contract.md") == 1
