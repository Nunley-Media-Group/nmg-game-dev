"""Toolchain guards for issue #68: UE 5.8, native Unreal MCP plus VibeUE, latest Blender MCP.

uproject_* / uplugin_* / fixture_*  — AC1, AC2: engine version, fixture plugins, INI, tracking
launcher_* / ue_test_runner_*       — AC1, AC2: 5.8 default, port 8000, native-server flags
blender_candidate_order_*           — AC5: blender_mcp add-on probed first
install_scripts_*                   — AC6: no tag, commit, or version pin
no_stale_ue_5_7_reference           — AC1: no UE 5.7 reference outside specs/ and CHANGELOG.md
"""

from __future__ import annotations

import json
import os
import pathlib
import re
from collections.abc import Iterator

import pytest
from _scaffold_contract import REPO_ROOT, UE_VERSION

DOGFOOD = REPO_ROOT / "fixtures" / "dogfood.uproject"
UPLUGIN = REPO_ROOT / "plugins" / "nmg-game-dev-ue-plugin" / "nmg-game-dev.uplugin"
EDITOR_SETTINGS = REPO_ROOT / "fixtures" / "Config" / "DefaultEditorPerProjectUserSettings.ini"
UNREAL_LAUNCHER = REPO_ROOT / "scripts" / "start-unreal-mcp.sh"
UE_TEST_RUNNER = REPO_ROOT / "scripts" / "run-ue-tests.sh"
BLENDER_LAUNCHER = REPO_ROOT / "scripts" / "start-blender-mcp.sh"

FIXTURE_PLUGINS = ("ModelContextProtocol", "EditorToolset", "VibeUE", "nmg-game-dev")
FIXTURE_TRACKED_FILES = (
    "fixtures/Source/Dogfood.Target.cs",
    "fixtures/Source/DogfoodEditor.Target.cs",
    "fixtures/Source/Dogfood/Dogfood.Build.cs",
    "fixtures/Config/DefaultEngine.ini",
    "fixtures/Config/DefaultInput.ini",
)
INSTALL_SCRIPTS = ("install-vibeue.sh", "install-blender-mcp-addon.sh")
BLENDER_CANDIDATES = (
    "blender_mcp",
    "bl_ext.user_default.blender_mcp",
    "blender-mcp-addon",
    "bl_ext.user_default.blender-mcp",
    "blender-mcp",
)

STALE_UE_REFERENCES = ("UE_5.7", "5.7.0", "Unreal Engine 5.7")
SCAN_SKIP_DIRS = frozenset(
    {
        ".git",
        ".nmg-sdlc",
        ".venv",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        "__pycache__",
        "specs",
        "Intermediate",
        "Saved",
        "Binaries",
        "ue-automation",
    }
)
# CHANGELOG.md keeps released history. This module names the stale tokens as data.
SCAN_SKIP_FILES = frozenset({"CHANGELOG.md", "tests/unit/test_toolchain_guards.py"})


def _code_lines(path: pathlib.Path) -> str:
    """Return a script's text with comment-only lines removed."""
    return "\n".join(
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )


def _repo_text_files() -> Iterator[pathlib.Path]:
    for root, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [d for d in dirs if d not in SCAN_SKIP_DIRS]
        for name in files:
            path = pathlib.Path(root) / name
            rel = path.relative_to(REPO_ROOT).as_posix()
            if rel in SCAN_SKIP_FILES or rel.startswith("fixtures/Plugins/"):
                continue
            yield path


def test_uproject_targets_ue_5_8() -> None:
    project = json.loads(DOGFOOD.read_text(encoding="utf-8"))
    assert project["EngineAssociation"] == UE_VERSION


def test_uproject_enables_native_mcp_vibeue_and_nmg_plugin() -> None:
    project = json.loads(DOGFOOD.read_text(encoding="utf-8"))
    enabled = {entry["Name"] for entry in project["Plugins"] if entry.get("Enabled") is True}
    missing = [name for name in FIXTURE_PLUGINS if name not in enabled]
    assert not missing, f"dogfood.uproject does not enable: {missing}"


