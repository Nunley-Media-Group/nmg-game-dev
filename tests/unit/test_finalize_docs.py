"""The finalize docs and tool descriptions name the #149 options and error codes (AC11, FR11).

``docs/mcp/finalize.md``, ``skills/finalize-asset/SKILL.md``, and the finalize MCP tool descriptions
in ``mcp-servers/finalize/tools.json`` must all describe the batch input, the wait option, the retry
defaults and overrides, and ``import_ue.editor_busy``.  They must no longer tell the caller to wait
and rerun by hand after ``finalize.job_running``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FINALIZE_MD = REPO_ROOT / "docs" / "mcp" / "finalize.md"
SKILL_MD = REPO_ROOT / "skills" / "finalize-asset" / "SKILL.md"
TOOLS_JSON = REPO_ROOT / "mcp-servers" / "finalize" / "tools.json"

REQUIRED_TERMS = (
    "batch",
    "requests",
    "wait_for_lock",
    "fail_fast",
    "NMG_GAME_DEV_UE_RETRIES",
    "NMG_GAME_DEV_UE_RETRY_DELAY_S",
    "import_ue.editor_busy",
)

STALE_WAIT_PHRASES = (
    "wait for it with `get_finalize_job`",
    "wait for it to finish",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _tool_text() -> str:
    """Return the finalize tool descriptions and parameter names as one searchable text."""
    tools = json.loads(_text(TOOLS_JSON))["tools"]
    parts: list[str] = []
    for tool in tools:
        parts.append(str(tool["description"]))
        parts.append(json.dumps(tool["inputSchema"]))
    return "\n".join(parts)


SURFACES = {
    "docs/mcp/finalize.md": FINALIZE_MD,
    "skills/finalize-asset/SKILL.md": SKILL_MD,
}


@pytest.mark.parametrize("term", REQUIRED_TERMS)
@pytest.mark.parametrize("surface", SURFACES)
def test_the_document_names_the_term(surface: str, term: str) -> None:
    text = _text(SURFACES[surface])
    if term == "batch":
        assert "batch" in text.lower()
    else:
        assert term in text


@pytest.mark.parametrize("term", REQUIRED_TERMS)
def test_the_tool_descriptions_name_the_term(term: str) -> None:
    text = _tool_text()
    if term == "batch":
        assert "batch" in text.lower()
    else:
        assert term in text


def test_the_retry_defaults_are_documented_with_their_values() -> None:
    for path in (FINALIZE_MD, SKILL_MD):
        text = _text(path)
        assert "20 s" in text, path
        assert any(phrase in text for phrase in ("4 retries", "up to 4 times", "`4`")), path
    assert "default 4" in _tool_text()
    assert "default 20" in _tool_text()


def test_the_pie_wait_default_is_documented() -> None:
    assert "600" in _text(FINALIZE_MD)
    assert "600" in _tool_text()


def test_the_docs_no_longer_tell_the_caller_to_wait_and_rerun_by_hand() -> None:
    for path in (FINALIZE_MD, SKILL_MD):
        lowered = _text(path).lower()
        for phrase in STALE_WAIT_PHRASES:
            assert phrase not in lowered, f"{path.name} still says {phrase!r}"


def test_the_batch_summary_and_exit_code_are_documented() -> None:
    text = _text(FINALIZE_MD)
    assert "result.batch" in text
    assert "Batch:" in text
    assert "finalize.batch_failed" in text
    assert "finalize.invalid_batch" in text
