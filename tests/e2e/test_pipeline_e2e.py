"""End-to-end pipeline tests against live Blender + UE + Meshy MCPs.

These tests are gated behind ``pytest --runslow`` and require:

- Blender running with the MCP add-on (``scripts/start-blender-mcp.sh``).
- UE Editor running with the VibeUE plugin (``scripts/start-unreal-mcp.sh``).
- ``MESHY_API_KEY`` set in the environment (for Meshy-supplement tests).
- A fixture UE project reachable at the path expected by the UE MCP bridge.

The fixture prompt is loaded from ``tests/e2e/fixtures/fixture_prompt.json``.
Wiring a real fixture UE project is out of scope for issue #4 — this module
ships the scaffold so the infrastructure is present when the fixture project
is ready.  All tests are marked ``@pytest.mark.xfail`` until the fixture UE
project is wired.

FR10: E2E is "Should" (not Must) per requirements.md, and is gated behind
``--runslow`` so it does not block the default ``pytest tests/`` run.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from nmg_game_dev.pipeline.prompt import Prompt

# ---------------------------------------------------------------------------
# Fixture prompt
# ---------------------------------------------------------------------------

_FIXTURE_PROMPT_PATH = Path(__file__).parent / "fixtures" / "fixture_prompt.json"


@pytest.fixture(scope="module")
def fixture_prompt() -> Prompt:
    data = json.loads(_FIXTURE_PROMPT_PATH.read_text())
    return Prompt(**data)


# ---------------------------------------------------------------------------
# End-to-end scenario: Blender-first (AC1)
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.xfail(
    reason=(
        "Fixture UE project not yet wired — scaffold ships in #4, "
        "wiring is out of scope.  Remove xfail when the fixture project is ready."
    ),
    strict=False,
)
def test_blender_first_e2e(fixture_prompt: Prompt, tmp_path: Path) -> None:
    """Full Blender-first pipeline against live Blender + UE MCPs.

    Requires:
    - ``BLENDER_MCP_PORT`` (default 9876) — Blender MCP listening.
    - ``UE_MCP_PORT`` (default 8088) — VibeUE MCP bridge listening.
    - The fixture prompt category/name directories must not clash with
      pre-existing UE content.
    """

    # Lazy import: real MCP client construction is a follow-up issue.
    # For now, this test documents the call site.
    pytest.skip(
        "Real MCP client loader is a follow-up issue — "
        "pass mcp_clients= manually when clients are available."
    )


@pytest.mark.slow
@pytest.mark.xfail(
    reason="Fixture UE project not yet wired — out of scope for #4.",
    strict=False,
)
def test_meshy_supplement_e2e(fixture_prompt: Prompt, tmp_path: Path) -> None:
    """Full Meshy-supplement pipeline against live Meshy + Blender + UE MCPs.

    Requires ``MESHY_API_KEY`` in the environment.
    """
    meshy_key = os.environ.get("MESHY_API_KEY")
    if not meshy_key:
        pytest.skip("MESHY_API_KEY not set — Meshy e2e skipped")

    pytest.skip(
        "Real MCP client loader is a follow-up issue — "
        "pass mcp_clients= manually when clients are available."
    )


@pytest.mark.slow
@pytest.mark.xfail(
    reason="Fixture UE project not yet wired — out of scope for #4.",
    strict=False,
)
def test_idempotent_resume_e2e(fixture_prompt: Prompt, tmp_path: Path) -> None:
    """Verify idempotent re-entry against live MCPs (AC3).

    Runs the pipeline twice with the same prompt and asserts that the second
    run serves all stages from cache without re-invoking any MCP.
    """
    pytest.skip(
        "Real MCP client loader is a follow-up issue — "
        "pass mcp_clients= manually when clients are available."
    )


@pytest.mark.slow
@pytest.mark.xfail(
    reason="Fixture UE project not yet wired — out of scope for #4.",
    strict=False,
)
def test_quality_gate_halt_e2e(tmp_path: Path) -> None:
    """Verify quality gate halts before UE import against live MCPs (AC4).

    Uses a prompt whose description includes an intentional over-budget hint
    that the Blender MCP add-on will honour when generating the mobile variant.
    """
    pytest.skip(
        "Real MCP client loader is a follow-up issue — "
        "pass mcp_clients= manually when clients are available."
    )
