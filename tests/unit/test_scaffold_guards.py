"""Scaffold guard unit tests for issue #1.

Each test function's name encodes the T015* sub-task and covering AC:
  plugin_json_schema           — T015a / AC1
  directory_exists             — T015b / AC2
  mcp_json_*                   — T015c / AC8
  no_leak_* / no_dogfood_*     — T015d / AC10, AC11
  no_repo_root_settings_json   — T015e / AC5b
  version_* / nmg_*_version    — T015f / AC7
  changelog_*                  — T015g / AC7
  agents_md_*                  — T015h / AC9
"""

from __future__ import annotations

import pathlib
import tomllib
from typing import Any

import pytest
from _scaffold_contract import (
    BANNED_DOGFOOD_ARTIFACTS,
    BANNED_SUBSTRINGS,
    CONSUMER_FACING,
    EXPECTED_VERSION,
    FLOATING_VERSION_REFS,
    REQUIRED_DIRS,
    REQUIRED_SERVERS,
)


def test_plugin_json_schema(plugin_data: dict[str, Any]) -> None:
    for field in ("name", "version", "description", "author", "skills"):
        assert field in plugin_data, f"plugin.json missing required field: {field!r}"

    assert plugin_data["name"] == "nmg-game-dev"
    assert plugin_data["version"] == EXPECTED_VERSION
    assert plugin_data["author"]["name"] == "Nunley Media Group"
    assert plugin_data["skills"] == "./skills/"
    assert "capabilities" not in plugin_data
    assert "requires" not in plugin_data


def test_marketplace_points_to_local_plugin(marketplace_data: dict[str, Any]) -> None:
    assert marketplace_data["name"] == "nmg-game-dev"
    entry = marketplace_data["plugins"][0]
    assert entry["name"] == "nmg-game-dev"
    assert entry["source"] == {"source": "local", "path": "."}
    assert entry["policy"]["installation"] == "AVAILABLE"
    assert entry["policy"]["authentication"] == "ON_INSTALL"


def test_consumer_codex_hooks_template(repo_root: pathlib.Path) -> None:
    assert (repo_root / "templates" / "consumer" / ".codex" / "hooks.json").is_file()
    assert (repo_root / "templates" / "consumer" / ".codex" / "config.toml").is_file()


def test_consumer_codex_config_enables_hooks(
    consumer_config_data: dict[str, Any],
) -> None:
    assert consumer_config_data["features"]["codex_hooks"] is True
    for server in REQUIRED_SERVERS:
        assert server in consumer_config_data["mcp_servers"]


@pytest.mark.parametrize("rel_dir", REQUIRED_DIRS)
def test_directory_exists(repo_root: pathlib.Path, rel_dir: str) -> None:
    assert (repo_root / rel_dir).is_dir(), f"Directory missing: {rel_dir}"


def test_mcp_json_exists(repo_root: pathlib.Path) -> None:
    assert (repo_root / ".mcp.json").is_file(), ".mcp.json missing at repo root"


def test_mcp_json_all_servers_declared(mcp_data: dict[str, Any]) -> None:
    for server in REQUIRED_SERVERS:
        assert server in mcp_data["mcpServers"], f".mcp.json missing server: {server!r}"


@pytest.mark.parametrize("banned", FLOATING_VERSION_REFS)
def test_mcp_json_no_floating_versions(mcp_text: str, banned: str) -> None:
    assert banned not in mcp_text, f".mcp.json contains floating version ref: {banned!r}"


def test_mcp_json_meshy_has_env(mcp_data: dict[str, Any]) -> None:
    meshy = mcp_data["mcpServers"]["meshy"]
    assert "env" in meshy, "meshy server entry missing env block"
    assert "MESHY_API_KEY" in meshy["env"], "meshy env missing MESHY_API_KEY"


