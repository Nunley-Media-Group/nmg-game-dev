"""Shared invariants for the issue #1 scaffold tests (BDD + unit)."""

from __future__ import annotations

import pathlib

REPO_ROOT = pathlib.Path(__file__).parent.parent.resolve()

EXPECTED_VERSION = "0.5.0"

REQUIRED_SERVERS = ("blender", "unreal", "meshy")
FLOATING_VERSION_REFS = ("latest", "main", "HEAD")

REQUIRED_DIRS = (
    ".agents/plugins",
    ".codex-plugin",
    "plugins/nmg-game-dev-blender-addon",
    "plugins/nmg-game-dev-ue-plugin",
    "skills",
    "mcp-servers",
    "scripts",
    "src/nmg_game_dev",
    "src/nmg_game_dev/pipeline",
    "src/nmg_game_dev/variants",
    "src/nmg_game_dev/quality",
    "src/nmg_game_dev/ship",
    "tests/unit",
    "tests/bdd/features",
    "tests/bdd/steps",
    "tests/blender",
    "tests/e2e/fixtures",
    "docs/onboarding",
    "docs/skills",
    "docs/mcp",
    "docs/contributing",
    "docs/decisions",
    "specs",
    "steering",
    "fixtures",
    "templates/consumer",
    "templates/consumer/.codex",
)

# Directories expected to carry a .gitkeep when otherwise empty in this issue.
GITKEEP_DIRS = (
    "plugins/nmg-game-dev-blender-addon",
    "plugins/nmg-game-dev-ue-plugin",
    "skills",
    "mcp-servers",
    "tests/unit",
    "tests/bdd/steps",
    "tests/blender",
    "tests/e2e/fixtures",
    "docs/onboarding",
    "docs/skills",
    "docs/mcp",
    "docs/contributing",
    "docs/decisions",
)

CONSUMER_FACING = (
    ".codex-plugin/plugin.json",
    ".agents/plugins/marketplace.json",
    "scripts/start-blender-mcp.sh",
    "scripts/start-unreal-mcp.sh",
    "templates/consumer/.codex/hooks.json",
    "templates/consumer/.codex/config.toml",
    ".mcp.json",
    "pyproject.toml",
)

BANNED_SUBSTRINGS = (
    "~/.cla" "ude/plugins/",
    ".cla" "ude/plugins/",
    ".cla" "ude-plugin",
    "CLA" "UDE.md",
    "Cla" "ude Code",
)

# start-unreal-mcp.sh legitimately references $PWD/fixtures/dogfood.uproject as a
# $PWD-relative contributor-mode fallback (design.md § Artifact specifications #4,
# resolution step 3). Safe for consumers: path only resolves inside nmg-game-dev.
# This list is the subset of CONSUMER_FACING that must NOT mention the dogfood fixture.
BANNED_DOGFOOD_ARTIFACTS = tuple(p for p in CONSUMER_FACING if p != "scripts/start-unreal-mcp.sh")
