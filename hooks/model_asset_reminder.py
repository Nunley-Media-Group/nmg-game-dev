"""PreToolUse reminder that routes Blender asset authoring to /model-asset (#130 FR3, FR4).

Claude Code runs this before each ``execute_blender_code`` call. The first call in a session
prints an ``additionalContext`` reminder; later calls for the same session print nothing. The hook
never denies or blocks a call, and any error leaves the call alone: exit 0 with no output.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

REMINDER = (
    "nmg-game-dev: to create or change an asset's geometry or materials in Blender, run the "
    "/model-asset skill (nmg-game-dev:model-asset) instead of authoring through "
    "execute_blender_code directly. Scene inspection and /finalize-asset runs are exempt; "
    "continue those as planned."
)
STATE_ENV = "NMG_GAME_DEV_HOOK_STATE_DIR"


def state_dir() -> Path:
    """Return the directory holding one marker file per reminded session."""
    override = os.environ.get(STATE_ENV)
    if override:
        return Path(override)
    return Path(tempfile.gettempdir()) / "nmg-game-dev-hooks" / "model-asset-reminder"


def main(stdin_text: str) -> str:
    """Return the hook's JSON output for one event, or "" to stay silent."""
    try:
        event = json.loads(stdin_text)
    except ValueError:
        return ""
    if not isinstance(event, dict):
        return ""
    session_id = event.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return ""
    try:
        marker = state_dir() / hashlib.sha256(session_id.encode("utf-8")).hexdigest()
        marker.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive create: the first call for a session wins, even when calls run concurrently.
        with marker.open("x", encoding="utf-8"):
            pass
    except (OSError, ValueError):
        # FileExistsError means this session was already reminded; any other error fails open.
        return ""
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": REMINDER,
        }
    }
    return json.dumps(payload)


if __name__ == "__main__":
    try:
        output = main(sys.stdin.read())
        if output:
            print(output)
    except Exception:
        # Fail open: an unexpected error must never block or annotate the tool call.
        pass
    sys.exit(0)
