"""The root project carries the Apple Silicon generation dependencies as floors (#143 AC1, FR1)."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
MARKER = "sys_platform == 'darwin' and platform_machine == 'arm64'"


def _load(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = tomllib.loads(path.read_text(encoding="utf-8"))
    return data


def test_root_dependencies_declare_the_floors_with_the_apple_silicon_marker() -> None:
    deps: list[str] = _load(REPO / "pyproject.toml")["project"]["dependencies"]
    assert f"mflux>=0.24.0; {MARKER}" in deps
    assert f"hf_transfer>=0.1.9; {MARKER}" in deps


def test_texture_ai_extra_declares_the_same_floors_and_no_exact_pin() -> None:
    extra: list[str] = _load(REPO / "pyproject.toml")["project"]["optional-dependencies"][
        "texture-ai"
    ]
    assert sorted(extra) == ["hf_transfer>=0.1.9", "mflux>=0.24.0"]
    assert not any("==" in entry for entry in extra)


def test_texture_gen_server_dependency_on_the_root_is_unchanged() -> None:
    server = REPO / "mcp-servers" / "texture-gen" / "pyproject.toml"
    deps: list[str] = _load(server)["project"]["dependencies"]
    assert deps == ["mcp==1.30.0", "nmg-game-dev[texture-ai]"]
