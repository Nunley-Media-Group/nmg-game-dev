"""PipelineError — the single exception type surfaced by every pipeline stage.

Matches the MCP-server error contract in ``steering/tech.md`` § API /
Interface Standards: structured ``code``, ``message``, and ``remediation``
fields.  Skills catch this at their boundary and render the remediation to
the developer.
"""

from __future__ import annotations


class PipelineError(Exception):
    """Raised when any pipeline stage fails.

    Always caught at skill boundaries — never silently swallowed inside the
    pipeline runner itself.

    Attributes:
        code: Stable namespaced error code, e.g. ``"quality.mobile_budget_exceeded"``.
            Uses ``<stage>.<condition>`` convention so future additions don't
            collide and skills can ``switch`` on it.
        message: Human-readable description of what went wrong.
        remediation: Copy-pasteable next action for the developer.
        stage: Name of the stage that raised — for observability / logging.
    """

    def __init__(
        self,
        code: str,
        message: str,
        remediation: str,
        stage: str,
    ) -> None:
        super().__init__(message)
        self.code: str = code
        self.message: str = message
        self.remediation: str = remediation
        self.stage: str = stage
