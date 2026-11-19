"""The finalize docs and tool descriptions name the batch options and the Godot import (#149, #249).

``docs/mcp/finalize.md``, ``skills/finalize-asset/SKILL.md``, and the finalize MCP tool descriptions
in ``mcp-servers/finalize/tools.json`` must all describe the batch input and the wait option. The
two documents must also describe the headless Godot import: the ``import_godot`` step in its place
in the step order, its error codes, and the resource paths it returns. The editor-era play-mode and
retry options must not come back, and the docs must no longer tell the caller to wait and rerun by
hand after ``finalize.job_running``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FINALIZE_MD = REPO_ROOT / "docs" / "mcp" / "finalize.md"
SKILL_MD = REPO_ROOT / "skills" / "finalize-asset" / "SKILL.md"
CONTRACT_MD = REPO_ROOT / "docs" / "asset-contract.md"
TOOLS_JSON = REPO_ROOT / "mcp-servers" / "finalize" / "tools.json"

BATCH_TERMS = ("batch", "requests", "wait_for_lock", "fail_fast")

GODOT_TERMS = (
    "import_godot",
    "import_anims",
    "godot --headless",
    "GODOT_BIN",
    "godot.not_found",
    "import_godot.project_missing",
    "import_godot.import_failed",
    "import_godot.mismatch",
    "import_godot.terrain_height_mismatch",
    "import_anims.clip_mismatch",
    "import_anims.failed",
)

STEP_ORDER = (
    "validate",
    "bake",
    "variants",
    "export",
    "export_anims",
    "reimport",
    "import_godot",
    "import_anims",
)

RETIRED_TERMS = ("pie_mode", "pie_wait_seconds", "editor_busy", "_RETRIES", "_RETRY_DELAY_S")

STALE_WAIT_PHRASES = (
    "wait for it with `get_finalize_job`",
    "wait for it to finish",
)

SURFACES = {
    "docs/mcp/finalize.md": FINALIZE_MD,
    "skills/finalize-asset/SKILL.md": SKILL_MD,
}


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


@pytest.mark.parametrize("term", BATCH_TERMS)
@pytest.mark.parametrize("surface", SURFACES)
def test_the_document_names_the_batch_term(surface: str, term: str) -> None:
    text = _text(SURFACES[surface])
    if term == "batch":
        assert "batch" in text.lower()
    else:
        assert term in text


@pytest.mark.parametrize("term", BATCH_TERMS)
def test_the_tool_descriptions_name_the_batch_term(term: str) -> None:
    text = _tool_text()
    if term == "batch":
        assert "batch" in text.lower()
    else:
        assert term in text


@pytest.mark.parametrize("term", GODOT_TERMS)
@pytest.mark.parametrize("surface", SURFACES)
def test_the_document_names_the_godot_import(surface: str, term: str) -> None:
    assert term in _text(SURFACES[surface])


@pytest.mark.parametrize("term", RETIRED_TERMS)
@pytest.mark.parametrize("surface", SURFACES)
def test_the_document_drops_the_editor_era_options(surface: str, term: str) -> None:
    assert term not in _text(SURFACES[surface])


@pytest.mark.parametrize("term", RETIRED_TERMS)
def test_the_tool_descriptions_drop_the_editor_era_options(term: str) -> None:
    assert term not in _tool_text()


def test_the_tool_descriptions_name_the_godot_step() -> None:
    assert "import_godot" in _tool_text()


def test_the_mcp_doc_lists_the_steps_in_order() -> None:
    text = _text(FINALIZE_MD)
    assert " → ".join(STEP_ORDER) in re.sub(r"\s*\n\s*", " ", text)
    steps = _text(FINALIZE_MD).split("## Steps", 1)[1].split("\n## ", 1)[0]
    rows = re.findall(r"^\| `([a-z_]+)` \|", steps, re.MULTILINE)
    assert tuple(rows[: len(STEP_ORDER)]) == STEP_ORDER


@pytest.mark.parametrize("output", ("desktop_resource_path", "mobile_resource_path"))
@pytest.mark.parametrize("surface", SURFACES)
def test_the_godot_resource_outputs_are_documented(surface: str, output: str) -> None:
    assert output in _text(SURFACES[surface])


def test_the_contract_error_table_lists_every_import_code_with_a_remediation() -> None:
    text = _text(CONTRACT_MD)
    table = text.split("## 10. Godot import errors", 1)[1]
    rows = {
        match.group(1): line
        for line in table.splitlines()
        if (match := re.match(r"\| `([a-z_.]+)` \|", line))
    }
    expected = {
        "godot.not_found",
        "import_godot.project_missing",
        "import_godot.import_failed",
        "import_godot.mismatch",
        "import_godot.terrain_height_mismatch",
        "import_anims.clip_mismatch",
        "import_anims.failed",
        "audio.ffmpeg_not_found",
    }
    assert set(rows) == expected
    for code, row in rows.items():
        cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
        assert len(cells) == 3 and all(cells), f"{code} row lacks a meaning or remediation"


def test_the_contract_states_the_godot_export_rules() -> None:
    text = _text(CONTRACT_MD)
    for needle in (
        ".glb",
        "1 unit = 1 m",
        "base centre",
        "meshes/generate_lods",
        "game/assets",
        "<Name>_Chunk_<row>_<col>.glb",
        "HeightMapShape3D",
        "A_<Name>_<Clip>.glb",
        "NmgAssets.resolve_variant_path",
        "assets/*/Desktop/*",
        "assets/*/Mobile/*",
    ):
        assert needle in text, needle


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
