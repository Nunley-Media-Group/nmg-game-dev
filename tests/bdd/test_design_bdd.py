# ruff: noqa: E501  -- step decorators repeat the Gherkin text verbatim, so they run long.
"""pytest-bdd bindings for design.feature: SCN001-SCN007 of #112.

The steps share one ``state`` dict per scenario.  The project root is a temp directory, and
``CLAUDE_PROJECT_DIR`` points at it, so nothing touches the real repository.  The Unreal editor is
a fake that answers each scaffold call the way the generated UE code does.
"""

from __future__ import annotations

import ast
import io
import json
import os
import re
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
from tests.finalize_fakes import FakeBlenderSession, FakeStepRunner, FakeUnrealRunner

FEATURE = "design.feature"
REPO_ROOT = Path(__file__).resolve().parents[2]
DESIGN_CONTRACT = REPO_ROOT / "docs" / "design-contract.md"


class FakeEditor:
    """Answers scaffold calls like the generated UE code: an existing target is not created."""

    def __init__(self, existing: set[str] | None = None) -> None:
        self.existing: set[str] = set(existing or ())
        self.created: list[str] = []

    def execute_python_code(self, code: str) -> str:
        assert "does_asset_exist(PATH)" in code, "the existence check must come first"
        path = _path_of(code)
        if path in self.existing:
            return _result(created=False, path=path)
        self.existing.add(path)
        self.created.append(path)
        return _result(created=True, path=path)


def _path_of(code: str) -> str:
    match = re.search(r"^PATH = (.+)$", code, re.MULTILINE)
    assert match, "the generated code assigns PATH"
    return str(ast.literal_eval(match.group(1)))


def _result(*, created: bool, path: str) -> str:
    return "NMG_RESULT " + json.dumps({"ok": True, "created": created, "path": path, "error": None})


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    return {"root": root, "tmp": tmp_path, "out": "", "exit": None, "editor": None, "before": None}


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
    code = design_main(
        ["scaffold", "--project", str(state["root"])],
        client=state["editor"],
        stdout=out,
        stderr=err,
    )
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
        export_root=str(state["tmp"] / "export"),
        blend=str(blend),
        service=service,
    )
    job_dir = cache / "jobs" / str(response["job_id"])
    request = FinalizeRequest.model_validate_json(
        (job_dir / "request.json").read_text(encoding="utf-8")
    )
    jobs.run_job(
        job_dir,
        clients=FinalizeClients(blender=FakeBlenderSession(), unreal=FakeUnrealRunner()),
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


@scenario(FEATURE, "Regions, missions, and systems are scaffolded in Unreal")
def test_regions_missions_and_systems_are_scaffolded_in_unreal() -> None:
    """AC5: each non-asset entry gets its UE asset and is marked scaffolded."""


@given("planned entries OldTown (region), FirstLight (mission in OldTown), and Stamina (system)")
def _planned_non_assets(state: dict[str, Any]) -> None:
    root = state["root"]
    _write(root, "regions/old-town.md", REGION)
    _write(root, "missions/first-light.md", MISSION)
    _write(root, "systems/stamina.md", SYSTEM)
    assert _sync(state) == 0


@when("design scaffold runs against the editor")
def _scaffold_against_editor(state: dict[str, Any]) -> None:
    state["editor"] = FakeEditor()
    _scaffold(state)


@then(
    "it creates /Game/Levels/OldTown/L_OldTown, /Game/Missions/FirstLight/DA_FirstLight, and /Game/Systems/Stamina/BPC_Stamina"
)
def _creates_three_assets(state: dict[str, Any]) -> None:
    assert state["exit"] == 0, state["err"]
    assert set(state["editor"].created) == {
        "/Game/Levels/OldTown/L_OldTown",
        "/Game/Missions/FirstLight/DA_FirstLight",
        "/Game/Systems/Stamina/BPC_Stamina",
    }


@then("the three entries are scaffolded")
def _three_scaffolded(state: dict[str, Any]) -> None:
    statuses = _statuses(state["root"])
    assert statuses["OldTown"] == statuses["FirstLight"] == statuses["Stamina"] == "scaffolded"


# --- SCN006 ------------------------------


@scenario(FEATURE, "Existing scaffold targets are left alone")
def test_existing_scaffold_targets_are_left_alone() -> None:
    """AC6: an existing target prints unchanged and is not modified; the others still scaffold."""


@given("/Game/Levels/OldTown/L_OldTown already exists")
def _level_exists(state: dict[str, Any]) -> None:
    root = state["root"]
    _write(root, "regions/old-town.md", REGION)
    _write(root, "missions/first-light.md", MISSION)
    _write(root, "systems/stamina.md", SYSTEM)
    assert _sync(state) == 0
    state["editor"] = FakeEditor(existing={"/Game/Levels/OldTown/L_OldTown"})


@when("design scaffold runs")
def _scaffold_runs(state: dict[str, Any]) -> None:
    _scaffold(state)


@then("it prints unchanged for OldTown without modifying the level")
def _unchanged_level(state: dict[str, Any]) -> None:
    assert state["exit"] == 0, state["err"]
    assert "unchanged region OldTown: /Game/Levels/OldTown/L_OldTown" in state["out"]
    assert "/Game/Levels/OldTown/L_OldTown" not in state["editor"].created


@then("the other entries still scaffold")
def _others_scaffold(state: dict[str, Any]) -> None:
    assert "created mission FirstLight: /Game/Missions/FirstLight/DA_FirstLight" in state["out"]
    assert "created system Stamina: /Game/Systems/Stamina/BPC_Stamina" in state["out"]
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