def test_uproject_keeps_repo_plugin_directory() -> None:
    project = json.loads(DOGFOOD.read_text(encoding="utf-8"))
    assert project["AdditionalPluginDirectories"] == ["../plugins"]


def test_uplugin_declares_ue_5_8_engine() -> None:
    manifest = json.loads(UPLUGIN.read_text(encoding="utf-8"))
    assert manifest["EngineVersion"] == f"{UE_VERSION}.0"


def test_editor_settings_auto_start_native_server_on_8000() -> None:
    settings = EDITOR_SETTINGS.read_text(encoding="utf-8")
    assert "[/Script/ModelContextProtocolEngine.ModelContextProtocolSettings]" in settings
    assert "bAutoStartServer=True" in settings
    assert "ServerPortNumber=8000" in settings


def test_fixture_source_and_config_are_tracked_not_ignored() -> None:
    ignored = {line.strip() for line in (REPO_ROOT / ".gitignore").read_text().splitlines()}
    assert "fixtures/Config/" not in ignored
    assert "fixtures/Source/" not in ignored
    assert "fixtures/Plugins/" in ignored


@pytest.mark.parametrize("rel", FIXTURE_TRACKED_FILES)
def test_fixture_source_and_config_files_exist(rel: str) -> None:
    assert (REPO_ROOT / rel).is_file(), f"fixture file missing: {rel}"


def test_unreal_launcher_defaults_to_port_8000_and_ue_5_8() -> None:
    text = UNREAL_LAUNCHER.read_text(encoding="utf-8")
    assert 'PORT="${UE_MCP_PORT:-8000}"' in text
    assert 'UE_ROOT="${UE_ROOT:-/Users/Shared/Epic Games/UE_5.8}"' in text


def test_unreal_launcher_passes_native_server_flags() -> None:
    code = _code_lines(UNREAL_LAUNCHER)
    assert "-ModelContextProtocolStartServer" in code
    assert '-ModelContextProtocolPort="${PORT}"' in code
    assert "-unattended" in code


def test_ue_test_runner_defaults_to_ue_5_8() -> None:
    text = UE_TEST_RUNNER.read_text(encoding="utf-8")
    assert 'UE_ROOT="${UE_ROOT:-/Users/Shared/Epic Games/UE_5.8}"' in text


def test_blender_candidate_order_prefers_blender_mcp_addon() -> None:
    text = BLENDER_LAUNCHER.read_text(encoding="utf-8")
    block = re.search(r"candidates \+= \[(.*?)\]", text, re.DOTALL)
    assert block is not None, "start-blender-mcp.sh has no candidates += [...] block"
    assert tuple(re.findall(r'"([^"]+)"', block.group(1))) == BLENDER_CANDIDATES


@pytest.mark.parametrize("name", INSTALL_SCRIPTS)
def test_install_scripts_pin_no_tag_commit_or_version(name: str) -> None:
    code = _code_lines(REPO_ROOT / "scripts" / name)
    for pattern in (r"--branch", r"--tags", r"\bcheckout\b", r"\btags?\b", r"==", r"@\d"):
        assert not re.search(pattern, code), f"{name} pins a version via {pattern!r}"


def test_install_vibeue_clones_default_branch_shallow() -> None:
    code = _code_lines(REPO_ROOT / "scripts" / "install-vibeue.sh")
    assert "git clone --depth 1" in code
    assert "pull --ff-only" in code
    assert "rev-parse --short HEAD" in code


def test_install_blender_addon_runs_latest_install_addon() -> None:
    code = _code_lines(REPO_ROOT / "scripts" / "install-blender-mcp-addon.sh")
    assert "uvx mcp-for-blender@latest install-addon" in code
    assert "command -v uvx" in code


def test_no_stale_ue_5_7_reference() -> None:
    hits: list[str] = []
    for path in _repo_text_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for token in STALE_UE_REFERENCES:
            if token in text:
                hits.append(f"{path.relative_to(REPO_ROOT).as_posix()}: {token}")
    assert not hits, "UE 5.7 references remain:\n" + "\n".join(hits)
