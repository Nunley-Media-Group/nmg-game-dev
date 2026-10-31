"""Lockfile drift guards: each committed uv.lock matches its pyproject.toml (#95; FR4-FR6).

The checks run uv offline and never relock. The module is skipped only when uv is not on PATH.
"""

from __future__ import annotations

import shutil
import tomllib
from pathlib import Path

import pytest

from tests.lock_fakes import (
    copy_projects,
    installed_version,
    label,
    lock_check,
    make_stale,
    project_dirs,
    set_version,
)

pytestmark = pytest.mark.skipif(
    shutil.which("uv") is None, reason="uv is required to check the committed lockfiles"
)

_PROJECTS = project_dirs()


@pytest.mark.parametrize("project", _PROJECTS, ids=lambda project: label(project))
def test_committed_lock_matches_its_pyproject(project: Path) -> None:
    assert lock_check(project) is None


def test_stale_pyproject_is_reported_with_the_project_to_relock(tmp_path: Path) -> None:
    root = copy_projects(tmp_path / "copy")
    make_stale(root)

    message = lock_check(root, root)

    assert message is not None, "a stale pyproject.toml passed uv lock --check"
    assert f"run `uv lock` in {label(root, root)}" in message


@pytest.mark.parametrize(
    "lock", [project / "uv.lock" for project in _PROJECTS], ids=lambda lock: label(lock.parent)
)
def test_nmg_game_dev_entry_records_no_version(lock: Path) -> None:
    packages = tomllib.loads(lock.read_text(encoding="utf-8"))["package"]
    entries = [package for package in packages if package["name"] == "nmg-game-dev"]
    assert len(entries) == 1, f"{lock} must hold exactly one nmg-game-dev entry"
    assert "version" not in entries[0], (
        f"{lock} records nmg-game-dev's version, so a VERSION bump would stale it"
    )


def test_version_bump_keeps_every_lock_in_sync(tmp_path: Path) -> None:
    root = copy_projects(tmp_path / "copy")
    set_version(root, "9.9.9")

    for project in project_dirs(root):
        assert lock_check(project, root) is None, f"{label(project, root)} went stale on a bump"
    assert installed_version(root) == "9.9.9"
