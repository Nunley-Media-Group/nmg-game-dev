"""Shared fakes for the onboarding tests (#7, #249): a framework root, a fixture consumer, and stub
commands.

No test in this module runs a real ``git``, ``mflux-save``, ``uv``, or Godot. ``FakeRunner`` logs
each argv and creates the files a real model save or ``git lfs install`` would leave behind.
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path

from nmg_game_dev.onboard.commands import HostFacts
from nmg_game_dev.process import CommandResult

REPO_ROOT = Path(__file__).resolve().parents[1]
GIB = 2**30
APPLE_SILICON = HostFacts(system="Darwin", machine="arm64")


GODOT_ADDON_FILES: dict[str, str] = {
    "plugin.cfg": '[plugin]\n\nname="nmg-game-dev"\nversion="0.0.0"\nscript="plugin.gd"\n',
    "plugin.gd": "@tool\nextends EditorPlugin\n",
    "nmg_assets.gd": "extends Node\n",
    "nmg_launch.gd": "extends Node\n",
    "nmg_mission_definition.gd": "class_name NmgMissionDefinition\nextends Resource\n",
    "tests/run_tests.gd": "extends SceneTree\n",
}
"""A stand-in for ``plugins/nmg-game-dev-godot-addon/addons/nmg_game_dev``."""


def make_framework(root: Path) -> Path:
    """A framework tree with every source onboarding copies, plus fixtures and .mcp.json to
    exclude."""
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    script = scripts / "start-blender-mcp.sh"
    script.write_text("#!/usr/bin/env bash\n# start-blender-mcp.sh\n", encoding="utf-8")
    script.chmod(0o755)
    (root / "docs").mkdir()
    shutil.copy(REPO_ROOT / "docs" / "asset-contract.md", root / "docs" / "asset-contract.md")
    shutil.copy(REPO_ROOT / "docs" / "design-contract.md", root / "docs" / "design-contract.md")
    template = root / "templates" / "consumer" / ".claude"
    template.mkdir(parents=True)
    shutil.copy(REPO_ROOT / "templates" / "consumer" / ".claude" / "settings.json", template)
    godot = root / "plugins" / "nmg-game-dev-godot-addon" / "addons" / "nmg_game_dev"
    (godot / "tests").mkdir(parents=True)
    for rel, text in GODOT_ADDON_FILES.items():
        (godot / rel).parent.mkdir(parents=True, exist_ok=True)
        (godot / rel).write_text(text, encoding="utf-8")
    addon = root / "plugins" / "nmg-game-dev-blender-addon"
    addon.mkdir(parents=True)
    (addon / "blender_manifest.toml").write_text(
        'schema_version = "1.0.0"\nid = "nmg_game_dev_blender_addon"\nversion = "0.13.0"\n'
    )
    (addon / "__init__.py").write_text("bl_info = {}\n", encoding="utf-8")
    secrets = root / "src" / "nmg_game_dev" / "secrets"
    secrets.mkdir(parents=True)
    shutil.copy(REPO_ROOT / "src" / "nmg_game_dev" / "secrets" / "scan.py", secrets / "scan.py")
    (root / "fixtures").mkdir()
    (root / "fixtures" / "sample.txt").write_text("framework-only\n")
    (root / ".mcp.json").write_text('{"mcpServers": {}}\n')
    return root


def make_consumer(root: Path) -> Path:
    """A consumer with no nmg-game-dev setup: unrelated Claude settings and a CLAUDE.md."""
    consumer = root / "Game"
    consumer.mkdir(parents=True)
    (consumer / ".claude").mkdir()
    settings = {"model": "opus", "permissions": {"allow": ["Bash(ls)"]}}
    (consumer / ".claude" / "settings.json").write_text(json.dumps(settings, indent=2) + "\n")
    (consumer / "CLAUDE.md").write_text("# Game\n\nProject notes.\n", encoding="utf-8")
    return consumer


def snapshot(root: Path) -> dict[str, bytes]:
    """Every file under ``root`` mapped to its bytes, for before-and-after comparisons."""
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class FakeRunner:
    """Stands in for subprocess: logs every argv and fakes the files each command leaves behind."""

    def __init__(self, *, fail: str | None = None, work_tree: bool = False) -> None:
        self.calls: list[list[str]] = []
        self.envs: list[dict[str, str] | None] = []
        self.fail = fail
        self.work_tree = work_tree

    def __call__(self, argv: Sequence[str], env: Mapping[str, str] | None = None) -> CommandResult:
        args = list(argv)
        self.calls.append(args)
        self.envs.append(None if env is None else dict(env))
        if "rev-parse" in args and "--is-inside-work-tree" in args:
            if self.work_tree:
                return CommandResult(returncode=0, stdout="true\n")
            return CommandResult(returncode=128, stderr="fatal: not a git repository")
        if "rev-parse" in args and "--git-path" in args:
            return CommandResult(returncode=0, stdout=".git/hooks\n")
        if args[-3:] == ["lfs", "install", "--local"]:
            if self.fail == "lfs-install":
                return CommandResult(returncode=1, stderr="refusing to overwrite pre-push")
            hook = Path(args[2]) / ".git" / "hooks" / "pre-push"
            hook.parent.mkdir(parents=True, exist_ok=True)
            hook.write_text('#!/bin/sh\ngit lfs pre-push "$@"\n', encoding="utf-8")
            return CommandResult(returncode=0)
        if args[:1] == ["mflux-save"]:
            if self.fail == "mflux-save":
                return CommandResult(returncode=1, stderr="download failed")
            path = Path(args[args.index("--path") + 1])
            path.mkdir(parents=True, exist_ok=True)
            (path / "weights.safetensors").write_bytes(b"weights")
            return CommandResult(returncode=0)
        return CommandResult(returncode=0)

    def argv_starting(self, *prefix: str) -> list[list[str]]:
        return [call for call in self.calls if call[: len(prefix)] == list(prefix)]


def no_godot_tools(name: str) -> str | None:
    """Every tool is on PATH except Godot and ffmpeg."""
    return None if name in ("godot", "ffmpeg") else f"/usr/bin/{name}"


def make_executable(path: Path) -> Path:
    """Create an executable stub at ``path`` (for GODOT_BIN and FFMPEG_BIN tests)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(0o755)
    assert os.access(path, os.X_OK)
    return path


def all_tools_present(name: str) -> str | None:
    return f"/usr/bin/{name}"


def mflux_missing(name: str) -> str | None:
    return None if name == "mflux-save" else f"/usr/bin/{name}"


def gib_free(_path: Path) -> int:
    return 100 * GIB


def small_disk(_path: Path) -> int:
    return 10 * GIB
