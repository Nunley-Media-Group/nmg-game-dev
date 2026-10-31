"""Lockfile helpers for the uv lock guards (#95; FR5, FR6; AC6, AC7).

``lock_check`` runs ``uv lock --check --offline`` and never relocks: a stale project is reported,
not repaired. ``copy_projects`` copies the root and both mcp-servers sub-projects with their
relative layout intact, because the sub-projects reach the root through ``../..``.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
_ROOT_FILES: Final[tuple[str, ...]] = ("pyproject.toml", "uv.lock", "VERSION", "CLAUDE.md")
_SKIP_WHEN_COPYING = shutil.ignore_patterns(".venv", "__pycache__", ".pytest_cache", "*.egg-info")


def project_dirs(root: Path = REPO_ROOT) -> list[Path]:
    """Return the root project, then each mcp-servers/* project that has a pyproject.toml."""
    servers = sorted(path.parent for path in (root / "mcp-servers").glob("*/pyproject.toml"))
    return [root, *servers]


def label(project: Path, root: Path = REPO_ROOT) -> str:
    """Return the project's directory relative to root ('.' for the root itself)."""
    return project.relative_to(root).as_posix()


def lock_check(project: Path, root: Path = REPO_ROOT) -> str | None:
    """Return None when project's uv.lock matches its pyproject.toml, else a message naming it."""
    result = subprocess.run(
        ["uv", "lock", "--check", "--offline"],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return None
    name = label(project, root)
    return (
        f"{name}/uv.lock is out of sync with {name}/pyproject.toml; "
        f"run `uv lock` in {name} and commit the result.\n{result.stderr.strip()}"
    )


def copy_projects(dest: Path) -> Path:
    """Copy the root and both mcp-servers sub-projects under dest; return the copied root."""
    dest.mkdir(parents=True, exist_ok=True)
    for name in _ROOT_FILES:
        shutil.copy2(REPO_ROOT / name, dest / name)
    shutil.copytree(REPO_ROOT / "src", dest / "src", ignore=_SKIP_WHEN_COPYING)
    for server in sorted((REPO_ROOT / "mcp-servers").iterdir()):
        if (server / "pyproject.toml").is_file():
            shutil.copytree(server, dest / "mcp-servers" / server.name, ignore=_SKIP_WHEN_COPYING)
    return dest


def set_version(root: Path, version: str) -> None:
    """Write version into root's VERSION file, the single source of the package version."""
    (root / "VERSION").write_text(f"{version}\n", encoding="utf-8")


def make_stale(root: Path) -> None:
    """Loosen the numpy pin in root's pyproject.toml so the committed uv.lock no longer matches."""
    pyproject = root / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    if '"numpy==2.4.6"' not in text:
        raise RuntimeError("expected the numpy==2.4.6 pin in pyproject.toml")
    pyproject.write_text(text.replace('"numpy==2.4.6"', '"numpy>=2.4.6"'), encoding="utf-8")


def installed_version(project: Path) -> str:
    """Return importlib.metadata's nmg-game-dev version in project's environment, built offline."""
    result = subprocess.run(
        [
            "uv",
            "run",
            "--offline",
            "--no-dev",
            "python",
            "-c",
            "import importlib.metadata as m; print(m.version('nmg-game-dev'))",
        ],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"uv run --offline failed in {project}: {result.stderr.strip()}")
    return result.stdout.strip()
