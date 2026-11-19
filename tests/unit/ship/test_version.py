"""AC1, AC2, AC6: the build version ship sets, its checks, and the line-level write (#254)."""

from __future__ import annotations

from pathlib import Path

import pytest

from nmg_game_dev.godot.presets import render_export_presets
from nmg_game_dev.godot.project import parse_config, read_config
from nmg_game_dev.ship.errors import ShipError
from nmg_game_dev.ship.version import (
    VersionPlan,
    patch_preset_literals,
    plan_version_edits,
    resolve_version,
    write_version,
)
from tests.ship_fakes import VERSION_KEYS, changed_keys

_ANDROID = 2
"""The preset index of Android in ``render_export_presets`` (macOS, iOS, Android, Windows, Web)."""
_PROJECT = (
    'config_version=5\n\n[application]\n\nconfig/name="Dogfood"\nconfig/version="1.2.3"\n'
    "\n[display]\n\nwindow/size/viewport_width=1280\n"
)


def _game(tmp_path: Path, project_text: str = _PROJECT) -> Path:
    """A ``game/`` folder with a project and export presets; Android starts at version/code 4."""
    game = tmp_path / "game"
    game.mkdir()
    (game / "project.godot").write_text(project_text, encoding="utf-8")
    presets = patch_preset_literals(
        render_export_presets("Dogfood"), _ANDROID, {"version/code": "4"}
    )
    (game / "export_presets.cfg").write_text(presets, encoding="utf-8")
    return game


@pytest.mark.parametrize(
    ("bump", "expected"),
    [("major", "2.0.0"), ("minor", "1.3.0"), ("patch", "1.2.4")],
)
def test_bump_raises_the_named_part_from_the_current_version(
    tmp_path: Path, bump: str, expected: str
) -> None:
    plan = resolve_version(_game(tmp_path) / "project.godot", bump, None)
    assert plan == VersionPlan(current="1.2.3", new=expected, changed=True)


def test_version_flag_sets_the_named_version(tmp_path: Path) -> None:
    plan = resolve_version(_game(tmp_path) / "project.godot", None, "1.3.0")
    assert plan == VersionPlan(current="1.2.3", new="1.3.0", changed=True)


def test_no_flag_ships_the_current_version_unchanged(tmp_path: Path) -> None:
    plan = resolve_version(_game(tmp_path) / "project.godot", None, None)
    assert plan == VersionPlan(current="1.2.3", new="1.2.3", changed=False)


@pytest.mark.parametrize("version", ["1.2.3", "1.0.0", "1.2.2"])
def test_a_version_not_above_the_current_one_is_refused(tmp_path: Path, version: str) -> None:
    with pytest.raises(ShipError) as caught:
        resolve_version(_game(tmp_path) / "project.godot", None, version)
    assert caught.value.code == "ship.version_not_increased"
    assert caught.value.stage == "preflight"


@pytest.mark.parametrize("version", ["1.3", "v1.3.0", "01.3.0", "1.3.0-rc1", "1.3.0.0", ""])
def test_a_malformed_version_flag_is_refused(tmp_path: Path, version: str) -> None:
    with pytest.raises(ShipError) as caught:
        resolve_version(_game(tmp_path) / "project.godot", None, version)
    assert caught.value.code == "ship.version_invalid"


def test_both_flags_together_are_refused(tmp_path: Path) -> None:
    with pytest.raises(ShipError) as caught:
        resolve_version(_game(tmp_path) / "project.godot", "minor", "1.3.0")
    assert caught.value.code == "ship.version_invalid"


def test_an_unknown_bump_part_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ShipError) as caught:
        resolve_version(_game(tmp_path) / "project.godot", "huge", None)
    assert caught.value.code == "ship.version_invalid"


@pytest.mark.parametrize("declared", ['"1.3"', '"v1.3.0"', '"1.3.0-beta"'])
def test_a_malformed_current_version_is_refused(tmp_path: Path, declared: str) -> None:
    project = _PROJECT.replace('config/version="1.2.3"', f"config/version={declared}")
    with pytest.raises(ShipError) as caught:
        resolve_version(_game(tmp_path, project) / "project.godot", None, None)
    assert caught.value.code == "ship.version_invalid"


def test_a_project_with_no_version_needs_a_flag(tmp_path: Path) -> None:
    project = _PROJECT.replace('config/version="1.2.3"\n', "")
    game = _game(tmp_path, project)
    with pytest.raises(ShipError) as caught:
        resolve_version(game / "project.godot", None, None)
    assert caught.value.code == "ship.version_missing"
    assert "--version X.Y.Z" in caught.value.remediation


def test_an_empty_version_counts_as_no_version(tmp_path: Path) -> None:
    project = _PROJECT.replace('config/version="1.2.3"', 'config/version=""')
    with pytest.raises(ShipError) as caught:
        resolve_version(_game(tmp_path, project) / "project.godot", None, None)
    assert caught.value.code == "ship.version_missing"


