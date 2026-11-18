"""AC7: the steering snippets describe freeform authoring plus finalize, with no superseded terms.

The guard reads the snippets as they are checked in. It fails when a prompt-to-asset term returns,
when the tech snippet's long-running Blender section stops naming the finalize job runner, MCP
tools, and CLI, or when that section points at an issue instead of describing the design. Since
#249 it also fails when the snippets stop describing the headless Godot flow: Godot as the engine,
never pinned, `godot --headless` only, a Blender-only session start, and the Godot layout.
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
    "mcp-servers/finalize/",
    "src/nmg_game_dev/finalize/",
    "src/nmg_game_dev/pipeline/",
    "src/nmg_game_dev/godot/",
    "src/nmg_game_dev/convert/",
    "plugins/nmg-game-dev-godot-addon/",
    "tests/godot/",
)
_RETIRED_STRUCTURE_PATHS = ("pipeline/stages", "prompt.py", "fixtures/", "build-platform")
_SESSION_START_HEADING = "### Session-start contract"
_GODOT_ENV = ("GODOT_BIN", "FFMPEG_BIN")


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


def test_product_snippet_names_godot_and_the_conversion_path(repo_root: pathlib.Path) -> None:
    text = _snippet(repo_root, "project-product.md")
    assert "Godot 4" in text
    assert "/convert-to-godot" in text
    assert "docs/skills/convert-to-godot.md" in text


def test_tech_stack_tracks_latest_godot_and_runs_it_headless(repo_root: pathlib.Path) -> None:
    stack = _section(_snippet(repo_root, "project-tech.md"), "## Technology Stack")
    assert "Godot 4" in stack
    assert "latest stable" in stack
    assert "never pinned" in stack
    assert "godot --headless" in stack
    assert "no live editor bridge" in stack


def test_tech_session_start_contract_is_blender_only(repo_root: pathlib.Path) -> None:
    section = _section(_snippet(repo_root, "project-tech.md"), _SESSION_START_HEADING)
    assert "start-blender-mcp.sh" in section
    scripts = set(re.findall(r"start-[a-z-]+\.sh", section))
    assert scripts == {"start-blender-mcp.sh"}


@pytest.mark.parametrize("variable", _GODOT_ENV)
def test_tech_environment_tables_name_the_godot_tools(
    repo_root: pathlib.Path, variable: str
) -> None:
    env = _section(_snippet(repo_root, "project-tech.md"), "### Required (per capability)")
    assert f"`{variable}`" in env


def test_tech_environment_drops_remote_windows_builds(repo_root: pathlib.Path) -> None:
    env = _section(_snippet(repo_root, "project-tech.md"), "### Required (per capability)")
    assert "WINDOWS_BUILD" not in env
    assert "WINDOWS_REMOTE" not in env


def test_tech_ship_flow_exports_through_godot_presets(repo_root: pathlib.Path) -> None:
    ship = _section(_snippet(repo_root, "project-tech.md"), "### Ship flow")
    assert "--export-release" in ship
    assert "export_presets.cfg" in ship
    assert "web" in ship
    assert "locally" in ship


def test_structure_restates_the_split_variant_rule_for_godot(repo_root: pathlib.Path) -> None:
    text = _snippet(repo_root, "project-structure.md")
    assert "game/assets/<Category>/<Name>/Desktop/" in text
    assert "game/assets/<Category>/<Name>/Mobile/" in text
    assert "NmgAssets.resolve_variant_path" in text
    assert "assets/*/Desktop/*" in text
    assert "assets/*/Mobile/*" in text


def test_structure_names_gdscript_conventions(repo_root: pathlib.Path) -> None:
    text = _snippet(repo_root, "project-structure.md")
    naming = _section(text, "### GDScript (Godot add-on, probes, scaffolds)")
    assert "snake_case.gd" in naming
    assert "class_name" in naming
    assert "PascalCase" in naming
