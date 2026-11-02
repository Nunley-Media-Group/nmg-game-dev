# ruff: noqa: E501  -- step decorators repeat the Gherkin text verbatim, so they run long.
"""pytest-bdd bindings for model_asset_routing.feature: SCN001-SCN005 of #130.

The reminder hook runs as a real subprocess (``sys.executable hooks/model_asset_reminder.py``) with
``NMG_GAME_DEV_HOOK_STATE_DIR`` under ``tmp_path``, so nothing touches the real temp directory. The
onboarding block is written into a temp ``CLAUDE.md``. ``OLD_BLOCK`` is the 0.21.0 block text.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, scenario, then, when

from nmg_game_dev.onboard.instructions import BEGIN, END, block_text, upsert_block
from tests.ship_fakes import parse_frontmatter

FEATURE = "model_asset_routing.feature"
REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL = REPO_ROOT / "skills" / "model-asset" / "SKILL.md"
HOOK = REPO_ROOT / "hooks" / "model_asset_reminder.py"

# The nmg-game-dev block /onboard-consumer wrote at 0.21.0, before the #130 routing paragraph.
OLD_BLOCK = (
    f"{BEGIN}\n"
    "## nmg-game-dev asset contract\n\n"
    "Assets authored for this project follow [the asset contract](docs/nmg-game-dev/asset-contract.md). Read it "
    "before you author, finalize, or import an asset.\n"
    "Design docs in [docs/design/](docs/design/) follow [the design contract]"
    "(docs/nmg-game-dev/design-contract.md). Read it before you write or change a design doc.\n"
    f"{END}"
)


@pytest.fixture
def state(tmp_path: Path) -> dict[str, Any]:
    return {"tmp": tmp_path, "state_dir": tmp_path / "hook-state", "results": [], "fields": {}}


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


def _execute_blender_code_event(session_id: str) -> str:
    return json.dumps(
        {
            "session_id": session_id,
            "hook_event_name": "PreToolUse",
            "tool_name": "mcp__blender__execute_blender_code",
        }
    )


# --- SCN001: the skill description states its trigger ---


@given("the frontmatter of skills/model-asset/SKILL.md")
def _skill_frontmatter(state: dict[str, Any]) -> None:
    state["text"] = SKILL.read_text(encoding="utf-8")
    state["fields"] = parse_frontmatter(state["text"])


@when("its description is read")
def _read_description(state: dict[str, Any]) -> None:
    state["description"] = state["fields"]["description"]


@then(
    "it is one line that says the skill is used whenever creating or changing an asset's geometry or materials in Blender"
)
def _description_one_line_trigger(state: dict[str, Any]) -> None:
    raw = [line for line in state["text"].splitlines() if line.startswith("description:")]
    assert len(raw) == 1, "the description must be a single frontmatter line"
    description = state["description"]
    assert description
    assert "\n" not in description
    # A colon followed by a space ends a YAML plain scalar, so the frontmatter would not parse.
    assert ": " not in description, "description has ': ', which breaks the YAML frontmatter"
    assert (
        "whenever you create or change an asset's geometry or materials in Blender" in description
    )


@then('it contains "freeform" and "Blender MCP"')
def _description_keeps_terms(state: dict[str, Any]) -> None:
    description = state["description"]
    assert "freeform" in description
    assert "Blender MCP" in description


# --- SCN002: onboarding refreshes the block with the /model-asset routing ---


@given("a consumer CLAUDE.md holding the 0.21.0 nmg-game-dev block")
def _old_block_claude_md(state: dict[str, Any]) -> None:
    path = state["tmp"] / "CLAUDE.md"
    path.write_text("# Game\n\n" + OLD_BLOCK + "\n", encoding="utf-8")
    state["claude"] = path


@when("onboarding writes the agent-instructions block")
def _onboarding_writes_block(state: dict[str, Any]) -> None:
    state["result"] = upsert_block("agent_instructions:CLAUDE.md", state["claude"], create=True)
    state["claude_text"] = state["claude"].read_text(encoding="utf-8")


@then('the step reports "refreshed"')
def _reports_refreshed(state: dict[str, Any]) -> None:
    result = state["result"]
    assert result is not None and result.status == "refreshed"


@then("the block tells the agent to run /model-asset for asset authoring or editing in Blender")
def _block_routes_to_model_asset(state: dict[str, Any]) -> None:
    assert (
        "Run `/model-asset` for any asset authoring or editing in Blender" in state["claude_text"]
    )


@then("the block exempts scene inspection and /finalize-asset")
def _block_exempts_inspection(state: dict[str, Any]) -> None:
    assert "Scene inspection and `/finalize-asset` runs do not need it." in state["claude_text"]


# --- SCN003: the first execute_blender_code call in a session gets the reminder ---


@given("an empty hook state directory")
def _empty_state_dir(state: dict[str, Any]) -> None:
    state["state_dir"].mkdir(parents=True, exist_ok=True)


@when('the reminder hook receives an execute_blender_code PreToolUse event for session "s-1"')
def _first_event(state: dict[str, Any]) -> None:
    state["results"].append(_run_hook(_execute_blender_code_event("s-1"), state["state_dir"]))


@then("it exits 0")
def _exits_zero(state: dict[str, Any]) -> None:
    assert state["results"][-1].returncode == 0, state["results"][-1].stderr


@then(
    "its additionalContext tells Claude to use /model-asset and exempts inspection and /finalize-asset"
)
def _context_routes_and_exempts(state: dict[str, Any]) -> None:
    payload = json.loads(state["results"][-1].stdout)
    specific = payload["hookSpecificOutput"]
    assert specific["hookEventName"] == "PreToolUse"
    context = specific["additionalContext"]
    assert "/model-asset" in context
    assert "Scene inspection" in context and "/finalize-asset" in context
    assert "exempt" in context


@then("it makes no permission or block decision")
def _no_decision(state: dict[str, Any]) -> None:
    payload = json.loads(state["results"][-1].stdout)
    assert "permissionDecision" not in payload["hookSpecificOutput"]
    assert "decision" not in payload


# --- SCN004: later calls in the same session stay silent ---


@given('the reminder hook has already reminded session "s-1"')
def _already_reminded(state: dict[str, Any]) -> None:
    state["state_dir"].mkdir(parents=True, exist_ok=True)
    first = _run_hook(_execute_blender_code_event("s-1"), state["state_dir"])
    assert first.returncode == 0 and first.stdout.strip(), "the first call must remind"


@when('it receives another execute_blender_code event for session "s-1"')
def _second_event(state: dict[str, Any]) -> None:
    state["results"].append(_run_hook(_execute_blender_code_event("s-1"), state["state_dir"]))


@then("it exits 0 with no output")
def _silent_repeat(state: dict[str, Any]) -> None:
    repeat = state["results"][-1]
    assert repeat.returncode == 0
    assert repeat.stdout == ""


@then('an event for session "s-2" receives the reminder')
def _other_session_reminded(state: dict[str, Any]) -> None:
    other = _run_hook(_execute_blender_code_event("s-2"), state["state_dir"])
    assert other.returncode == 0
    assert "/model-asset" in json.loads(other.stdout)["hookSpecificOutput"]["additionalContext"]


# --- SCN005: existing behavior is kept and the hook fails open ---


@given("the onboarding block and the reminder hook")
def _block_and_hook(state: dict[str, Any]) -> None:
    state["state_dir"].mkdir(parents=True, exist_ok=True)


@when(
    "the block is generated and the hook receives invalid JSON, an event without a session id, or an unwritable state directory"
)
def _fail_open_cases(state: dict[str, Any]) -> None:
    state["block"] = block_text()
    blocked = state["tmp"] / "not-a-directory"
    blocked.write_text("a regular file where the state directory should be", encoding="utf-8")
    state["results"] = [
        _run_hook("this is not json", state["state_dir"]),
        _run_hook(json.dumps({"hook_event_name": "PreToolUse"}), state["state_dir"]),
        _run_hook(_execute_blender_code_event("s-3"), blocked),
    ]


@then("the block still links the asset contract and the design contract")
def _block_links_contracts(state: dict[str, Any]) -> None:
    block = state["block"]
    assert "](docs/nmg-game-dev/asset-contract.md)" in block
    assert "](docs/nmg-game-dev/design-contract.md)" in block


@then("the hook exits 0 with no output in each case")
def _fails_open(state: dict[str, Any]) -> None:
    for result in state["results"]:
        assert result.returncode == 0, result.stderr
        assert result.stdout == ""


@scenario(FEATURE, "The skill description states its trigger")
def test_skill_description_states_its_trigger() -> None:
    """SCN001 (AC1): the one-line description names the Blender asset trigger and keeps freeform and Blender MCP."""


@scenario(FEATURE, "Onboarding refreshes the block with the /model-asset routing")
def test_onboarding_refreshes_the_block_with_the_routing() -> None:
    """SCN002 (AC2): a 0.21.0 block is replaced in place, reports refreshed, and routes to /model-asset."""


@scenario(FEATURE, "The first execute_blender_code call in a session gets the reminder")
def test_first_execute_blender_code_call_gets_the_reminder() -> None:
    """SCN003 (AC3): the first call exits 0 with routing additionalContext and no decision."""


@scenario(FEATURE, "Later calls in the same session stay silent")
def test_later_calls_in_the_same_session_stay_silent() -> None:
    """SCN004 (AC4): a repeat call for a session is silent; another session is reminded."""


@scenario(FEATURE, "Existing behavior is kept and the hook fails open")
def test_existing_behavior_is_kept_and_the_hook_fails_open() -> None:
    """SCN005 (AC5): the block still links both contracts; bad input or an unwritable state dir exits 0 silently."""
