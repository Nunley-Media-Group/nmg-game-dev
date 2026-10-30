"""AC7: the steering snippets describe freeform authoring plus finalize, with no superseded terms.

The guard reads the snippets as they are checked in. It fails when a prompt-to-asset term returns,
when the tech snippet's long-running Blender section stops naming the finalize job runner, MCP
tools, and CLI, or when that section points at an issue instead of describing the design.
"""

from __future__ import annotations

import pathlib
import re

import pytest

_SNIPPETS = ("project-product.md", "project-tech.md", "project-structure.md")
_SUPERSEDED_TERMS = ("new-prop", "new-character", "generate_mesh", 'source="meshy"')
_LONG_RUNNING_HEADING = "### Long-running Blender work"
_FINALIZE_TOOLS = ("finalize_asset", "run_finalize_step", "get_finalize_job")
_STRUCTURE_PATHS = (
    "plugins/nmg-game-dev-blender-addon/finalize_core/",
    "scripts/blender/finalize_entry.py",
    "scripts/blender/finalize_session.py",
    "scripts/unreal/build_master_material.py",
    "mcp-servers/finalize/",
    "src/nmg_game_dev/finalize/",
    "src/nmg_game_dev/pipeline/",
    "src/nmg_game_dev/unreal/",
)
_RETIRED_STRUCTURE_PATHS = ("pipeline/stages", "prompt.py")


def _snippet(repo_root: pathlib.Path, name: str) -> str:
    return (repo_root / "steering" / "snippets" / name).read_text(encoding="utf-8")


def _section(text: str, heading: str) -> str:
    """Return the text from ``heading`` up to the next heading of level one to three."""
    start = text.index(heading)
    body_start = start + len(heading)
    following = re.search(r"\n#{1,3} ", text[body_start:])
    end = body_start + following.start() if following else len(text)
    return text[start:end]


@pytest.mark.parametrize("term", _SUPERSEDED_TERMS)
@pytest.mark.parametrize("name", _SNIPPETS)
def test_snippets_omit_superseded_terms(repo_root: pathlib.Path, name: str, term: str) -> None:
    assert term not in _snippet(repo_root, name)


def test_product_snippet_describes_freeform_authoring_and_finalize(
    repo_root: pathlib.Path,
) -> None:
    text = _snippet(repo_root, "project-product.md")
    assert "freeform" in text
    assert "finalize" in text


def test_tech_long_running_section_names_job_runner_tools_and_cli(
    repo_root: pathlib.Path,
) -> None:
    text = _snippet(repo_root, "project-tech.md")
    assert text.count(_LONG_RUNNING_HEADING) == 1
    section = _section(text, _LONG_RUNNING_HEADING)
    assert "job runner" in section
    assert "run-job" in section
    assert "python -m nmg_game_dev.finalize" in section
    for tool in _FINALIZE_TOOLS:
        assert tool in section
    assert "Load-back rule" in section


def test_tech_long_running_section_does_not_point_at_issue_69(repo_root: pathlib.Path) -> None:
    section = _section(_snippet(repo_root, "project-tech.md"), _LONG_RUNNING_HEADING)
    assert "#69" not in section


@pytest.mark.parametrize("path", _STRUCTURE_PATHS)
def test_structure_lists_finalize_locations(repo_root: pathlib.Path, path: str) -> None:
    assert path in _snippet(repo_root, "project-structure.md")


@pytest.mark.parametrize("path", _RETIRED_STRUCTURE_PATHS)
def test_structure_omits_retired_stage_modules(repo_root: pathlib.Path, path: str) -> None:
    assert path not in _snippet(repo_root, "project-structure.md")
