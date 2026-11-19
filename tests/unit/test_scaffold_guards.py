"""Scaffold guard unit tests for issue #1, updated for the Godot engine (#249).

Each test function's name encodes the T015* sub-task and covering AC:
  plugin_json_schema           — T015a / AC1
  directory_exists             — T015b / AC2
  mcp_json_*                   — T015c / AC8; #64 AC4 (no Meshy server); #249 (no engine server)
  steering_snippets_*          — #64 AC5 (no Meshy source in steering); #249 gate and version rows
  no_leak_* / no_fixture_*     — T015d / AC10, AC11
  no_repo_root_settings_json   — T015e / AC5b
  version_* / nmg_*_version    — T015f / AC7; #249 plugin.cfg in the triangulation
  changelog_*                  — T015g / AC7
  claude_md_*                  — T015h / AC9
"""

from __future__ import annotations

import pathlib
import re
import tomllib
from typing import Any

import pytest
from _scaffold_contract import (
    BANNED_SUBSTRINGS,
    BLENDER_MCP_PACKAGE,
    CONSUMER_FACING,
    EXPECTED_VERSION,
    GODOT_PLUGIN_CFG,
    REPO_FIXTURE_REFERENCES,
    REPO_ROOT,
    REQUIRED_DIRS,
    REQUIRED_SERVERS,
    SESSION_START_SCRIPTS,
    godot_plugin_cfg_version,
)


def test_plugin_json_schema(repo_root: pathlib.Path, plugin_data: dict[str, Any]) -> None:
    for field in ("name", "version", "description", "author"):
        assert field in plugin_data, f"plugin.json missing required field: {field!r}"

    assert plugin_data["name"] == "nmg-game-dev"
    assert plugin_data["version"] == EXPECTED_VERSION
    assert plugin_data["author"]["name"] == "Nunley Media Group"
    # Claude Code discovers skills from the default skills/ folder; no manifest field.
    assert (repo_root / "skills").is_dir()
    assert "capabilities" not in plugin_data
    assert "requires" not in plugin_data


def test_no_marketplace_in_repo(repo_root: pathlib.Path) -> None:
    # nmg-game-dev is listed in the nmg-plugins marketplace; this repo carries no marketplace.
    assert not (repo_root / ".claude-plugin" / "marketplace.json").exists()


def test_consumer_claude_settings_template(consumer_hooks_data: dict[str, Any]) -> None:
    commands = [
        h["command"]
        for entry in consumer_hooks_data["hooks"]["SessionStart"]
        for h in entry["hooks"]
    ]
    assert any("start-blender-mcp.sh" in c for c in commands)
    # Blender is the only session-start launcher; Godot only ever runs headless on demand.
    for command in commands:
        assert any(script in command for script in SESSION_START_SCRIPTS), command


@pytest.mark.parametrize("rel_dir", REQUIRED_DIRS)
def test_directory_exists(repo_root: pathlib.Path, rel_dir: str) -> None:
    assert (repo_root / rel_dir).is_dir(), f"Directory missing: {rel_dir}"


def test_mcp_json_exists(repo_root: pathlib.Path) -> None:
    assert (repo_root / ".mcp.json").is_file(), ".mcp.json missing at repo root"


def test_mcp_json_all_servers_declared(mcp_data: dict[str, Any]) -> None:
    for server in REQUIRED_SERVERS:
        assert server in mcp_data["mcpServers"], f".mcp.json missing server: {server!r}"


def test_mcp_json_declares_no_engine_server(mcp_data: dict[str, Any]) -> None:
    # The plugin's servers are exactly these; Godot is driven headless, with no MCP server.
    assert set(mcp_data["mcpServers"]) == set(REQUIRED_SERVERS)
    assert not any(entry.get("type") == "http" for entry in mcp_data["mcpServers"].values())


@pytest.mark.parametrize("banned", ("mcp-remote", "8088", "bridge"))
def test_mcp_json_has_no_bridge_wording(mcp_text: str, banned: str) -> None:
    assert banned not in mcp_text.lower(), f".mcp.json still mentions {banned!r}"


