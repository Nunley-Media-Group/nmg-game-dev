"""The secret-scan onboarding steps: the scanner copy and the pre-commit hook (#255 FR2, AC5).

``ensure_secret_scanner`` syncs ``src/nmg_game_dev/secrets/scan.py`` to
``scripts/nmg_secret_scan.py`` with the usual drift rules. ``ensure_precommit_hook`` writes a
``pre-commit`` hook that runs that copy with ``--staged``. An existing nmg hook is ``unchanged``.
A foreign hook is never overwritten: the step is ``conflict`` and its remediation names the line to
add to it. Outside a git work tree the hook step is ``skipped``. All git commands go through the
injected ``Runner``.
"""

from __future__ import annotations

import stat
from pathlib import Path

from nmg_game_dev.onboard.commands import Runner
from nmg_game_dev.onboard.errors import OnboardError
from nmg_game_dev.onboard.files import sync_file
from nmg_game_dev.onboard.lfs import NOT_A_REPO
from nmg_game_dev.onboard.report import StepResult

SCANNER_SRC = Path("src/nmg_game_dev/secrets/scan.py")
SCANNER_DST = "scripts/nmg_secret_scan.py"
HOOK_NAME = "pre-commit"
HOOK_MARKER = "# nmg-game-dev secret scan"
CALL_LINE = (
    'python3 "$(git rev-parse --show-toplevel)/scripts/nmg_secret_scan.py" --staged || exit 1'
)
HOOK_TEXT = f"#!/bin/sh\n{HOOK_MARKER}\n{CALL_LINE}\n"
HOOK_LOOKUP_REMEDIATION = (
    "Check that the consumer is a healthy git repository, then re-run onboarding."
)


def ensure_secret_scanner(name: str, framework: Path, target: Path, refresh: bool) -> StepResult:
    """Copy the framework scanner to ``scripts/nmg_secret_scan.py`` (drift-checked)."""
    return sync_file(framework / SCANNER_SRC, target, SCANNER_DST, name=name, refresh=refresh)


def _display(hooks: Path, target: Path) -> str:
    try:
        return str(hooks.relative_to(target))
    except ValueError:
        return str(hooks)


def ensure_precommit_hook(name: str, target: Path, *, run: Runner) -> StepResult:
    """Install the nmg pre-commit hook in the git work tree at ``target``, or report why not.

    Returns ``skipped`` outside a git work tree, ``unchanged`` when the hook already carries the nmg
    marker, ``installed`` when no hook existed, and ``conflict`` when a foreign hook exists.
    """
    inside = run(["git", "-C", str(target), "rev-parse", "--is-inside-work-tree"], None)
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return StepResult(name, "skipped", NOT_A_REPO)
    lookup = run(["git", "-C", str(target), "rev-parse", "--git-path", "hooks"], None)
    if lookup.returncode != 0 or not lookup.stdout.strip():
        raise OnboardError(
            "onboard.precommit_hook_failed",
            f"git rev-parse --git-path hooks failed in {target}: {lookup.stderr.strip()}",
            HOOK_LOOKUP_REMEDIATION,
        )
    hooks = Path(lookup.stdout.strip())
    if not hooks.is_absolute():
        hooks = target / hooks
    hook = hooks / HOOK_NAME
    if not hook.exists():
        hooks.mkdir(parents=True, exist_ok=True)
        hook.write_text(HOOK_TEXT, encoding="utf-8")
        hook.chmod(hook.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return StepResult(
            name, "installed", f"wrote the secret-scan {HOOK_NAME} hook to {_display(hook, target)}"
        )
    text = hook.read_text(encoding="utf-8", errors="replace")
    if HOOK_MARKER in text:
        return StepResult(
            name, "unchanged", f"secret-scan hook present in {_display(hook, target)}"
        )
    return StepResult(
        name,
        "conflict",
        f"onboard.precommit_hook_conflict: a {HOOK_NAME} hook already exists at "
        f"{_display(hook, target)}; it was left unchanged",
        f"Add this line to it: {CALL_LINE}",
    )
