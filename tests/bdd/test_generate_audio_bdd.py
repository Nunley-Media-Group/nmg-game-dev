# ruff: noqa: E501  -- step decorators repeat the Gherkin text verbatim, so they run long.
"""pytest-bdd bindings for generate_audio.feature: SCN001-SCN007 of #242.

The guard hook runs as a real subprocess (``sys.executable hooks/generate_audio_guard.py``) with
``NMG_GAME_DEV_HOOK_STATE_DIR`` under ``tmp_path``, so nothing touches the real temp directory. The
skill scenarios read ``skills/generate-audio/SKILL.md``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenario, then, when

FEATURE = "generate_audio.feature"
REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL = REPO_ROOT / "skills" / "generate-audio" / "SKILL.md"
HOOK = REPO_ROOT / "hooks" / "generate_audio_guard.py"
MARKER_SUBDIR = "generate-audio-reminder"


@pytest.fixture
def state(tmp_path: Path) -> dict[str, Any]:
    return {"tmp": tmp_path, "state_dir": tmp_path / "hook-state", "results": [], "text": ""}


def _run_hook(stdin_text: str, state_dir: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, NMG_GAME_DEV_HOOK_STATE_DIR=str(state_dir))
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=stdin_text,
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=30,
    )


def _audio_event(session_id: str, tool: str, tool_input: dict[str, Any]) -> str:
    return json.dumps(
        {
            "session_id": session_id,
            "hook_event_name": "PreToolUse",
            "tool_name": f"mcp__elevenlabs__{tool}",
            "tool_input": tool_input,
        }
    )


def _last(state: dict[str, Any]) -> subprocess.CompletedProcess[str]:
    results: list[subprocess.CompletedProcess[str]] = state["results"]
    return results[-1]


def _flow(text: str) -> str:
    start = text.index("## Flow")
    end = text.index("## Failure modes and remediation")
    return text[start:end]


def _music_step(text: str) -> str:
    start = text.index("**Music: instrumental by default.**")
    end = text.index("**One take.**")
    return text[start:end]


# --- SCN001: the first single-take call in a session gets the routing reminder ---


@given("an empty hook state directory")
def _empty_state_dir(state: dict[str, Any]) -> None:
    state["state_dir"].mkdir(parents=True, exist_ok=True)


@given(parsers.parse('the audio guard hook has already reminded session "{session}"'))
def _already_reminded(state: dict[str, Any], session: str) -> None:
    state["state_dir"].mkdir(parents=True, exist_ok=True)
    first = _run_hook(
        _audio_event(
            session,
            "creative_generate_in_flow",
            {"node_type": "music", "generations_count": 1},
        ),
        state["state_dir"],
    )
    assert first.returncode == 0 and first.stdout.strip(), "the first single-take call must remind"


@when(
    parsers.re(
        r'the audio guard hook receives a (?P<tool>creative_generate_in_flow|creative_generate_speech) event with (?:node_type "(?P<node_type>[a-z]+)" and )?generations_count (?P<count>\d+) for session "(?P<session>[^"]+)"'
    )
)
def _audio_event_step(
    state: dict[str, Any],
    tool: str,
    count: str,
    session: str,
    node_type: str | None = None,
) -> None:
    tool_input: dict[str, Any] = {"generations_count": int(count)}
    if node_type is not None:
        tool_input["node_type"] = node_type
    state["results"].append(_run_hook(_audio_event(session, tool, tool_input), state["state_dir"]))


@when(parsers.parse('the audio guard hook receives "{stdin_text}" on stdin'))
def _raw_stdin(state: dict[str, Any], stdin_text: str) -> None:
    state["results"].append(_run_hook(stdin_text, state["state_dir"]))


@then("it exits 0")
def _exits_zero(state: dict[str, Any]) -> None:
    assert _last(state).returncode == 0, _last(state).stderr


@then("it exits 0 with empty stdout")
def _exits_zero_silent(state: dict[str, Any]) -> None:
    result = _last(state)
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


@then("its additionalContext names /generate-audio and nmg-game-dev:generate-audio")
def _context_names_skill(state: dict[str, Any]) -> None:
    specific = json.loads(_last(state).stdout)["hookSpecificOutput"]
    assert specific["hookEventName"] == "PreToolUse"
    context = specific["additionalContext"]
    assert "/generate-audio" in context
    assert "nmg-game-dev:generate-audio" in context


@then("it makes no permission decision")
def _no_decision(state: dict[str, Any]) -> None:
    payload = json.loads(_last(state).stdout)
    assert "permissionDecision" not in payload["hookSpecificOutput"]
    assert "decision" not in payload


# --- SCN002: a multi-take call is denied ---


@then('its permissionDecision is "deny"')
def _denied(state: dict[str, Any]) -> None:
    specific = json.loads(_last(state).stdout)["hookSpecificOutput"]
    assert specific["permissionDecision"] == "deny"


@then("its permissionDecisionReason states generations_count: 1 and names /generate-audio")
def _deny_reason(state: dict[str, Any]) -> None:
    reason = json.loads(_last(state).stdout)["hookSpecificOutput"]["permissionDecisionReason"]
    assert "generations_count: 1" in reason
    assert "/generate-audio" in reason


# --- SCN004 / SCN007: silence, and no marker for non-audio or unreadable input ---


@then("no reminder marker is written")
def _no_marker(state: dict[str, Any]) -> None:
    marker_dir = state["state_dir"] / MARKER_SUBDIR
    assert not marker_dir.exists() or not any(marker_dir.iterdir())


# --- SCN005 / SCN006: the skill's music and prompt rules ---


@given("the body of skills/generate-audio/SKILL.md")
def _skill_body(state: dict[str, Any]) -> None:
    state["text"] = SKILL.read_text(encoding="utf-8")


@when("its music instructions are read")
def _read_music(state: dict[str, Any]) -> None:
    state["section"] = _music_step(state["text"])


@when("its prompt instructions are read")
def _read_prompt(state: dict[str, Any]) -> None:
    state["section"] = _flow(state["text"])


@then(
    "they direct setting the instrumental option read from creative_get_model_schema unless the user asked for vocals and supplied lyrics"
)
def _music_direction(state: dict[str, Any]) -> None:
    section = state["section"]
    assert "creative_get_model_schema" in section
    assert "instrumental" in section
    assert "unless the developer explicitly asked for vocals and supplied lyrics" in section


@then("they direct using only the user's lyrics when vocals are requested")
def _lyrics_direction(state: dict[str, Any]) -> None:
    assert "only the developer's lyrics" in state["section"]


@then(
    "they direct reading creative_get_model_guide and the design-doc entry such as docs/design/systems/audio.md"
)
def _prompt_sources(state: dict[str, Any]) -> None:
    section = state["section"]
    assert "creative_get_model_guide" in section
    assert "docs/design/systems/audio.md" in section


@then(
    "they forbid adding any genre, instrument, mood, or vocal element absent from the request and design doc"
)
def _prompt_forbids(state: dict[str, Any]) -> None:
    assert "Add no genre, instrument, mood, or vocal element" in state["section"]


@then("they direct generations_count: 1 and importing with import_audio")
def _take_and_import(state: dict[str, Any]) -> None:
    section = state["section"]
    assert "generations_count: 1" in section
    assert "import_audio" in section


# --- Scenario bindings ---


@scenario(FEATURE, "The first single-take audio generation in a session gets the routing reminder")
def test_first_single_take_audio_generation_gets_the_reminder() -> None:
    """SCN001 (AC1): a single-take music call exits 0 with the /generate-audio context and no decision."""


@scenario(FEATURE, "A multi-take audio generation is denied")
def test_multi_take_audio_generation_is_denied() -> None:
    """SCN002 (AC2): a speech call with generations_count 3 is denied and names /generate-audio."""


@scenario(FEATURE, "A repeat single-take call in the same session passes silently")
def test_repeat_single_take_call_passes_silently() -> None:
    """SCN003 (AC3): a repeat call for the same session exits 0 with empty stdout."""


@scenario(FEATURE, "Unreadable hook input fails open")
def test_unreadable_hook_input_fails_open() -> None:
    """SCN004 (AC4): input that is not JSON exits 0 with empty stdout."""


@scenario(FEATURE, "The skill makes music instrumental unless vocals come with lyrics")
def test_skill_makes_music_instrumental_unless_vocals_come_with_lyrics() -> None:
    """SCN005 (AC5): the music step reads the instrumental option and uses only the user's lyrics."""


@scenario(FEATURE, "The skill builds prompts only from the brief")
def test_skill_builds_prompts_only_from_the_brief() -> None:
    """SCN006 (AC6): the prompt is built from the brief, one take, then import_audio."""


@scenario(FEATURE, "Non-audio ElevenLabs generation is left alone")
def test_non_audio_elevenlabs_generation_is_left_alone() -> None:
    """SCN007 (AC7): an image in-flow call exits 0 with empty stdout and writes no marker."""