def test_mcp_json_blender_tracks_latest(mcp_data: dict[str, Any]) -> None:
    blender = mcp_data["mcpServers"]["blender"]
    assert blender["command"] == "uvx"
    assert blender["args"] == [BLENDER_MCP_PACKAGE]
    assert blender["env"]["BLENDER_MCP_DISABLE_TELEMETRY"] == "1"


@pytest.mark.parametrize("server", REQUIRED_SERVERS)
def test_mcp_json_carries_no_version_constraint(mcp_data: dict[str, Any], server: str) -> None:
    entry = mcp_data["mcpServers"][server]
    refs = [entry.get("command", ""), *entry.get("args", []), entry.get("url", "")]
    for ref in refs:
        assert not re.search(r"==|[<>]|@\d", ref), f"{server} pins a version in {ref!r}"


def test_mcp_json_declares_the_optional_meshy_server(
    mcp_data: dict[str, Any], mcp_text: str
) -> None:
    entry = mcp_data["mcpServers"]["meshy"]
    assert entry["command"] == "uv"
    assert entry["args"] == [
        "run",
        "--project",
        "${CLAUDE_PLUGIN_ROOT}/mcp-servers/meshy",
        "meshy-mcp",
    ]
    assert "env" not in entry, "the meshy entry must not carry a key in its env"
    assert "MESHY_API_KEY" not in mcp_text, ".mcp.json must not reference MESHY_API_KEY"
    assert "meshy-mcp-server" not in mcp_text, ".mcp.json still pins meshy-mcp-server"


_EXPECTED_WIRING: dict[str, dict[str, Any]] = {
    "blender": {
        "command": "uvx",
        "args": ["mcp-for-blender@latest"],
        "env": {"BLENDER_MCP_DISABLE_TELEMETRY": "1"},
    },
    "finalize": {
        "command": "uv",
        "args": ["run", "--project", "${CLAUDE_PLUGIN_ROOT}/mcp-servers/finalize", "finalize-mcp"],
    },
    "texture-gen": {
        "command": "uv",
        "args": [
            "run",
            "--project",
            "${CLAUDE_PLUGIN_ROOT}/mcp-servers/texture-gen",
            "texture-gen-mcp",
        ],
    },
}


@pytest.mark.parametrize("server", sorted(_EXPECTED_WIRING))
def test_mcp_json_other_entries_keep_their_wiring(mcp_data: dict[str, Any], server: str) -> None:
    entry = mcp_data["mcpServers"][server]
    wiring = {key: entry[key] for key in ("type", "command", "args", "env", "url") if key in entry}
    assert wiring == _EXPECTED_WIRING[server], f"{server} wiring changed for #98"


MESHY_SOURCE_STRINGS = (
    "--source meshy",
    'source="meshy"',
    "meshy-mcp-server",
    "MESHY_API_KEY",
)

STEERING_SNIPPETS = sorted((REPO_ROOT / "steering" / "snippets").glob("*.md"))


def test_steering_snippets_found() -> None:
    # Guards the parametrized scan below against silently running over zero files.
    assert STEERING_SNIPPETS, "no steering/snippets/*.md files found to scan"


@pytest.mark.parametrize("snippet", STEERING_SNIPPETS, ids=lambda p: p.name)
@pytest.mark.parametrize("banned", MESHY_SOURCE_STRINGS)
def test_steering_snippets_do_not_offer_meshy(snippet: pathlib.Path, banned: str) -> None:
    assert banned not in snippet.read_text(), (
        f"{snippet.name} offers Meshy as a source (found {banned!r})"
    )


@pytest.mark.parametrize("artifact", CONSUMER_FACING)
@pytest.mark.parametrize(
    "banned",
    BANNED_SUBSTRINGS,
    ids=[
        "legacy-user-plugin-path",
        "legacy-project-plugin-path",
        "legacy-host-name",
    ],
)
def test_no_leak_consumer_artifacts(artifact_text: Any, artifact: str, banned: str) -> None:
    assert banned not in artifact_text(artifact), f"Banned substring {banned!r} found in {artifact}"