@pytest.mark.parametrize("artifact", CONSUMER_FACING)
@pytest.mark.parametrize(
    "banned",
    BANNED_SUBSTRINGS,
    ids=[
        "legacy-user-plugin-path",
        "legacy-project-plugin-path",
        "legacy-plugin-manifest-dir",
        "legacy-pointer-doc",
        "legacy-host-name",
    ],
)
def test_no_leak_consumer_artifacts(artifact_text: Any, artifact: str, banned: str) -> None:
    assert banned not in artifact_text(artifact), f"Banned substring {banned!r} found in {artifact}"


@pytest.mark.parametrize("artifact", BANNED_DOGFOOD_ARTIFACTS)
def test_no_dogfood_reference_in_non_launcher_artifacts(artifact_text: Any, artifact: str) -> None:
    assert "fixtures/dogfood.uproject" not in artifact_text(artifact), (
        f"Dogfood fixture reference found in {artifact} (AC10 leak)"
    )


def test_no_repo_root_settings_json(repo_root: pathlib.Path) -> None:
    assert not (repo_root / ".codex" / "hooks.json").exists(), (
        ".codex/hooks.json found at repo root — must not exist. "
        "SessionStart hooks belong in templates/consumer/.codex/hooks.json only."
    )


def test_version_file(version_text: str) -> None:
    assert version_text == f"{EXPECTED_VERSION}\n", (
        f"VERSION file unexpected content: {version_text!r}"
    )


def test_plugin_json_version(plugin_data: dict[str, Any]) -> None:
    assert plugin_data["version"] == EXPECTED_VERSION


def test_pyproject_version(pyproject_data: dict[str, Any]) -> None:
    assert pyproject_data["project"]["version"] == EXPECTED_VERSION


def test_nmg_game_dev_package_version() -> None:
    import importlib

    pkg = importlib.import_module("nmg_game_dev")
    assert pkg.__version__ == EXPECTED_VERSION


def test_version_triangulation(
    version_text: str, plugin_data: dict[str, Any], pyproject_data: dict[str, Any]
) -> None:
    file_version = version_text.strip()
    plugin_version = plugin_data["version"]
    pyproject_version = pyproject_data["project"]["version"]
    assert file_version == plugin_version == pyproject_version, (
        f"Version mismatch: VERSION={file_version!r},"
        f" plugin.json={plugin_version!r},"
        f" pyproject.toml={pyproject_version!r}"
    )


def test_stack_manifest_versions(repo_root: pathlib.Path, version_text: str) -> None:
    expected = version_text.strip()

    blender_manifest_path = (
        repo_root / "plugins" / "nmg-game-dev-blender-addon" / "blender_manifest.toml"
    )
    with blender_manifest_path.open("rb") as fh:
        blender_manifest = tomllib.load(fh)
    assert blender_manifest["version"] == expected

    import json

    ue_manifest_path = repo_root / "plugins" / "nmg-game-dev-ue-plugin" / "nmg-game-dev.uplugin"
    with ue_manifest_path.open() as fh:
        ue_manifest = json.load(fh)
    assert ue_manifest["VersionName"] == expected


def test_changelog_exists(repo_root: pathlib.Path) -> None:
    assert (repo_root / "CHANGELOG.md").is_file()


def test_changelog_has_unreleased(changelog_text: str) -> None:
    assert "## [Unreleased]" in changelog_text


def test_changelog_references_issue_1(changelog_text: str) -> None:
    assert "#1" in changelog_text


def test_agents_md_exists(repo_root: pathlib.Path) -> None:
    assert (repo_root / "AGENTS.md").is_file()


@pytest.mark.parametrize(
    "ref",
    ["steering/product.md", "steering/tech.md", "steering/structure.md", "$nmg-sdlc:draft-issue"],
)
def test_agents_md_references(agents_md_text: str, ref: str) -> None:
    assert ref in agents_md_text, f"AGENTS.md missing required reference: {ref!r}"


def test_agents_md_is_pointer_only(agents_md_text: str) -> None:
    lines = agents_md_text.splitlines()
    assert len(lines) < 60, (
        f"AGENTS.md has {len(lines)} lines — likely duplicating steering content"
    )