def test_a_first_ship_counts_the_missing_version_as_zero(tmp_path: Path) -> None:
    project = _PROJECT.replace('config/version="1.2.3"\n', "")
    game = _game(tmp_path, project)
    assert resolve_version(game / "project.godot", "minor", None).new == "0.1.0"
    assert resolve_version(game / "project.godot", None, "1.0.0").new == "1.0.0"


def test_write_sets_each_shipping_preset_and_changes_only_version_lines(tmp_path: Path) -> None:
    game = _game(tmp_path)
    project_before = (game / "project.godot").read_text(encoding="utf-8")
    presets_before = (game / "export_presets.cfg").read_text(encoding="utf-8")
    write_version(resolve_version(game / "project.godot", "minor", None), game)

    project_after = (game / "project.godot").read_text(encoding="utf-8")
    presets_after = (game / "export_presets.cfg").read_text(encoding="utf-8")
    assert read_config(game / "project.godot")[("application", "config/version")] == '"1.3.0"'
    assert project_after.replace('config/version="1.3.0"', 'config/version="1.2.3"') == (
        project_before
    )
    assert changed_keys(presets_before, presets_after) <= VERSION_KEYS
    assert changed_keys(project_before, project_after) == {"config/version"}

    options = parse_config(presets_after)
    assert options[("preset.0.options", "application/short_version")] == '"1.3.0"'
    assert options[("preset.0.options", "application/version")] == '"1.3.0"'
    assert options[("preset.1.options", "application/short_version")] == '"1.3.0"'
    assert options[("preset.1.options", "application/version")] == '"1.3.0"'
    assert options[("preset.2.options", "version/name")] == '"1.3.0"'
    assert options[("preset.2.options", "version/code")] == "5"
    assert options[("preset.3.options", "application/file_version")] == '"1.3.0.0"'
    assert options[("preset.3.options", "application/product_version")] == '"1.3.0.0"'
    assert ("preset.4.options", "application/version") not in options


def test_android_version_code_starts_at_one_when_absent(tmp_path: Path) -> None:
    game = _game(tmp_path)
    presets = render_export_presets("Dogfood")
    (game / "export_presets.cfg").write_text(presets, encoding="utf-8")
    write_version(resolve_version(game / "project.godot", None, "1.3.0"), game)
    options = parse_config((game / "export_presets.cfg").read_text(encoding="utf-8"))
    assert options[("preset.2.options", "version/code")] == "1"


def test_a_project_without_an_application_section_gets_one(tmp_path: Path) -> None:
    game = _game(tmp_path, "config_version=5\n")
    write_version(resolve_version(game / "project.godot", None, "1.0.0"), game)
    assert (
        (game / "project.godot")
        .read_text(encoding="utf-8")
        .endswith('\n[application]\n\nconfig/version="1.0.0"\n')
    )


def test_a_project_without_a_version_line_gets_it_under_application(tmp_path: Path) -> None:
    project = 'config_version=5\n\n[application]\n\nconfig/name="Dogfood"\n'
    game = _game(tmp_path, project)
    write_version(resolve_version(game / "project.godot", None, "1.0.0"), game)
    text = (game / "project.godot").read_text(encoding="utf-8")
    assert text.startswith('config_version=5\n\n[application]\nconfig/version="1.0.0"\n')
    assert 'config/name="Dogfood"' in text


def test_no_flag_writes_nothing(tmp_path: Path) -> None:
    game = _game(tmp_path)
    before = {name: (game / name).read_bytes() for name in ("project.godot", "export_presets.cfg")}
    write_version(resolve_version(game / "project.godot", None, None), game)
    assert {name: (game / name).read_bytes() for name in before} == before


def test_a_dry_run_plan_names_the_version_and_each_file_change(tmp_path: Path) -> None:
    game = _game(tmp_path)
    before = (game / "project.godot").read_bytes()
    plan = resolve_version(game / "project.godot", "patch", None)
    lines = plan_version_edits(plan, game).lines
    assert lines[0] == "DRY-RUN: version 1.2.3 -> 1.2.4"
    assert any(
        line.startswith('DRY-RUN: set application/config/version="1.2.4" in ') for line in lines
    )
    assert any("version/code=5 in" in line for line in lines)
    assert any('Windows Desktop application/file_version="1.2.4.0"' in line for line in lines)
    assert (game / "project.godot").read_bytes() == before


def test_a_dry_run_plan_for_no_flag_has_no_lines(tmp_path: Path) -> None:
    game = _game(tmp_path)
    plan = resolve_version(game / "project.godot", None, None)
    assert plan_version_edits(plan, game).lines == ()


def test_write_leaves_no_temporary_file_behind(tmp_path: Path) -> None:
    game = _game(tmp_path)
    write_version(resolve_version(game / "project.godot", None, "1.3.0"), game)
    assert sorted(path.name for path in game.iterdir()) == [
        "export_presets.cfg",
        "project.godot",
    ]