@pytest.mark.parametrize("artifact", CONSUMER_FACING)
@pytest.mark.parametrize("fixture_ref", REPO_FIXTURE_REFERENCES)
def test_no_fixture_reference_in_consumer_artifacts(
    artifact_text: Any, artifact: str, fixture_ref: str
) -> None:
    assert fixture_ref not in artifact_text(artifact), (
        f"In-repo fixture reference {fixture_ref!r} found in {artifact} (AC10 leak)"
    )


def test_no_repo_root_settings_json(repo_root: pathlib.Path) -> None:
    assert not (repo_root / ".claude" / "settings.json").exists(), (
        ".claude/settings.json found at repo root — must not exist. "
        "SessionStart hooks belong in templates/consumer/.claude/settings.json only."
    )


def test_version_file(version_text: str) -> None:
    assert version_text == f"{EXPECTED_VERSION}\n", (
        f"VERSION file unexpected content: {version_text!r}"
    )


def test_plugin_json_version(plugin_data: dict[str, Any]) -> None:
    assert plugin_data["version"] == EXPECTED_VERSION


def test_pyproject_version(pyproject_data: dict[str, Any]) -> None:
    project = pyproject_data["project"]
    assert "version" not in project, "project.version must be dynamic, not a static value"
    assert "version" in project["dynamic"]
    assert pyproject_data["tool"]["hatch"]["version"]["path"] == "VERSION"


def test_nmg_game_dev_package_version() -> None:
    import importlib

    pkg = importlib.import_module("nmg_game_dev")
    assert pkg.__version__ == EXPECTED_VERSION


def test_version_triangulation(
    version_text: str, plugin_data: dict[str, Any], pyproject_data: dict[str, Any]
) -> None:
    file_version = version_text.strip()
    plugin_version = plugin_data["version"]
    # pyproject.toml takes its version from VERSION at build time, so only the plugin manifest
    # needs an equality check against the file.
    assert "version" in pyproject_data["project"]["dynamic"]
    assert pyproject_data["tool"]["hatch"]["version"]["path"] == "VERSION"
    assert file_version == plugin_version, (
        f"Version mismatch: VERSION={file_version!r}, plugin.json={plugin_version!r}"
    )
    addon_version = godot_plugin_cfg_version()
    assert file_version == addon_version, (
        f"Version mismatch: VERSION={file_version!r}, plugin.cfg={addon_version!r}"
    )


def test_stack_manifest_versions(repo_root: pathlib.Path, version_text: str) -> None:
    expected = version_text.strip()

    blender_manifest_path = (
        repo_root / "plugins" / "nmg-game-dev-blender-addon" / "blender_manifest.toml"
    )
    with blender_manifest_path.open("rb") as fh:
        blender_manifest = tomllib.load(fh)
    assert blender_manifest["version"] == expected

    assert GODOT_PLUGIN_CFG.is_file(), f"Godot add-on manifest missing: {GODOT_PLUGIN_CFG}"
    assert godot_plugin_cfg_version() == expected


def test_godot_plugin_cfg_names_the_addon_and_its_script() -> None:
    text = GODOT_PLUGIN_CFG.read_text(encoding="utf-8")
    assert text.lstrip().startswith("[plugin]")
    assert 'name="nmg-game-dev"' in text
    assert 'script="plugin.gd"' in text


def test_plugin_cfg_version_parser_reads_only_the_plugin_section(tmp_path: pathlib.Path) -> None:
    cfg = tmp_path / "plugin.cfg"
    cfg.write_text('[other]\nversion="9.9.9"\n\n[plugin]\nname="x"\nversion="1.2.3"\n')
    assert godot_plugin_cfg_version(cfg) == "1.2.3"


# --- #249: the steering snippets describe the Godot gates and version files -------------------


def _tech_snippet() -> str:
    text: str = (REPO_ROOT / "steering" / "snippets" / "project-tech.md").read_text(
        encoding="utf-8"
    )
    return text


def test_tech_versioning_table_lists_the_godot_plugin_cfg() -> None:
    versioning = _tech_snippet().split("## Versioning", 1)[1].split("\n## ", 1)[0]
    rows = [line for line in versioning.splitlines() if line.startswith("| `")]
    files = [row.split("|")[1].strip() for row in rows]
    assert files[:4] == [
        "`VERSION`",
        "`.claude-plugin/plugin.json`",
        "`plugins/nmg-game-dev-blender-addon/blender_manifest.toml`",
        "`plugins/nmg-game-dev-godot-addon/addons/nmg_game_dev/plugin.cfg`",
    ]
    plugin_cfg_row = rows[3]
    assert "`version`" in plugin_cfg_row


