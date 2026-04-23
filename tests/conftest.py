"""Shared pytest fixtures for the nmg-game-dev test suite."""

from __future__ import annotations

import json
import pathlib
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest
from _scaffold_contract import REPO_ROOT as _REPO_ROOT

REPO_ROOT: pathlib.Path = _REPO_ROOT


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


class FakeBlenderMcp:
    """Scripted fake for the BlenderMcp Protocol used in pipeline tests.

    Each call returns a canned response with a deterministic ``output_path``.
    Tests can inject a side-effect by setting ``run_script_side_effect``.
    """

    def __init__(self, tmp_path: Path) -> None:
        self._tmp = tmp_path
        self.run_script_side_effect: Exception | None = None
        self.run_script_calls: list[str] = []

    def run_script(self, script: str, **_kwargs: object) -> dict[str, object]:
        if self.run_script_side_effect is not None:
            raise self.run_script_side_effect
        self.run_script_calls.append(script)
        idx = len(self.run_script_calls)
        # Real files so StageArtifact.content_hash has bytes to stream.
        out = self._tmp / f"blender_out_{idx}.fbx"
        out.write_bytes(b"FAKE_BLENDER_MESH")
        desktop_out = self._tmp / f"desktop_{idx}.fbx"
        mobile_out = self._tmp / f"mobile_{idx}.fbx"
        desktop_out.write_bytes(b"FAKE_DESKTOP")
        mobile_out.write_bytes(b"FAKE_MOBILE")
        return {
            "output_path": str(out),
            "desktop_path": str(desktop_out),
            "mobile_path": str(mobile_out),
            "poly_count_desktop": 5_000,
            "poly_count_mobile": 2_000,
            "texture_bytes_desktop": 1_000_000,
            "texture_bytes_mobile": 512_000,
        }

    def ping(self) -> bool:
        return True

    @property
    def call_count(self) -> int:
        return len(self.run_script_calls)


class FakeUnrealMcp:
    """Scripted fake for the UnrealMcp Protocol used in pipeline tests."""

    def __init__(self, tmp_path: Path) -> None:
        self._tmp = tmp_path
        self.import_asset_side_effect: Exception | None = None
        self.import_asset_calls: list[tuple[str, str]] = []

    def import_asset(
        self,
        source_path: str,
        destination_path: str,
        **_kwargs: object,
    ) -> dict[str, object]:
        if self.import_asset_side_effect is not None:
            raise self.import_asset_side_effect
        self.import_asset_calls.append((source_path, destination_path))
        dest_dir = self._tmp / destination_path.lstrip("/")
        dest_dir.mkdir(parents=True, exist_ok=True)
        imported = dest_dir / "SM_asset.uasset"
        imported.write_bytes(b"FAKE_UE_ASSET")
        return {"imported_path": str(imported)}

    def ping(self) -> bool:
        return True

    @property
    def call_count(self) -> int:
        return len(self.import_asset_calls)


class FakeMeshyMcp:
    """Scripted fake for the MeshyMcp Protocol used in pipeline tests."""

    def __init__(self, tmp_path: Path) -> None:
        self._tmp = tmp_path
        self.generate_side_effect: Exception | None = None
        self.generate_calls: list[str] = []

    def generate(self, prompt: str, **_kwargs: object) -> dict[str, object]:
        if self.generate_side_effect is not None:
            raise self.generate_side_effect
        self.generate_calls.append(prompt)
        out = self._tmp / f"meshy_out_{len(self.generate_calls)}.fbx"
        out.write_bytes(b"FAKE_MESHY_MESH")
        return {"output_path": str(out)}

    @property
    def call_count(self) -> int:
        return len(self.generate_calls)


@pytest.fixture()
def fake_blender(tmp_path: Path) -> FakeBlenderMcp:
    """Scripted Blender MCP fake."""
    return FakeBlenderMcp(tmp_path)


@pytest.fixture()
def fake_unreal(tmp_path: Path) -> FakeUnrealMcp:
    """Scripted Unreal MCP fake."""
    return FakeUnrealMcp(tmp_path)


@pytest.fixture()
def fake_meshy(tmp_path: Path) -> FakeMeshyMcp:
    """Scripted Meshy MCP fake."""
    return FakeMeshyMcp(tmp_path)


@pytest.fixture()
def fake_mcp_clients(
    fake_blender: FakeBlenderMcp,
    fake_unreal: FakeUnrealMcp,
    fake_meshy: FakeMeshyMcp,
) -> Any:
    """McpClients DI container populated with scripted fakes (all three MCPs)."""
    from nmg_game_dev.pipeline.stages._base import McpClients

    return McpClients(blender=fake_blender, unreal=fake_unreal, meshy=fake_meshy)


@pytest.fixture()
def fake_mcp_clients_no_meshy(
    fake_blender: FakeBlenderMcp,
    fake_unreal: FakeUnrealMcp,
) -> Any:
    """McpClients DI container without a Meshy client (Blender-first pipelines)."""
    from nmg_game_dev.pipeline.stages._base import McpClients

    return McpClients(blender=fake_blender, unreal=fake_unreal, meshy=None)
