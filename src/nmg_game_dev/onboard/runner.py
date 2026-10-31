"""Onboard a consumer project: preflight, then the install steps in design order (#7 FR1, FR2, AC5).

Preflight resolves the ``.uproject``, the models directory, the framework sources, git, and (only
when
a model is missing) the platform and free disk. Every failure raises ``OnboardError`` before the
first
consumer write. The steps then run in this order: scripts, settings hooks, asset contract, design
contract, design dir, agent instructions, UE plugin, VibeUE, ``.uproject`` plugins, MCP auto-start
ini, Blender add-on, texture models, texture env.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Mapping
from pathlib import Path

from nmg_game_dev.onboard.blender import DEFAULT_EXTENSIONS_DIR, link_addon
from nmg_game_dev.onboard.commands import (
    FreeBytes,
    HostFacts,
    Runner,
    Which,
    default_host,
    default_run,
)
from nmg_game_dev.onboard.errors import OnboardError
from nmg_game_dev.onboard.files import sync_file, sync_tree
from nmg_game_dev.onboard.gitignore import ensure_gitignore_env
from nmg_game_dev.onboard.instructions import upsert_block
from nmg_game_dev.onboard.report import StepResult
from nmg_game_dev.onboard.settings import merge_env, merge_session_hooks
from nmg_game_dev.onboard.textures import REQUIRED_FREE_BYTES, install_models, missing_models
from nmg_game_dev.onboard.unreal import enable_plugins, ensure_mcp_autostart, ensure_vibeue
from nmg_game_dev.texture.paths import HF_HOME_NAME, MODELS_DIR_ENV

START_SCRIPTS: tuple[str, ...] = ("start-blender-mcp.sh", "start-unreal-mcp.sh")
ASSET_CONTRACT_SRC = Path("docs/asset-contract.md")
ASSET_CONTRACT_DST = "docs/nmg-game-dev/asset-contract.md"
DESIGN_CONTRACT_SRC = Path("docs/design-contract.md")
DESIGN_CONTRACT_DST = "docs/nmg-game-dev/design-contract.md"
DESIGN_DIR_REL = "docs/design"
HOOK_TEMPLATE = Path("templates/consumer/.claude/settings.json")
UE_PLUGIN_SRC = Path("plugins/nmg-game-dev-ue-plugin")
UE_PLUGIN_DST = "Plugins/nmg-game-dev"
UE_PLUGIN_DESCRIPTOR = Path("plugins/nmg-game-dev-ue-plugin/nmg-game-dev.uplugin")
BLENDER_ADDON_MANIFEST = Path("plugins/nmg-game-dev-blender-addon/blender_manifest.toml")
INI_REL = "Config/DefaultEditorPerProjectUserSettings.ini"
EXTENSIONS_DIR_ENV = "BLENDER_EXTENSIONS_DIR"
REQUIRED_FRAMEWORK: tuple[Path, ...] = (
    Path("scripts/start-blender-mcp.sh"),
    Path("scripts/start-unreal-mcp.sh"),
    ASSET_CONTRACT_SRC,
    DESIGN_CONTRACT_SRC,
    HOOK_TEMPLATE,
    UE_PLUGIN_DESCRIPTOR,
    BLENDER_ADDON_MANIFEST,
)


def _gib(value: int) -> str:
    return f"{value / 2**30:.1f} GiB"


def resolve_uproject(consumer: Path, uproject: Path | None) -> Path:
    """The ``.uproject`` to enable: the one given, else the only one at the consumer root."""
    if uproject is not None:
        path = uproject if uproject.is_absolute() else consumer / uproject
        if not path.is_file():
            raise OnboardError(
                "onboard.uproject_not_found",
                f"No .uproject at {path}.",
                "Pass --uproject with the path to the project's .uproject file.",
            )
        return path
    found = sorted(consumer.glob("*.uproject"))
    if not found:
        raise OnboardError(
            "onboard.uproject_not_found",
            f"No .uproject in {consumer}.",
            "Run onboarding from the project root, or pass --uproject <file>.",
        )
    if len(found) > 1:
        names = ", ".join(p.name for p in found)
        raise OnboardError(
            "onboard.uproject_ambiguous",
            f"Several .uproject files in {consumer}: {names}.",
            "Pass --uproject with the one project file to onboard.",
        )
    return found[0]


def resolve_models_dir(models_dir: Path | None, env: Mapping[str, str]) -> Path:
    """The texture models root: ``--models-dir``, else ``TEXTURE_GEN_MODELS_DIR``."""
    if models_dir is not None:
        return models_dir.expanduser()
    raw = env.get(MODELS_DIR_ENV, "").strip()
    if raw:
        return Path(raw).expanduser()
    raise OnboardError(
        "onboard.models_dir_missing",
        "No texture models directory was given.",
        "Pass --models-dir <volume>/nmg-texture-models (list volumes with "
        "`python -m nmg_game_dev.onboard volumes`), or set TEXTURE_GEN_MODELS_DIR.",
    )


def _nearest_existing(path: Path) -> Path:
    current = path
    while not current.exists() and current != current.parent:
        current = current.parent
    return current


def _check_framework(framework: Path) -> None:
    missing = [str(rel) for rel in REQUIRED_FRAMEWORK if not (framework / rel).exists()]
    if missing:
        raise OnboardError(
            "onboard.framework_incomplete",
            f"The framework at {framework} is missing: {', '.join(missing)}.",
            "Set CLAUDE_PLUGIN_ROOT to a complete nmg-game-dev checkout, or reinstall the plugin.",
        )


def _check_prerequisites(
    models_root: Path,
    host: HostFacts,
    free_bytes: FreeBytes,
    which: Which,
) -> None:
    if which("git") is None:
        raise OnboardError(
            "onboard.git_missing",
            "git is not on PATH; VibeUE cannot be cloned.",
            "Install git (xcode-select --install on macOS), then re-run onboarding.",
        )
    if not missing_models(models_root):
        return
    if host.system != "Darwin" or host.machine != "arm64":
        raise OnboardError(
            "onboard.unsupported_platform",
            f"Local texture models need Apple Silicon macOS; this host is {host.system} "
            f"{host.machine}.",
            "Run onboarding on an Apple Silicon Mac, or skip the texture models on this host.",
        )
    free = free_bytes(_nearest_existing(models_root))
    if free < REQUIRED_FREE_BYTES:
        raise OnboardError(
            "onboard.insufficient_disk",
            f"{models_root} has {_gib(free)} free; the models need at least 60.0 GiB.",
            "Choose a volume with at least 60 GiB free (`python -m nmg_game_dev.onboard volumes`) "
            "and re-run with --models-dir <volume>/nmg-texture-models.",
        )


def _extensions_dir(env: Mapping[str, str]) -> Path:
    raw = env.get(EXTENSIONS_DIR_ENV, "").strip()
    return Path(raw).expanduser() if raw else DEFAULT_EXTENSIONS_DIR


def _design_dir(target: Path) -> StepResult:
    """Create ``docs/design/`` when absent. An existing directory is left alone: the design docs in
    it belong to the consumer, so they are never listed, read, or changed."""
    path = target / DESIGN_DIR_REL
    if path.is_dir():
        return StepResult("design_dir", "unchanged", f"{DESIGN_DIR_REL}/ exists")
    path.mkdir(parents=True)
    return StepResult("design_dir", "installed", f"created {DESIGN_DIR_REL}/")


def run_onboard(
    consumer: Path,
    *,
    framework: Path,
    uproject: Path | None = None,
    models_dir: Path | None = None,
    refresh: bool = False,
    env: Mapping[str, str] | None = None,
    run: Runner = default_run,
    which: Which = shutil.which,
    host: HostFacts | None = None,
    free_bytes: FreeBytes = lambda path: shutil.disk_usage(str(path)).free,
) -> list[StepResult]:
    """Onboard ``consumer`` from ``framework`` and return one StepResult per step."""
    env_map: Mapping[str, str] = os.environ if env is None else env
    facts = default_host() if host is None else host
    target = consumer.expanduser().resolve()
    if not target.is_dir():
        raise OnboardError(
            "onboard.consumer_missing",
            f"The consumer directory {target} does not exist.",
            "Pass --consumer with the project root.",
        )
    project_file = resolve_uproject(target, uproject)
    models_root = resolve_models_dir(models_dir, env_map)
    _check_framework(framework)
    _check_prerequisites(models_root, facts, free_bytes, which)

    results: list[StepResult] = []
    for script in START_SCRIPTS:
        results.append(
            sync_file(
                framework / "scripts" / script,
                target,
                f"scripts/{script}",
                name=f"scripts/{script}",
                refresh=refresh,
            )
        )
    results.append(
        merge_session_hooks(
            "settings_hooks",
            target / ".claude" / "settings.json",
            framework / HOOK_TEMPLATE,
        )
    )
    results.append(
        sync_file(
            framework / ASSET_CONTRACT_SRC,
            target,
            ASSET_CONTRACT_DST,
            name="asset_contract",
            refresh=refresh,
        )
    )
    results.append(
        sync_file(
            framework / DESIGN_CONTRACT_SRC,
            target,
            DESIGN_CONTRACT_DST,
            name="design_contract",
            refresh=refresh,
        )
    )
    results.append(_design_dir(target))
    for filename, create in (("CLAUDE.md", True), ("AGENTS.md", False)):
        block = upsert_block(f"agent_instructions:{filename}", target / filename, create=create)
        if block is not None:
            results.append(block)
    results.append(
        sync_tree(
            framework / UE_PLUGIN_SRC, target, UE_PLUGIN_DST, name="ue_plugin", refresh=refresh
        )
    )
    results.append(ensure_vibeue(target, run=run, refresh=refresh))
    results.append(enable_plugins("uproject_plugins", project_file))
    results.append(ensure_mcp_autostart("mcp_autostart_ini", target / INI_REL))
    results.append(link_addon(framework, _extensions_dir(env_map), refresh=refresh))
    results.append(install_models(models_root, run=run, which=which))
    results.append(
        merge_env(
            "texture_env",
            target / ".claude" / "settings.local.json",
            {
                MODELS_DIR_ENV: str(models_root),
                "HF_HOME": str(models_root / HF_HOME_NAME),
            },
        )
    )
    results.append(ensure_gitignore_env("gitignore_env", target / ".gitignore"))
    return results
