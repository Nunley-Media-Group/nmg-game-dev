"""Shared MCP-error translation helpers for pipeline stages.

Every MCP-calling stage (generate, cleanup, variants, import_ue) wraps its
client call with the same three concerns: translate a low-level exception
into a canonical ``PipelineError``, validate that required string fields are
present in the response, and point the remediation at the right launcher
script. These helpers centralise the boilerplate so stage modules stay
focused on their own logic.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Literal

from ..errors import PipelineError

Server = Literal["blender", "unreal", "meshy"]

_REMEDIATION: dict[Server, str] = {
    "blender": (
        "Ensure Blender is running with the MCP add-on enabled. "
        "Run scripts/start-blender-mcp.sh to launch it."
    ),
    "unreal": (
        "Ensure UE Editor is running with the VibeUE plugin enabled. "
        "Run scripts/start-unreal-mcp.sh to launch it."
    ),
    "meshy": (
        "Ensure MESHY_API_KEY is set and the Meshy MCP server is reachable. "
        "Check .mcp.json for the correct server version pin."
    ),
}


@contextmanager
def translate_mcp_errors(*, server: Server, stage: str) -> Iterator[None]:
    """Convert any raw MCP-client exception into a canonical ``PipelineError``.

    ``PipelineError`` raised inside the block passes through unchanged so
    stage-specific validation failures keep their original code/message.
    """
    try:
        yield
    except PipelineError:
        raise
    except Exception as exc:
        raise PipelineError(
            code=f"mcp.{server}.unreachable",
            message=f"{server.title()} MCP unreachable during {stage} stage: {exc}",
            remediation=_REMEDIATION[server],
            stage=stage,
        ) from exc


def require_str_field(
    result: dict[str, object],
    field: str,
    *,
    server: Server,
    stage: str,
) -> str:
    """Return ``result[field]`` when it is a non-empty string, else raise.

    The raised error uses the canonical ``mcp.<server>.invalid_response`` code
    so skills and tests can branch on the same failure class regardless of
    which stage surfaced it.
    """
    value = result.get(field, "")
    if isinstance(value, str) and value:
        return value
    raise PipelineError(
        code=f"mcp.{server}.invalid_response",
        message=f"{server.title()} MCP returned no {field} in {stage} response",
        remediation=f"Check the {server.title()} MCP server version against .mcp.json pins.",
        stage=stage,
    )


def as_int(value: object, default: int = 0) -> int:
    """Coerce a JSON-loaded numeric value to ``int``, rejecting ``bool``.

    ``bool`` is a subclass of ``int``, so ``isinstance(True, int)`` is ``True``.
    An MCP response that returns a boolean where a count is expected would
    silently coerce to ``0`` or ``1`` without this guard.
    """
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return int(value)
    return default
