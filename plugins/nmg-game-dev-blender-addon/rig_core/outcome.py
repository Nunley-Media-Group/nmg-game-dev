"""Result builders and the error type shared by every rig_core function."""

from __future__ import annotations

from typing import Any

STATUS_OK = "ok"
STATUS_FALLBACK = "fallback required"
STATUS_SPIKE = "follow-up spike required"

MIXAMO_FALLBACK_NOTE = (
    "Optional fallback only: rig and animate the character by hand in Mixamo and bring "
    "the result back in. Nothing in nmg-game-dev contacts Mixamo."
)


def ok(**data: Any) -> dict[str, Any]:
    """Return a success result that carries data."""
    return {"status": STATUS_OK, **data}


def fail(status: str, code: str, message: str, remediation: str) -> dict[str, Any]:
    """Return a failure result. Fallback remediation always ends with the Mixamo note."""
    if status == STATUS_FALLBACK:
        remediation = f"{remediation} {MIXAMO_FALLBACK_NOTE}"
    return {"status": status, "code": code, "message": message, "remediation": remediation}


class RigError(Exception):
    """A failure inside rig_core that callers turn into a result dict."""

    def __init__(self, status: str, code: str, message: str, remediation: str) -> None:
        super().__init__(message)
        self.result = fail(status, code, message, remediation)
