"""scripts/run-blender-tests.sh isolates each run's user scripts (#189) and passes Blender's exit
status through (#95).

The shim tests replace BLENDER_BIN with a script that records what the gate exported and exits with
a chosen status, so they need no Blender. The real-Blender tests run a headless gate against a
tmp_path suite; they skip only when no Blender resolves (see tests/release_fakes.py).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from tests.release_fakes import REPO_ROOT, resolved_blender, run_gate, write_suite

_SHIM = '#!/bin/sh\nprintf \'%s\\n\' "$@" > "$NMG_BLENDER_ARGV_LOG"\nexit 0\n'

# Records the BLENDER_USER_SCRIPTS the gate exported and whether that directory existed while
# Blender ran. With NMG_PEER_ID set, it waits for the peer run to reach the same point, so the two
# runs overlap.
_SCRIPTS_SHIM = """#!/bin/sh
printf '%s\\n' "$BLENDER_USER_SCRIPTS" > "$NMG_SCRIPTS_LOG"
if [ -d "$BLENDER_USER_SCRIPTS" ]; then echo present >> "$NMG_SCRIPTS_LOG"; fi
if [ -n "${NMG_PEER_ID:-}" ]; then
  : > "$NMG_RENDEZVOUS/$NMG_RUN_ID"
  waited=0
  while [ ! -e "$NMG_RENDEZVOUS/$NMG_PEER_ID" ] && [ "$waited" -lt 200 ]; do
    sleep 0.05
    waited=$((waited + 1))
  done
  if [ -e "$NMG_RENDEZVOUS/$NMG_PEER_ID" ]; then echo overlapped >> "$NMG_SCRIPTS_LOG"; fi
fi
exit "${NMG_SHIM_EXIT:-0}"
"""

# Runs inside the real headless gate. The gate exports BLENDER_USER_SCRIPTS, so the add-on link must
# resolve under that per-run directory, and the enabled add-on must load from this checkout.
_ISOLATION_SUITE = """\
import importlib
import os
from pathlib import Path

import addon_utils
import bpy

CHECKOUT = Path({checkout!r})
ADDON_SRC = Path({addon_src!r})
MODULE_ID = "nmg_game_dev_blender_addon"


def test_the_add_on_loads_from_this_run_and_this_checkout():
    run_scripts = Path(os.environ["BLENDER_USER_SCRIPTS"]).resolve()
    assert Path(bpy.utils.user_resource("SCRIPTS")).resolve() == run_scripts
    assert (run_scripts / "addons" / MODULE_ID).resolve() == ADDON_SRC.resolve()
    assert addon_utils.enable(MODULE_ID, default_set=True, persistent=False) is not None
    try:
        module = importlib.import_module(MODULE_ID)
        assert Path(module.__file__).resolve().is_relative_to(CHECKOUT.resolve())
    finally:
        addon_utils.disable(MODULE_ID, default_set=False)
"""

_ADDON_SRC = REPO_ROOT / "plugins" / "nmg-game-dev-blender-addon"

needs_blender = pytest.mark.skipif(
    resolved_blender() is None,
    reason="no Blender resolves: set BLENDER_BIN or BLENDER_APP to run the gate for real",
)


def _shim(tmp_path: Path) -> Path:
    shim = tmp_path / "blender"
    shim.write_text(_SHIM, encoding="utf-8")
    shim.chmod(0o755)
    return shim


def _scripts_shim(tmp_path: Path) -> Path:
    shim = tmp_path / "blender-scripts"
    shim.write_text(_SCRIPTS_SHIM, encoding="utf-8")
    shim.chmod(0o755)
    return shim


def _tree(root: Path) -> dict[str, bytes | None]:
    """Map every path under root to its bytes (files) or None (directories)."""
    return {
        str(path.relative_to(root)): path.read_bytes() if path.is_file() else None
        for path in root.rglob("*")
    }


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


def test_gate_runs_blender_with_a_per_run_user_scripts_directory_not_the_callers(
    tmp_path: Path,
) -> None:
    users_scripts = tmp_path / "users-scripts"
    (users_scripts / "addons").mkdir(parents=True)
    (users_scripts / "addons" / "marker.txt").write_text("keep", encoding="utf-8")
    before = _tree(users_scripts)
    log = tmp_path / "scripts.txt"

    result = run_gate(
        {
            "BLENDER_BIN": str(_scripts_shim(tmp_path)),
            "BLENDER_USER_SCRIPTS": str(users_scripts),
            "NMG_SCRIPTS_LOG": str(log),
        }
    )

    assert result.returncode == 0, result.stderr
    seen, presence = log.read_text(encoding="utf-8").splitlines()
    assert Path(seen) != users_scripts
    assert presence == "present"
    assert _tree(users_scripts) == before


@pytest.mark.parametrize("exit_code", [0, 3])
def test_gate_removes_its_user_scripts_directory_and_exits_with_blenders_status(
    tmp_path: Path, exit_code: int
) -> None:
    log = tmp_path / "scripts.txt"

    result = run_gate(
        {
            "BLENDER_BIN": str(_scripts_shim(tmp_path)),
            "NMG_SCRIPTS_LOG": str(log),
            "NMG_SHIM_EXIT": str(exit_code),
        }
    )

    assert result.returncode == exit_code, result.stderr
    seen, presence = log.read_text(encoding="utf-8").splitlines()
    assert presence == "present"
    assert not Path(seen).exists()


def test_concurrent_gate_runs_each_use_their_own_user_scripts_directory(tmp_path: Path) -> None:
    shim = _scripts_shim(tmp_path)
    rendezvous = tmp_path / "rendezvous"
    rendezvous.mkdir()
    peers = {"a": "b", "b": "a"}
    logs = {run: tmp_path / f"{run}.txt" for run in peers}

    with ThreadPoolExecutor(max_workers=len(peers)) as pool:
        futures = {
            run: pool.submit(
                run_gate,
                {
                    "BLENDER_BIN": str(shim),
                    "NMG_SCRIPTS_LOG": str(logs[run]),
                    "NMG_RENDEZVOUS": str(rendezvous),
                    "NMG_RUN_ID": run,
                    "NMG_PEER_ID": peer,
                },
            )
            for run, peer in peers.items()
        }
        results = {run: future.result() for run, future in futures.items()}

    for run, result in results.items():
        assert result.returncode == 0, f"run {run}: {result.stderr}"
    seen = {run: log.read_text(encoding="utf-8").splitlines() for run, log in logs.items()}
    assert all("overlapped" in lines for lines in seen.values())
    assert all(lines[1] == "present" for lines in seen.values())
    assert seen["a"][0] != seen["b"][0]


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


@needs_blender
def test_a_real_gate_run_loads_the_add_on_from_its_own_location_and_checkout(
    tmp_path: Path,
) -> None:
    suite = write_suite(
        tmp_path,
        _ISOLATION_SUITE.format(checkout=str(REPO_ROOT), addon_src=str(_ADDON_SRC)),
    )

    result = run_gate({}, str(suite))

    assert result.returncode == 0, result.stdout + result.stderr
