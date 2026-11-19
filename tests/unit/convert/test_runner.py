"""``run_convert`` on a fixture Unreal consumer in a real git repository (#249 AC11–AC13).

Every collaborator is a recording fake from ``tests/convert_fakes.py``; git is real, so the
deletions go through ``git rm`` and the dirty-tree guard reads a real ``git status``.
"""

from __future__ import annotations

import io
import json
import shutil
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pytest

from nmg_game_dev.convert import __main__ as convert_cli
from nmg_game_dev.convert import runner as convert_runner
from nmg_game_dev.convert.plan import AssetItem, AudioItem, ConversionPlan
from nmg_game_dev.convert.runner import (
    ConvertResult,
    ScaffoldOutcome,
    replace_settings,
    run_convert,
)
from nmg_game_dev.design.scaffold import ScaffoldLine, ScaffoldReport
from nmg_game_dev.godot.runner import SubprocessGodotRunner
from nmg_game_dev.onboard.commands import CommandResult, default_run
from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.pipeline.request import FinalizeRequest
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
    assert "kept: 1 item failed" in report
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

    def fake_run(root: Path, *, dry_run: bool, onboard: object) -> ConvertResult:
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


# --- Review repairs: settings, deletions, resume, dry run, defaults ------------------------------


def test_invalid_settings_json_is_a_reported_failure_not_a_crash(consumer: Path) -> None:
    """F3: invalid settings.json is convert.settings_invalid; the report is still written."""
    settings = consumer / ".claude" / "settings.json"
    settings.write_text("{ not json", encoding="utf-8")
    git(consumer, "add", "-A")
    git(consumer, "commit", "-q", "-m", "break settings")
    result, printed = convert(consumer, Collaborators())

    assert result.exit_code == 1
    assert [(f.item, f.code) for f in result.failures] == [
        ("settings:.claude/settings.json", "convert.settings_invalid")
    ]
    assert "settings.json" in result.failures[0].remediation
    assert not result.deleted
    assert (consumer / "Game.uproject").exists()
    report = (consumer / "godot-conversion-report.md").read_text()
    assert "| `settings:.claude/settings.json` | `convert.settings_invalid` |" in report
    assert "kept: 1 item failed" in report
    assert "failed settings:.claude/settings.json [convert.settings_invalid]" in printed

    # Fixing the JSON and rerunning finishes the conversion.
    settings.write_text(json.dumps({"env": {"UE_ROOT": "/ue", "KEEP": "1"}}) + "\n")
    second, _ = convert(consumer, Collaborators())
    assert second.exit_code == 0 and second.deleted
    assert json.loads(settings.read_text()) == {"env": {"KEEP": "1"}}


def test_settings_local_json_loses_its_ue_env_too(consumer: Path) -> None:
    with (consumer / ".git" / "info" / "exclude").open("a") as exclude:
        exclude.write(".claude/settings.local.json\n")  # private, as in a real consumer
    local = consumer / ".claude" / "settings.local.json"
    local.write_text(json.dumps({"env": {"UE_ENGINE": "/ue", "MINE": "1"}}) + "\n")
    result, printed = convert(consumer, Collaborators())
    assert result.exit_code == 0
    assert json.loads(local.read_text()) == {"env": {"MINE": "1"}}
    assert "updated .claude/settings.local.json" in printed


