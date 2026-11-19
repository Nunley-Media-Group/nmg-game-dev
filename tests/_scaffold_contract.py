"""Shared invariants for the issue #1 scaffold tests (BDD + unit), updated for Godot (#249)."""

from __future__ import annotations

import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).parent.parent.resolve()

# Derived from VERSION (the versioning source of truth) so release bumps never strand a pin.
EXPECTED_VERSION = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()

# The plugin's MCP servers. Godot runs headless only, so there is no engine server.
REQUIRED_SERVERS = ("blender", "finalize", "texture-gen", "meshy")

# Toolchain contract: the latest mcp-for-blender release; Godot is resolved at run time.
BLENDER_MCP_PACKAGE = "mcp-for-blender@latest"

# The Godot runtime add-on manifest, versioned with VERSION (steering Versioning table).
GODOT_ADDON_DIR = REPO_ROOT / "plugins" / "nmg-game-dev-godot-addon" / "addons" / "nmg_game_dev"
GODOT_PLUGIN_CFG = GODOT_ADDON_DIR / "plugin.cfg"

REQUIRED_DIRS = (
    ".claude-plugin",
    "plugins/nmg-game-dev-blender-addon",
    "plugins/nmg-game-dev-godot-addon/addons/nmg_game_dev",
    "skills",
    "mcp-servers",
    "scripts",
    "src/nmg_game_dev",
    "src/nmg_game_dev/godot",
    "src/nmg_game_dev/pipeline",
    "src/nmg_game_dev/variants",
    "src/nmg_game_dev/quality",
    "src/nmg_game_dev/ship",
    "tests/unit",
    "tests/bdd/features",
    "tests/bdd/steps",
    "tests/blender",
    "tests/godot",
    "docs/onboarding",
    "docs/skills",
    "docs/mcp",
    "docs/contributing",
    "specs",
    "steering",
    "templates/consumer",
    "templates/consumer/.claude",
)

# Directories expected to carry a .gitkeep when otherwise empty.
GITKEEP_DIRS = (
    "plugins/nmg-game-dev-blender-addon",
    "plugins/nmg-game-dev-godot-addon",
    "skills",
    "mcp-servers",
    "tests/unit",
    "tests/bdd/steps",
    "tests/blender",
    "docs/onboarding",
    "docs/skills",
    "docs/mcp",
    "docs/contributing",
)

CONSUMER_FACING = (
    ".claude-plugin/plugin.json",
    "scripts/start-blender-mcp.sh",
    "templates/consumer/.claude/settings.json",
    ".mcp.json",
    "pyproject.toml",
)

# The only launcher a consumer's SessionStart hooks run.
SESSION_START_SCRIPTS = ("start-blender-mcp.sh",)

# Legacy Codex host artifacts must not reappear in consumer-facing deliverables.
BANNED_SUBSTRINGS = (
    ".cod" + "ex/",
    "cod" + "ex_hooks",
    "Cod" + "ex",
)

# The in-repo fixture Godot project must never leak into a consumer-facing artifact.
REPO_FIXTURE_REFERENCES = ("tests/godot/fixture",)


def godot_plugin_cfg_version(path: pathlib.Path = GODOT_PLUGIN_CFG) -> str:
    """Return the quoted ``version`` value of ``plugin.cfg``'s ``[plugin]`` section."""
    section = ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        match = re.fullmatch(r'version\s*=\s*"([^"]*)"', line)
        if section == "plugin" and match:
            return match.group(1)
    raise AssertionError(f"{path} has no [plugin] version")
