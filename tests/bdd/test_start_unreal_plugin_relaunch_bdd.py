"""pytest-bdd bindings for start_unreal_plugin_relaunch.feature: SCN001-SCN007 of #150.

Each scenario runs the real start-unreal-mcp.sh against a temporary project and a fake UE_ROOT
(tests/start_unreal_fakes.py), so nothing compiles and no editor starts.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, scenario, then, when

from tests.start_unreal_fakes import (
    BUILD_ACTION_GRAPH_INVALID,
    BUILD_ACTION_GRAPH_REASON,
    BUILD_LOG,
    BUILD_OK,
    Sandbox,
    expected_build_argv,
    make_sandbox,
    read_events,
    run_launcher,
    wait_for_editor,
)

FEATURE = "start_unreal_plugin_relaunch.feature"


@dataclass
class RelaunchScenario:
    tmp_path: Path
    dylib: str = "missing"
    code_project: bool = False
    second_module: bool = False
    engine_ini_newer: bool = False
    build_body: str = BUILD_OK
    sandbox: Sandbox | None = None
    result: subprocess.CompletedProcess[str] | None = None


@pytest.fixture
def scn(tmp_path: Path) -> RelaunchScenario:
    return RelaunchScenario(tmp_path=tmp_path)


def _tags(sandbox: Sandbox) -> list[str]:
    return [event[0] for event in read_events(sandbox.events)]


@scenario(FEATURE, "A config change does not trigger a build")
def test_scn001_config_change_does_not_build() -> None:
    pass


@scenario(FEATURE, "The plugin build selects a single editor target")
def test_scn002_single_editor_target() -> None:
    pass


@scenario(FEATURE, "Current UE 5.8 binaries skip the build")
def test_scn003_current_binaries_skip() -> None:
    pass


@scenario(FEATURE, "A change to one module does not mark the plugin stale")
def test_scn004_one_module_change_is_not_stale() -> None:
    pass


@scenario(FEATURE, "A failed rebuild with existing binaries still launches")
def test_scn005_failed_rebuild_still_launches() -> None:
    pass


@scenario(FEATURE, "A failed build with a missing binary stops the launch")
def test_scn006_failed_build_with_missing_binary_stops() -> None:
    pass


@scenario(FEATURE, "The failure report shows UnrealBuildTool's reason")
def test_scn007_failure_report_shows_ubt_reason() -> None:
    pass


@given(
    'a project whose plugin "Fake" has a libUnrealEditor-FakeEditor.dylib newer than its sources'
)
def given_current_lib_binary(scn: RelaunchScenario) -> None:
    scn.dylib = "current"


@given(
    'a project whose plugin "Fake" has a libUnrealEditor-FakeEditor.dylib older than its sources'
)
def given_stale_lib_binary(scn: RelaunchScenario) -> None:
    scn.dylib = "stale"


@given("the project's Config/DefaultEngine.ini is newer than that binary")
def given_engine_ini_newer(scn: RelaunchScenario) -> None:
    scn.engine_ini_newer = True


@given(parsers.parse('a {kind} project whose plugin "Fake" has no editor binary'))
def given_kind_without_binary(scn: RelaunchScenario, kind: str) -> None:
    assert kind in ("Blueprint-only", "code"), kind
    scn.code_project = kind == "code"
    scn.dylib = "missing"


@given('a project whose plugin "Fake" has no editor binary')
def given_plugin_without_binary(scn: RelaunchScenario) -> None:
    scn.dylib = "missing"


@given('a project whose plugin "Fake" has modules A and B')
def given_two_modules(scn: RelaunchScenario) -> None:
    scn.second_module = True


@given("module A's binary is newer than module A's sources and older than module B's sources")
def given_module_a_between(scn: RelaunchScenario) -> None:
    scn.dylib = "current"


@given("module B's binary is newer than module B's sources")
def given_module_b_current(scn: RelaunchScenario) -> None:
    # make_sandbox writes module B's binary newer than its sources whenever second_module is set.
    assert scn.second_module


@given('Build.sh prints "Result: Failed (ActionGraphInvalid)" and exits 9')
def given_build_sh_action_graph(scn: RelaunchScenario) -> None:
    scn.build_body = BUILD_ACTION_GRAPH_INVALID


@given(
    'Build.sh prints "Action graph is invalid; unable to continue"'
    ' then "Result: Failed (ActionGraphInvalid)" and exits 9'
)
def given_build_sh_action_graph_reason(scn: RelaunchScenario) -> None:
    scn.build_body = BUILD_ACTION_GRAPH_REASON


@when("start-unreal-mcp.sh runs")
def when_launcher_runs(scn: RelaunchScenario) -> None:
    scn.sandbox = make_sandbox(
        scn.tmp_path,
        dylib=scn.dylib,
        code_project=scn.code_project,
        second_module=scn.second_module,
        engine_ini_newer=scn.engine_ini_newer,
        build_body=scn.build_body,
    )
    scn.result = run_launcher(scn.sandbox)


@then("Build.sh does not run")
def then_build_sh_not_run(scn: RelaunchScenario) -> None:
    assert scn.sandbox is not None
    assert "build" not in _tags(scn.sandbox)


@then("the editor launches")
def then_editor_launches(scn: RelaunchScenario) -> None:
    assert scn.result is not None and scn.sandbox is not None
    assert scn.result.returncode == 0, scn.result.stderr
    wait_for_editor(scn.sandbox.events)


@then("Build.sh runs with Mac Development -Project=<uproject> -TargetType=Editor -NoEngineChanges")
def then_build_sh_single_target(scn: RelaunchScenario) -> None:
    assert scn.sandbox is not None
    events = read_events(scn.sandbox.events)
    assert events and events[0] == expected_build_argv(scn.sandbox), events


@then("Build.sh receives no UnrealEditor target name")
def then_no_unreal_editor_target(scn: RelaunchScenario) -> None:
    assert scn.sandbox is not None
    events = read_events(scn.sandbox.events)
    assert events and "UnrealEditor" not in events[0], events


@then("it exits 0")
def then_exits_zero(scn: RelaunchScenario) -> None:
    assert scn.result is not None
    assert scn.result.returncode == 0, scn.result.stderr


@then(
    "stderr warns that the plugin build failed, names /tmp/unreal-mcp-build.log,"
    " and says the editor starts on the existing plugin binaries"
)
def then_stderr_warns_and_names_log(scn: RelaunchScenario) -> None:
    assert scn.result is not None
    assert "warning: plugin build failed" in scn.result.stderr, scn.result.stderr
    assert str(BUILD_LOG) in scn.result.stderr, scn.result.stderr
    assert "starting the editor on the existing plugin binaries" in scn.result.stderr


@then("the editor launches after the build")
def then_editor_launches_after_build(scn: RelaunchScenario) -> None:
    assert scn.sandbox is not None
    assert [event[0] for event in wait_for_editor(scn.sandbox.events)] == ["build", "editor"]


@then("it exits non-zero")
def then_exits_non_zero(scn: RelaunchScenario) -> None:
    assert scn.result is not None
    assert scn.result.returncode != 0, scn.result.stderr


@then("the editor does not launch")
def then_editor_does_not_launch(scn: RelaunchScenario) -> None:
    assert scn.sandbox is not None
    assert "editor" not in _tags(scn.sandbox)


@then("stderr names /tmp/unreal-mcp-build.log")
def then_stderr_names_log(scn: RelaunchScenario) -> None:
    assert scn.result is not None
    assert str(BUILD_LOG) in scn.result.stderr, scn.result.stderr


@then('stderr contains "Result: Failed (ActionGraphInvalid)"')
def then_stderr_contains_reason(scn: RelaunchScenario) -> None:
    assert scn.result is not None
    assert "Result: Failed (ActionGraphInvalid)" in scn.result.stderr, scn.result.stderr


@then('stderr does not contain "no compiler error found"')
def then_stderr_lacks_placeholder(scn: RelaunchScenario) -> None:
    assert scn.result is not None
    assert "no compiler error found" not in scn.result.stderr, scn.result.stderr
