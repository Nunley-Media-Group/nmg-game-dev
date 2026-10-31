"""The Blender add-on link: created, unchanged, drift, and refresh (#7 FR6, AC3, AC8, AC9)."""

from __future__ import annotations

import os
from pathlib import Path

from nmg_game_dev.onboard.blender import link_addon


def test_link_is_created_then_unchanged(tmp_path: Path) -> None:
    framework = tmp_path / "framework"
    source = framework / "plugins" / "nmg-game-dev-blender-addon"
    source.mkdir(parents=True)
    extensions = tmp_path / "ext" / "user_default"

    assert link_addon(framework, extensions, refresh=False).status == "installed"
    link = extensions / "nmg_game_dev_blender_addon"
    assert Path(os.readlink(link)) == source
    assert link_addon(framework, extensions, refresh=False).status == "unchanged"


def test_wrong_target_is_drift_and_refresh_relinks(tmp_path: Path) -> None:
    framework = tmp_path / "framework"
    (framework / "plugins" / "nmg-game-dev-blender-addon").mkdir(parents=True)
    other = tmp_path / "elsewhere"
    other.mkdir()
    extensions = tmp_path / "ext"
    extensions.mkdir()
    link = extensions / "nmg_game_dev_blender_addon"
    link.symlink_to(other, target_is_directory=True)

    drift = link_addon(framework, extensions, refresh=False)
    assert drift.status == "drift" and drift.remediation == "re-run with --refresh"
    assert os.readlink(link) == str(other)

    refreshed = link_addon(framework, extensions, refresh=True)
    assert refreshed.status == "refreshed"
    assert os.readlink(link) == str(framework / "plugins" / "nmg-game-dev-blender-addon")


def test_real_directory_at_link_path_is_drift_until_refresh(tmp_path: Path) -> None:
    framework = tmp_path / "framework"
    (framework / "plugins" / "nmg-game-dev-blender-addon").mkdir(parents=True)
    extensions = tmp_path / "ext"
    (extensions / "nmg_game_dev_blender_addon").mkdir(parents=True)

    assert link_addon(framework, extensions, refresh=False).status == "drift"
    assert link_addon(framework, extensions, refresh=True).status == "refreshed"
    assert (extensions / "nmg_game_dev_blender_addon").is_symlink()
