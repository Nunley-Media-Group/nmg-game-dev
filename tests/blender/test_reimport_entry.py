"""Re-import entry lookup under Blender headless: AC2, AC3 (SCN002, SCN003; FR2).

The resolver is exercised directly, and run_isolated is run with subprocess.run captured, so no
fresh Blender is spawned. CLAUDE_PLUGIN_ROOT and CHECKOUT_ENTRY_SCRIPT are patched per test.
"""

from __future__ import annotations

import importlib
import json
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

bpy = pytest.importorskip("bpy")


@pytest.fixture()
def reimport(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.contract_core.reimport")


@pytest.fixture()
def absent_checkout(reimport: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the checkout fallback at a path that does not exist."""
    absent = tmp_path / "no-checkout" / "scripts" / "blender" / "contract_entry.py"
    monkeypatch.setattr(reimport, "CHECKOUT_ENTRY_SCRIPT", absent)
    return absent


@pytest.fixture()
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    yield


def _entry_under(root: Path) -> Path:
    entry = root / "scripts" / "blender" / "contract_entry.py"
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text("# headless entry stub\n", encoding="utf-8")
    return entry


def test_ac2_entry_resolves_through_claude_plugin_root(
    reimport: Any,
    absent_checkout: Path,  # noqa: ARG001 — the checkout must be absent for this to prove anything
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin_root = tmp_path / "plugin"
    entry = _entry_under(plugin_root)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin_root))

    assert reimport.entry_script() == entry


def test_ac2_run_isolated_launches_the_plugin_root_entry(
    reimport: Any,
    absent_checkout: Path,  # noqa: ARG001
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin_root = tmp_path / "plugin"
    entry = _entry_under(plugin_root)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin_root))
    launched: list[list[str]] = []

    def capture(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        launched.append(list(command))
        report = Path(command[command.index("--report") + 1])
        report.write_text(json.dumps({"kind": "reimport", "passed": True}), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(reimport.subprocess, "run", capture)

    report = reimport.run_isolated(tmp_path / "Desktop", {"asset": "Crate"})

    assert len(launched) == 1
    assert launched[0][launched[0].index("--python") + 1] == str(entry)
    assert report == {"kind": "reimport", "passed": True}


def test_ac3_unset_plugin_root_uses_the_checkout_entry(
    reimport: Any,
    clean_environment: None,  # noqa: ARG001
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkout = _entry_under(tmp_path / "checkout")
    monkeypatch.setattr(reimport, "CHECKOUT_ENTRY_SCRIPT", checkout)

    assert reimport.entry_script() == checkout


def test_ac3_plugin_root_without_the_script_uses_the_checkout_entry(
    reimport: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkout = _entry_under(tmp_path / "checkout")
    monkeypatch.setattr(reimport, "CHECKOUT_ENTRY_SCRIPT", checkout)
    empty_root = tmp_path / "empty-root"
    empty_root.mkdir()
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(empty_root))

    assert reimport.entry_script() == checkout


def test_ac3_missing_everywhere_raises_entry_missing_naming_claude_plugin_root(
    reimport: Any,
    absent_checkout: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    empty_root = tmp_path / "empty-root"
    empty_root.mkdir()
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(empty_root))

    with pytest.raises(reimport.ContractError) as caught:
        reimport.entry_script()

    error = caught.value
    assert error.code == "reimport.entry_missing"
    assert str(empty_root / "scripts" / "blender" / "contract_entry.py") in error.message
    assert str(absent_checkout) in error.message
    assert "CLAUDE_PLUGIN_ROOT" in error.remediation


def test_ac3_unset_plugin_root_missing_everywhere_still_names_both_locations(
    reimport: Any,
    absent_checkout: Path,
    clean_environment: None,  # noqa: ARG001
) -> None:
    with pytest.raises(reimport.ContractError) as caught:
        reimport.entry_script()

    error = caught.value
    assert error.code == "reimport.entry_missing"
    assert "CLAUDE_PLUGIN_ROOT (unset)" in error.message
    assert str(absent_checkout) in error.message
    assert "CLAUDE_PLUGIN_ROOT" in error.remediation


def test_ac3_run_isolated_raises_entry_missing_before_launching(
    reimport: Any,
    absent_checkout: Path,  # noqa: ARG001
    clean_environment: None,  # noqa: ARG001
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launched: list[list[str]] = []
    monkeypatch.setattr(reimport.subprocess, "run", lambda command, **_: launched.append(command))

    with pytest.raises(reimport.ContractError) as caught:
        reimport.run_isolated(tmp_path / "Desktop", {"asset": "Crate"})

    assert caught.value.code == "reimport.entry_missing"
    assert launched == []
