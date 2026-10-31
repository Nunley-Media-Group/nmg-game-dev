"""Settings merges keep unrelated keys and add each framework entry once (#7 FR3, FR7, AC1, AC4,
AC8)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from nmg_game_dev.onboard.settings import merge_env, merge_session_hooks

TEMPLATE: dict[str, Any] = {
    "hooks": {
        "SessionStart": [
            {
                "matcher": "startup",
                "hooks": [
                    {"type": "command", "command": 'bash "$CLAUDE_PROJECT_DIR/scripts/a.sh"'},
                    {"type": "command", "command": 'bash "$CLAUDE_PROJECT_DIR/scripts/b.sh"'},
                ],
            }
        ]
    }
}


def _write(path: Path, data: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")
    return path


def test_hooks_are_added_and_unrelated_keys_kept(tmp_path: Path) -> None:
    template = _write(tmp_path / "template.json", TEMPLATE)
    settings = _write(tmp_path / ".claude" / "settings.json", {"model": "opus", "env": {"X": "1"}})

    result = merge_session_hooks("settings_hooks", settings, template)

    assert result.status == "installed"
    data = json.loads(settings.read_text())
    assert data["model"] == "opus"
    assert data["env"] == {"X": "1"}
    commands = [h["command"] for g in data["hooks"]["SessionStart"] for h in g["hooks"]]
    assert commands == [h["command"] for h in TEMPLATE["hooks"]["SessionStart"][0]["hooks"]]


def test_hooks_are_not_duplicated_on_rerun(tmp_path: Path) -> None:
    template = _write(tmp_path / "template.json", TEMPLATE)
    settings = _write(tmp_path / "settings.json", {})
    merge_session_hooks("settings_hooks", settings, template)
    once = settings.read_text()

    result = merge_session_hooks("settings_hooks", settings, template)

    assert result.status == "unchanged"
    assert settings.read_text() == once


def test_existing_hook_is_kept_and_only_missing_one_added(tmp_path: Path) -> None:
    template = _write(tmp_path / "template.json", TEMPLATE)
    existing = {
        "hooks": {
            "SessionStart": [
                {
                    "matcher": "other",
                    "hooks": [
                        {"type": "command", "command": 'bash "$CLAUDE_PROJECT_DIR/scripts/a.sh"'}
                    ],
                }
            ]
        }
    }
    settings = _write(tmp_path / "settings.json", existing)

    merge_session_hooks("settings_hooks", settings, template)

    data = json.loads(settings.read_text())
    commands = [h["command"] for g in data["hooks"]["SessionStart"] for h in g["hooks"]]
    assert commands == [
        'bash "$CLAUDE_PROJECT_DIR/scripts/a.sh"',
        'bash "$CLAUDE_PROJECT_DIR/scripts/b.sh"',
    ]
    assert data["hooks"]["SessionStart"][0]["matcher"] == "other"


def test_merge_env_sets_values_and_keeps_others(tmp_path: Path) -> None:
    local = _write(tmp_path / ".claude" / "settings.local.json", {"env": {"KEEP": "yes"}})
    values = {"TEXTURE_GEN_MODELS_DIR": "/vol/models", "HF_HOME": "/vol/models/hf-cache"}

    first = merge_env("texture_env", local, values)
    second = merge_env("texture_env", local, values)

    assert first.status == "installed"
    assert second.status == "unchanged"
    env = json.loads(local.read_text())["env"]
    assert env == {"KEEP": "yes", **values}
    assert not [key for key in env if key.endswith("_API_KEY")]


UNREAL_COMMAND = 'bash "$CLAUDE_PROJECT_DIR/scripts/start-unreal-mcp.sh"'
BLENDER_COMMAND = 'bash "$CLAUDE_PROJECT_DIR/scripts/start-blender-mcp.sh"'
REAL_TEMPLATE = (
    Path(__file__).resolve().parents[3] / "templates" / "consumer" / ".claude" / "settings.json"
)


def _unreal_template(timeout: int | None) -> dict[str, Any]:
    hook: dict[str, Any] = {"type": "command", "command": UNREAL_COMMAND}
    if timeout is not None:
        hook["timeout"] = timeout
    return {"hooks": {"SessionStart": [{"matcher": "startup", "hooks": [hook]}]}}


def _unreal_timeout(settings: Path) -> object:
    groups = json.loads(settings.read_text())["hooks"]["SessionStart"]
    hook = next(h for g in groups for h in g["hooks"] if h["command"] == UNREAL_COMMAND)
    return hook.get("timeout")


def test_template_gives_the_unreal_hook_900_seconds_and_leaves_blender_alone() -> None:
    hooks = json.loads(REAL_TEMPLATE.read_text())["hooks"]["SessionStart"][0]["hooks"]

    unreal = [h for h in hooks if "start-unreal-mcp.sh" in h["command"]]
    blender = [h for h in hooks if "start-blender-mcp.sh" in h["command"]]

    assert [h.get("timeout") for h in unreal] == [900]
    assert [h.get("timeout") for h in blender] == [None]


def test_missing_hook_is_added_with_its_timeout(tmp_path: Path) -> None:
    template = _write(tmp_path / "template.json", _unreal_template(900))
    settings = _write(tmp_path / "settings.json", {})

    result = merge_session_hooks("settings_hooks", settings, template)

    assert result.status == "installed"
    assert _unreal_timeout(settings) == 900


def test_missing_timeout_is_raised_and_reported_refreshed(tmp_path: Path) -> None:
    template = _write(tmp_path / "template.json", _unreal_template(900))
    blender = {"type": "command", "command": BLENDER_COMMAND, "timeout": 5}
    settings = _write(
        tmp_path / "settings.json",
        {
            "model": "opus",
            "hooks": {
                "SessionStart": [
                    {
                        "matcher": "startup",
                        "hooks": [blender, {"type": "command", "command": UNREAL_COMMAND}],
                    }
                ]
            },
        },
    )

    result = merge_session_hooks("settings_hooks", settings, template)

    assert result.status == "refreshed"
    data = json.loads(settings.read_text())
    assert data["model"] == "opus"
    assert data["hooks"]["SessionStart"] == [
        {
            "matcher": "startup",
            "hooks": [blender, {"type": "command", "command": UNREAL_COMMAND, "timeout": 900}],
        }
    ]


def test_lower_timeout_is_raised_to_the_template_value(tmp_path: Path) -> None:
    template = _write(tmp_path / "template.json", _unreal_template(900))
    settings = _write(
        tmp_path / "settings.json",
        {
            "hooks": {
                "SessionStart": [
                    {"hooks": [{"type": "command", "command": UNREAL_COMMAND, "timeout": 120}]}
                ]
            }
        },
    )

    result = merge_session_hooks("settings_hooks", settings, template)

    assert result.status == "refreshed"
    assert _unreal_timeout(settings) == 900


@pytest.mark.parametrize("timeout", [900, 1800])
def test_equal_or_higher_timeout_is_unchanged(tmp_path: Path, timeout: int) -> None:
    template = _write(tmp_path / "template.json", _unreal_template(900))
    settings = _write(
        tmp_path / "settings.json",
        {
            "hooks": {
                "SessionStart": [
                    {"hooks": [{"type": "command", "command": UNREAL_COMMAND, "timeout": timeout}]}
                ]
            }
        },
    )
    before = settings.read_text()

    result = merge_session_hooks("settings_hooks", settings, template)

    assert result.status == "unchanged"
    assert settings.read_text() == before
