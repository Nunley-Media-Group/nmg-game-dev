"""pytest-bdd bindings for start_unreal_plugin_build.feature: SCN001-SCN005 of #103.

SCN001-SCN004 run the real start-unreal-mcp.sh against a temporary project and a fake UE_ROOT
(tests/start_unreal_fakes.py), so nothing compiles and no editor starts. SCN005 merges a consumer
settings file into the shipped consumer template.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, scenario, then, when

from nmg_game_dev.onboard.report import StepResult
from nmg_game_dev.onboard.settings import merge_session_hooks
from tests.start_unreal_fakes import (
    BUILD_LOG,
    BUILD_OK,
    REPO_ROOT,
    Sandbox,
    expected_build_argv,
    make_sandbox,
    read_events,
    run_launcher,
    wait_for_editor,
)

FEATURE = "start_unreal_plugin_build.feature"
TEMPLATE = REPO_ROOT / "templates" / "consumer" / ".claude" / "settings.json"
UNREAL_COMMAND = 'bash "$CLAUDE_PROJECT_DIR/scripts/start-unreal-mcp.sh"'
BUILD_ERROR = "Foo.cpp:3:1: error: boom"


@dataclass
class BuildScenario:
    tmp_path: Path
    dylib: str = "missing"
    build_sh: bool = True
    build_body: str = BUILD_OK
    sandbox: Sandbox | None = None
    result: subprocess.CompletedProcess[str] | None = None
    settings: Path | None = None
    merge: StepResult | None = None


@pytest.fixture
def scn(tmp_path: Path) -> BuildScenario:
    return BuildScenario(tmp_path=tmp_path)


@scenario(FEATURE, "Missing plugin binaries are built before the editor launches")
def test_scn001_missing_binaries_built() -> None:
    pass


@scenario(FEATURE, "Current plugin binaries skip the build")
def test_scn002_current_binaries_skip() -> None:
    pass


@scenario(FEATURE, "A failed plugin build stops the launch")
def test_scn003_failed_build_stops() -> None:
    pass


@scenario(FEATURE, "A missing Build.sh is reported")
def test_scn004_missing_build_sh() -> None:
    pass


@scenario(FEATURE, "Onboarding gives the Unreal hook room to build")
def test_scn005_hook_timeout() -> None:
    pass


@given(
    'a project whose plugin "Fake" has Source/ but no Binaries/Mac/UnrealEditor-FakeEditor.dylib'
)
def given_plugin_without_dylib(scn: BuildScenario) -> None:
    scn.dylib = "missing"


@given('a project whose plugin "Fake" has an editor dylib newer than its sources')
def given_plugin_with_current_dylib(scn: BuildScenario) -> None:
    scn.dylib = "current"


@given('a project whose plugin "Fake" needs a build')
def given_plugin_needs_build(scn: BuildScenario) -> None:
    scn.dylib = "missing"


@given('Build.sh prints "Foo.cpp:3:1: error: boom" and exits 2')
def given_build_sh_fails(scn: BuildScenario) -> None:
    scn.build_body = f'printf "{BUILD_ERROR}\\n"\nexit 2'


@given("UE_ROOT has no Engine/Build/BatchFiles/Mac/Build.sh")
def given_ue_root_without_build_sh(scn: BuildScenario) -> None:
    scn.build_sh = False


@when("start-unreal-mcp.sh runs")
def when_launcher_runs(scn: BuildScenario) -> None:
    scn.sandbox = make_sandbox(
        scn.tmp_path, dylib=scn.dylib, build_sh=scn.build_sh, build_body=scn.build_body
    )
    scn.result = run_launcher(scn.sandbox)


@then("it logs that it is building project plugins (Fake)")
def then_logs_building(scn: BuildScenario) -> None:
    assert scn.result is not None
    assert "start-unreal-mcp: building project plugins (Fake)" in scn.result.stderr, (
        scn.result.stderr
    )


@then(
    "Build.sh runs with UnrealEditor Mac Development"
    " -Project=<uproject> -TargetType=Editor -NoEngineChanges"
)
def then_build_sh_argv(scn: BuildScenario) -> None:
    assert scn.sandbox is not None
    events = read_events(scn.sandbox.events)
    assert events and events[0] == expected_build_argv(scn.sandbox), events


@then("the editor launches after the build succeeds")
def then_editor_after_build(scn: BuildScenario) -> None:
    assert scn.result is not None and scn.sandbox is not None
    assert scn.result.returncode == 0, scn.result.stderr
    assert [event[0] for event in wait_for_editor(scn.sandbox.events)] == ["build", "editor"]


@then("the editor launches")
def then_editor_launches(scn: BuildScenario) -> None:
    assert scn.result is not None and scn.sandbox is not None
    assert scn.result.returncode == 0, scn.result.stderr
    wait_for_editor(scn.sandbox.events)


@then("Build.sh does not run")
def then_build_sh_not_run(scn: BuildScenario) -> None:
    assert scn.sandbox is not None
    assert "build" not in [event[0] for event in read_events(scn.sandbox.events)]


@then("it exits non-zero")
def then_exits_non_zero(scn: BuildScenario) -> None:
    assert scn.result is not None
    assert scn.result.returncode != 0, scn.result.stderr


@then("the editor does not launch")
def then_editor_does_not_launch(scn: BuildScenario) -> None:
    assert scn.sandbox is not None
    assert "editor" not in [event[0] for event in read_events(scn.sandbox.events)]


@then('stderr names /tmp/unreal-mcp-build.log and "Foo.cpp:3:1: error: boom"')
def then_stderr_names_log_and_error(scn: BuildScenario) -> None:
    assert scn.result is not None
    assert str(BUILD_LOG) in scn.result.stderr, scn.result.stderr
    assert BUILD_ERROR in scn.result.stderr, scn.result.stderr


@then("it exits non-zero without launching the editor")
def then_exits_non_zero_without_editor(scn: BuildScenario) -> None:
    assert scn.result is not None and scn.sandbox is not None
    assert scn.result.returncode != 0, scn.result.stderr
    assert read_events(scn.sandbox.events) == []


@then("stderr names the missing Build.sh path and UE_ROOT")
def then_stderr_names_build_sh(scn: BuildScenario) -> None:
    assert scn.result is not None and scn.sandbox is not None
    assert str(scn.sandbox.build_sh) in scn.result.stderr, scn.result.stderr
    assert "UE_ROOT" in scn.result.stderr, scn.result.stderr


@given("a consumer settings.json whose start-unreal-mcp.sh hook has no timeout")
def given_consumer_settings_without_timeout(scn: BuildScenario) -> None:
    settings = scn.tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    hook = {"type": "command", "command": UNREAL_COMMAND}
    settings.write_text(
        json.dumps({"hooks": {"SessionStart": [{"matcher": "startup", "hooks": [hook]}]}}),
        encoding="utf-8",
    )
    scn.settings = settings


@when("the SessionStart hooks are merged")
def when_session_hooks_merged(scn: BuildScenario) -> None:
    assert scn.settings is not None
    scn.merge = merge_session_hooks("settings_hooks", scn.settings, TEMPLATE)


def _unreal_hook(settings: Path) -> dict[str, Any]:
    groups = json.loads(settings.read_text(encoding="utf-8"))["hooks"]["SessionStart"]
    return next(h for g in groups for h in g["hooks"] if h["command"] == UNREAL_COMMAND)


@then("the start-unreal-mcp.sh hook has timeout 900")
def then_unreal_hook_timeout(scn: BuildScenario) -> None:
    assert scn.settings is not None
    assert _unreal_hook(scn.settings).get("timeout") == 900


@then("the merge reports refreshed")
def then_merge_reports_refreshed(scn: BuildScenario) -> None:
    assert scn.merge is not None
    assert scn.merge.status == "refreshed", scn.merge