def test_replace_settings_raises_settings_invalid(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("[1, 2", encoding="utf-8")
    with pytest.raises(PipelineError) as caught:
        replace_settings(path)
    assert caught.value.code == "convert.settings_invalid"
    assert path.read_text() == "[1, 2"


def test_git_rm_failure_is_delete_failed_and_reported(consumer: Path) -> None:
    """F11: convert.delete_failed is recorded, the report says so, and the state file stays."""

    def failing_git(argv: Sequence[str], env: Mapping[str, str] | None) -> CommandResult:
        if "rm" in argv:
            return CommandResult(1, stderr="fatal: index.lock exists")
        return default_run(argv, env)

    out = io.StringIO()
    result = run_convert(consumer, out=out, git=failing_git, **Collaborators().kwargs())  # type: ignore[arg-type]

    assert [(f.item, f.code) for f in result.failures] == [("deletions", "convert.delete_failed")]
    assert not result.deleted
    assert (consumer / "Game.uproject").exists()
    assert (consumer / "game" / ".nmg-convert.json").is_file()
    report = (consumer / "godot-conversion-report.md").read_text()
    assert "failed: git rm failed" in report and "done:" not in report
    assert "failed deletions [convert.delete_failed]" in out.getvalue()


def test_deletion_stopped_after_git_rm_resumes_and_finishes(
    consumer: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F11: the .uproject is gone but the state file stays, so a rerun resumes and finishes."""
    # An ignored file git rm leaves behind, so the runner removes the remainder itself.
    with (consumer / ".git" / "info" / "exclude").open("a") as exclude:
        exclude.write("Content/untracked.tmp\n")
    (consumer / "Content" / "untracked.tmp").write_text("x")
    real_rmtree = shutil.rmtree
    calls = {"n": 0}

    def flaky_rmtree(path: object, *args: object, **kwargs: object) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("Device busy")
        real_rmtree(path)  # type: ignore[arg-type]

    monkeypatch.setattr(shutil, "rmtree", flaky_rmtree)
    result, _ = convert(consumer, Collaborators())
    assert [(f.item, f.code) for f in result.failures] == [("deletions", "convert.item_failed")]
    assert not (consumer / "Game.uproject").exists()
    assert (consumer / "game" / ".nmg-convert.json").is_file()
    report = (consumer / "godot-conversion-report.md").read_text()
    assert "failed: OSError: Device busy" in report

    rerun = Collaborators()
    second, _ = convert(consumer, rerun)
    assert second.exit_code == 0 and second.deleted
    assert rerun.finalized == [] and rerun.imported == []
    assert not (consumer / "Content").exists()
    assert not (consumer / "game" / ".nmg-convert.json").exists()
    resumed = (consumer / "godot-conversion-report.md").read_text()
    assert "done: `Content/`" in resumed
    # P2: Source/ and the .umap were already gone, yet the resumed report still lists them for
    # manual porting and names every deletion of the first run.
    assert "| `Source/Game/Game.cpp` |" in resumed
    assert "| `Content/Maps/Main.umap` |" in resumed
    assert second.plan.deletions == result.plan.deletions
    assert second.plan.manual_port == result.plan.manual_port


def test_dry_run_marks_items_discovery_knows_will_fail(consumer: Path) -> None:
    git(consumer, "rm", "-q", "SourceArt/Props/crate.blend")
    git(consumer, "commit", "-q", "-m", "drop source")
    _result, printed = convert(consumer, Collaborators(), dry_run=True)
    lines = printed.splitlines()
    assert "PLAN convert asset:Characters/Hero" in lines
    assert any(
        line.startswith("PLAN fail asset:Props/Crate [convert.source_missing]") for line in lines
    )
    assert "PLAN convert asset:Props/Crate" not in lines


def test_cli_passes_models_dir_to_onboarding(
    consumer: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """F18: --models-dir reaches run_onboard through the default onboard collaborator."""
    seen: dict[str, object] = {}

    def fake_run(root: Path, *, dry_run: bool, onboard: Callable[[Path], object]) -> ConvertResult:
        onboard(root)
        return ConvertResult(plan=ConversionPlan(), dry_run=dry_run)

    def fake_onboard(root: Path, **kwargs: object) -> list[object]:
        seen.update(kwargs, root=root)
        return []

    monkeypatch.setattr(convert_cli, "run_convert", fake_run)
    monkeypatch.setattr("nmg_game_dev.onboard.runner.run_onboard", fake_onboard)
    models = tmp_path / "models"
    assert convert_cli.main(["--project", str(consumer), "--models-dir", str(models)]) == 0
    assert seen["models_dir"] == models
    assert seen["root"] == consumer


# --- Default collaborators (F16) -----------------------------------------------------------------


def test_default_onboard_calls_run_onboard_with_the_framework(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: dict[str, object] = {}

    def fake(root: Path, **kwargs: object) -> list[object]:
        seen.update(kwargs, root=root)
        return []

    monkeypatch.setattr("nmg_game_dev.onboard.runner.run_onboard", fake)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path / "plugin"))
    convert_runner.default_onboard(tmp_path, models_dir=tmp_path / "m")
    assert seen == {
        "root": tmp_path,
        "framework": (tmp_path / "plugin").resolve(),
        "models_dir": tmp_path / "m",
    }


def test_default_finalize_builds_a_valid_request(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: list[object] = []
    monkeypatch.setattr("nmg_game_dev.pipeline.finalize", seen.append)
    blend = tmp_path / "SourceArt" / "Crate.blend"
    blend.parent.mkdir()
    blend.write_bytes(b"blend")
    item = AssetItem("Props", "Crate", "standard_prop", blend)
    convert_runner.default_finalize(item, tmp_path / "game" / "assets")
    (request,) = seen
    assert isinstance(request, FinalizeRequest)
    assert (request.collection, request.category, request.asset_class) == (
        "Crate",
        "Props",
        "standard_prop",
    )
    assert request.blend is not None and Path(request.blend) == blend
    assert Path(request.export_root) == tmp_path / "game" / "assets"


@pytest.mark.parametrize(
    ("kind", "loop", "function", "godot_kind"),
    [("SFX", False, "import_wav", "sfx"), ("Music", True, "import_ogg", "music")],
)
def test_default_import_wav_picks_the_importer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    kind: str,
    loop: bool,
    function: str,
    godot_kind: str,
) -> None:
    calls: list[tuple[str, tuple[object, ...]]] = []
    monkeypatch.setattr("nmg_game_dev.godot.binary.resolve_godot", lambda: tmp_path / "godot")

    def installed(*args: object) -> None:
        calls.append(("installed", args))

    def importer(*args: object) -> dict[str, str]:
        calls.append((function, args))
        return {"godot_asset": "res://x"}

    monkeypatch.setattr("nmg_game_dev.audio.godot_import.installed_result", installed)
    monkeypatch.setattr(f"nmg_game_dev.audio.godot_import.{function}", importer)
    wav = tmp_path / "Beep.wav"
    convert_runner.default_import_wav(tmp_path, AudioItem(kind, "Beep", wav, loop))
    assert [name for name, _args in calls] == ["installed", function]
    installed_args = calls[0][1]
    assert installed_args[:4] == (tmp_path, godot_kind, "Beep", loop)
    assert calls[1][1][:4] == (tmp_path, wav, "Beep", loop)
    runner = calls[1][1][4]
    assert isinstance(runner, SubprocessGodotRunner) and runner.binary == tmp_path / "godot"


def test_default_import_wav_counts_an_installed_sound_as_done(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """F6: a sound an interrupted run installed is re-checked, not re-imported."""
    monkeypatch.setattr("nmg_game_dev.godot.binary.resolve_godot", lambda: tmp_path / "godot")
    monkeypatch.setattr(
        "nmg_game_dev.audio.godot_import.installed_result", lambda *args: {"godot_asset": "done"}
    )

    def never(*_args: object) -> None:
        raise AssertionError("import_wav must not run for an installed sound")

    monkeypatch.setattr("nmg_game_dev.audio.godot_import.import_wav", never)
    item = AudioItem("SFX", "Beep", tmp_path / "Beep.wav", False)
    assert convert_runner.default_import_wav(tmp_path, item) == {"godot_asset": "done"}


def test_default_scaffold_maps_report_lines(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake(root: Path, report: ScaffoldReport, *, statuses: object) -> None:
        assert statuses == {"scaffolded"}
        report.lines.append(ScaffoldLine("created", "region", "Harbor", "game/levels/..."))
        report.lines.append(
            ScaffoldLine("error", "mission", "Intro", "bad", code="design.unknown_reference")
        )

    monkeypatch.setattr("nmg_game_dev.design.scaffold.run_scaffold", fake)
    assert convert_runner.default_scaffold(tmp_path) == [
        ScaffoldOutcome("region", "Harbor", None, "game/levels/..."),
        ScaffoldOutcome("mission", "Intro", "design.unknown_reference", "bad"),
    ]


def test_default_preflight_resolves_godot_and_blender(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("nmg_game_dev.godot.binary.resolve_godot", lambda: tmp_path / "godot")
    monkeypatch.setattr(
        "nmg_game_dev.pipeline.blender_proc.resolve_blender", lambda: tmp_path / "blender"
    )
    assert convert_runner.default_preflight() == (tmp_path / "godot", tmp_path / "blender")
