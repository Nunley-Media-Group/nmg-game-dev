"""``run_convert`` on a fixture Unreal consumer in a real git repository (#249 AC11–AC13).

Every collaborator is a recording fake from ``tests/convert_fakes.py``; git is real, so the
deletions go through ``git rm`` and the dirty-tree guard reads a real ``git status``.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from nmg_game_dev.convert import __main__ as convert_cli
from nmg_game_dev.convert.runner import ConvertResult, replace_settings, run_convert
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

UNREAL_PATHS = ("Content", "Source", "Config", "Plugins", "Game.uproject")
ALL_KEYS = [
    "asset:Characters/Hero",
    "asset:Props/Crate",
    "audio:SFX/Click",
    "audio:Music/Theme",
    "scaffold:mission/Intro",
    "scaffold:region/Harbor",
    "scaffold:system/Inventory",
]


@pytest.fixture
def consumer(tmp_path: Path) -> Path:
    return make_unreal_consumer(tmp_path / "Game")


def convert(
    root: Path, fakes: Collaborators, *, dry_run: bool = False
) -> tuple[ConvertResult, str]:
    out = io.StringIO()
    result = run_convert(root, dry_run=dry_run, out=out, **fakes.kwargs())  # type: ignore[arg-type]
    return result, out.getvalue()


def test_full_conversion(consumer: Path) -> None:
    """AC11: onboard, finalize, import, re-scaffold, settings, report, then git rm."""
    fakes = Collaborators()
    result, printed = convert(consumer, fakes)

    assert result.exit_code == 0 and result.failures == []
    assert result.converted == ALL_KEYS
    assert fakes.onboard_calls == [consumer.resolve()]
    assert fakes.preflight_calls == 1

    export_root = consumer.resolve() / "game" / "assets"
    assert fakes.finalized == [
        (
            "Characters",
            "Hero",
            "character",
            consumer.resolve() / "SourceArt/Characters/HERO.blend",
            export_root,
        ),
        (
            "Props",
            "Crate",
            "standard_prop",
            consumer.resolve() / "SourceArt/Props/crate.blend",
            export_root,
        ),
    ]
    assert (export_root / "Props" / "Crate" / "Mobile" / "Crate.glb").is_file()
    assert [(kind, name, loop) for kind, name, _wav, loop in fakes.imported] == [
        ("SFX", "Click", False),
        ("Music", "Theme", True),
    ]
    assert fakes.scaffold_calls == 1
    scaffolded = sorted(p.name for p in (consumer / "game" / "scaffolded").iterdir())
    assert scaffolded == ["Harbor.txt", "Intro.txt", "Inventory.txt"]

    settings = json.loads((consumer / ".claude" / "settings.json").read_text())
    assert settings["env"] == {"KEEP_ME": "1"}
    assert settings["model"] == "opus"
    groups = settings["hooks"]["SessionStart"]
    assert groups == [
        {"matcher": "startup", "hooks": [{"type": "command", "command": BLENDER_HOOK}]}
    ]

    report = (consumer / "godot-conversion-report.md").read_text()
    for key in ALL_KEYS:
        assert f"- `{key}`" in report
    assert "## Failed\n\nNone." in report
    for path in (
        "Source/Game/Game.cpp",
        "Source/Game/Game.h",
        "Content/Maps/Main.umap",
        "Content/Misc/Stray.uasset",
    ):
        assert f"| `{path}` |" in report
    assert "Content/Props/Crate/Desktop/SM_Crate.uasset" not in report
    assert "done: `Content/`" in report

    assert result.deleted
    for name in (*UNREAL_PATHS, "scripts/start-unreal-mcp.sh"):
        assert not (consumer / name).exists(), name
    assert tracked(consumer, [*UNREAL_PATHS, "scripts/start-unreal-mcp.sh"]) == []
    staged = git(consumer, "diff", "--cached", "--name-status")
    assert "D\tGame.uproject" in staged and "D\tContent/Maps/Main.umap" in staged
    assert (consumer / "scripts" / "start-blender-mcp.sh").is_file()
    assert (consumer / "SourceArt" / "Props" / "crate.blend").is_file()
    assert not (consumer / "game" / ".nmg-convert.json").exists()
    assert "deleted Game.uproject" in printed


def test_one_failure_keeps_unreal_and_a_rerun_retries_only_it(consumer: Path) -> None:
    """AC12: no deletion, a report row with code and remediation, exit 1, resume."""
    before = git(consumer, "ls-files")
    fakes = Collaborators(fail={"asset:Props/Crate"})
    result, printed = convert(consumer, fakes)

    assert result.exit_code == 1
    assert [(f.item, f.code, f.remediation) for f in result.failures] == [
        ("asset:Props/Crate", FAIL_CODE, FAIL_REMEDIATION)
    ]
    assert not result.deleted
    for name in UNREAL_PATHS:
        assert (consumer / name).exists(), name
    assert git(consumer, "ls-files") == before
    report = (consumer / "godot-conversion-report.md").read_text()
    assert f"| `asset:Props/Crate` | `{FAIL_CODE}` | {FAIL_REMEDIATION} |" in report
    assert "kept: 1 items failed" in report
    assert f"failed asset:Props/Crate [{FAIL_CODE}]" in printed
    state = json.loads((consumer / "game" / ".nmg-convert.json").read_text())
    assert state["version"] == 1
    assert sorted(state["done"]) == sorted(key for key in ALL_KEYS if key != "asset:Props/Crate")

    rerun = Collaborators()
    second, _ = convert(consumer, rerun)

    assert second.exit_code == 0
    assert finalized_names(rerun) == ["Crate"]
    assert rerun.imported == []
    assert rerun.scaffold_calls == 0
    assert second.deleted
    assert not (consumer / "Game.uproject").exists()
    report = (consumer / "godot-conversion-report.md").read_text()
    for key in ALL_KEYS:
        assert f"- `{key}`" in report


def test_scaffold_failure_is_reported_per_entry(consumer: Path) -> None:
    """AC12: a scaffold error line becomes a failed item with its design code."""
    fakes = Collaborators(scaffold_fail={"region/Harbor"})
    result, _ = convert(consumer, fakes)
    assert [(f.item, f.code) for f in result.failures] == [
        ("scaffold:region/Harbor", "design.scaffold_failed")
    ]
    assert result.failures[0].remediation
    assert (consumer / "Content").is_dir()


def test_source_missing_fails_only_that_asset(consumer: Path) -> None:
    """FR11: no SourceArt match is convert.source_missing; finalize is not called for it."""
    git(consumer, "rm", "-q", "SourceArt/Props/crate.blend")
    git(consumer, "commit", "-q", "-m", "drop source")
    fakes = Collaborators()
    result, _ = convert(consumer, fakes)
    assert [(f.item, f.code) for f in result.failures] == [
        ("asset:Props/Crate", "convert.source_missing")
    ]
    assert finalized_names(fakes) == ["Hero"]
    assert (consumer / "Game.uproject").exists()


def test_source_ambiguous_fails_only_that_asset(consumer: Path) -> None:
    """FR11: several case-insensitive matches are convert.source_ambiguous."""
    extra = consumer / "SourceArt" / "Archive" / "Crate.blend"
    extra.parent.mkdir()
    extra.write_bytes(b"blend")
    git(consumer, "add", "-A")
    git(consumer, "commit", "-q", "-m", "second source")
    fakes = Collaborators()
    result, _ = convert(consumer, fakes)
    assert [(f.item, f.code) for f in result.failures] == [
        ("asset:Props/Crate", "convert.source_ambiguous")
    ]
    assert "SourceArt/Archive/Crate.blend" in result.failures[0].message
    assert finalized_names(fakes) == ["Hero"]


def test_dirty_worktree_stops_before_any_write(consumer: Path) -> None:
    """AC13: uncommitted changes give convert.dirty_worktree and change nothing."""
    (consumer / "README.md").write_text("# Game\n\nlocal edit\n")
    before = snapshot(consumer)
    fakes = Collaborators()
    with pytest.raises(PipelineError) as caught:
        convert(consumer, fakes)
    assert caught.value.code == "convert.dirty_worktree"
    assert caught.value.remediation
    assert snapshot(consumer) == before
    assert fakes.onboard_calls == [] and fakes.preflight_calls == 0


def test_missing_project_file_is_not_unreal(tmp_path: Path) -> None:
    """AC13: no .uproject gives convert.not_unreal and changes nothing."""
    root = make_unreal_consumer(tmp_path / "Game", uproject=False)
    before = snapshot(root)
    fakes = Collaborators()
    with pytest.raises(PipelineError) as caught:
        convert(root, fakes)
    assert caught.value.code == "convert.not_unreal"
    assert snapshot(root) == before
    assert fakes.onboard_calls == []


def test_dry_run_prints_the_plan_and_writes_nothing(consumer: Path) -> None:
    """AC13: --dry-run prints PLAN lines for every conversion and deletion only."""
    before = snapshot(consumer)
    fakes = Collaborators()
    result, printed = convert(consumer, fakes, dry_run=True)

    assert result.exit_code == 0 and result.dry_run
    assert printed.splitlines() == [
        *(f"PLAN convert {key}" for key in ALL_KEYS),
        "PLAN delete Content/",
        "PLAN delete Source/",
        "PLAN delete Config/",
        "PLAN delete Plugins/",
        "PLAN delete Game.uproject",
        "PLAN delete scripts/start-unreal-mcp.sh",
    ]
    assert snapshot(consumer) == before
    assert git(consumer, "status", "--porcelain") == ""
    assert fakes.onboard_calls == [] and fakes.finalized == [] and fakes.scaffold_calls == 0


def test_preflight_failure_stops_before_any_write(consumer: Path) -> None:
    """Design step 2: a missing Godot stops the run before onboarding."""
    before = snapshot(consumer)
    fakes = Collaborators(
        preflight_error=PipelineError("godot.not_found", "no godot", "Install Godot 4.", "godot")
    )
    with pytest.raises(PipelineError) as caught:
        convert(consumer, fakes)
    assert caught.value.code == "godot.not_found"
    assert snapshot(consumer) == before


def test_onboard_failure_converts_nothing_and_deletes_nothing(consumer: Path) -> None:
    def failing_onboard(root: Path) -> object:
        raise PipelineError("onboard.models_dir_missing", "no models", "Pass --models-dir.", "x")

    fakes = Collaborators()
    out = io.StringIO()
    kwargs = {**fakes.kwargs(), "onboard": failing_onboard}
    result = run_convert(consumer, out=out, **kwargs)  # type: ignore[arg-type]
    assert [(f.item, f.code) for f in result.failures] == [
        ("onboard", "onboard.models_dir_missing")
    ]
    assert fakes.finalized == [] and fakes.imported == []
    assert (consumer / "Game.uproject").exists()


def test_replace_settings_keeps_other_hooks_and_env(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"hooks": {"Stop": []}, "env": {"KEEP": "1"}}) + "\n")
    before = path.read_text()
    assert replace_settings(path) is False
    assert path.read_text() == before
    assert replace_settings(tmp_path / "missing.json") is False


def test_cli_exit_codes(
    consumer: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """__main__: 2 on an argument error, 1 on a guard failure, 0 on a dry run."""
    assert convert_cli.main(["--bogus"]) == 2
    assert convert_cli.main(["--project", str(consumer / "nope")]) == 2

    fakes = Collaborators()

    def fake_run(root: Path, *, dry_run: bool) -> ConvertResult:
        return run_convert(root, dry_run=dry_run, **fakes.kwargs())  # type: ignore[arg-type]

    monkeypatch.setattr(convert_cli, "run_convert", fake_run)
    capsys.readouterr()
    assert convert_cli.main(["--project", str(consumer), "--dry-run", "--json"]) == 0
    out = capsys.readouterr().out
    assert "PLAN delete Game.uproject" in out
    payload = json.loads(out[out.index("{") :])
    assert payload["dry_run"] is True and payload["deletions"][0] == "Content/"

    (consumer / "README.md").write_text("dirty\n")
    assert convert_cli.main(["--project", str(consumer)]) == 1
    err = capsys.readouterr().err
    assert "ERROR [convert.dirty_worktree]" in err and "Remediation:" in err

    (consumer / "README.md").write_text("# Game\n")
    fakes.fail = {"audio:SFX/Click"}
    assert convert_cli.main(["--project", str(consumer)]) == 1
    assert "ERROR [finalize.validate_failed] audio:SFX/Click" in capsys.readouterr().err
