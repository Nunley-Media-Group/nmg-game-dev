"""Shared fakes for the #7 onboarding tests: a framework root, a fixture consumer, and stub
commands.

No test in this module runs a real ``git``, ``mflux-save``, or ``uv``. ``FakeRunner`` logs each argv
and creates the files a real clone or model save would leave behind.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path

from nmg_game_dev.onboard.commands import CommandResult, HostFacts

REPO_ROOT = Path(__file__).resolve().parents[1]
GIB = 2**30
PINNED_COMMIT = "bc7bc45c1e2025123778560f45c15d1f8e1be41d"
APPLE_SILICON = HostFacts(system="Darwin", machine="arm64")


def make_framework(root: Path) -> Path:
    """A framework tree with every source onboarding copies, plus fixtures and .mcp.json to
    exclude."""
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    for name in ("start-blender-mcp.sh", "start-unreal-mcp.sh"):
        script = scripts / name
        script.write_text(f"#!/usr/bin/env bash\n# {name}\n", encoding="utf-8")
        script.chmod(0o755)
    (root / "docs").mkdir()
    shutil.copy(REPO_ROOT / "docs" / "asset-contract.md", root / "docs" / "asset-contract.md")
    template = root / "templates" / "consumer" / ".claude"
    template.mkdir(parents=True)
    shutil.copy(REPO_ROOT / "templates" / "consumer" / ".claude" / "settings.json", template)
    ue = root / "plugins" / "nmg-game-dev-ue-plugin"
    (ue / "Source" / "NmgGameDevRuntime" / "Public").mkdir(parents=True)
    (ue / "nmg-game-dev.uplugin").write_text('{"FileVersion": 3, "VersionName": "0.13.0"}\n')
    (ue / "Source" / "NmgGameDevRuntime" / "Public" / "NmgAssetResolver.h").write_text(
        "#pragma once\n"
    )
    (ue / "Binaries" / "Linux").mkdir(parents=True)
    (ue / "Binaries" / "Linux" / "junk.so").write_bytes(b"built")
    (ue / "Intermediate" / "Build").mkdir(parents=True)
    (ue / "Intermediate" / "Build" / "junk.txt").write_text("generated\n")
    addon = root / "plugins" / "nmg-game-dev-blender-addon"
    addon.mkdir(parents=True)
    (addon / "blender_manifest.toml").write_text(
        'schema_version = "1.0.0"\nid = "nmg_game_dev_blender_addon"\nversion = "0.13.0"\n'
    )
    (addon / "__init__.py").write_text("bl_info = {}\n", encoding="utf-8")
    (root / "fixtures").mkdir()
    (root / "fixtures" / "dogfood.uproject").write_text("{}\n")
    (root / ".mcp.json").write_text('{"mcpServers": {}}\n')
    return root


def make_consumer(root: Path) -> Path:
    """A consumer with one .uproject, unrelated Claude settings, and an existing CLAUDE.md."""
    consumer = root / "Game"
    consumer.mkdir(parents=True)
    uproject = {
        "FileVersion": 3,
        "EngineAssociation": "5.8",
        "Modules": [{"Name": "Game", "Type": "Runtime"}],
        "Plugins": [{"Name": "Other", "Enabled": True}],
        "Description": "keep me",
    }
    (consumer / "Game.uproject").write_text(json.dumps(uproject, indent="\t") + "\n")
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

    def __init__(self, *, head: str = PINNED_COMMIT, fail: str | None = None) -> None:
        self.calls: list[list[str]] = []
        self.envs: list[dict[str, str] | None] = []
        self.head = head
        self.fail = fail

    def __call__(self, argv: Sequence[str], env: Mapping[str, str] | None = None) -> CommandResult:
        args = list(argv)
        self.calls.append(args)
        self.envs.append(None if env is None else dict(env))
        if args[:2] == ["git", "clone"]:
            if self.fail == "clone":
                return CommandResult(returncode=128, stderr="clone refused")
            target = Path(args[-1])
            (target / ".git").mkdir(parents=True)
            (target / "VibeUE.uplugin").write_text('{"FileVersion": 3}\n')
            return CommandResult(returncode=0)
        if "rev-parse" in args:
            return CommandResult(returncode=0, stdout=f"{self.head}\n")
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


def all_tools_present(name: str) -> str | None:
    return f"/usr/bin/{name}"


def mflux_missing(name: str) -> str | None:
    return None if name == "mflux-save" else f"/usr/bin/{name}"


def gib_free(_path: Path) -> int:
    return 100 * GIB


def small_disk(_path: Path) -> int:
    return 10 * GIB
