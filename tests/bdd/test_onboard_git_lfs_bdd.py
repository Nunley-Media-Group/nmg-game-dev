"""pytest-bdd bindings for onboard_git_lfs.feature: SCN001–SCN007 (#122).

Each scenario runs the real ``run_onboard`` against a fixture consumer, with stub commands from
``tests/onboard_fakes.py``. No real git or git-lfs runs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pytest_bdd import given, parsers, scenario, then, when

from nmg_game_dev.onboard import OnboardError, run_onboard
from nmg_game_dev.onboard.lfs import BEGIN, END, LFS_PATTERNS, block_text
from nmg_game_dev.onboard.report import format_report
from tests.onboard_fakes import (
    APPLE_SILICON,
    FakeRunner,
    all_tools_present,
    gib_free,
    make_consumer,
    make_framework,
    snapshot,
)

FEATURE = "onboard_git_lfs.feature"
GITATTRIBUTES = ".gitattributes"
RULE_LINES = [f"{pattern} filter=lfs diff=lfs merge=lfs -text" for pattern in LFS_PATTERNS]


def _context(tmp_path: Path) -> dict[str, Any]:
    volume = tmp_path / "volume"
    return {
        "framework": make_framework(tmp_path / "framework"),
        "consumer": make_consumer(tmp_path),
        "models": volume / "nmg-texture-models",
        "env": {
            "BLENDER_EXTENSIONS_DIR": str(tmp_path / "ext" / "user_default"),
            "TEXTURE_GEN_MODELS_DIR": str(volume / "nmg-texture-models"),
        },
        "runner": FakeRunner(),
        "which": all_tools_present,
        "error": None,
        "results": [],
        "before": None,
        "calls_after": [],
    }


def _install(ctx: dict[str, Any], *, refresh: bool = False) -> None:
    try:
        ctx["results"] = run_onboard(
            ctx["consumer"],
            framework=ctx["framework"],
            models_dir=ctx["models"],
            refresh=refresh,
            env=ctx["env"],
            run=ctx["runner"],
            which=ctx["which"],
            host=APPLE_SILICON,
            free_bytes=gib_free,
        )
        ctx["error"] = None
    except OnboardError as error:
        ctx["error"] = error


def _again(ctx: dict[str, Any]) -> None:
    """Run onboarding again and keep only the commands that second run issued."""
    mark = len(ctx["runner"].calls)
    _install(ctx)
    ctx["calls_after"] = ctx["runner"].calls[mark:]


def _attributes(ctx: dict[str, Any]) -> str:
    text: str = (ctx["consumer"] / GITATTRIBUTES).read_text(encoding="utf-8")
    return text


def _block_span(text: str) -> tuple[int, int]:
    start = text.index(BEGIN)
    return start, text.index(END) + len(END)


def _report_has(ctx: dict[str, Any], line: str) -> bool:
    return any(row.startswith(line) for row in format_report(ctx["results"]).splitlines())


# --- SCN001 ------------------------------


@scenario(FEATURE, "Fresh consumer gets the LFS block")
def test_fresh_consumer_gets_the_lfs_block() -> None:
    """AC1: .gitattributes is created with the managed block; the report says installed."""


@given("a consumer with no .gitattributes and git-lfs on PATH", target_fixture="ctx")
def _no_gitattributes(tmp_path: Path) -> dict[str, Any]:
    ctx = _context(tmp_path)
    assert not (ctx["consumer"] / GITATTRIBUTES).exists()
    return ctx


@when("onboarding installs into the consumer")
def _onboard(ctx: dict[str, Any]) -> None:
    _install(ctx)


@then(".gitattributes holds the nmg-game-dev managed block with one LFS line per framework pattern")
def _block_has_every_pattern(ctx: dict[str, Any]) -> None:
    assert ctx["error"] is None
    text = _attributes(ctx)
    start, end = _block_span(text)
    assert text.count(BEGIN) == 1
    assert text[start:end].split("\n") == [BEGIN, *RULE_LINES, END]


@then(parsers.re(r'^the report prints "(?P<line>[^"]+)"$'))
def _report_prints(ctx: dict[str, Any], line: str) -> None:
    assert _report_has(ctx, line), format_report(ctx["results"])


# --- SCN002 ------------------------------


@scenario(FEATURE, "Consumer lines outside the block are preserved")
def test_consumer_lines_are_preserved() -> None:
    """AC2: the block is appended once and every original byte is kept."""


@given(
    "a consumer whose .gitattributes has its own lines and no managed block",
    target_fixture="ctx",
)
def _own_lines(tmp_path: Path) -> dict[str, Any]:
    ctx = _context(tmp_path)
    original = b"# Game notes\r\n*.md text=auto\r\nlast line without newline"
    (ctx["consumer"] / GITATTRIBUTES).write_bytes(original)
    ctx["original"] = original
    return ctx


@then("the managed block is appended once")
def _appended_once(ctx: dict[str, Any]) -> None:
    assert ctx["error"] is None
    assert _attributes(ctx).count(BEGIN) == 1


@then("every original line is kept byte-for-byte")
def _original_kept(ctx: dict[str, Any]) -> None:
    assert (ctx["consumer"] / GITATTRIBUTES).read_bytes().startswith(ctx["original"])


# --- SCN003 ------------------------------


@scenario(FEATURE, "Re-running onboarding leaves the block unchanged")
def test_rerun_leaves_the_block_unchanged() -> None:
    """AC3: a second run leaves .gitattributes byte-for-byte unchanged and reports unchanged."""


@given("a consumer that has been onboarded once", target_fixture="ctx")
def _onboarded_once(tmp_path: Path) -> dict[str, Any]:
    ctx = _context(tmp_path)
    _install(ctx)
    assert ctx["error"] is None
    ctx["before"] = (ctx["consumer"] / GITATTRIBUTES).read_bytes()
    return ctx


@when("onboarding installs into the consumer again")
def _onboard_again(ctx: dict[str, Any]) -> None:
    _again(ctx)


@then(".gitattributes is byte-for-byte unchanged")
def _byte_for_byte_unchanged(ctx: dict[str, Any]) -> None:
    assert (ctx["consumer"] / GITATTRIBUTES).read_bytes() == ctx["before"]


# --- SCN004 ------------------------------


@scenario(FEATURE, "An edited block reports drift and refresh restores it")
def test_edited_block_reports_drift_and_refresh_restores_it() -> None:
    """AC4: drift is reported and left alone; --refresh replaces only the managed block."""


@given("an onboarded consumer whose managed block has been edited", target_fixture="ctx")
def _edited_block(tmp_path: Path) -> dict[str, Any]:
    ctx = _context(tmp_path)
    _install(ctx)
    assert ctx["error"] is None
    edited = _attributes(ctx).replace(RULE_LINES[0], "*.blend text=auto")
    edited += "*.local text=auto\n"
    (ctx["consumer"] / GITATTRIBUTES).write_text(edited, encoding="utf-8", newline="")
    start, end = _block_span(edited)
    ctx["before"] = edited.encode("utf-8")
    ctx["outside_before"] = (edited[:start], edited[end:])
    return ctx


@when("onboarding installs into the consumer without --refresh")
def _onboard_without_refresh(ctx: dict[str, Any]) -> None:
    _install(ctx)


@then(
    parsers.re(r'^the report prints "(?P<line>[^"]+)" with remediation "(?P<remediation>[^"]+)"$')
)
def _report_prints_with_remediation(ctx: dict[str, Any], line: str, remediation: str) -> None:
    matches = [r for r in ctx["results"] if f"{r.status} {r.name}" == line]
    assert matches, line
    assert matches[0].remediation == remediation


@then(".gitattributes is unchanged")
def _unchanged_after_drift(ctx: dict[str, Any]) -> None:
    assert (ctx["consumer"] / GITATTRIBUTES).read_bytes() == ctx["before"]


@when("onboarding installs into the consumer with --refresh")
def _onboard_with_refresh(ctx: dict[str, Any]) -> None:
    _install(ctx, refresh=True)


@then("only the managed block is replaced")
def _only_block_replaced(ctx: dict[str, Any]) -> None:
    assert ctx["error"] is None
    text = _attributes(ctx)
    start, end = _block_span(text)
    assert text[start:end] == block_text()
    assert (text[:start], text[end:]) == ctx["outside_before"]


# --- SCN005 ------------------------------


@scenario(FEATURE, "LFS hooks are installed in a git consumer")
def test_lfs_hooks_installed_in_a_git_consumer() -> None:
    """AC5: git lfs install --local runs once; a rerun with the hook present runs none."""


@given("a consumer that is a git work tree with no LFS pre-push hook", target_fixture="ctx")
def _git_work_tree(tmp_path: Path) -> dict[str, Any]:
    ctx = _context(tmp_path)
    ctx["runner"] = FakeRunner(work_tree=True)
    return ctx


@then('"git lfs install --local" runs in the consumer')
def _install_ran(ctx: dict[str, Any]) -> None:
    consumer = str(ctx["consumer"])
    assert ctx["runner"].argv_starting("git", "-C", consumer, "lfs", "install", "--local")


@then('no "git lfs install" runs')
def _no_install_on_rerun(ctx: dict[str, Any]) -> None:
    assert [call for call in ctx["calls_after"] if call[-3:] == ["lfs", "install", "--local"]] == []


# --- SCN006 ------------------------------


@scenario(FEATURE, "Missing git-lfs fails preflight")
def test_missing_git_lfs_fails_preflight() -> None:
    """AC6: git-lfs off PATH raises onboard.git_lfs_missing before any consumer write."""


@given("a consumer and git-lfs is not on PATH", target_fixture="ctx")
def _no_git_lfs(tmp_path: Path) -> dict[str, Any]:
    ctx = _context(tmp_path)
    ctx["which"] = lambda name: None if name == "git-lfs" else f"/usr/bin/{name}"
    ctx["before"] = snapshot(ctx["consumer"])
    return ctx


@then(
    parsers.re(
        r'^onboarding fails with "(?P<code>[^"]+)" and remediation "(?P<remediation>[^"]+)"$'
    )
)
def _fails_with(ctx: dict[str, Any], code: str, remediation: str) -> None:
    assert ctx["error"] is not None, "onboarding did not fail"
    assert ctx["error"].code == code
    assert ctx["error"].remediation == remediation


@then("no consumer file is written")
def _nothing_written(ctx: dict[str, Any]) -> None:
    assert snapshot(ctx["consumer"]) == ctx["before"]


# --- SCN007 ------------------------------


@scenario(FEATURE, "A consumer that is not a git repository")
def test_consumer_that_is_not_a_git_repository() -> None:
    """AC7: .gitattributes is written, git_lfs_hooks is skipped, and onboarding completes."""


@given("a consumer that is not inside a git work tree", target_fixture="ctx")
def _not_a_work_tree(tmp_path: Path) -> dict[str, Any]:
    return _context(tmp_path)


@then("onboarding completes")
def _completes(ctx: dict[str, Any]) -> None:
    assert ctx["error"] is None
    assert {r.name for r in ctx["results"]} >= {"gitattributes_lfs", "git_lfs_hooks"}


@then(".gitattributes holds the nmg-game-dev managed block")
def _block_present(ctx: dict[str, Any]) -> None:
    assert ctx["error"] is None
    text = _attributes(ctx)
    start, end = _block_span(text)
    assert text[start:end] == block_text()
