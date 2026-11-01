"""The Git LFS steps: the managed .gitattributes block and the LFS hooks (#122 AC1–AC5, AC7)."""

from __future__ import annotations

from pathlib import Path

import pytest

from nmg_game_dev.onboard.errors import OnboardError
from nmg_game_dev.onboard.lfs import (
    BEGIN,
    END,
    LFS_PATTERNS,
    block_text,
    ensure_gitattributes_lfs,
    ensure_lfs_hooks,
)
from tests.onboard_fakes import FakeRunner

GITATTRIBUTES = "gitattributes_lfs"
RULE = "{} filter=lfs diff=lfs merge=lfs -text"


def test_block_has_one_rule_per_pattern_in_fr2_order_between_markers() -> None:
    assert len(LFS_PATTERNS) == 22
    assert LFS_PATTERNS[0] == "*.blend" and LFS_PATTERNS[-1] == "*.mp4"
    lines = block_text().split("\n")
    assert lines[0] == BEGIN and lines[-1] == END
    assert lines[1:-1] == [RULE.format(pattern) for pattern in LFS_PATTERNS]


def test_missing_gitattributes_is_created_with_the_block(tmp_path: Path) -> None:
    """AC1: a missing .gitattributes is created holding the block; the result is installed."""
    target = tmp_path / ".gitattributes"
    result = ensure_gitattributes_lfs(GITATTRIBUTES, target, refresh=False)
    assert result.name == GITATTRIBUTES and result.status == "installed"
    assert target.read_text(encoding="utf-8") == block_text() + "\n"


@pytest.mark.parametrize(
    "original",
    [
        b"*.md text=auto\n*.sh text eol=lf",
        b"# Game\r\n*.md text=auto\r\n",
    ],
    ids=["no-final-newline", "crlf"],
)
def test_consumer_lines_are_kept_byte_for_byte_and_block_appended_once(
    tmp_path: Path, original: bytes
) -> None:
    """AC2: existing lines, including a missing final newline and CRLF, stay as written."""
    target = tmp_path / ".gitattributes"
    target.write_bytes(original)
    result = ensure_gitattributes_lfs(GITATTRIBUTES, target, refresh=False)
    assert result.status == "installed"
    after = target.read_bytes()
    assert after.startswith(original)
    text = after.decode("utf-8")
    assert text.count(BEGIN) == 1 and text.count(END) == 1
    assert text.endswith(block_text() + "\n")


def test_second_run_is_unchanged_and_leaves_the_bytes_alone(tmp_path: Path) -> None:
    """AC3: a block that matches the framework is unchanged, and the file bytes do not move."""
    target = tmp_path / ".gitattributes"
    ensure_gitattributes_lfs(GITATTRIBUTES, target, refresh=False)
    before = target.read_bytes()
    result = ensure_gitattributes_lfs(GITATTRIBUTES, target, refresh=False)
    assert result.status == "unchanged"
    assert target.read_bytes() == before


def test_edited_block_is_drift_then_refresh_replaces_only_the_block(tmp_path: Path) -> None:
    """AC4: an edited block is drift without refresh; with refresh only the block is replaced."""
    target = tmp_path / ".gitattributes"
    ensure_gitattributes_lfs(GITATTRIBUTES, target, refresh=False)
    edited_block = block_text().replace(RULE.format("*.blend"), "*.blend text=auto")
    target.write_bytes(("# header\r\n" + edited_block + "\n*.local text=auto\r\n").encode("utf-8"))

    before = target.read_bytes()
    drift = ensure_gitattributes_lfs(GITATTRIBUTES, target, refresh=False)
    assert drift.status == "drift"
    assert drift.remediation == "re-run with --refresh"
    assert target.read_bytes() == before

    refreshed = ensure_gitattributes_lfs(GITATTRIBUTES, target, refresh=True)
    assert refreshed.status == "refreshed"
    assert target.read_bytes() == (
        "# header\r\n" + block_text() + "\n*.local text=auto\r\n"
    ).encode("utf-8")


def test_a_stray_begin_marker_is_not_swept_into_a_refresh(tmp_path: Path) -> None:
    """A begin marker with no end marker after it is consumer text, so a refresh keeps it."""
    target = tmp_path / ".gitattributes"
    target.write_text(f"{BEGIN}\n*.keep text=auto\n", encoding="utf-8")
    result = ensure_gitattributes_lfs(GITATTRIBUTES, target, refresh=True)
    assert result.status == "installed"
    text = target.read_text(encoding="utf-8")
    assert text.startswith(f"{BEGIN}\n*.keep text=auto\n")
    assert text.endswith(block_text() + "\n")


def test_git_consumer_gets_lfs_hooks_installed_once(consumer: Path) -> None:
    """AC5: in a work tree with no LFS pre-push, install runs once; a rerun runs no install."""
    runner = FakeRunner(work_tree=True)
    first = ensure_lfs_hooks("git_lfs_hooks", consumer, run=runner)
    assert first.status == "installed"
    assert first.detail == "ran git lfs install --local"
    assert runner.argv_starting("git", "-C", str(consumer), "lfs", "install", "--local") == [
        ["git", "-C", str(consumer), "lfs", "install", "--local"]
    ]

    rerun = FakeRunner(work_tree=True)
    second = ensure_lfs_hooks("git_lfs_hooks", consumer, run=rerun)
    assert second.status == "unchanged"
    assert rerun.argv_starting("git", "-C", str(consumer), "lfs") == []


def test_custom_pre_push_without_lfs_still_triggers_the_install(consumer: Path) -> None:
    """AC5: only a pre-push that mentions git lfs counts as the LFS hook."""
    hook = consumer / ".git" / "hooks" / "pre-push"
    hook.parent.mkdir(parents=True)
    hook.write_text("#!/bin/sh\nrun-project-checks\n", encoding="utf-8")
    runner = FakeRunner(work_tree=True)
    assert ensure_lfs_hooks("git_lfs_hooks", consumer, run=runner).status == "installed"


def test_failed_lfs_install_raises_hooks_failed(consumer: Path) -> None:
    """AC5: a non-zero exit from git lfs install raises onboard.git_lfs_hooks_failed."""
    runner = FakeRunner(work_tree=True, fail="lfs-install")
    with pytest.raises(OnboardError) as caught:
        ensure_lfs_hooks("git_lfs_hooks", consumer, run=runner)
    assert caught.value.code == "onboard.git_lfs_hooks_failed"
    assert "refusing to overwrite pre-push" in caught.value.message
    assert caught.value.remediation


def test_consumer_outside_a_work_tree_is_skipped(consumer: Path) -> None:
    """AC7: outside a git work tree the step is skipped with its reason and runs no install."""
    runner = FakeRunner()
    result = ensure_lfs_hooks("git_lfs_hooks", consumer, run=runner)
    assert result.status == "skipped"
    assert result.detail == "not a git repository"
    assert result.remediation is None
    assert runner.argv_starting("git", "-C", str(consumer), "lfs") == []
