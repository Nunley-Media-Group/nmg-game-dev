# ruff: noqa: E501  -- step decorators repeat the Gherkin text verbatim, so they run long.
"""pytest-bdd bindings for convert_to_godot.feature: SCN011-SCN013 (#249 AC11-AC13).

Each scenario runs the real ``run_convert`` on the fixture Unreal consumer from
``tests/convert_fakes.py`` in a real git repository. Every collaborator (onboarding, finalize, the
WAV import, the scaffold, and the Godot preflight) is a recording fake, so no Blender, Godot, or
ffmpeg runs. The steps share one ``state`` dict per scenario.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, scenario, then, when

from nmg_game_dev.pipeline.errors import PipelineError
from tests.convert_fakes import (
    BLENDER_HOOK,
    FAIL_CODE,
    FAIL_REMEDIATION,
    Collaborators,
    finalized_names,
    git,
    make_unreal_consumer,
    snapshot,
    tracked,
)
from tests.unit.convert.test_runner import ALL_KEYS, UNREAL_PATHS, convert

FEATURE = "convert_to_godot.feature"
UNREAL_SCRIPT = "scripts/start-unreal-mcp.sh"
MANUAL_PORT = (
    "Source/Game/Game.cpp",
    "Source/Game/Game.h",
    "Content/Maps/Main.umap",
    "Content/Misc/Stray.uasset",
)
FAILED_ASSET = "asset:Props/Crate"


@pytest.fixture
def state(tmp_path: Path) -> dict[str, Any]:
    return {"tmp": tmp_path}


def _report(root: Path) -> str:
    return (root / "godot-conversion-report.md").read_text(encoding="utf-8")


def _run(state: dict[str, Any], fakes: Collaborators) -> None:
    state["fakes"] = fakes
    state["result"], state["printed"] = convert(state["root"], fakes)


@scenario(FEATURE, "Converting an Unreal consumer to Godot")
def test_scn011_converting_an_unreal_consumer() -> None:
    """AC11: every item converts into game/, the report is written, and Unreal is removed."""


@scenario(FEATURE, "Partial conversion keeps Unreal and resumes")
def test_scn012_partial_conversion_keeps_unreal_and_resumes() -> None:
    """AC12: one failure keeps every Unreal file; a rerun converts only that asset."""


@scenario(FEATURE, "Conversion guards and dry run")
def test_scn013_conversion_guards_and_dry_run() -> None:
    """AC13: a dirty tree or a missing .uproject stops before writing; --dry-run writes nothing."""


# --- Given ---------------------------------------------------------------------------------------


@given(
    "a clean Unreal consumer with finalized assets, SourceArt sources, WAVs, a scaffolded backlog, and an Unreal hook"
)
def _clean_consumer(state: dict[str, Any]) -> None:
    root = make_unreal_consumer(state["tmp"] / "Game")
    assert git(root, "status", "--porcelain") == ""
    settings = (root / ".claude" / "settings.json").read_text(encoding="utf-8")
    assert UNREAL_SCRIPT in settings
    state["root"] = root


@given("a conversion in which one asset fails")
def _one_failure(state: dict[str, Any]) -> None:
    root = make_unreal_consumer(state["tmp"] / "Game")
    state["root"] = root
    state["tracked_before"] = git(root, "ls-files")
    state["fakes"] = Collaborators(fail={FAILED_ASSET})


@given("a consumer with uncommitted changes")
def _dirty_consumer(state: dict[str, Any]) -> None:
    root = make_unreal_consumer(state["tmp"] / "Game")
    (root / "README.md").write_text("# Game\n\nlocal edit\n", encoding="utf-8")
    state["root"] = root
    state["before"] = snapshot(root)


# --- When ----------------------------------------------------------------------------------------


@when("/convert-to-godot runs")
def _convert_runs(state: dict[str, Any]) -> None:
    fakes = Collaborators()
    state["fakes"] = fakes
    try:
        state["result"], state["printed"] = convert(state["root"], fakes)
        state["error"] = None
    except PipelineError as error:
        state["error"] = error


@when("/convert-to-godot finishes")
def _convert_finishes(state: dict[str, Any]) -> None:
    _run(state, state["fakes"])


# --- Then ----------------------------------------------------------------------------------------


@then("every asset, audio file, and scaffolded entry is converted into game/")
def _all_converted(state: dict[str, Any]) -> None:
    assert state["error"] is None, state["error"]
    result = state["result"]
    fakes: Collaborators = state["fakes"]
    root: Path = state["root"].resolve()
    assert result.exit_code == 0 and result.failures == []
    assert result.converted == ALL_KEYS
    assert fakes.onboard_calls == [root]
    assets = root / "game" / "assets"
    assert sorted(finalized_names(fakes)) == ["Crate", "Hero"]
    assert {export_root for *_rest, export_root in fakes.finalized} == {assets}
    for category, name in (("Props", "Crate"), ("Characters", "Hero")):
        for variant in ("Desktop", "Mobile"):
            assert (assets / category / name / variant / f"{name}.glb").is_file()
    assert (assets / "Audio" / "Theme.ogg").is_file()
    assert (assets / "Audio" / "Click.wav").is_file()
    assert [(kind, name, loop) for kind, name, _wav, loop in fakes.imported] == [
        ("SFX", "Click", False),
        ("Music", "Theme", True),
    ]
    assert fakes.scaffold_calls == 1
    scaffolded = sorted(path.name for path in (root / "game" / "scaffolded").iterdir())
    assert scaffolded == ["Harbor.txt", "Intro.txt", "Inventory.txt"]


@then("godot-conversion-report.md lists the converted and manual-port items")
def _report_lists(state: dict[str, Any]) -> None:
    report = _report(state["root"])
    for key in ALL_KEYS:
        assert f"- `{key}`" in report, key
    assert "## Failed\n\nNone." in report
    for path in MANUAL_PORT:
        assert f"| `{path}` |" in report, path


@then("Content/, Source/, Config/, Plugins/, the .uproject, and the Unreal scripts are removed")
def _unreal_removed(state: dict[str, Any]) -> None:
    root: Path = state["root"]
    assert state["result"].deleted
    for name in (*UNREAL_PATHS, UNREAL_SCRIPT):
        assert not (root / name).exists(), name
    assert tracked(root, [*UNREAL_PATHS, UNREAL_SCRIPT]) == []
    # The Blender side stays: its start script, its hook, and the SourceArt sources.
    assert (root / "scripts" / "start-blender-mcp.sh").is_file()
    assert (root / "SourceArt" / "Props" / "crate.blend").is_file()
    settings = json.loads((root / ".claude" / "settings.json").read_text(encoding="utf-8"))
    commands = [
        hook["command"] for group in settings["hooks"]["SessionStart"] for hook in group["hooks"]
    ]
    assert commands == [BLENDER_HOOK]
    assert not any(key.startswith("UE_") for key in settings["env"])


@then(
    "no Unreal file is deleted, the report lists the failure with its code and remediation, and the exit code is non-zero"
)
def _kept_and_reported(state: dict[str, Any]) -> None:
    root: Path = state["root"]
    result = state["result"]
    assert result.exit_code == 1
    assert not result.deleted
    for name in (*UNREAL_PATHS, UNREAL_SCRIPT):
        assert (root / name).exists(), name
    assert git(root, "ls-files") == state["tracked_before"]
    assert [(f.item, f.code, f.remediation) for f in result.failures] == [
        (FAILED_ASSET, FAIL_CODE, FAIL_REMEDIATION)
    ]
    assert f"| `{FAILED_ASSET}` | `{FAIL_CODE}` | {FAIL_REMEDIATION} |" in _report(root)
    assert f"failed {FAILED_ASSET} [{FAIL_CODE}]" in state["printed"]


@then("a rerun converts only the failed asset")
def _rerun_only_failed(state: dict[str, Any]) -> None:
    rerun = Collaborators()
    _run(state, rerun)
    result = state["result"]
    assert result.exit_code == 0
    assert finalized_names(rerun) == ["Crate"]
    assert rerun.imported == []
    assert rerun.scaffold_calls == 0
    assert result.deleted
    assert not (state["root"] / "Game.uproject").exists()


@then('it stops with "convert.dirty_worktree" and writes nothing')
def _dirty_stops(state: dict[str, Any]) -> None:
    error = state["error"]
    assert isinstance(error, PipelineError)
    assert error.code == "convert.dirty_worktree"
    assert error.remediation
    assert snapshot(state["root"]) == state["before"]
    fakes: Collaborators = state["fakes"]
    assert fakes.onboard_calls == [] and fakes.preflight_calls == 0


@then('on a clean consumer without a .uproject it stops with "convert.not_unreal"')
def _not_unreal(state: dict[str, Any]) -> None:
    root = make_unreal_consumer(state["tmp"] / "NoProject", uproject=False)
    before = snapshot(root)
    fakes = Collaborators()
    with pytest.raises(PipelineError) as caught:
        convert(root, fakes)
    assert caught.value.code == "convert.not_unreal"
    assert caught.value.remediation
    assert snapshot(root) == before
    assert fakes.onboard_calls == []


@then(
    "with --dry-run on a valid consumer it prints every planned conversion and deletion and writes nothing"
)
def _dry_run(state: dict[str, Any]) -> None:
    root = make_unreal_consumer(state["tmp"] / "DryRun")
    before = snapshot(root)
    fakes = Collaborators()
    result, printed = convert(root, fakes, dry_run=True)
    assert result.exit_code == 0 and result.dry_run
    assert printed.splitlines() == [
        *(f"PLAN convert {key}" for key in ALL_KEYS),
        "PLAN delete Content/",
        "PLAN delete Source/",
        "PLAN delete Config/",
        "PLAN delete Plugins/",
        "PLAN delete Game.uproject",
        f"PLAN delete {UNREAL_SCRIPT}",
    ]
    assert snapshot(root) == before
    assert git(root, "status", "--porcelain") == ""
    assert fakes.onboard_calls == [] and fakes.finalized == [] and fakes.scaffold_calls == 0
