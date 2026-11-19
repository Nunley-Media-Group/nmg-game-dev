# ruff: noqa: E501  -- step decorators repeat the Gherkin text verbatim, so they run long.
"""pytest-bdd bindings for generate_audio_node_types.feature: SCN001-SCN004 of #285.

The guard hook runs as a real subprocess (``sys.executable hooks/generate_audio_guard.py``) with
``NMG_GAME_DEV_HOOK_STATE_DIR`` under ``tmp_path``, so nothing touches the real temp directory. The
guarded set is read from the hook source, the recorded MCP snapshot is read from its fixture, and
the docs table is parsed from ``docs/mcp/elevenlabs.md``.
"""

from __future__ import annotations

import json
import os
import re
import runpy
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenario, then, when

FEATURE = "generate_audio_node_types.feature"
REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK = REPO_ROOT / "hooks" / "generate_audio_guard.py"
SKILL = REPO_ROOT / "skills" / "generate-audio" / "SKILL.md"
DOCS = REPO_ROOT / "docs" / "mcp" / "elevenlabs.md"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "elevenlabs" / "flow_node_types.json"
MARKER_SUBDIR = "generate-audio-reminder"
# A row of the "### Guarded node types" table: the node_type identifier in backticks, first column.
TABLE_ID = re.compile(r"^\|\s*`([a-z][a-z-]*)`\s*\|", re.MULTILINE)


@pytest.fixture
def state(tmp_path: Path) -> dict[str, Any]:
    return {"tmp": tmp_path, "state_dir": tmp_path / "hook-state", "results": []}


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


def _in_flow_event(session_id: str, tool_input: dict[str, Any]) -> str:
    return json.dumps(
        {
            "session_id": session_id,
            "hook_event_name": "PreToolUse",
            "tool_name": "mcp__elevenlabs__creative_generate_in_flow",
            "tool_input": tool_input,
        }
    )


def _last(state: dict[str, Any]) -> subprocess.CompletedProcess[str]:
    results: list[subprocess.CompletedProcess[str]] = state["results"]
    return results[-1]


def _guard_node_types() -> set[str]:
    """Return the hook's AUDIO_NODE_TYPES, loaded from its source without running its main block."""
    namespace = runpy.run_path(str(HOOK))
    node_types: tuple[str, ...] = namespace["AUDIO_NODE_TYPES"]
    return set(node_types)


def _fixture_audio_types() -> set[str]:
    """Return every fixture type with audio output, plus composition (mixed audio when audio-only)."""
    data: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    audio: set[str] = {
        entry["type"] for entry in data["node_types"] if entry["output_modality"] == "audio"
    }
    return audio | {"composition"}


def _docs_table_types(text: str) -> set[str]:
    start = text.index("### Guarded node types")
    end = text.index("## Parameters")
    return set(TABLE_ID.findall(text[start:end]))


# --- SCN001 / SCN003: the hook's answer for one in-flow audio call ---


@given("an empty hook state directory")
def _empty_state_dir(state: dict[str, Any]) -> None:
    state["state_dir"].mkdir(parents=True, exist_ok=True)


@when(
    parsers.re(
        r'the audio guard hook receives a creative_generate_in_flow event with node_type "(?P<node_type>[a-z-]+)" and no generations_count for session "(?P<session>[^"]+)"'
    )
)
def _multi_take_step(state: dict[str, Any], node_type: str, session: str) -> None:
    event = _in_flow_event(session, {"node_type": node_type})
    state["results"].append(_run_hook(event, state["state_dir"]))


@when(
    parsers.re(
        r'the audio guard hook receives a creative_generate_in_flow event with node_type "(?P<node_type>[a-z-]+)" and generations_count (?P<count>\d+) for session "(?P<session>[^"]+)"'
    )
)
def _counted_step(state: dict[str, Any], node_type: str, count: str, session: str) -> None:
    event = _in_flow_event(session, {"node_type": node_type, "generations_count": int(count)})
    state["results"].append(_run_hook(event, state["state_dir"]))


@then("it exits 0")
def _exits_zero(state: dict[str, Any]) -> None:
    assert _last(state).returncode == 0, _last(state).stderr


