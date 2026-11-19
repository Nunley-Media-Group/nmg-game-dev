"""pytest-bdd bindings for ship_versioning.feature: the build version, changelog, and release notes
(#254 SCN001-SCN006).

Each scenario runs the real ship flow against the fake Godot and PATH shims in
``tests/ship_fakes.py``, so no scenario runs Godot, contacts a store, or reads a credential.
SCN005 runs ``scripts/run-godot-tests.sh`` against a fake Godot to check that the add-on ships its
version files; the real Godot run is the ``gate-godot-headless`` gate.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

import pytest
from pytest_bdd import given, parsers, scenario, then, when

from nmg_game_dev.godot.project import parse_config
from nmg_game_dev.process import CommandResult
from nmg_game_dev.ship.artifacts import ReleaseEntry, artifact_sha256
from nmg_game_dev.ship.errors import ShipError
from nmg_game_dev.ship.version import patch_preset_literals
from tests.ship_fakes import (
    REPO_ROOT,
    VERSION_KEYS,
    ShipSandbox,
    changed_keys,
    consumer_bytes,
    make_sandbox,
)

_ADDON: Final[Path] = REPO_ROOT / "plugins" / "nmg-game-dev-godot-addon" / "addons" / "nmg_game_dev"
_GATE: Final[Path] = REPO_ROOT / "scripts" / "run-godot-tests.sh"
_ADDON_FILES: Final[tuple[str, ...]] = (
    "nmg_build.gd",
    "nmg_version_label.gd",
    "tests/test_nmg_build.gd",
)
_ANDROID: Final = 2
_WINDOWS: Final = 3
_FAKE_GODOT: Final = r"""
import json
import os
import re
import sys
from pathlib import Path

args = sys.argv[1:]
project = Path(args[args.index("--path") + 1])
rest = args[args.index("--path") + 2 :]
log = Path(os.environ["FAKE_GODOT_LOG"])
with log.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps({"argv": args}) + "\n")
if rest == ["--import"]:
    sys.exit(0)
if rest[:2] == ["-s", "res://addons/nmg_game_dev/tests/run_tests.gd"]:
    present = [
        name
        for name in ("nmg_build.gd", "nmg_version_label.gd", "tests/test_nmg_build.gd")
        if (project / "addons" / "nmg_game_dev" / name).is_file()
    ]
    script = Path(os.environ["FAKE_GATE_SCRIPT"]).read_text(encoding="utf-8")
    names = re.findall(r'"(test_[a-z_]+\.gd::test_[a-z_]+)"', script)
    with log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"addon_files": present}) + "\n")
    for name in names:
        print(f"PASS {name}")
    print(f"{len(names)} passed, 0 failed")
    sys.exit(0)
