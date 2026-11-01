# Tasks: Configure Git LFS for binary assets during consumer onboarding

**Issue**: #122
**Date**: 2026-11-01
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/7-consumer-onboarding-onboard-consumer-skill-asset-contract-install-and-onboarding-docs/

## Implementation Tasks

### T001: Add the `skipped` report status

**File(s)**: `src/nmg_game_dev/onboard/report.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- FR6: `Status` includes `skipped`; `format_report` prints `skipped <step>: <detail>` with no remediation line when none is set.
- The module docstring lists `skipped`.

### T002: Implement the LFS module

**File(s)**: `src/nmg_game_dev/onboard/lfs.py`
**Type**: Create
**Depends**: T001
**Acceptance**:
- FR2: `LFS_PATTERNS` holds the 22 patterns in FR2 order; `block_text()` renders `# nmg-game-dev:begin`, one `<pattern> filter=lfs diff=lfs merge=lfs -text` line each, `# nmg-game-dev:end`.
- FR1, FR3: `ensure_gitattributes_lfs` creates, appends, verifies, drifts, or refreshes the block exactly as in design.md, preserving all bytes outside the block (including CRLF).
- FR5: `ensure_lfs_hooks` detects the work tree and hooks dir through the injected `Runner` with `git -C <consumer>`, and returns `installed` / `unchanged` / `skipped` (`not a git repository`) or raises `onboard.git_lfs_hooks_failed`.
- Type hints on all public functions; `from __future__ import annotations`.

### T003: Wire preflight and steps into `run_onboard`

**File(s)**: `src/nmg_game_dev/onboard/runner.py`, `src/nmg_game_dev/onboard/__init__.py`
**Type**: Modify
**Depends**: T002
**Acceptance**:
- FR4: `_check_prerequisites` raises `onboard.git_lfs_missing` with remediation `Install Git LFS (brew install git-lfs), then re-run onboarding.` when `which("git-lfs")` is `None`, after the git check.
- FR7: `gitattributes_lfs` then `git_lfs_hooks` are appended right after `gitignore_env`; the existing step order is unchanged.
- Docstrings that list step order or statuses include the new steps and `skipped`.

### T004: Extend the onboarding test fakes

**File(s)**: `tests/onboard_fakes.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- `FakeRunner(work_tree=...)` answers `rev-parse --is-inside-work-tree`, `rev-parse --git-path hooks`, and `lfs install --local` as described in design.md; `fail="lfs-install"` makes the install exit 1.
- Existing `rev-parse HEAD` behavior for VibeUE is unchanged.

### T005: Unit tests for AC1–AC7

**File(s)**: `tests/unit/onboard/test_lfs.py`, `tests/unit/onboard/test_runner.py`
**Type**: Create | Modify
**Depends**: T003, T004
**Acceptance**:
- AC1: missing `.gitattributes` is created with the block built from `LFS_PATTERNS`; result `installed`.
- AC2: existing lines (including a file without a final newline and a CRLF file) are kept byte-for-byte and the block is appended once.
- AC3: a second call is `unchanged` and the file bytes are identical.
- AC4: an edited block is `drift` with remediation `re-run with --refresh` and the file unchanged; with `refresh=True` only the block is replaced and the result is `refreshed`.
- AC5: with `FakeRunner(work_tree=True)`, `["git", "-C", <consumer>, "lfs", "install", "--local"]` runs once and the result is `installed`; a re-run runs no install and is `unchanged`; `fail="lfs-install"` raises `onboard.git_lfs_hooks_failed`.
- AC6: `which` returning `None` for `git-lfs` raises `onboard.git_lfs_missing` with the exact remediation and `snapshot(consumer)` is unchanged.
- AC7: a non-work-tree consumer gets `.gitattributes` and `skipped git_lfs_hooks: not a git repository`, and later steps' results are still returned.
- `test_rerun_is_a_no_op` accepts `skipped` for `git_lfs_hooks` only; `test_fresh_install_installs_framework_files` includes `gitattributes_lfs` and `git_lfs_hooks`; the report order has both new steps directly after `gitignore_env`.
- Evidence: `repository.tests` (`uv run pytest tests/unit tests/bdd -q`), `repository.lint`, `repository.format`, `repository.types`.

### T006: BDD scenarios for AC1–AC7

**File(s)**: `tests/bdd/features/onboard_git_lfs.feature`, `tests/bdd/test_onboard_git_lfs_bdd.py`
**Type**: Create
**Depends**: T003, T004
**Acceptance**:
- The feature file holds SCN001–SCN007 matching this spec's `feature.gherkin`, one per AC.
- Step bindings run the real `run_onboard` against `make_consumer` / `make_framework` with `FakeRunner`, as `tests/bdd/test_onboard_bdd.py` does.
- Evidence: `repository.tests`.

### T007: Update onboarding docs and skill

**File(s)**: `skills/onboard-consumer/references/install-steps.md`, `skills/onboard-consumer/SKILL.md`, `docs/onboarding/index.md`, `tests/unit/onboard/test_docs_and_skill.py`
**Type**: Modify
**Depends**: T003
**Acceptance**:
- FR8: install-steps.md preflight table lists `git-lfs` on PATH → `onboard.git_lfs_missing`; its step table has `gitattributes_lfs` (`.gitattributes`, managed block, drift-checked) and `git_lfs_hooks` (`git lfs install --local`, skipped outside a git work tree) after `gitignore_env`.
- SKILL.md flow step 3 lists `skipped`; failure modes list `onboard.git_lfs_missing` (install Git LFS, re-run) and `onboard.git_lfs_hooks_failed`.
- docs/onboarding/index.md flow step 1 mentions the Git LFS setup and a section explains converting already-committed files with `git add --renormalize .` (and that onboarding never runs it or `git lfs migrate`).
- `test_docs_and_skill.py` asserts those strings are present; evidence `repository.tests`.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #122 | 2026-11-01 | Initial feature tasks |