@then("it exits 0 with empty stdout")
def _exits_zero_silent(state: dict[str, Any]) -> None:
    result = _last(state)
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


@then('its permissionDecision is "deny"')
def _denied(state: dict[str, Any]) -> None:
    specific = json.loads(_last(state).stdout)["hookSpecificOutput"]
    assert specific["permissionDecision"] == "deny"


@then("its permissionDecisionReason states generations_count: 1 and names /generate-audio")
def _deny_reason(state: dict[str, Any]) -> None:
    reason = json.loads(_last(state).stdout)["hookSpecificOutput"]["permissionDecisionReason"]
    assert "generations_count: 1" in reason
    assert "/generate-audio" in reason


@then("no reminder marker is written")
def _no_marker(state: dict[str, Any]) -> None:
    marker_dir = state["state_dir"] / MARKER_SUBDIR
    assert not marker_dir.exists() or not any(marker_dir.iterdir())


# --- SCN002: the recorded MCP list, the hook set, and the docs table agree ---


@given("the recorded ElevenLabs node-type list in tests/fixtures/elevenlabs/flow_node_types.json")
def _recorded_list(state: dict[str, Any]) -> None:
    assert FIXTURE.is_file(), FIXTURE


@when("the audio node types are derived as every audio-output type plus composition")
def _derive(state: dict[str, Any]) -> None:
    state["derived"] = _fixture_audio_types()


@then("they equal the guard hook's AUDIO_NODE_TYPES")
def _equal_guard(state: dict[str, Any]) -> None:
    assert state["derived"] == _guard_node_types()


@then("docs/mcp/elevenlabs.md lists exactly those node types")
def _docs_list(state: dict[str, Any]) -> None:
    docs_types = _docs_table_types(DOCS.read_text(encoding="utf-8"))
    assert docs_types == state["derived"]


# --- SCN004: the skill and the doc name every guarded type, each with generations_count: 1 ---


@given("the bodies of skills/generate-audio/SKILL.md and docs/mcp/elevenlabs.md")
def _bodies_exist(state: dict[str, Any]) -> None:
    assert SKILL.is_file() and DOCS.is_file()


@when("they are read")
def _read_bodies(state: dict[str, Any]) -> None:
    state["bodies"] = {
        "skills/generate-audio/SKILL.md": SKILL.read_text(encoding="utf-8"),
        "docs/mcp/elevenlabs.md": DOCS.read_text(encoding="utf-8"),
    }


@then("each names every node type in the guard hook's AUDIO_NODE_TYPES")
def _each_names_every_type(state: dict[str, Any]) -> None:
    bodies: dict[str, str] = state["bodies"]
    for name, body in bodies.items():
        for node_type in sorted(_guard_node_types()):
            assert f"`{node_type}`" in body, f"{name} does not name {node_type!r}"


@then("each states generations_count: 1")
def _each_states_one_take(state: dict[str, Any]) -> None:
    bodies: dict[str, str] = state["bodies"]
    for name, body in bodies.items():
        assert "generations_count: 1" in body, f"{name} does not state generations_count: 1"


# --- Scenario bindings ---


@scenario(FEATURE, "A multi-take call for any audio node type is denied")
def test_multi_take_call_for_any_audio_node_type_is_denied() -> None:
    """SCN001 (AC1): a guarded in-flow call with no generations_count is denied and names /generate-audio."""


@scenario(FEATURE, "The guarded set matches the MCP's audio-output node types")
def test_guarded_set_matches_the_mcp_audio_output_node_types() -> None:
    """SCN002 (AC2): the audio set derived from the fixture equals AUDIO_NODE_TYPES and the docs table."""


@scenario(FEATURE, "Non-audio node types are left alone")
def test_non_audio_node_types_are_left_alone() -> None:
    """SCN003 (AC3): a non-audio in-flow call with generations_count 4 exits 0 silently, no marker."""


@scenario(FEATURE, "The skill and the doc name every guarded audio node type")
def test_skill_and_doc_name_every_guarded_audio_node_type() -> None:
    """SCN004 (AC4): the skill and the doc name each identifier and state generations_count: 1."""