sys.exit(1)
"""


@dataclass
class VersionScenario:
    """The state one scenario carries from its Given steps to its Then steps."""

    sandbox: ShipSandbox
    capsys: pytest.CaptureFixture[str]
    before: dict[str, bytes] = field(default_factory=dict)
    error: ShipError | None = None
    entries: list[ReleaseEntry] = field(default_factory=list)
    output: str = ""
    addon_seen: list[str] = field(default_factory=list)


@pytest.fixture
def versioning(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> VersionScenario:
    return VersionScenario(sandbox=make_sandbox(tmp_path), capsys=capsys)


@scenario("ship_versioning.feature", "/ship sets the version")
def test_ship_sets_the_version() -> None:
    """SCN001: --bump minor writes 1.3.0 to the project and every preset, and nothing else."""


@scenario("ship_versioning.feature", "The version must increase")
def test_the_version_must_increase() -> None:
    """SCN002: a version not above the current one, or malformed, stops before any Godot run."""


@scenario("ship_versioning.feature", "A changelog entry is required")
def test_a_changelog_entry_is_required() -> None:
    """SCN003: a version with no CHANGELOG.md section stops before any Godot command."""


@scenario("ship_versioning.feature", "Release notes carry the version, changes, and gate results")
def test_release_notes_carry_the_version_changes_and_gates() -> None:
    """SCN004: the release notes show the version, the changelog text, and the gate results."""


@scenario("ship_versioning.feature", "The game shows its version")
def test_the_game_shows_its_version() -> None:
    """SCN005: the add-on ships NmgBuild and NmgVersionLabel, and their tests run in Godot."""


@scenario("ship_versioning.feature", "Dry run changes nothing")
def test_dry_run_changes_nothing() -> None:
    """SCN006: a dry run prints the planned version and changelog lines and writes no file."""


# --- helpers ----------------------------------------------------------------------------------


def _set_project_version(sandbox: ShipSandbox, version: str) -> None:
    text = sandbox.project.read_text(encoding="utf-8")
    current = parse_config(text)[("application", "config/version")]
    sandbox.project.write_text(
        text.replace(f"config/version={current}", f'config/version="{version}"'), encoding="utf-8"
    )


def _add_changelog_section(sandbox: ShipSandbox, heading: str, text: str) -> None:
    path = sandbox.game.parent / "CHANGELOG.md"
    path.write_text(
        path.read_text(encoding="utf-8") + f"\n## {heading}\n\n{text}\n", encoding="utf-8"
    )


def _ship_command(state: VersionScenario, command: str) -> None:
    """Run ``/ship <command>``: the target, then the --bump, --version, and --dry-run flags."""
    tokens = command.split()
    target, flags = tokens[0], tokens[1:]
    bump = version = None
    dry_run = "--dry-run" in flags
    for index, token in enumerate(flags):
        if token == "--bump":
            bump = flags[index + 1]
        elif token == "--version":
            version = flags[index + 1]
    state.before = consumer_bytes(state.sandbox)
    try:
        state.entries = state.sandbox.ship(target, dry_run=dry_run, bump=bump, version=version)
    except ShipError as error:
        state.error = error
    captured = state.capsys.readouterr()
    state.output += captured.out + captured.err


def _notes(state: VersionScenario) -> str:
    return (state.sandbox.release_dir / "RELEASE-NOTES.md").read_text(encoding="utf-8")


def _section(notes: str, heading: str) -> list[str]:
    """The lines under ``heading`` up to the next level-two heading."""
    lines = notes.splitlines()
    start = lines.index(heading) + 1
    end = next((i for i in range(start, len(lines)) if lines[i].startswith("## ")), len(lines))
    return lines[start:end]


# --- Given ------------------------------------------------------------------------------------


@given(
    parsers.parse(
        'a consumer at version "{version}" whose Android preset has version/code {code:d} '
        'and a CHANGELOG.md with a "## {heading}" section'
    )
)
def _consumer_with_android_code(
    versioning: VersionScenario, version: str, code: int, heading: str
) -> None:
    _set_project_version(versioning.sandbox, version)
    presets = versioning.sandbox.game / "export_presets.cfg"
    text = presets.read_text(encoding="utf-8")
    presets.write_text(
        patch_preset_literals(text, _ANDROID, {"version/code": str(code)}), encoding="utf-8"
    )
    _add_changelog_section(versioning.sandbox, heading, "- Faster loading.")


@given(
    parsers.parse(
        'a consumer at version "{version}" whose CHANGELOG.md has no "## {heading}" section'
    )
)
def _consumer_without_section(versioning: VersionScenario, version: str, heading: str) -> None:
    _set_project_version(versioning.sandbox, version)


@given(
    parsers.parse(
        'a consumer at version "{version}" with a "## {heading}" changelog section "{text}"'
    )
)
def _consumer_with_section_text(
    versioning: VersionScenario, version: str, heading: str, text: str
) -> None:
    _set_project_version(versioning.sandbox, version)
    _add_changelog_section(versioning.sandbox, heading, text)


@given(parsers.parse('a consumer at version "{version}" with a "## {heading}" changelog section'))
def _consumer_with_section(versioning: VersionScenario, version: str, heading: str) -> None:
    _set_project_version(versioning.sandbox, version)
    _add_changelog_section(versioning.sandbox, heading, "- Smaller download.")


@given(parsers.parse('a consumer at version "{version}"'))
def _consumer_at_version(versioning: VersionScenario, version: str) -> None:
    _set_project_version(versioning.sandbox, version)


@given(parsers.parse('the project tests print "{summary}"'))
def _project_tests(versioning: VersionScenario, summary: str) -> None:
    sandbox = versioning.sandbox
    tests = sandbox.game / "tests"
    tests.mkdir()
    (tests / "run_tests.gd").write_text("extends SceneTree\n", encoding="utf-8")
    sandbox.godot.responses["-s"] = lambda args, project: CommandResult(0, stdout=f"{summary}\n")


@given("the add-on with NmgBuild and NmgVersionLabel")
def _addon_present() -> None:
    for name in _ADDON_FILES:
        assert (_ADDON / name).is_file(), name


# --- When -------------------------------------------------------------------------------------


@when(parsers.parse('"/ship {command}" runs'))
def _ship_runs(versioning: VersionScenario, command: str) -> None:
    _ship_command(versioning, command)


@when(parsers.parse('"/ship {command}" succeeds'))
def _ship_succeeds(versioning: VersionScenario, command: str) -> None:
    _ship_command(versioning, command)
    assert versioning.error is None, versioning.error


@when(parsers.parse("/ship runs with {flags}"))
def _ship_runs_with(versioning: VersionScenario, flags: str) -> None:
    _ship_command(versioning, f"all {flags}")


@when("the add-on tests run in headless Godot")
def _addon_tests_run(versioning: VersionScenario, tmp_path: Path) -> None:
    """Run the gate script against a fake Godot, which records the add-on files it sees."""
    fake = tmp_path / "godot_fake.py"
    fake.write_text(_FAKE_GODOT, encoding="utf-8")
    wrapper = tmp_path / "godot"
    wrapper.write_text(f"#!/bin/sh\nexec '{sys.executable}' '{fake}' \"$@\"\n", encoding="utf-8")
    wrapper.chmod(0o755)
    log = tmp_path / "godot_calls.jsonl"
    env = {
        **os.environ,
        "GODOT_BIN": str(wrapper),
        "FAKE_GODOT_LOG": str(log),
        "FAKE_GATE_SCRIPT": str(_GATE),
    }
    subprocess.run([str(_GATE)], env=env, capture_output=True, text=True, check=False)
    for line in log.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if "addon_files" in record:
            versioning.addon_seen = record["addon_files"]


# --- Then -------------------------------------------------------------------------------------


@then(parsers.parse('game/project.godot has application/config/version "{version}"'))
def _project_has_version(versioning: VersionScenario, version: str) -> None:
    text = versioning.sandbox.project.read_text(encoding="utf-8")
    assert parse_config(text)[("application", "config/version")] == f'"{version}"'


@then(
    parsers.parse(
        'the macOS and iOS presets have version "{version}", the Android preset has '
        'version/name "{name}" and version/code {code:d}, and the Windows preset has "{windows}"'
    )
)
def _presets_have_version(
    versioning: VersionScenario, version: str, name: str, code: int, windows: str
) -> None:
    text = (versioning.sandbox.game / "export_presets.cfg").read_text(encoding="utf-8")
    options = parse_config(text)
    assert options[("preset.0.options", "application/short_version")] == f'"{version}"'
    assert options[("preset.0.options", "application/version")] == f'"{version}"'
    assert options[("preset.1.options", "application/short_version")] == f'"{version}"'
    assert options[("preset.1.options", "application/version")] == f'"{version}"'
    assert options[("preset.2.options", "version/name")] == f'"{name}"'
    assert options[("preset.2.options", "version/code")] == str(code)
    assert options[("preset.3.options", "application/file_version")] == f'"{windows}"'
    assert options[("preset.3.options", "application/product_version")] == f'"{windows}"'


@then("no other line of either file changed")
def _only_version_lines_changed(versioning: VersionScenario) -> None:
    sandbox = versioning.sandbox
    project_before = versioning.before["project"].decode("utf-8")
    presets_before = versioning.before["presets"].decode("utf-8")
    project_after = sandbox.project.read_text(encoding="utf-8")
    presets_after = (sandbox.game / "export_presets.cfg").read_text(encoding="utf-8")
    assert changed_keys(project_before, project_after) == {"config/version"}
    assert changed_keys(presets_before, presets_after) <= VERSION_KEYS


@then(parsers.parse('it stops with "{code}" and no Godot command ran and no file changed'))
def _stops_with_no_change(versioning: VersionScenario, code: str) -> None:
    assert versioning.error is not None, "the ship did not stop"
    assert versioning.error.code == code
    assert versioning.sandbox.godot.calls == []
    assert consumer_bytes(versioning.sandbox) == versioning.before


@then(parsers.parse('it stops with "{code}" before any Godot command'))
def _stops_before_godot(versioning: VersionScenario, code: str) -> None:
    assert versioning.error is not None, "the ship did not stop"
    assert versioning.error.code == code
    assert versioning.sandbox.godot.calls == []


@then(parsers.parse('release/RELEASE-NOTES.md is headed "{heading}"'))
def _notes_headed(versioning: VersionScenario, heading: str) -> None:
    assert _notes(versioning).splitlines()[0] == heading


@then(parsers.parse('it includes "{text}" under "{heading}"'))
def _notes_include(versioning: VersionScenario, text: str, heading: str) -> None:
    assert any(text in line for line in _section(_notes(versioning), heading))


@then(parsers.parse('it lists "{item}" under "{heading}"'))
def _notes_list(versioning: VersionScenario, item: str, heading: str) -> None:
    assert f"- {item}" in _section(_notes(versioning), heading)


@then("it keeps the artifact SHA-256 table")
def _notes_keep_table(versioning: VersionScenario) -> None:
    notes = _notes(versioning)
    assert "| Platform | Artifact | SHA-256 |" in notes
    assert versioning.entries, "the ship produced no artifact"
    for entry in versioning.entries:
        assert f"`{entry.sha256}`" in notes
        assert entry.sha256 == artifact_sha256(versioning.sandbox.release_dir / entry.path)


@then(parsers.parse('it prints "{first}" and "{second}"'))
def _prints_both(versioning: VersionScenario, first: str, second: str) -> None:
    assert first in versioning.output
    assert second in versioning.output


@then("project.godot, export_presets.cfg, and CHANGELOG.md are byte-identical")
def _consumer_unchanged(versioning: VersionScenario) -> None:
    assert consumer_bytes(versioning.sandbox) == versioning.before


@then(
    'NmgBuild.version() returns the project version and an NmgVersionLabel shows "v" followed by it'
)
def _addon_shows_version(versioning: VersionScenario) -> None:
    assert set(_ADDON_FILES) <= set(versioning.addon_seen), versioning.addon_seen
    build = (_ADDON / "nmg_build.gd").read_text(encoding="utf-8")
    label = (_ADDON / "nmg_version_label.gd").read_text(encoding="utf-8")
    assert 'const VERSION_SETTING: String = "application/config/version"' in build
    assert "static func version() -> String:" in build
    assert 'var prefix: String = "v"' in label
    assert "text = prefix + version" in label
