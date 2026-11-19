"""PreToolUse guard for ElevenLabs audio generation (#242 FR2, FR3, FR4, FR7).

Claude Code runs this before each ElevenLabs ``creative_generate_speech`` call and each
``creative_generate_in_flow`` call. An audio call is a speech call or an in-flow call whose
``node_type`` is in ``AUDIO_NODE_TYPES``. It denies an audio call whose ``generations_count`` is not
the integer 1, because game audio is generated one take at a time. An allowed audio call gets a
once-per-session ``additionalContext`` reminder that names the ``/generate-audio`` skill. Calls
for other ElevenLabs generation (for example ``node_type`` ``image``) are left alone. Any error
leaves the call alone: exit 0 with no output.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

DENY_REASON = (
    "nmg-game-dev: game audio is generated one take at a time. Set generations_count: 1 on this "
    "call and follow the /generate-audio skill (nmg-game-dev:generate-audio)."
)
REMINDER = (
    "nmg-game-dev: run ElevenLabs sound-effect, music, and speech generation through the "
    "/generate-audio skill (nmg-game-dev:generate-audio): one take (generations_count: 1), "
    "instrumental music unless the user asked for vocals and gave lyrics, and a prompt built only "
    "from the user's request and the design docs. Import the saved file with import_audio."
)
STATE_ENV = "NMG_GAME_DEV_HOOK_STATE_DIR"
# In-flow node types whose output is audio, plus composition (a mixed audio file when only audio
# sources are connected). tests/fixtures/elevenlabs/flow_node_types.json derives this set.
AUDIO_NODE_TYPES = (
    "tts",
    "sfx",
    "music",
    "dubbing-audio",
    "voice-changer",
    "voice-isolator",
    "audio-effects",
    "video-to-music",
    "composition",
)
SPEECH_SUFFIX = "__creative_generate_speech"
IN_FLOW_SUFFIX = "__creative_generate_in_flow"


def state_dir() -> Path:
    """Return the directory holding one marker file per reminded session."""
    override = os.environ.get(STATE_ENV)
    if override:
        return Path(override) / "generate-audio-reminder"
    return Path(tempfile.gettempdir()) / "nmg-game-dev-hooks" / "generate-audio-reminder"


def _is_audio_call(tool_name: str, tool_input: dict[str, object]) -> bool:
    """Return True for speech calls and for in-flow calls whose node_type is in AUDIO_NODE_TYPES."""
    if tool_name.endswith(SPEECH_SUFFIX):
        return True
    if tool_name.endswith(IN_FLOW_SUFFIX):
        node_type = tool_input.get("node_type")
        return isinstance(node_type, str) and node_type in AUDIO_NODE_TYPES
    return False


def _deny_payload() -> str:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": DENY_REASON,
        }
    }
    return json.dumps(payload)


def _reminder_payload() -> str:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": REMINDER,
        }
    }
    return json.dumps(payload)


def main(stdin_text: str) -> str:
    """Return the hook's JSON output for one event, or "" to stay silent."""
    try:
        event = json.loads(stdin_text)
    except ValueError:
        return ""
    if not isinstance(event, dict):
        return ""
    tool_input = event.get("tool_input")
    tool_name = event.get("tool_name")
    if not isinstance(tool_input, dict) or not isinstance(tool_name, str):
        return ""
    if not _is_audio_call(tool_name, tool_input):
        return ""
    # Single take only when the value is the integer 1: True, 1.0, and "1" are all denied.
    count = tool_input.get("generations_count")
    if not (type(count) is int and count == 1):
        return _deny_payload()
    session_id = event.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return ""
    try:
        marker = state_dir() / hashlib.sha256(session_id.encode("utf-8")).hexdigest()
        marker.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive create: the first allowed call for a session wins, even when calls run
        # concurrently.
        with marker.open("x", encoding="utf-8"):
            pass
    except (OSError, ValueError):
        # FileExistsError means this session was already reminded; any other error fails open.
        return ""
    return _reminder_payload()


if __name__ == "__main__":
    try:
        output = main(sys.stdin.read())
        if output:
            print(output)
    except Exception:
        # Fail open: an unexpected error must never block or annotate the tool call.
        pass
    sys.exit(0)
