"""Shared fixtures for the audio import tests (#155).

An autouse guard replaces ``UnrealMcpClient`` in the audio modules, so a test that forgets to inject
a fake client fails instead of reaching a real Unreal MCP endpoint. Tests that need the fake use the
``fake_unreal`` fixture, which points the modules at a ``FakeUnrealPythonClient``.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tests.unit.fake_unreal import FakeEditor, FakeUnrealPythonClient

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "audio"


def _forbidden(*_args: Any, **_kwargs: Any) -> None:
    raise AssertionError("audio tests must inject a fake Unreal client, never a live endpoint")


@pytest.fixture(autouse=True)
def _no_live_unreal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("nmg_game_dev.audio.core.UnrealMcpClient", _forbidden)
    monkeypatch.setattr("nmg_game_dev.audio.__main__.UnrealMcpClient", _forbidden)


@pytest.fixture
def fixture_file() -> Callable[[str], Path]:
    """Return a path to a committed fixture clip by file name, e.g. ``tone.mp3``."""

    def _path(name: str) -> Path:
        return FIXTURES / name

    return _path


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty project root that ``CLAUDE_PROJECT_DIR`` points at."""
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    return root


@pytest.fixture
def source_file(tmp_path: Path, fixture_file: Callable[[str], Path]) -> Callable[[str], Path]:
    """Copy a fixture into a fresh folder outside the project, the way a saved download sits."""
    saved = tmp_path / "saved"
    saved.mkdir()

    def _copy(name: str) -> Path:
        target = saved / name
        shutil.copyfile(fixture_file(name), target)
        return target

    return _copy


@pytest.fixture
def fake_unreal(monkeypatch: pytest.MonkeyPatch) -> FakeUnrealPythonClient:
    """A reachable fake client, wired in as the default for the tool and the CLI."""
    client = FakeUnrealPythonClient(FakeEditor())

    def _factory(*_args: Any, **_kwargs: Any) -> FakeUnrealPythonClient:
        return client

    monkeypatch.setattr("nmg_game_dev.audio.core.UnrealMcpClient", _factory)
    monkeypatch.setattr("nmg_game_dev.audio.__main__.UnrealMcpClient", _factory)
    return client
