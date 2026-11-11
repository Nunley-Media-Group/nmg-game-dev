"""start-unreal-mcp.sh plugin builds before launch (#103 AC1-AC4, #150 AC1-AC7).

Each test runs the real launcher against a temporary project and a fake UE_ROOT (see
tests/start_unreal_fakes.py). Nothing is compiled and no editor starts.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

import pytest

from tests.start_unreal_fakes import (
    BUILD_ACTION_GRAPH_INVALID,
    BUILD_ACTION_GRAPH_REASON,
    BUILD_LOG,
    MODULE,
    expected_build_argv,
    make_sandbox,
    read_events,
    run_launcher,
    wait_for_editor,
)


def _tags(events: list[list[str]]) -> list[str]:
    return [event[0] for event in events]


def test_missing_binaries_are_built_before_the_editor_launches(tmp_path: Path) -> None:
    sandbox = make_sandbox(tmp_path, dylib="missing")

    result = run_launcher(sandbox)

    assert result.returncode == 0, result.stderr
    assert "start-unreal-mcp: building project plugins (Fake)" in result.stderr
    events = wait_for_editor(sandbox.events)
    assert [event[0] for event in events] == ["build", "editor"]
    assert events[0] == expected_build_argv(sandbox)


def test_current_binaries_skip_the_build(tmp_path: Path) -> None:
    sandbox = make_sandbox(tmp_path, dylib="current")

    result = run_launcher(sandbox)

    assert result.returncode == 0, result.stderr
    events = wait_for_editor(sandbox.events)
    assert [event[0] for event in events] == ["editor"]
    assert "building project plugins" not in result.stderr


def test_failed_build_stops_the_launch_and_names_the_first_error(tmp_path: Path) -> None:
    sandbox = make_sandbox(
        tmp_path,
        dylib="missing",
        build_body='printf "Foo.cpp:3:1: error: boom\\n"\nexit 2',
    )

    result = run_launcher(sandbox)

    assert result.returncode == 2, result.stderr
    assert str(BUILD_LOG) in result.stderr
    assert "Foo.cpp:3:1: error: boom" in result.stderr
    # The launcher exits before its detached launch, so the editor can never have recorded an argv.
    assert [event[0] for event in read_events(sandbox.events)] == ["build"]


def test_missing_build_sh_is_reported_without_launching(tmp_path: Path) -> None:
    sandbox = make_sandbox(tmp_path, dylib="missing", build_sh=False)

    result = run_launcher(sandbox)

    assert result.returncode != 0
    assert str(sandbox.build_sh) in result.stderr
    assert "UE_ROOT" in result.stderr
    assert read_events(sandbox.events) == []


def test_plugin_disabled_in_the_uproject_is_not_built(tmp_path: Path) -> None:
    sandbox = make_sandbox(tmp_path, dylib="missing")
    data = json.loads(sandbox.uproject.read_text(encoding="utf-8"))
    data["Plugins"][0]["Enabled"] = False
    sandbox.uproject.write_text(json.dumps(data), encoding="utf-8")

    result = run_launcher(sandbox)

    assert result.returncode == 0, result.stderr
    assert "building project plugins" not in result.stderr
    assert [event[0] for event in wait_for_editor(sandbox.events)] == ["editor"]


def test_plugin_under_additional_plugin_directories_is_built(tmp_path: Path) -> None:
    sandbox = make_sandbox(tmp_path, dylib="missing")
    shared = tmp_path / "Shared"
    shared.mkdir()
    shutil.move(str(sandbox.project / "Plugins"), str(shared / "Plugins"))
    data = json.loads(sandbox.uproject.read_text(encoding="utf-8"))
    data["AdditionalPluginDirectories"] = ["../Shared/Plugins"]
    sandbox.uproject.write_text(json.dumps(data), encoding="utf-8")

    result = run_launcher(sandbox)

    assert result.returncode == 0, result.stderr
    assert "start-unreal-mcp: building project plugins (Fake)" in result.stderr
    events = wait_for_editor(sandbox.events)
    assert [event[0] for event in events] == ["build", "editor"]


def test_config_change_newer_than_binaries_does_not_trigger_a_build(tmp_path: Path) -> None:
    """#150 AC1: a newer DefaultEngine.ini neither builds nor blocks the launch."""
    sandbox = make_sandbox(tmp_path, dylib="current", engine_ini_newer=True)

    result = run_launcher(sandbox)

    assert result.returncode == 0, result.stderr
    assert "building project plugins" not in result.stderr
    assert _tags(wait_for_editor(sandbox.events)) == ["editor"]