def _gate_rows() -> dict[str, str]:
    gates = _tech_snippet().split("## Verification Gates", 1)[1].split("\n## ", 1)[0]
    rows: dict[str, str] = {}
    for line in gates.splitlines():
        match = re.match(r"\| `([^`]+)` \|", line)
        if match:
            rows[match.group(1)] = line
    return rows


def test_tech_gate_table_registers_gate_godot_headless() -> None:
    row = _gate_rows()["gate-godot-headless"]
    for path in (
        "plugins/nmg-game-dev-godot-addon/**",
        "src/nmg_game_dev/godot/**",
        "tests/godot/**",
        "scripts/run-godot-tests.sh",
    ):
        assert f"`{path}`" in row, path
    assert "GODOT_BIN" in row
    assert ".cache/godot" in row


def test_tech_gate_table_ship_smoke_paths_match_the_manifest() -> None:
    row = _gate_rows()["gate-ship-smoke"]
    applies = row.split("|")[2]
    assert re.findall(r"`([^`]+)`", applies) == [
        "skills/ship/**",
        "src/nmg_game_dev/ship/**",
        "scripts/sign-macos.sh",
        "scripts/notarize-macos.sh",
        "scripts/ship-smoke.sh",
        "src/nmg_game_dev/godot/presets.py",
        "tests/godot/**",
    ]


def test_tech_gate_table_has_only_engine_neutral_gates() -> None:
    assert set(_gate_rows()) == {
        "repository.tests",
        "repository.lint",
        "repository.format",
        "repository.types",
        "gate-blender-headless",
        "gate-godot-headless",
        "gate-mcp-schema",
        "gate-shellcheck",
        "gate-ship-smoke",
        "plugin.validate",
        "plugin.session-smoke",
    }


def test_changelog_exists(repo_root: pathlib.Path) -> None:
    assert (repo_root / "CHANGELOG.md").is_file()


def test_changelog_has_unreleased(changelog_text: str) -> None:
    assert "## [Unreleased]" in changelog_text


def test_changelog_references_issue_1(changelog_text: str) -> None:
    assert "#1" in changelog_text


def test_claude_md_exists(repo_root: pathlib.Path) -> None:
    assert (repo_root / "CLAUDE.md").is_file()


@pytest.mark.parametrize(
    "ref",
    [
        "steering/snippets/project-product.md",
        "steering/snippets/project-tech.md",
        "steering/snippets/project-structure.md",
        "/sdlc-draft-issue",
    ],
)
def test_claude_md_references(claude_md_text: str, ref: str) -> None:
    assert ref in claude_md_text, f"CLAUDE.md missing required reference: {ref!r}"


def test_claude_md_is_pointer_only(claude_md_text: str) -> None:
    lines = claude_md_text.splitlines()
    assert len(lines) < 60, (
        f"CLAUDE.md has {len(lines)} lines — likely duplicating steering content"
    )


# --- #155: the optional ElevenLabs flow ships no server and no key handling -------------------


def test_mcp_json_has_no_elevenlabs_entry(mcp_data: dict[str, Any], mcp_text: str) -> None:
    assert "elevenlabs" not in mcp_data["mcpServers"], ".mcp.json must not declare ElevenLabs"
    assert "ELEVENLABS" not in mcp_text, ".mcp.json must not mention ELEVENLABS"


@pytest.mark.parametrize("banned", ("api.elevenlabs.io", "ELEVENLABS_API_KEY"))
def test_no_nmg_module_or_server_calls_elevenlabs(repo_root: pathlib.Path, banned: str) -> None:
    scanned = [
        *(repo_root / "src" / "nmg_game_dev").rglob("*.py"),
        *(repo_root / "mcp-servers").rglob("*.py"),
    ]
    offenders = [
        str(path.relative_to(repo_root))
        for path in scanned
        if banned in path.read_text(encoding="utf-8")
    ]
    assert not offenders, f"{banned!r} found in {offenders}"
