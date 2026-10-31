"""Filesystem locations for texture models and generated output (#7 FR13, AC14, AC20).

``install_argv`` and ``install_command`` are the single source of the ``mflux-save`` command. The
onboarding step (``nmg_game_dev.onboard.textures``) imports them, so the install and the
remediation text never drift apart.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Mapping
from pathlib import Path

from nmg_game_dev.texture.registry import BackendSpec

MODELS_DIR_ENV = "TEXTURE_GEN_MODELS_DIR"
HF_HOME_NAME = "hf-cache"
OUTPUT_DIR_ENV = "NMG_GAME_DEV_TEXTURE_DIR"
PROJECT_DIR_ENV = "CLAUDE_PROJECT_DIR"
DEFAULT_OUTPUT_SUBDIR = Path("SourceArt") / "Textures" / "Generated"
SLUG_MAX_LENGTH = 48


def models_dir(env: Mapping[str, str]) -> Path | None:
    """The models root from ``TEXTURE_GEN_MODELS_DIR``, or None when it is unset or blank."""
    raw = env.get(MODELS_DIR_ENV, "").strip()
    return Path(raw).expanduser() if raw else None


def weights_dir(spec: BackendSpec, root: Path) -> Path:
    """Where the saved 4-bit weights of ``spec`` live: ``<root>/<id>-q4``."""
    return root / f"{spec.id}-q4"


def install_argv(backend_id: str, root: Path) -> list[str]:
    """The ``mflux-save`` argument vector that saves ``backend_id`` into ``root``."""
    return [
        "mflux-save",
        "--model",
        backend_id,
        "--quantize",
        "4",
        "--path",
        str(root / f"{backend_id}-q4"),
    ]


def install_command(backend_id: str, root: Path) -> str:
    """The shell form of :func:`install_argv`, quoted for copy-paste."""
    return shlex.join(install_argv(backend_id, root))


def output_root(env: Mapping[str, str], cwd: Path) -> Path:
    """Where generated textures go: ``NMG_GAME_DEV_TEXTURE_DIR``, else the project's SourceArt."""
    override = env.get(OUTPUT_DIR_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    project = env.get(PROJECT_DIR_ENV, "").strip()
    base = Path(project) if project else cwd
    return base / DEFAULT_OUTPUT_SUBDIR


def slugify(text: str) -> str:
    """Kebab-case name of at most 48 characters, derived from a prompt."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    slug = slug[:SLUG_MAX_LENGTH].strip("-")
    return slug or "texture"
