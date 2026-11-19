"""Unit tests for the #242 ElevenLabs audio guard: matcher, deny, reminder, and fail-open.

The hook is a stdlib script under ``hooks/`` rather than a package, so it is loaded by path. The
subprocess runs that drive it end to end are in ``tests/bdd/test_generate_audio_bdd.py``.
"""

from __future__ import annotations

import importlib.util
import io
import json
import re
import runpy
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests.ship_fakes import REPO_ROOT

HOOK_PATH = REPO_ROOT / "hooks" / "generate_audio_guard.py"
HOOKS_JSON = REPO_ROOT / "hooks" / "hooks.json"
STATE_ENV = "NMG_GAME_DEV_HOOK_STATE_DIR"
SPEECH = "mcp__elevenlabs__creative_generate_speech"
IN_FLOW = "mcp__elevenlabs__creative_generate_in_flow"
MISSING = object()


def _load_hook() -> ModuleType:
    spec = importlib.util.spec_from_file_location("generate_audio_guard", HOOK_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hook = _load_hook()


def _hooks_config() -> Any:
    return json.loads(HOOKS_JSON.read_text(encoding="utf-8"))


def _guard_entry() -> dict[str, Any]:
    entries: list[Any] = _hooks_config()["hooks"]["PreToolUse"]
    (entry,) = [
        candidate
        for candidate in entries
        if any("generate_audio_guard.py" in item["command"] for item in candidate["hooks"])
    ]
    guard: dict[str, Any] = entry
    return guard


def _matcher() -> re.Pattern[str]:
    return re.compile(_guard_entry()["matcher"])


def _input(count: Any = 1, node_type: str | None = None) -> dict[str, Any]:
    """Build a tool_input; ``count`` of MISSING omits generations_count entirely."""
    tool_input: dict[str, Any] = {}
    if node_type is not None:
        tool_input["node_type"] = node_type
    if count is not MISSING:
        tool_input["generations_count"] = count
    return tool_input


def _event(tool_name: str, tool_input: Any, session_id: str | None = "s-1") -> str:
    event: dict[str, Any] = {"tool_name": tool_name, "tool_input": tool_input}
    if session_id is not None:
        event["session_id"] = session_id
    return json.dumps(event)


# --- AC1 / FR2: the matcher and the command entry ---


@pytest.mark.parametrize(
    "tool_name",
    [
        IN_FLOW,
        SPEECH,
        "mcp__claude_ai_ElevenLabs__creative_generate_speech",
    ],
)
def test_matcher_covers_the_elevenlabs_audio_generation_tools(tool_name: str) -> None:
    assert _matcher().search(tool_name) is not None


@pytest.mark.parametrize(
    "tool_name",
    [
        "mcp__elevenlabs__creative_generate_image",
        "mcp__elevenlabs__creative_list_voices",
        "mcp__blender__execute_blender_code",
    ],
)
def test_matcher_leaves_other_tools_alone(tool_name: str) -> None:
    assert _matcher().search(tool_name) is None


def test_guard_entry_runs_the_script_as_a_command_hook_with_a_10_second_timeout() -> None:
    (command_hook,) = _guard_entry()["hooks"]
    assert command_hook["type"] == "command"
    assert command_hook["command"] == (
        'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/generate_audio_guard.py"'
    )
    assert command_hook["timeout"] == 10


# --- AC2 / FR2: multi-take or unclear counts are denied ---


@pytest.mark.parametrize(
    ("tool_name", "node_type"),
    [
        (IN_FLOW, "sfx"),
        (IN_FLOW, "music"),
        (IN_FLOW, "tts"),
        (SPEECH, None),
    ],
)
@pytest.mark.parametrize("count", [MISSING, 0, 2, "1", 1.5, True])
def test_multi_take_or_unclear_count_is_denied(
    tool_name: str,
    node_type: str | None,
    count: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(STATE_ENV, str(tmp_path / "state"))
    payload = json.loads(hook.main(_event(tool_name, _input(count, node_type))))
    specific = payload["hookSpecificOutput"]
    assert specific["hookEventName"] == "PreToolUse"
    assert specific["permissionDecision"] == "deny"
    reason = specific["permissionDecisionReason"]
    assert "one take at a time" in reason
    assert "generations_count: 1" in reason
    assert "/generate-audio" in reason


def test_deny_writes_no_marker_and_leaves_the_reminder_for_a_later_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state"
    monkeypatch.setenv(STATE_ENV, str(state))
    denied = json.loads(hook.main(_event(SPEECH, _input(3))))
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert not state.exists()
    allowed = json.loads(hook.main(_event(SPEECH, _input(1))))
    assert "/generate-audio" in allowed["hookSpecificOutput"]["additionalContext"]


# --- AC1 / AC3 / FR3: single-take calls get the reminder once per session ---


@pytest.mark.parametrize(
    ("tool_name", "node_type"),
    [
        (IN_FLOW, "sfx"),
        (IN_FLOW, "music"),
        (IN_FLOW, "tts"),
        (SPEECH, None),
    ],
)
def test_first_single_take_call_gets_the_reminder_and_no_decision(
    tool_name: str, node_type: str | None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(STATE_ENV, str(tmp_path / "state"))
    payload = json.loads(hook.main(_event(tool_name, _input(1, node_type))))
    specific = payload["hookSpecificOutput"]
    assert specific["hookEventName"] == "PreToolUse"
    assert "/generate-audio" in specific["additionalContext"]
    assert "nmg-game-dev:generate-audio" in specific["additionalContext"]
    assert "permissionDecision" not in specific
    assert "decision" not in payload


def test_repeat_single_take_call_for_the_same_session_is_silent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(STATE_ENV, str(tmp_path / "state"))
    event = _event(SPEECH, _input(1), session_id="s-1")
    assert hook.main(event) != ""
    assert hook.main(event) == ""


def test_a_second_session_gets_the_reminder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(STATE_ENV, str(tmp_path / "state"))
    assert hook.main(_event(SPEECH, _input(1), session_id="s-1")) != ""
    assert hook.main(_event(SPEECH, _input(1), session_id="s-2")) != ""


def test_marker_is_a_hash_under_the_generate_audio_subdirectory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state"
    monkeypatch.setenv(STATE_ENV, str(state))
    hook.main(_event(SPEECH, _input(1), session_id="../escape/s-1"))
    subdir = state / "generate-audio-reminder"
    markers = list(subdir.iterdir())
    assert len(markers) == 1
    assert markers[0].parent == subdir
    assert len(markers[0].name) == 64


def test_allowed_call_without_a_session_id_is_silent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state"
    monkeypatch.setenv(STATE_ENV, str(state))
    assert hook.main(_event(SPEECH, _input(1), session_id=None)) == ""
    assert not state.exists()


def test_state_dir_honors_the_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(STATE_ENV, str(tmp_path / "override"))
    assert hook.state_dir() == tmp_path / "override" / "generate-audio-reminder"


def test_state_dir_defaults_under_the_temp_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(STATE_ENV, raising=False)
    expected = Path(tempfile.gettempdir()) / "nmg-game-dev-hooks" / "generate-audio-reminder"
    assert hook.state_dir() == expected


# --- AC7 / FR7: other ElevenLabs generation is left alone ---


@pytest.mark.parametrize("count", [MISSING, 1, 4])
@pytest.mark.parametrize("node_type", ["image", "video"])
def test_non_audio_in_flow_generation_is_left_alone(
    node_type: str, count: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state"
    monkeypatch.setenv(STATE_ENV, str(state))
    assert hook.main(_event(IN_FLOW, _input(count, node_type))) == ""
    assert not state.exists()


def test_non_string_node_type_is_not_audio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = tmp_path / "state"
    monkeypatch.setenv(STATE_ENV, str(state))
    assert hook.main(_event(IN_FLOW, {"node_type": ["sfx"], "generations_count": 1})) == ""
    assert not state.exists()


def test_other_elevenlabs_tool_names_are_left_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state"
    monkeypatch.setenv(STATE_ENV, str(state))
    event = _event("mcp__elevenlabs__creative_generate_image", _input(4))
    assert hook.main(event) == ""
    assert not state.exists()


# --- AC4 / FR4: unreadable input and errors fail open ---


@pytest.mark.parametrize(
    "stdin_text",
    [
        "not json",
        "",
        "[]",
        json.dumps({}),
        json.dumps({"tool_input": "x"}),
        json.dumps({"tool_name": SPEECH, "tool_input": "x"}),
        json.dumps({"tool_name": SPEECH}),
    ],
)
def test_invalid_or_unexpected_input_fails_open(
    stdin_text: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state"
    monkeypatch.setenv(STATE_ENV, str(state))
    assert hook.main(stdin_text) == ""
    assert not state.exists()


def test_unwritable_state_dir_fails_open(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    blocked = tmp_path / "blocked"
    blocked.write_text("a regular file, not a directory", encoding="utf-8")
    monkeypatch.setenv(STATE_ENV, str(blocked))
    assert hook.main(_event(SPEECH, _input(1))) == ""


def test_os_error_while_reading_state_fails_open(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken_state_dir() -> Path:
        raise PermissionError("denied")

    monkeypatch.setattr(hook, "state_dir", broken_state_dir)
    assert hook.main(_event(SPEECH, _input(1))) == ""


def test_unexpected_exception_exits_zero_with_no_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom(_text: str) -> Any:
        raise RuntimeError("unexpected")

    monkeypatch.setattr(json, "loads", boom)
    monkeypatch.setattr(sys, "stdin", io.StringIO(_event(SPEECH, _input(1))))
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(str(HOOK_PATH), run_name="__main__")
    assert exit_info.value.code == 0
    assert capsys.readouterr().out == ""
