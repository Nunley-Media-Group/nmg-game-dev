"""scripts/run-blender-tests.sh passes Blender's exit status through to the gate (#95; FR1, AC1).

The argv test shims BLENDER_BIN with a script that records its arguments. The exit-code tests run
a real Blender against a tmp_path suite; they skip only when no Blender resolves (see
tests/release_fakes.py).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.release_fakes import resolved_blender, run_gate, write_suite

_SHIM = '#!/bin/sh\nprintf \'%s\\n\' "$@" > "$NMG_BLENDER_ARGV_LOG"\nexit 0\n'

needs_blender = pytest.mark.skipif(
    resolved_blender() is None,
    reason="no Blender resolves: set BLENDER_BIN or BLENDER_APP to run the gate for real",
)


def _shim(tmp_path: Path) -> Path:
    shim = tmp_path / "blender"
    shim.write_text(_SHIM, encoding="utf-8")
    shim.chmod(0o755)
    return shim


def test_gate_passes_the_exit_code_flag_and_the_target_to_blender(tmp_path: Path) -> None:
    argv_log = tmp_path / "argv.txt"

    result = run_gate(
        {"BLENDER_BIN": str(_shim(tmp_path)), "NMG_BLENDER_ARGV_LOG": str(argv_log)}, "tests/unit"
    )

    assert result.returncode == 0, result.stderr
    assert argv_log.read_text(encoding="utf-8").splitlines() == [
        "--background",
        "--python-exit-code",
        "1",
        "--python",
        "tests/blender/_runner.py",
        "--",
        "tests/unit",
    ]


def test_gate_defaults_the_target_to_tests_blender(tmp_path: Path) -> None:
    argv_log = tmp_path / "argv.txt"

    result = run_gate({"BLENDER_BIN": str(_shim(tmp_path)), "NMG_BLENDER_ARGV_LOG": str(argv_log)})

    assert result.returncode == 0, result.stderr
    assert argv_log.read_text(encoding="utf-8").splitlines()[-1] == "tests/blender"


@needs_blender
def test_a_failing_blender_test_fails_the_gate(tmp_path: Path) -> None:
    suite = write_suite(tmp_path, "def test_fails():\n    assert False\n")

    result = run_gate({}, str(suite))

    assert result.returncode == 1, result.stdout + result.stderr


@needs_blender
def test_an_erroring_blender_test_fails_the_gate(tmp_path: Path) -> None:
    suite = write_suite(
        tmp_path,
        "import pytest\n\n"
        "@pytest.fixture\n"
        "def broken():\n"
        "    raise RuntimeError('fixture error')\n\n"
        "def test_errors(broken):\n"
        "    pass\n",
    )

    result = run_gate({}, str(suite))

    assert result.returncode != 0, result.stdout + result.stderr


@needs_blender
def test_a_passing_blender_suite_exits_zero(tmp_path: Path) -> None:
    suite = write_suite(tmp_path, "def test_passes():\n    assert True\n")

    result = run_gate({}, str(suite))

    assert result.returncode == 0, result.stdout + result.stderr
