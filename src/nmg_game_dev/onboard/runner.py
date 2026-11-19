"""Onboard a consumer project: preflight, then the install steps in design order (#7, #249 FR10).

Preflight checks the game directory, the models directory, the framework sources, git, git-lfs, and
(only when a model is missing) the platform and free disk. Every failure raises ``OnboardError``
before the first consumer write. The steps then run in this order: the Blender start script,
settings hooks, asset contract, design contract, design dir, agent instructions, Godot project,
Godot add-on, export presets, Godot and ffmpeg checks, Blender add-on, texture models, texture env,
gitignore env, gitattributes LFS, git LFS hooks, secret scanner, pre-commit hook.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Mapping
from pathlib import Path

from nmg_game_dev.godot.binary import DEFAULT_GODOT_APP_BINARY
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
from nmg_game_dev.onboard.godot import (
    ADDON_REL,
    PRESETS_FILE,
    PROJECT_FILE,
    ensure_export_presets,
    ensure_godot_project,
    find_ffmpeg,
    find_godot,
    project_name_of,
)
from nmg_game_dev.onboard.instructions import upsert_block
from nmg_game_dev.onboard.lfs import ensure_gitattributes_lfs, ensure_lfs_hooks
from nmg_game_dev.onboard.report import StepResult
from nmg_game_dev.onboard.secrets_hook import ensure_precommit_hook, ensure_secret_scanner
from nmg_game_dev.onboard.settings import merge_env, merge_session_hooks
from nmg_game_dev.onboard.textures import REQUIRED_FREE_BYTES, install_models, missing_models
from nmg_game_dev.texture.paths import HF_HOME_NAME, MODELS_DIR_ENV

START_SCRIPTS: tuple[str, ...] = ("start-blender-mcp.sh",)
ASSET_CONTRACT_SRC = Path("docs/asset-contract.md")
ASSET_CONTRACT_DST = "docs/nmg-game-dev/asset-contract.md"
DESIGN_CONTRACT_SRC = Path("docs/design-contract.md")
DESIGN_CONTRACT_DST = "docs/nmg-game-dev/design-contract.md"
DESIGN_DIR_REL = "docs/design"
HOOK_TEMPLATE = Path("templates/consumer/.claude/settings.json")
GODOT_ADDON_SRC = Path("plugins/nmg-game-dev-godot-addon/addons/nmg_game_dev")
GODOT_ADDON_IGNORE: tuple[str, ...] = ("tests",)
BLENDER_ADDON_MANIFEST = Path("plugins/nmg-game-dev-blender-addon/blender_manifest.toml")
SECRETS_SCANNER_SRC = Path("src/nmg_game_dev/secrets/scan.py")
EXTENSIONS_DIR_ENV = "BLENDER_EXTENSIONS_DIR"
DEFAULT_GAME_DIR = "game"
REQUIRED_FRAMEWORK: tuple[Path, ...] = (
    Path("scripts/start-blender-mcp.sh"),
    ASSET_CONTRACT_SRC,
    DESIGN_CONTRACT_SRC,
    HOOK_TEMPLATE,
    GODOT_ADDON_SRC / "plugin.cfg",
    BLENDER_ADDON_MANIFEST,
    SECRETS_SCANNER_SRC,
)


def _gib(value: int) -> str:
    return f"{value / 2**30:.1f} GiB"


def resolve_game_dir(game_dir: str) -> str:
    """The Godot project folder relative to the consumer root (default ``game``)."""
    rel = Path(game_dir)
    if not game_dir.strip() or rel.is_absolute() or ".." in rel.parts:
        raise OnboardError(
            "onboard.game_dir_invalid",
            f"--game-dir {game_dir!r} is not a folder inside the consumer.",
            "Pass --game-dir with a relative folder such as game.",
        )
    return rel.as_posix()


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
            "git is not on PATH; the Git LFS setup needs it.",
            "Install git (xcode-select --install on macOS), then re-run onboarding.",
        )
    if which("git-lfs") is None:
        raise OnboardError(
            "onboard.git_lfs_missing",
            "git-lfs is not on PATH; binary assets cannot be tracked in Git LFS.",
            "Install Git LFS (brew install git-lfs), then re-run onboarding.",
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
    game_dir: str = DEFAULT_GAME_DIR,
    models_dir: Path | None = None,
    refresh: bool = False,
    env: Mapping[str, str] | None = None,
    run: Runner = default_run,
    which: Which = shutil.which,
    host: HostFacts | None = None,
    free_bytes: FreeBytes = lambda path: shutil.disk_usage(str(path)).free,
    godot_app: Path = DEFAULT_GODOT_APP_BINARY,
) -> list[StepResult]:
    """Onboard ``consumer`` from ``framework`` and return one StepResult per step.

    ``game_dir`` is the Godot project folder relative to the consumer root. ``godot_app`` is the
    last place the Godot executable is looked for, after ``GODOT_BIN`` and ``godot`` on PATH.
    """
    env_map: Mapping[str, str] = os.environ if env is None else env
    facts = default_host() if host is None else host
    target = consumer.expanduser().resolve()
    if not target.is_dir():
        raise OnboardError(
            "onboard.consumer_missing",
            f"The consumer directory {target} does not exist.",
            "Pass --consumer with the project root.",
        )
    game_rel = resolve_game_dir(game_dir)
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
    game = target / game_rel
    project_name = project_name_of(game / PROJECT_FILE, target.name)
    results.append(
        ensure_godot_project("godot_project", game / PROJECT_FILE, project_name, refresh=refresh)
    )
    results.append(
        sync_tree(
            framework / GODOT_ADDON_SRC,
            target,
            f"{game_rel}/{ADDON_REL}",
            name="godot_addon",
            refresh=refresh,
            ignore=GODOT_ADDON_IGNORE,
        )
    )
    results.append(
        ensure_export_presets(
            "export_presets",
            game / PRESETS_FILE,
            project_name_of(game / PROJECT_FILE, project_name),
            refresh=refresh,
        )
    )
    results.append(find_godot("godot_binary", env_map, which, default_app=godot_app))
    results.append(find_ffmpeg("ffmpeg_binary", env_map, which))
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
    results.append(ensure_gitignore_env("gitignore_env", target / ".gitignore", game_dir=game_rel))
    results.append(
        ensure_gitattributes_lfs("gitattributes_lfs", target / ".gitattributes", refresh=refresh)
    )
    results.append(ensure_lfs_hooks("git_lfs_hooks", target, run=run))
    results.append(ensure_secret_scanner("secret_scanner", framework, target, refresh))
    results.append(ensure_precommit_hook("precommit_hook", target, run=run))
    return results
