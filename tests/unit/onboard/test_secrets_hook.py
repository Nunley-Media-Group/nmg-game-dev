"""The #255 onboarding steps: the scanner copy and the pre-commit hook (AC5, FR2, T002).

The install-state tests use ``FakeRunner``. The commit test runs a real ``git commit`` in a
temporary repository, through the hook that onboarding installed, and no key is ever committed.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from nmg_game_dev.onboard import run_onboard
from nmg_game_dev.onboard.commands import default_run
from nmg_game_dev.onboard.report import format_report
from nmg_game_dev.onboard.secrets_hook import (
    CALL_LINE,
    HOOK_MARKER,
    HOOK_TEXT,
    ensure_precommit_hook,
    ensure_secret_scanner,
)
from tests.onboard_fakes import (
    APPLE_SILICON,
    REPO_ROOT,
    FakeRunner,
    all_tools_present,
    gib_free,
    make_consumer,
    make_framework,
)

SCANNER_SRC = REPO_ROOT / "src" / "nmg_game_dev" / "secrets" / "scan.py"
HOOK = Path(".git") / "hooks" / "pre-commit"
FOREIGN_HOOK = "#!/bin/sh\necho 'a team hook'\nexit 0\n"
MESHY = "msy_" + "Ab3dEf6hIj9kLm2nOp5q"


def _repo_hook(consumer: Path) -> Path:
    return consumer / HOOK


# Scanner copy ------------------------------------------------------------------------------------


def test_the_scanner_copy_is_installed_byte_identical(tmp_path: Path) -> None:
    framework = make_framework(tmp_path / "framework")
    consumer = make_consumer(tmp_path)

    result = ensure_secret_scanner("secret_scanner", framework, consumer, False)

    assert result.status == "installed"
    assert (consumer / "scripts" / "nmg_secret_scan.py").read_bytes() == SCANNER_SRC.read_bytes()
    assert ensure_secret_scanner("secret_scanner", framework, consumer, False).status == "unchanged"


def test_an_edited_scanner_copy_is_drift_until_refresh(tmp_path: Path) -> None:
    framework = make_framework(tmp_path / "framework")
    consumer = make_consumer(tmp_path)
    ensure_secret_scanner("secret_scanner", framework, consumer, False)
    copy = consumer / "scripts" / "nmg_secret_scan.py"
    copy.write_text("# edited by the consumer\n", encoding="utf-8")

    drift = ensure_secret_scanner("secret_scanner", framework, consumer, False)
    assert drift.status == "drift"
    assert copy.read_text(encoding="utf-8") == "# edited by the consumer\n"

    refreshed = ensure_secret_scanner("secret_scanner", framework, consumer, True)
    assert refreshed.status == "refreshed"
    assert copy.read_bytes() == SCANNER_SRC.read_bytes()


# Hook install states (AC5) -----------------------------------------------------------------------


def test_no_hook_installs_the_nmg_hook_executable(tmp_path: Path) -> None:
    consumer = make_consumer(tmp_path)

    result = ensure_precommit_hook("precommit_hook", consumer, run=FakeRunner(work_tree=True))

    assert result.status == "installed"
    hook = _repo_hook(consumer)
    assert hook.read_text(encoding="utf-8") == HOOK_TEXT
    assert os.access(hook, os.X_OK)
    assert HOOK_MARKER in HOOK_TEXT
    assert CALL_LINE in HOOK_TEXT


def test_the_nmg_hook_is_unchanged_on_a_rerun(tmp_path: Path) -> None:
    consumer = make_consumer(tmp_path)
    ensure_precommit_hook("precommit_hook", consumer, run=FakeRunner(work_tree=True))
    before = _repo_hook(consumer).read_bytes()

    result = ensure_precommit_hook("precommit_hook", consumer, run=FakeRunner(work_tree=True))

    assert result.status == "unchanged"
    assert _repo_hook(consumer).read_bytes() == before


def test_a_foreign_hook_is_a_conflict_left_byte_identical(tmp_path: Path) -> None:
    consumer = make_consumer(tmp_path)
    hook = _repo_hook(consumer)
    hook.parent.mkdir(parents=True)
    hook.write_text(FOREIGN_HOOK, encoding="utf-8")

    result = ensure_precommit_hook("precommit_hook", consumer, run=FakeRunner(work_tree=True))

    assert result.status == "conflict"
    assert "onboard.precommit_hook_conflict" in result.detail
    assert result.remediation == f"Add this line to it: {CALL_LINE}"
    assert CALL_LINE == (
        'python3 "$(git rev-parse --show-toplevel)/scripts/nmg_secret_scan.py" --staged || exit 1'
    )
    assert hook.read_text(encoding="utf-8") == FOREIGN_HOOK


def test_outside_a_work_tree_the_hook_step_is_skipped(tmp_path: Path) -> None:
    consumer = make_consumer(tmp_path)

    result = ensure_precommit_hook("precommit_hook", consumer, run=FakeRunner())

    assert result.status == "skipped"
    assert result.detail == "not a git repository"
    assert not _repo_hook(consumer).exists()


@pytest.mark.skipif(
    subprocess.run(["git", "--version"], capture_output=True, check=False).returncode != 0,
    reason="git is not installed",
)
def test_a_subfolder_of_a_larger_repository_skips_the_hook(tmp_path: Path) -> None:
    """The hook runs the scanner from the repository root, so a subfolder target would block
    every commit; the step is skipped instead (review F2)."""
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True, capture_output=True)
    consumer = make_consumer(tmp_path / "games")

    result = ensure_precommit_hook("precommit_hook", consumer, run=default_run)

    assert result.status == "skipped"
    assert "subfolder" in result.detail
    assert result.remediation is not None
    assert not (tmp_path / HOOK).exists()


def test_a_conflict_is_reported_by_onboarding_and_still_exits_clean(tmp_path: Path) -> None:
    """Onboarding reports the conflict as a step and does not raise (AC5)."""
    framework = make_framework(tmp_path / "framework")
    consumer = make_consumer(tmp_path)
    hook = _repo_hook(consumer)
    hook.parent.mkdir(parents=True)
    hook.write_text(FOREIGN_HOOK, encoding="utf-8")
    volume = tmp_path / "volume"

    results = run_onboard(
        consumer,
        framework=framework,
        models_dir=volume / "nmg-texture-models",
        env={
            "BLENDER_EXTENSIONS_DIR": str(tmp_path / "ext"),
            "TEXTURE_GEN_MODELS_DIR": str(volume / "nmg-texture-models"),
        },
        run=FakeRunner(work_tree=True),
        which=all_tools_present,
        host=APPLE_SILICON,
        free_bytes=gib_free,
        godot_app=tmp_path / "no-godot-app",
    )

    report = format_report(results)
    precommit = next(r for r in results if r.name == "precommit_hook")
    assert precommit.status == "conflict"
    assert "conflict precommit_hook: onboard.precommit_hook_conflict" in report
    assert f"  Remediation: Add this line to it: {CALL_LINE}" in report
    assert hook.read_text(encoding="utf-8") == FOREIGN_HOOK


# The installed hook blocks a real commit (AC1, AC2) ----------------------------------------------


def _commit(repo: Path, message: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=Hook Test",
            "-c",
            "user.email=hook-test@example.invalid",
            "commit",
            "-q",
            "-m",
            message,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.skipif(
    subprocess.run(["git", "--version"], capture_output=True, check=False).returncode != 0,
    reason="git is not installed",
)
def test_the_onboarded_hook_blocks_a_real_commit_of_a_key_and_passes_a_clean_one(
    tmp_path: Path,
) -> None:
    framework = make_framework(tmp_path / "framework")
    repo = tmp_path / "consumer"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True, capture_output=True)
    assert ensure_secret_scanner("secret_scanner", framework, repo, False).status == "installed"
    assert ensure_precommit_hook("precommit_hook", repo, run=default_run).status == "installed"

    (repo / "scripts" / "setup.gd").write_text(f'var key = "{MESHY}"\n', encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "scripts/setup.gd"], check=True)
    blocked = _commit(repo, "add the setup script")

    assert blocked.returncode == 1
    assert "scripts/setup.gd:1: meshy msy_… (sha256:" in blocked.stderr
    assert MESHY not in blocked.stdout + blocked.stderr
    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", "-q", "HEAD"],
        capture_output=True,
        check=False,
    )
    assert head.returncode != 0, "a blocked commit must not reach the branch"

    subprocess.run(["git", "-C", str(repo), "rm", "-q", "--cached", "scripts/setup.gd"], check=True)
    (repo / "scripts" / "setup.gd").unlink()
    (repo / "main.gd").write_text("extends Node\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "main.gd"], check=True)
    passed = _commit(repo, "add the main script")

    assert passed.returncode == 0, passed.stderr
    assert passed.stdout == "" and passed.stderr == ""