@pytest.mark.parametrize("code_project", [False, True], ids=["blueprint-only", "code"])
def test_plugin_build_selects_a_single_editor_target(tmp_path: Path, code_project: bool) -> None:
    """#150 AC2: one -TargetType=Editor selector and no named target, for either project kind."""
    sandbox = make_sandbox(tmp_path, dylib="missing", code_project=code_project)

    result = run_launcher(sandbox)

    assert result.returncode == 0, result.stderr
    events = wait_for_editor(sandbox.events)
    assert _tags(events) == ["build", "editor"]
    assert events[0] == expected_build_argv(sandbox)
    assert "UnrealEditor" not in events[0]


def test_current_unreal_editor_lib_binaries_skip_the_build(tmp_path: Path) -> None:
    """#150 AC3: the UE 5.8 libUnrealEditor-<Module>.dylib name is the one checked."""
    sandbox = make_sandbox(tmp_path, dylib="current")
    assert sandbox.dylib.name == f"libUnrealEditor-{MODULE}.dylib"

    result = run_launcher(sandbox)

    assert result.returncode == 0, result.stderr
    assert _tags(wait_for_editor(sandbox.events)) == ["editor"]


def test_legacy_unreal_editor_binary_name_is_accepted_without_the_lib_prefixed_file(
    tmp_path: Path,
) -> None:
    """#150 FR2: UnrealEditor-<Module>.dylib counts only when the lib-prefixed file is absent."""
    sandbox = make_sandbox(tmp_path, dylib="current")
    sandbox.dylib.rename(sandbox.dylib.with_name(f"UnrealEditor-{MODULE}.dylib"))

    result = run_launcher(sandbox)

    assert result.returncode == 0, result.stderr
    assert _tags(wait_for_editor(sandbox.events)) == ["editor"]


def test_uplugin_newer_than_binaries_does_not_trigger_a_build(tmp_path: Path) -> None:
    """#150 FR3: the .uplugin is not a staleness input."""
    sandbox = make_sandbox(tmp_path, dylib="current")
    uplugin = sandbox.project / "Plugins" / "Fake" / "Fake.uplugin"
    now = time.time()
    os.utime(uplugin, (now, now))

    result = run_launcher(sandbox)

    assert result.returncode == 0, result.stderr
    assert "building project plugins" not in result.stderr
    assert _tags(wait_for_editor(sandbox.events)) == ["editor"]


def test_change_to_one_module_does_not_mark_the_plugin_stale(tmp_path: Path) -> None:
    """#150 AC4: module A's binary is older than module B's sources, yet nothing is stale."""
    sandbox = make_sandbox(tmp_path, dylib="current", second_module=True)

    result = run_launcher(sandbox)

    assert result.returncode == 0, result.stderr
    assert "building project plugins" not in result.stderr
    assert _tags(wait_for_editor(sandbox.events)) == ["editor"]


def test_failed_rebuild_with_usable_binaries_warns_and_launches(tmp_path: Path) -> None:
    """#150 AC5: a failed build with every binary present warns, names the log, and launches."""
    sandbox = make_sandbox(tmp_path, dylib="stale", build_body=BUILD_ACTION_GRAPH_INVALID)

    result = run_launcher(sandbox)

    assert result.returncode == 0, result.stderr
    assert "warning: plugin build failed (exit 9)" in result.stderr
    assert str(BUILD_LOG) in result.stderr
    assert "starting the editor on the existing plugin binaries" in result.stderr
    assert _tags(wait_for_editor(sandbox.events)) == ["build", "editor"]


def test_failed_build_with_a_missing_binary_stops_without_launching(tmp_path: Path) -> None:
    """#150 AC6: a failed build with a missing binary exits non-zero and never launches."""
    sandbox = make_sandbox(tmp_path, dylib="missing", build_body=BUILD_ACTION_GRAPH_INVALID)

    result = run_launcher(sandbox)

    assert result.returncode == 9, result.stderr
    assert str(BUILD_LOG) in result.stderr
    assert _tags(read_events(sandbox.events)) == ["build"]


def test_failure_report_shows_the_unreal_build_tool_reason(tmp_path: Path) -> None:
    """#150 AC7: with no error: line, the report shows UBT's Result line, not a placeholder."""
    sandbox = make_sandbox(tmp_path, dylib="missing", build_body=BUILD_ACTION_GRAPH_REASON)

    result = run_launcher(sandbox)

    assert "Result: Failed (ActionGraphInvalid)" in result.stderr, result.stderr
    assert "failure reason: Result: Failed (ActionGraphInvalid)" in result.stderr, result.stderr
    assert "no compiler error found" not in result.stderr
