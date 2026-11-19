"""pytest-bdd bindings for ship_secret_untracked.feature: SCN001–SCN003 (#296 AC1–AC3).

Each scenario runs the real ship runner against the ship sandbox from ``tests/ship_fakes.py``,
with a fake Godot, in a temporary consumer. SCN001 and SCN002 run in a real ``git init`` work tree;
SCN003 has no git. Every key is assembled at runtime, and no scenario contacts a service.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from pytest_bdd import given, parsers, scenario, then, when

from nmg_game_dev.secrets.scan import fingerprint, mask
from nmg_game_dev.ship.errors import ShipError
from tests.ship_fakes import ShipSandbox, make_sandbox

FEATURE = "ship_secret_untracked.feature"
MESHY = "msy_" + "Ab3dEf6hIj9kLm2nOp5q"
LEAK = f'var key = "{MESHY}"\n'
LEAK_PATH = "game/scripts/leak.gd"
LOCATIONS: dict[str, tuple[str, bool]] = {
    # The location phrase -> (consumer-relative path, whether .gitignore covers it).
    "an untracked file under game/ that is ignored": ("game/scripts/local_keys.gd", True),
    "an untracked file outside game/": ("notes/keys.gd", False),
    "an untracked file under game/.godot/": ("game/.godot/editor/keys.gd", False),
}


@dataclass
class ShipRun:
    """One ``/ship --dry-run``: the sandbox it ran in and the structured error it stopped with."""

    sandbox: ShipSandbox
    error: ShipError | None = None


def _git_init(consumer: Path) -> None:
    subprocess.run(["git", "-C", str(consumer), "init", "-q"], check=True, capture_output=True)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# --- SCN001 ------------------------------


@scenario(FEATURE, "An untracked key under game/ stops the ship")
def test_an_untracked_key_under_game_stops_the_ship() -> None:
    """AC1: an untracked, unignored file under game/ is scanned, also in a dry run."""


@given(
    "a consumer git repository with an untracked, unignored file under game/ "
    "containing a Meshy key",
    target_fixture="ship",
)
def _untracked_meshy_key(tmp_path: Path) -> ShipSandbox:
    sandbox = make_sandbox(tmp_path)
    _git_init(sandbox.game.parent)
    _write(sandbox.game.parent / LEAK_PATH, LEAK)
    return sandbox


# --- SCN002 ------------------------------


@scenario(FEATURE, "Ignored and non-exported untracked files do not fail the gate")
def test_ignored_and_non_exported_untracked_files_do_not_fail_the_gate() -> None:
    """AC2: a key the export never includes does not fail the gate."""


@given(
    parsers.parse("a consumer git repository whose only key is in {location}"),
    target_fixture="ship",
)
def _only_key_in(tmp_path: Path, location: str) -> ShipSandbox:
    rel, ignored = LOCATIONS[location]
    sandbox = make_sandbox(tmp_path)
    consumer = sandbox.game.parent
    _git_init(consumer)
    if ignored:
        _write(consumer / ".gitignore", f"{rel}\n")
    _write(consumer / rel, LEAK)
    return sandbox


# --- SCN003 ------------------------------


@scenario(FEATURE, "Outside git, local secret stores are skipped and other files are scanned")
def test_outside_git_local_secret_stores_are_skipped_and_other_files_are_scanned() -> None:
    """AC3: outside git the local stores and dependency folders pass; any other file stops."""


@given(
    parsers.parse('a consumer that is not a git work tree with a key in "{path}"'),
    target_fixture="ship",
)
def _outside_git_key(tmp_path: Path, path: str) -> ShipSandbox:
    sandbox = make_sandbox(tmp_path)
    _write(sandbox.game.parent / path, f"key {MESHY}\n")
    return sandbox


# --- Shared steps ------------------------------


@when('"/ship macos --dry-run" runs', target_fixture="ship_run")
def _ship_dry_run(ship: ShipSandbox) -> ShipRun:
    run = ShipRun(ship)
    try:
        ship.ship("macos", dry_run=True)
    except ShipError as error:
        run.error = error
    return run


@then(parsers.parse('it stops with "{code}" listing the masked match for that file'))
def _stops_listing_the_masked_file(ship_run: ShipRun, code: str) -> None:
    error = ship_run.error
    assert error is not None, "the ship ran past the secret scan"
    assert error.code == code
    assert f"{LEAK_PATH}:1: meshy {mask(MESHY)} ({fingerprint(MESHY)})" in error.message


@then("no Godot command ran")
def _no_godot_command(ship_run: ShipRun) -> None:
    assert ship_run.sandbox.godot.calls == []


@then("the unmasked key does not appear in the error")
def _key_not_in_error(ship_run: ShipRun) -> None:
    error = ship_run.error
    assert error is not None
    assert MESHY not in f"{error.message}\n{error.remediation}"


@then("the secret gate passes")
def _gate_passes(ship_run: ShipRun) -> None:
    assert ship_run.error is None, f"the ship stopped: {ship_run.error}"


@then(parsers.parse('the secret gate stops with "{code}"'))
def _gate_stops(ship_run: ShipRun, code: str) -> None:
    error = ship_run.error
    assert error is not None, "the ship ran past the secret scan"
    assert error.code == code
