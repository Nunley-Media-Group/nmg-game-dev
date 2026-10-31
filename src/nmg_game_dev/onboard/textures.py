"""Install the local texture models on the chosen disk (#7 FR7, AC4, AC5).

Model ids and their order come from the texture registry, so there is one list. ``mflux-save`` runs
one model after another with ``HF_HOME`` under the models root. ``uv tool install mflux==0.24.0``
runs only when ``mflux-save`` is not on PATH, and a model whose ``<id>-q4`` folder is already
populated is skipped.
"""

from __future__ import annotations

from pathlib import Path

from nmg_game_dev.onboard.commands import Runner, Which
from nmg_game_dev.onboard.errors import OnboardError
from nmg_game_dev.onboard.report import StepResult
from nmg_game_dev.texture.paths import HF_HOME_NAME, install_argv, install_command, weights_dir
from nmg_game_dev.texture.registry import REGISTRY

TEXTURE_MODELS: tuple[tuple[str, str], ...] = tuple(
    (spec.id, spec.repo) for spec in REGISTRY.values()
)
REQUIRED_FREE_BYTES = 60 * 2**30
MFLUX_VERSION = "0.24.0"
MFLUX_SAVE = "mflux-save"

__all__ = [
    "MFLUX_VERSION",
    "REQUIRED_FREE_BYTES",
    "TEXTURE_MODELS",
    "install_command",
    "install_models",
    "missing_models",
]


def missing_models(models_dir: Path) -> list[str]:
    """Registry ids whose ``<id>-q4`` folder is absent or empty under ``models_dir``."""
    missing: list[str] = []
    for spec in REGISTRY.values():
        folder = weights_dir(spec, models_dir)
        if not folder.is_dir() or not any(folder.iterdir()):
            missing.append(spec.id)
    return missing


def install_models(models_dir: Path, *, run: Runner, which: Which) -> StepResult:
    """Save every missing registry model with ``mflux-save --quantize 4``, one after the other."""
    missing = missing_models(models_dir)
    if not missing:
        return StepResult("texture_models", "unchanged", f"all models present in {models_dir}")
    models_dir.mkdir(parents=True, exist_ok=True)
    if which(MFLUX_SAVE) is None:
        install = run(["uv", "tool", "install", f"mflux=={MFLUX_VERSION}"], None)
        if install.returncode != 0:
            raise OnboardError(
                "onboard.mflux_install_failed",
                f"`uv tool install mflux=={MFLUX_VERSION}` failed (exit {install.returncode}).",
                "Install uv (https://docs.astral.sh/uv/), then re-run onboarding.",
            )
    hf_home = {"HF_HOME": str(models_dir / HF_HOME_NAME)}
    for backend_id in missing:
        result = run(install_argv(backend_id, models_dir), hf_home)
        if result.returncode != 0:
            raise OnboardError(
                "onboard.model_install_failed",
                f"mflux-save failed for {backend_id} (exit {result.returncode}).",
                f"Check disk space and network access, then re-run "
                f"`{install_command(backend_id, models_dir)}`.",
            )
    return StepResult(
        "texture_models",
        "installed",
        f"saved {', '.join(missing)} into {models_dir}",
    )
