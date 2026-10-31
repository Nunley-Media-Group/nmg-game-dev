"""Unreal setup: uproject plugins, MCP auto-start ini, and the VibeUE clone tracking branch 5-8
(#7 FR5, AC2, AC9; #104 AC1-AC3)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nmg_game_dev.onboard.errors import OnboardError
from nmg_game_dev.onboard.unreal import (
    DEFAULT_PORT,
    VIBEUE_URL,
    enable_plugins,
    ensure_mcp_autostart,
    ensure_vibeue,
)
from tests.onboard_fakes import BRANCH_HEAD, FakeRunner

OLD_PIN = "bc7bc45c1e2025123778560f45c15d1f8e1be41d"


def test_enable_plugins_keeps_other_entries_and_fields(tmp_path: Path) -> None:
    uproject = tmp_path / "Game.uproject"
    uproject.write_text(
        json.dumps(
            {
                "FileVersion": 3,
                "Plugins": [
                    {"Name": "Other", "Enabled": True},
                    {"Name": "VibeUE", "Enabled": False},
                ],
            }
        )
    )
    result = enable_plugins("uproject_plugins", uproject)
    assert result.status == "installed"
    data = json.loads(uproject.read_text())
    assert data["FileVersion"] == 3
    assert {e["Name"]: e["Enabled"] for e in data["Plugins"]} == {
        "Other": True,
        "VibeUE": True,
        "ModelContextProtocol": True,
        "EditorToolset": True,
        "nmg-game-dev": True,
    }
    assert enable_plugins("uproject_plugins", uproject).status == "unchanged"


def test_mcp_autostart_creates_section_with_port(tmp_path: Path) -> None:
    ini = tmp_path / "Config" / "DefaultEditorPerProjectUserSettings.ini"
    assert ensure_mcp_autostart("mcp_autostart_ini", ini).status == "installed"
    text = ini.read_text()
    assert "[/Script/ModelContextProtocolEngine.ModelContextProtocolSettings]" in text
    assert "bAutoStartServer=True" in text
    assert f"ServerPortNumber={DEFAULT_PORT}" in text
    assert ensure_mcp_autostart("mcp_autostart_ini", ini).status == "unchanged"


def test_mcp_autostart_keeps_an_existing_port_and_other_sections(tmp_path: Path) -> None:
    ini = tmp_path / "settings.ini"
    ini.write_text(
        "[Other]\nKeep=1\n\n"
        "[/Script/ModelContextProtocolEngine.ModelContextProtocolSettings]\n"
        "bAutoStartServer=False\nServerPortNumber=9001\n\n"
        "[More]\nAlso=2\n"
    )
    ensure_mcp_autostart("mcp_autostart_ini", ini)
    text = ini.read_text()
    assert "bAutoStartServer=True" in text and "bAutoStartServer=False" not in text
    assert text.count("ServerPortNumber=") == 1 and "ServerPortNumber=9001" in text
    assert "[Other]\nKeep=1" in text and "[More]\nAlso=2" in text


def test_vibeue_is_cloned_from_branch_5_8(tmp_path: Path) -> None:
    """AC1: a fresh install clones branch 5-8 at depth 1 and reports the cloned commit."""
    runner = FakeRunner()
    result = ensure_vibeue(tmp_path, run=runner, refresh=False)
    assert result.status == "installed"
    assert result.detail == f"cloned 5-8 ({BRANCH_HEAD[:12]}) into Plugins/VibeUE"
    assert runner.calls[0] == [
        "git",
        "clone",
        "--depth",
        "1",
        "--branch",
        "5-8",
        VIBEUE_URL,
        str(tmp_path / "Plugins" / "VibeUE"),
    ]
    assert ensure_vibeue(tmp_path, run=FakeRunner(), refresh=False).status == "unchanged"


def test_vibeue_old_pin_is_drift_naming_both_commits_then_refresh_moves_to_branch_head(
    tmp_path: Path,
) -> None:
    """AC2: HEAD at the old pin is drift against the 5-8 head; --refresh fetches 5-8 and moves."""
    ensure_vibeue(tmp_path, run=FakeRunner(), refresh=False)
    drifted = FakeRunner(head=OLD_PIN)
    result = ensure_vibeue(tmp_path, run=drifted, refresh=False)
    assert result.status == "drift"
    assert OLD_PIN[:12] in result.detail and BRANCH_HEAD[:12] in result.detail
    assert not any(call[:2] == ["git", "clone"] for call in drifted.calls)

    target = str(tmp_path / "Plugins" / "VibeUE")
    fix = FakeRunner(head=OLD_PIN)
    assert ensure_vibeue(tmp_path, run=fix, refresh=True).status == "refreshed"
    assert ["git", "-C", target, "fetch", "--depth", "1", "origin", "5-8"] in fix.calls
    assert ["git", "-C", target, "checkout", "--force", "FETCH_HEAD"] in fix.calls


def test_vibeue_at_current_branch_head_is_unchanged(tmp_path: Path) -> None:
    """AC3: a checkout at the origin 5-8 head is left alone, with no fetch or checkout."""
    ensure_vibeue(tmp_path, run=FakeRunner(), refresh=False)
    runner = FakeRunner()
    result = ensure_vibeue(tmp_path, run=runner, refresh=True)
    assert result.status == "unchanged"
    assert not any("fetch" in call or "checkout" in call for call in runner.calls)


def test_vibeue_unreachable_origin_is_unchanged_not_drift(tmp_path: Path) -> None:
    """AC3: when ls-remote fails, the 5-8 head could not be checked, so the checkout is kept."""
    ensure_vibeue(tmp_path, run=FakeRunner(), refresh=False)
    runner = FakeRunner(head=OLD_PIN, fail="ls-remote")
    result = ensure_vibeue(tmp_path, run=runner, refresh=True)
    assert result.status == "unchanged"
    assert "could not check the 5-8 head" in result.detail
    assert OLD_PIN[:12] in result.detail
    assert not any("fetch" in call or "checkout" in call for call in runner.calls)


def test_vibeue_ls_remote_asks_for_branch_5_8(tmp_path: Path) -> None:
    ensure_vibeue(tmp_path, run=FakeRunner(), refresh=False)
    runner = FakeRunner()
    ensure_vibeue(tmp_path, run=runner, refresh=False)
    assert ["git", "ls-remote", VIBEUE_URL, "refs/heads/5-8"] in runner.calls


def test_vibeue_clone_failure_raises(tmp_path: Path) -> None:
    with pytest.raises(OnboardError) as caught:
        ensure_vibeue(tmp_path, run=FakeRunner(fail="clone"), refresh=False)
    assert caught.value.code == "onboard.vibeue_clone_failed"
