"""Shared pytest fixtures for the nmg-game-dev test suite."""

from __future__ import annotations

import json
import pathlib
import sys
import tomllib
from typing import Any

import pytest
from _scaffold_contract import REPO_ROOT


@pytest.fixture(scope="session")
def repo_root() -> pathlib.Path:
    return REPO_ROOT


@pytest.fixture(scope="session", autouse=True)
def _ensure_src_on_path() -> None:
    src = str(REPO_ROOT / "src")
    if src not in sys.path:
        sys.path.insert(0, src)


@pytest.fixture(scope="session")
def plugin_data() -> dict[str, Any]:
    with (REPO_ROOT / ".claude-plugin" / "plugin.json").open() as fh:
        data: dict[str, Any] = json.load(fh)
    return data


@pytest.fixture(scope="session")
def plugin_text() -> str:
    return (REPO_ROOT / ".claude-plugin" / "plugin.json").read_text()


@pytest.fixture(scope="session")
def mcp_data() -> dict[str, Any]:
    with (REPO_ROOT / ".mcp.json").open() as fh:
        data: dict[str, Any] = json.load(fh)
    return data


@pytest.fixture(scope="session")
def mcp_text() -> str:
    return (REPO_ROOT / ".mcp.json").read_text()


@pytest.fixture(scope="session")
def pyproject_data() -> dict[str, Any]:
    with (REPO_ROOT / "pyproject.toml").open("rb") as fh:
        data: dict[str, Any] = tomllib.load(fh)
    return data


@pytest.fixture(scope="session")
def changelog_text() -> str:
    return (REPO_ROOT / "CHANGELOG.md").read_text()


@pytest.fixture(scope="session")
def claude_md_text() -> str:
    return (REPO_ROOT / "CLAUDE.md").read_text()


@pytest.fixture(scope="session")
def version_text() -> str:
    return (REPO_ROOT / "VERSION").read_text()


@pytest.fixture(scope="session")
def consumer_settings_data() -> dict[str, Any]:
    with (REPO_ROOT / "templates" / "consumer" / ".claude" / "settings.json").open() as fh:
        data: dict[str, Any] = json.load(fh)
    return data


@pytest.fixture(scope="session")
def artifact_text(repo_root: pathlib.Path) -> Any:
    cache: dict[str, str] = {}

    def _read(rel: str) -> str:
        if rel not in cache:
            cache[rel] = (repo_root / rel).read_text()
        return cache[rel]

    return _read
