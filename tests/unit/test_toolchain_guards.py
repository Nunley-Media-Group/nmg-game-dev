"""Toolchain guards: the latest Blender MCP and add-on, and Godot 4 resolved headless, never pinned.

blender_candidate_order_*     — #68 AC5: the blender_mcp add-on is probed first
install_scripts_*             — #68 AC6: no tag, commit, or version pin
mcp_json_blender_*            — the Blender MCP server tracks its latest release
godot_*                       — #249 FR2, FR14: Godot resolves from GODOT_BIN, then PATH, and the
                                gate downloads the latest stable release, never a pinned one
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from _scaffold_contract import BLENDER_MCP_PACKAGE, REPO_ROOT

from nmg_game_dev.godot import resolve_godot
from nmg_game_dev.pipeline.errors import PipelineError

BLENDER_LAUNCHER = REPO_ROOT / "scripts" / "start-blender-mcp.sh"
GODOT_TEST_RUNNER = REPO_ROOT / "scripts" / "run-godot-tests.sh"
GODOT_BINARY_MODULE = REPO_ROOT / "src" / "nmg_game_dev" / "godot" / "binary.py"

INSTALL_SCRIPTS = ("install-blender-mcp-addon.sh",)
BLENDER_CANDIDATES = (
    "blender_mcp",
    "bl_ext.user_default.blender_mcp",
    "blender-mcp-addon",
    "bl_ext.user_default.blender-mcp",
    "blender-mcp",
)
# A Godot 4 release tag or archive name, such as 4.3-stable or Godot_v4.3-stable_macos.
GODOT_VERSION_LITERAL = re.compile(r"\b4\.\d+(?:\.\d+)?-stable\b|Godot_v4\.\d")


def _code_lines(path: Path) -> str:
    """Return a script's text with comment-only lines removed."""
    text = path.read_text(encoding="utf-8")
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def test_blender_candidate_order_prefers_blender_mcp_addon() -> None:
    text = BLENDER_LAUNCHER.read_text(encoding="utf-8")
    block = re.search(r"candidates \+= \[(.*?)\]", text, re.DOTALL)
    assert block is not None, "start-blender-mcp.sh has no candidates += [...] block"
    assert tuple(re.findall(r'"([^"]+)"', block.group(1))) == BLENDER_CANDIDATES


@pytest.mark.parametrize("name", INSTALL_SCRIPTS)
def test_install_scripts_pin_no_tag_commit_or_version(name: str) -> None:
    code = _code_lines(REPO_ROOT / "scripts" / name)
    for pattern in (r"--tags", r"\bcheckout\b", r"\btags?\b", r"==", r"@\d", r"--branch"):
        assert not re.search(pattern, code), f"{name} pins a version via {pattern!r}"


def test_install_blender_addon_runs_latest_install_addon() -> None:
    code = _code_lines(REPO_ROOT / "scripts" / "install-blender-mcp-addon.sh")
    assert "uvx mcp-for-blender@latest install-addon" in code
    assert "command -v uvx" in code


def test_mcp_json_blender_tracks_latest() -> None:
    servers = json.loads((REPO_ROOT / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]
    assert servers["blender"]["args"] == [BLENDER_MCP_PACKAGE]


def _executable(path: Path) -> Path:
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def test_godot_resolves_env_then_path_then_app(tmp_path: Path) -> None:
    env_bin = _executable(tmp_path / "env-godot")
    path_bin = _executable(tmp_path / "path-godot")
    app_bin = _executable(tmp_path / "Godot")
    on_path = {"godot": str(path_bin)}

    def which(name: str) -> str | None:
        return on_path.get(name)

    def no_which(name: str) -> str | None:
        return None

    env = {"GODOT_BIN": str(env_bin)}
    assert resolve_godot(env, which, default_app=app_bin) == env_bin
    assert resolve_godot({}, which, default_app=app_bin) == path_bin
    assert resolve_godot({}, no_which, default_app=app_bin) == app_bin
    with pytest.raises(PipelineError) as raised:
        resolve_godot({}, no_which, default_app=tmp_path / "absent")
    assert raised.value.code == "godot.not_found"
    assert "latest stable" in raised.value.remediation


def test_godot_resolver_names_no_version() -> None:
    code = GODOT_BINARY_MODULE.read_text(encoding="utf-8")
    assert not GODOT_VERSION_LITERAL.search(code), "binary.py names a Godot version"


def test_godot_gate_downloads_the_latest_stable_release() -> None:
    code = _code_lines(GODOT_TEST_RUNNER)
    assert "GODOT_BIN" in code
    assert "command -v godot" in code
    assert "releases/latest" in code
    assert ".cache/godot" in code
    assert not GODOT_VERSION_LITERAL.search(code), "run-godot-tests.sh pins a Godot version"


def test_godot_cache_is_git_ignored() -> None:
    ignored = {line.strip() for line in (REPO_ROOT / ".gitignore").read_text().splitlines()}
    assert ".cache/godot/" in ignored or ".cache/" in ignored
