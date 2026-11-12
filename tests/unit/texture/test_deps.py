"""The dependency probe: mflux and mlx are found without being imported, and the error names the
plugin-root command (#143 FR2, AC2)."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from nmg_game_dev.texture.deps import (
    missing_module,
    plugin_root,
    require_dependencies,
    run_command,
)
from nmg_game_dev.texture.errors import TextureGenError

# Captured at import, before the autouse fixture patches the module attribute.
REAL_MISSING_MODULE = missing_module


def _finder(missing: set[str], seen: list[str]) -> Callable[[str], object | None]:
    def find_spec(name: str) -> object | None:
        seen.append(name)
        return None if name in missing else object()

    return find_spec


def test_missing_module_reports_the_first_module_that_cannot_be_found() -> None:
    assert REAL_MISSING_MODULE(_finder({"mlx"}, [])) == "mlx"
    assert REAL_MISSING_MODULE(_finder({"mflux", "mlx"}, [])) == "mflux"
    assert REAL_MISSING_MODULE(_finder(set(), [])) is None


def test_missing_module_asks_about_both_modules_and_imports_neither() -> None:
    seen: list[str] = []
    assert REAL_MISSING_MODULE(_finder(set(), seen)) is None
    assert seen == ["mflux", "mlx"]


def test_the_real_probe_does_not_import_mlx() -> None:
    had_mlx = "mlx" in sys.modules
    REAL_MISSING_MODULE()
    assert ("mlx" in sys.modules) == had_mlx


def test_require_dependencies_names_the_module_and_the_plugin_root_command() -> None:
    with pytest.raises(TextureGenError) as caught:
        require_dependencies(lambda: "mlx")
    error = caught.value
    assert error.code == "texture.dependencies_missing"
    assert "mlx" in error.message
    assert "uv run --project" in error.remediation
    assert "Apple Silicon" in error.remediation


def test_require_dependencies_passes_when_every_module_is_present() -> None:
    require_dependencies(lambda: None)


def test_plugin_root_honours_claude_plugin_root() -> None:
    assert plugin_root({"CLAUDE_PLUGIN_ROOT": "/opt/nmg"}) == Path("/opt/nmg")


def test_plugin_root_finds_the_nmg_game_dev_checkout_without_the_env_var() -> None:
    root = plugin_root({})
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "nmg-game-dev"' in text


def test_run_command_runs_generate_from_the_plugin_root_quoted_for_copy_paste() -> None:
    command = run_command(Path("/opt/nmg game"))
    assert command.startswith(
        "uv run --project '/opt/nmg game' python -m nmg_game_dev.texture generate"
    )
