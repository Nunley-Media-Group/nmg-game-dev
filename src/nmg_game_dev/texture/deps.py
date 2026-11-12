"""Dependency probe for local texture generation: mflux and mlx must be importable (#143 FR2).

``missing_module`` asks the import system whether each required module can be found, without
importing it, so a host without the texture-ai dependencies fails before any worker starts or any
job is queued. ``plugin_root`` and ``run_command`` name the command that works on an Apple Silicon
Mac, which is the remediation for every missing module.
"""

from __future__ import annotations

import importlib.util
import os
import shlex
import sys
import tomllib
from collections.abc import Callable, Mapping
from pathlib import Path

from nmg_game_dev.texture.errors import TextureGenError

REQUIRED_MODULES: tuple[str, ...] = ("mflux", "mlx")
PLUGIN_ROOT_ENV = "CLAUDE_PLUGIN_ROOT"
PROJECT_NAME = "nmg-game-dev"
UNKNOWN_ROOT = Path("<plugin root>")

DepsProbe = Callable[[], str | None]


def missing_module(
    find_spec: Callable[[str], object | None] = importlib.util.find_spec,
) -> str | None:
    """Return the first required module that cannot be found, or None when all can. Never
    imports."""
    for module in REQUIRED_MODULES:
        if find_spec(module) is None:
            return module
    return None


def probe_missing(probe: DepsProbe | None = None) -> str | None:
    """Run ``probe``, or the real check when none is given. Looked up at call time, so tests can
    patch it."""
    return (missing_module if probe is None else probe)()


def _project_name(pyproject: Path) -> str | None:
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    name = data.get("project", {}).get("name")
    return name if isinstance(name, str) else None


def plugin_root(env: Mapping[str, str] | None = None) -> Path:
    """The nmg-game-dev project root: ``CLAUDE_PLUGIN_ROOT`` when set, else the checkout around
    this file."""
    env_map = os.environ if env is None else env
    raw = env_map.get(PLUGIN_ROOT_ENV, "").strip()
    if raw:
        return Path(raw).expanduser()
    for parent in Path(__file__).resolve().parents:
        if _project_name(parent / "pyproject.toml") == PROJECT_NAME:
            return parent
    return UNKNOWN_ROOT


def run_command(root: Path | None = None) -> str:
    """The generate command that runs from the plugin root, quoted for copy-paste."""
    base = plugin_root() if root is None else root
    return f"uv run --project {shlex.quote(str(base))} python -m nmg_game_dev.texture generate …"


def dependencies_missing_error(module: str) -> TextureGenError:
    """The ``texture.dependencies_missing`` error that names ``module`` and the plugin-root
    command."""
    return TextureGenError(
        "texture.dependencies_missing",
        f"The {module} module is not installed in this Python environment ({sys.executable}).",
        f"On an Apple Silicon Mac, run texture generation from the plugin root: {run_command()}",
    )


def require_dependencies(probe: DepsProbe | None = None) -> None:
    """Raise ``texture.dependencies_missing`` unless every required module can be found."""
    module = probe_missing(probe)
    if module is not None:
        raise dependencies_missing_error(module)
