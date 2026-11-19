"""Unit tests for the Godot boundary package (#249 T001: FR1, FR2, AC2)."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from nmg_game_dev.godot import (
    ensure_keys,
    find_project,
    import_project,
    parse_config,
    parse_nmg_result,
    render_export_presets,
    res_path,
    resolve_godot,
    run_probe,
)
from nmg_game_dev.godot.presets import PRESETS
from nmg_game_dev.godot.runner import (
    DEFAULT_TIMEOUT_S,
    CommandResult,
    SubprocessGodotRunner,
    default_timeout,
)
from nmg_game_dev.pipeline.errors import PipelineError
from tests.godot_fakes import FakeGodotRunner


def _exe(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


# --- resolve_godot -------------------------------------------------------------------------------


def test_resolve_prefers_godot_bin(tmp_path: Path) -> None:
    binary = _exe(tmp_path / "bin" / "godot4")
    found = resolve_godot({"GODOT_BIN": str(binary)}, lambda _: "/usr/bin/godot")
    assert found == binary


def test_resolve_falls_back_to_path_when_godot_bin_is_not_executable(tmp_path: Path) -> None:
    found = resolve_godot({"GODOT_BIN": str(tmp_path / "missing")}, lambda _: "/opt/godot")
    assert found == Path("/opt/godot")


def test_resolve_falls_back_to_app_bundle(tmp_path: Path) -> None:
    app = _exe(tmp_path / "Godot.app" / "Contents" / "MacOS" / "Godot")
    assert resolve_godot({}, lambda _: None, default_app=app) == app


def test_resolve_raises_not_found_with_remediation(tmp_path: Path) -> None:
    with pytest.raises(PipelineError) as raised:
        resolve_godot({"GODOT_BIN": "/nope"}, lambda _: None, default_app=tmp_path / "Godot")
    assert raised.value.code == "godot.not_found"
    assert "GODOT_BIN" in raised.value.remediation
    assert "GODOT_BIN=/nope" in raised.value.message


# --- parse_nmg_result ----------------------------------------------------------------------------


def test_parse_returns_last_result_line() -> None:
    out = 'noise\nNMG_RESULT {"a": 1}\nmore\nNMG_RESULT {"a": 2}\n'
    assert parse_nmg_result(out, error_code="x.failed") == {"a": 2}


@pytest.mark.parametrize("out", ["nothing here", "NMG_RESULT {bad", "NMG_RESULT [1, 2]"])
def test_parse_missing_or_malformed_raises_given_code(out: str) -> None:
    with pytest.raises(PipelineError) as raised:
        parse_nmg_result(out, error_code="import_godot.mismatch")
    assert raised.value.code == "import_godot.mismatch"
    assert raised.value.remediation


# --- runner --------------------------------------------------------------------------------------


def test_subprocess_runner_argv_is_headless_with_dummy_audio(tmp_path: Path) -> None:
    runner = SubprocessGodotRunner(Path("/bin/godot"))
    argv = runner.argv(["--import"], project=tmp_path)
    assert argv[:6] == [
        "/bin/godot",
        "--headless",
        "--audio-driver",
        "Dummy",
        "--path",
        str(tmp_path),
    ]
    assert argv[6:] == ["--import"]


def test_subprocess_runner_runs_binary(tmp_path: Path) -> None:
    script = tmp_path / "fake-godot"
    script.write_text('#!/bin/sh\necho "args: $*"\nexit 3\n')
    script.chmod(0o755)
    result = SubprocessGodotRunner(script).run(["--import"], project=tmp_path)
    assert result.returncode == 3
    assert "--headless" in result.stdout and "--import" in result.stdout


def test_subprocess_runner_missing_binary_is_127(tmp_path: Path) -> None:
    result = SubprocessGodotRunner(tmp_path / "absent").run(["--import"], project=tmp_path)
    assert result.returncode == 127


def test_import_project_passes(tmp_path: Path) -> None:
    runner = FakeGodotRunner()
    import_project(runner, tmp_path)
    assert runner.calls == [["--import"]]


def test_import_project_error_line_raises(tmp_path: Path) -> None:
    with pytest.raises(PipelineError) as raised:
        import_project(FakeGodotRunner(import_errors=True), tmp_path)
    assert raised.value.code == "import_godot.import_failed"
    assert "ERROR: Failed loading resource" in raised.value.message


def test_import_project_error_line_on_exit_0_raises(tmp_path: Path) -> None:
    # Godot --import commonly exits 0 when a resource fails, so the ERROR: line alone must fail.
    runner = FakeGodotRunner()
    runner.run = lambda *_a, **_k: CommandResult(  # type: ignore[method-assign]
        0, stdout="Godot Engine v4\nERROR: Failed loading resource: res://broken.glb\n"
    )
    with pytest.raises(PipelineError) as raised:
        import_project(runner, tmp_path, error_code="import_anims.failed")
    assert raised.value.code == "import_anims.failed"
    assert raised.value.message.endswith("ERROR: Failed loading resource: res://broken.glb")


def test_import_project_timeout_reports_the_timeout(tmp_path: Path) -> None:
    runner = FakeGodotRunner()
    runner.run = lambda *_a, **_k: CommandResult(  # type: ignore[method-assign]
        124, stderr="Godot did not finish within 900 s and was stopped"
    )
    with pytest.raises(PipelineError) as raised:
        import_project(runner, tmp_path)
    assert "did not finish within 900 s" in raised.value.message
    assert "NMG_GODOT_TIMEOUT_S" in raised.value.remediation


def test_run_probe_timeout_reports_the_timeout(tmp_path: Path) -> None:
    runner = FakeGodotRunner(
        {
            "probe_asset.gd": CommandResult(
                124, stderr="Godot did not finish within 5 s and was stopped"
            )
        }
    )
    with pytest.raises(PipelineError) as raised:
        run_probe(runner, tmp_path, "probe_asset.gd", {}, error_code="import_godot.mismatch")
    assert "did not finish within 5 s" in raised.value.message
    assert "quarantine" in raised.value.remediation


def test_subprocess_runner_bounds_every_run_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hang = tmp_path / "godot"
    hang.write_text("#!/bin/sh\nsleep 30\n")
    hang.chmod(0o755)
    monkeypatch.setenv("NMG_GODOT_TIMEOUT_S", "0.5")
    runner = SubprocessGodotRunner(hang)
    assert runner.timeout == 0.5
    result = runner.run(["--import"], project=tmp_path)
    assert result.returncode == 124
    assert "did not finish within 0.5 s" in result.stderr


def test_default_timeout_ignores_a_bad_override() -> None:
    assert default_timeout({"NMG_GODOT_TIMEOUT_S": "soon"}) == DEFAULT_TIMEOUT_S
    assert default_timeout({"NMG_GODOT_TIMEOUT_S": "-1"}) == DEFAULT_TIMEOUT_S
    assert default_timeout({}) == DEFAULT_TIMEOUT_S
    assert default_timeout({"NMG_GODOT_TIMEOUT_S": "60"}) == 60.0


def test_import_project_nonzero_exit_without_error_line_raises(tmp_path: Path) -> None:
    runner = FakeGodotRunner()
    runner.run = lambda *_a, **_k: CommandResult(2)  # type: ignore[method-assign]
    with pytest.raises(PipelineError) as raised:
        import_project(runner, tmp_path)
    assert "exited 2" in raised.value.message


def test_run_probe_copies_script_and_passes_params(tmp_path: Path) -> None:
    script = tmp_path / "probe_x.gd"
    script.write_text("extends SceneTree\n")
    project = tmp_path / "game"
    project.mkdir()
    runner = FakeGodotRunner({"probe_x.gd": lambda params: {"echo": params["glb"]}})
    result = run_probe(runner, project, script, {"glb": "res://a.glb"}, error_code="x.failed")
    assert result == {"echo": "res://a.glb"}
    assert (project / ".godot" / "nmg_probes" / "probe_x.gd").is_file()
    call = runner.calls[0]
    assert call[:2] == ["-s", "res://.godot/nmg_probes/probe_x.gd"]
    assert call[2] == "--" and os.path.isabs(call[3])


def test_run_probe_failure_raises_error_code(tmp_path: Path) -> None:
    script = tmp_path / "probe_y.gd"
    script.write_text("extends SceneTree\n")
    runner = FakeGodotRunner({"probe_y.gd": CommandResult(1, stderr="ERROR: boom")})
    with pytest.raises(PipelineError) as raised:
        run_probe(runner, tmp_path, script, {}, error_code="audio.import_failed")
    assert raised.value.code == "audio.import_failed"
    assert "ERROR: boom" in raised.value.message


# --- project -------------------------------------------------------------------------------------


def test_find_project_walks_up(tmp_path: Path) -> None:
    (tmp_path / "game").mkdir()
    (tmp_path / "game" / "project.godot").write_text("config_version=5\n")
    nested = tmp_path / "game" / "assets" / "Props"
    nested.mkdir(parents=True)
    assert find_project(nested) == (tmp_path / "game").resolve()
    assert res_path(tmp_path / "game", nested / "Crate.glb") == "res://assets/Props/Crate.glb"


def test_find_project_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(PipelineError) as raised:
        find_project(tmp_path)
    assert raised.value.code == "import_godot.project_missing"


def test_ensure_keys_adds_missing_and_reports_drift() -> None:
    text = 'config_version=5\n\n[application]\n\nconfig/name="Old"\n'
    required = {
        ("application", "config/name"): '"New"',
        ("application", "run/main_scene"): '""',
        ("rendering", "renderer/rendering_method.mobile"): '"gl_compatibility"',
        ("", "config_version"): "5",
    }
    new_text, added, drifted = ensure_keys(text, required)
    assert drifted == [("application", "config/name")]
    assert added == [
        ("application", "run/main_scene"),
        ("rendering", "renderer/rendering_method.mobile"),
    ]
    parsed = parse_config(new_text)
    assert parsed[("application", "config/name")] == '"Old"'
    assert parsed[("application", "run/main_scene")] == '""'
    assert parsed[("rendering", "renderer/rendering_method.mobile")] == '"gl_compatibility"'
    again, added2, _ = ensure_keys(new_text, required)
    assert again == new_text and added2 == []


# --- presets -------------------------------------------------------------------------------------


def test_export_presets_have_variant_filters_and_target_options() -> None:
    text = render_export_presets("My Game")
    parsed = parse_config(text)
    by_name = {
        value.strip('"'): section
        for (section, key), value in parsed.items()
        if key == "name" and section.startswith("preset.")
    }
    assert set(by_name) == set(PRESETS.values())
    for target, preset in PRESETS.items():
        section = by_name[preset]
        expected = "assets/*/Mobile/*" if target in ("macos", "windows") else "assets/*/Desktop/*"
        assert parsed[(section, "exclude_filter")] == f'"{expected}"'
        assert parsed[(section, "platform")] == f'"{preset}"'
    assert parsed[(by_name["Web"] + ".options", "variant/thread_support")] == "false"
    assert parsed[(by_name["Windows Desktop"] + ".options", "binary_format/embed_pck")] == "true"
    assert parsed[(by_name["macOS"] + ".options", "codesign/codesign")] == "0"
    android = by_name["Android"] + ".options"
    assert parsed[(android, "gradle_build/use_gradle_build")] == "true"
    assert parsed[(android, "gradle_build/export_format")] == "1"
    assert render_export_presets("My Game") == text
