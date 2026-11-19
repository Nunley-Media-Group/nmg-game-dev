"""pytest-bdd bindings for godot_gate_required_tests.feature: SCN001 and SCN002 of #297.

SCN001 reads scripts/run-godot-tests.sh and test_nmg_build.gd. SCN002 runs the gate script on a
sandbox PATH with the fake godot from tests/unit/test_run_godot_tests.py, whose tests_missing_build
mode prints a PASS line for every required test except one NmgBuild test, so no Godot process runs.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Final

import pytest
from pytest_bdd import given, scenario, then, when

from tests.unit.test_run_godot_tests import (
    _FAKE_GODOT,
    FIXTURE,
    NMG_BUILD_TESTS,
    REPO_ROOT,
    SCRIPT,
    _build_test_ids,
    _required_tests,
    _write_tool,
)

FEATURE: Final = "godot_gate_required_tests.feature"
DROPPED_TEST: Final = "test_nmg_build.gd::test_version_label_shows_the_prefixed_version"


@pytest.fixture
def state(tmp_path: Path) -> dict[str, Any]:
    return {"tmp": tmp_path}


def _gate_env(root: Path) -> dict[str, str]:
    """The sandbox environment for scripts/run-godot-tests.sh with a fake ``godot`` on PATH."""
    godot = _write_tool(root / "path-bin" / "godot", _FAKE_GODOT)
    return {
        "PATH": os.pathsep.join(
            [str(godot.parent), str(Path(sys.executable).parent), "/usr/bin", "/bin"]
        ),
        "HOME": str(root),
        "LANG": "C",
        "GODOT_CACHE_DIR": str(root / "cache"),
        "FAKE_GODOT_LOG": str(root / "godot.jsonl"),
        "FAKE_EXPECTED": str(FIXTURE / "expected-probe.json"),
    }


def _run_gate(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


@scenario(FEATURE, "Every build test is required")
def test_every_build_test_is_required() -> None:
    """AC1: the required_tests array lists every test_* function in test_nmg_build.gd."""


@scenario(FEATURE, "A missing build test fails the gate")
def test_a_missing_build_test_fails_the_gate() -> None:
    """AC2: a run with no PASS line for one build test exits 5 and names that test."""


@given("scripts/run-godot-tests.sh and test_nmg_build.gd")
def _given_gate_and_build_tests(state: dict[str, Any]) -> None:
    assert SCRIPT.is_file()
    assert NMG_BUILD_TESTS.is_file()


@when("the required_tests array is read")
def _read_required_tests(state: dict[str, Any]) -> None:
    state["required"] = _required_tests()


@then("it lists every test_* function in test_nmg_build.gd")
def _lists_every_build_test(state: dict[str, Any]) -> None:
    build_ids = _build_test_ids()
    assert build_ids, "test_nmg_build.gd has no test_* functions"
    assert [test for test in build_ids if test not in state["required"]] == []


@given("a Godot add-on test run with no PASS line for one test_nmg_build.gd test")
def _given_one_build_test_missing(state: dict[str, Any]) -> None:
    state["env"] = {**_gate_env(state["tmp"]), "FAKE_GODOT_MODE": "tests_missing_build"}


@when("scripts/run-godot-tests.sh runs")
def _run_gate_script(state: dict[str, Any]) -> None:
    state["result"] = _run_gate(state["env"])


@then("it exits 5")
def _exits_5(state: dict[str, Any]) -> None:
    assert state["result"].returncode == 5, state["result"].stderr


@then("stderr names the missing test_nmg_build.gd test")
def _names_the_missing_test(state: dict[str, Any]) -> None:
    assert f"no PASS line for {DROPPED_TEST}" in state["result"].stderr
