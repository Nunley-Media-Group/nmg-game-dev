"""start-unreal-mcp.sh builds stale or missing project plugin binaries before launch (#103 AC1-AC4).

Each test runs the real launcher against a temporary project and a fake UE_ROOT (see
tests/start_unreal_fakes.py). Nothing is compiled and no editor starts.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from tests.start_unreal_fakes import (
    BUILD_LOG,
    expected_build_argv,
    make_sandbox,
    read_events,
    run_launcher,
    wait_for_editor,
)


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
