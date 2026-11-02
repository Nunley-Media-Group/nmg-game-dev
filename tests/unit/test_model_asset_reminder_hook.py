"""Unit tests for the #130 PreToolUse reminder: matcher, first-call output, state dir, fail-open.

The hook is a stdlib script under ``hooks/`` rather than a package, so it is loaded by path. The
end-to-end subprocess runs are in ``tests/bdd/test_model_asset_routing_bdd.py``.
"""

from __future__ import annotations

import importlib.util
import json
import re
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests.ship_fakes import REPO_ROOT

HOOK_PATH = REPO_ROOT / "hooks" / "model_asset_reminder.py"
HOOKS_JSON = REPO_ROOT / "hooks" / "hooks.json"
STATE_ENV = "NMG_GAME_DEV_HOOK_STATE_DIR"


def _load_hook() -> ModuleType:
    spec = importlib.util.spec_from_file_location("model_asset_reminder", HOOK_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hook = _load_hook()


def _hooks_config() -> Any:
    return json.loads(HOOKS_JSON.read_text(encoding="utf-8"))


def _matcher() -> re.Pattern[str]:
    (entry,) = _hooks_config()["hooks"]["PreToolUse"]
    return re.compile(entry["matcher"])


@pytest.mark.parametrize(
    "tool_name",
    [
        "mcp__blender__execute_blender_code",
        "mcp__plugin_nmg-game-dev_blender__execute_blender_code",
    ],
)
def test_matcher_covers_the_scoped_and_unscoped_execute_blender_code(tool_name: str) -> None:
    assert _matcher().search(tool_name) is not None


@pytest.mark.parametrize(
    "tool_name",
    [
        "mcp__blender__get_scene_info",
        "mcp__blender__look",
        "mcp__blender__execute_blender_code_v2",
        "mcp__unreal__execute_python_code",
    ],
)
def test_matcher_leaves_other_tools_alone(tool_name: str) -> None:
    assert _matcher().search(tool_name) is None


def test_hooks_json_registers_one_command_hook_on_pretooluse() -> None:
    config = _hooks_config()
    assert set(config["hooks"]) == {"PreToolUse"}
    (command_hook,) = config["hooks"]["PreToolUse"][0]["hooks"]
    assert command_hook["type"] == "command"
    assert command_hook["command"] == (
        'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/model_asset_reminder.py"'
    )


def test_first_call_prints_routing_context_and_no_decision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(STATE_ENV, str(tmp_path / "state"))
    payload = json.loads(hook.main(json.dumps({"session_id": "s-1"})))
    specific = payload["hookSpecificOutput"]
    assert specific["hookEventName"] == "PreToolUse"
    assert "/model-asset" in specific["additionalContext"]
    assert "/finalize-asset" in specific["additionalContext"]
    assert "permissionDecision" not in specific
    assert "decision" not in payload


def test_repeat_call_for_the_same_session_is_silent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(STATE_ENV, str(tmp_path / "state"))
    event = json.dumps({"session_id": "s-1"})
    assert hook.main(event) != ""
    assert hook.main(event) == ""


def test_marker_name_is_a_hash_inside_the_state_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state"
    monkeypatch.setenv(STATE_ENV, str(state))
    hook.main(json.dumps({"session_id": "../escape/s-1"}))
    markers = list(state.iterdir())
    assert len(markers) == 1
    assert markers[0].parent == state
    assert len(markers[0].name) == 64


def test_state_dir_honors_the_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(STATE_ENV, str(tmp_path / "override"))
    assert hook.state_dir() == tmp_path / "override"


def test_state_dir_defaults_under_the_temp_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(STATE_ENV, raising=False)
    expected = Path(tempfile.gettempdir()) / "nmg-game-dev-hooks" / "model-asset-reminder"
    assert hook.state_dir() == expected


def test_unwritable_state_dir_fails_open(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    blocked = tmp_path / "blocked"
    blocked.write_text("a regular file, not a directory", encoding="utf-8")
    monkeypatch.setenv(STATE_ENV, str(blocked))
    assert hook.main(json.dumps({"session_id": "s-1"})) == ""


@pytest.mark.parametrize(
    "stdin_text",
    [
        "not json",
        "",
        "[]",
        json.dumps({}),
        json.dumps({"session_id": ""}),
        json.dumps({"session_id": 42}),
    ],
)
def test_invalid_or_sessionless_input_is_silent(
    stdin_text: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(STATE_ENV, str(tmp_path / "state"))
    assert hook.main(stdin_text) == ""
    assert not (tmp_path / "state").exists()


def test_os_error_while_reading_state_fails_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken_state_dir() -> Path:
        raise PermissionError("denied")

    monkeypatch.setattr(hook, "state_dir", broken_state_dir)
    assert hook.main(json.dumps({"session_id": "s-1"})) == ""
