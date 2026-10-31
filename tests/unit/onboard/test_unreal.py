"""Unreal setup: uproject plugins, MCP auto-start ini, and the pinned VibeUE clone (#7 FR5, AC2,
AC9)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nmg_game_dev.onboard.errors import OnboardError
from nmg_game_dev.onboard.unreal import (
    DEFAULT_PORT,
    VIBEUE_COMMIT,
    enable_plugins,
    ensure_mcp_autostart,
    ensure_vibeue,
)
from tests.onboard_fakes import FakeRunner


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


def test_vibeue_is_cloned_at_the_pinned_tag(tmp_path: Path) -> None:
    runner = FakeRunner()
    result = ensure_vibeue(tmp_path, run=runner, refresh=False)
    assert result.status == "installed"
    assert runner.calls[0][:2] == ["git", "clone"]
    assert runner.calls[0][-1] == str(tmp_path / "Plugins" / "VibeUE")
    assert ensure_vibeue(tmp_path, run=FakeRunner(), refresh=False).status == "unchanged"


def test_vibeue_wrong_head_is_drift_then_refreshed(tmp_path: Path) -> None:
    ensure_vibeue(tmp_path, run=FakeRunner(), refresh=False)
    wrong = FakeRunner(head="1" * 40)
    assert ensure_vibeue(tmp_path, run=wrong, refresh=False).status == "drift"
    fix = FakeRunner(head="1" * 40)
    assert ensure_vibeue(tmp_path, run=fix, refresh=True).status == "refreshed"
    assert [
        "git",
        "-C",
        str(tmp_path / "Plugins" / "VibeUE"),
        "checkout",
        "--force",
        VIBEUE_COMMIT,
    ] in fix.calls


def test_vibeue_clone_failure_raises(tmp_path: Path) -> None:
    with pytest.raises(OnboardError) as caught:
        ensure_vibeue(tmp_path, run=FakeRunner(fail="clone"), refresh=False)
    assert caught.value.code == "onboard.vibeue_clone_failed"
