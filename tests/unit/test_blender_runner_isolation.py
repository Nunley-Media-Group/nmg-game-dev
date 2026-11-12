"""tests/blender/_runner.py links the add-on only inside BLENDER_USER_SCRIPTS (#189).

The runner refuses otherwise. It imports bpy only inside its functions, so this test loads it by
file path and injects a fake bpy module. The guard runs without Blender and must not create anything
when it refuses.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from tests.release_fakes import REPO_ROOT

_RUNNER_PATH = REPO_ROOT / "tests" / "blender" / "_runner.py"
_ADDON_SRC = REPO_ROOT / "plugins" / "nmg-game-dev-blender-addon"
_MODULE_ID = "nmg_game_dev_blender_addon"


class _FakeBpy(ModuleType):
    """Stand-in for bpy: only bpy.utils.user_resource, which the runner calls."""

    def __init__(self, addons: Path) -> None:
        super().__init__("bpy")
        self.addons = addons
        self.resource_calls: list[dict[str, object]] = []
        self.utils = SimpleNamespace(user_resource=self._user_resource)

    def _user_resource(self, resource_type: str, path: str = "", create: bool = False) -> str:
        self.resource_calls.append({"resource_type": resource_type, "path": path, "create": create})
        return str(self.addons)


def _load_runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location("blender_runner_under_test", _RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _install_fake_bpy(monkeypatch: pytest.MonkeyPatch, addons: Path) -> _FakeBpy:
    fake = _FakeBpy(addons)
    monkeypatch.setitem(sys.modules, "bpy", fake)
    return fake


def test_the_add_on_link_is_created_only_under_the_run_user_scripts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _load_runner()
    run_scripts = tmp_path / "run-scripts"
    addons = run_scripts / "addons"
    monkeypatch.setenv("BLENDER_USER_SCRIPTS", str(run_scripts))
    fake = _install_fake_bpy(monkeypatch, addons)

    runner._install_addon_link()

    link = addons / _MODULE_ID
    assert link.is_symlink()
    assert link.resolve() == _ADDON_SRC.resolve()
    assert fake.resource_calls == [{"resource_type": "SCRIPTS", "path": "addons", "create": False}]


def test_the_runner_refuses_to_link_when_user_scripts_is_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _load_runner()
    monkeypatch.delenv("BLENDER_USER_SCRIPTS", raising=False)
    _install_fake_bpy(monkeypatch, tmp_path / "users-scripts" / "addons")

    with pytest.raises(RuntimeError, match="scripts/run-blender-tests.sh"):
        runner._install_addon_link()

    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("outside_name", ["users-real-scripts", "run-scripts-sibling"])
def test_the_runner_refuses_an_addons_path_outside_the_run_user_scripts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, outside_name: str
) -> None:
    runner = _load_runner()
    run_scripts = tmp_path / "run-scripts"
    outside = tmp_path / outside_name / "addons"
    outside.mkdir(parents=True)
    monkeypatch.setenv("BLENDER_USER_SCRIPTS", str(run_scripts))
    fake = _install_fake_bpy(monkeypatch, outside)

    with pytest.raises(RuntimeError, match="outside BLENDER_USER_SCRIPTS"):
        runner._install_addon_link()

    assert list(outside.iterdir()) == []
    assert not run_scripts.exists()
    assert all(call["create"] is False for call in fake.resource_calls)
