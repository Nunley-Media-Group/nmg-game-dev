# Tasks: Scan untracked exportable files in the /ship secret gate

**Issue**: #296
**Date**: 2026-11-19
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/255-block-commits-and-builds-that-contain-api-keys-in-consumer-projects/

## Implementation Tasks

### T001: Add the ship file source to the scanner

**File(s)**: `src/nmg_game_dev/secrets/scan.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- FR1: `shippable_files(root, project, run)` yields tracked files then the untracked files from `git ls-files -z --others --exclude-standard -- <project>/`; `scan_shippable` applies the existing patterns, `.env` rule, and allow file.
- FR2: untracked paths under `<project>/.godot/`, symbolic links, and non-regular paths are skipped.
- FR3: outside a git work tree `shippable_files` returns the existing `_walk_files(root)` unchanged.
- FR4: the module imports only the standard library; `scan_tracked`, `scan_staged`, and `main` behave as before.

### T002: Point the /ship gate at the new scan

**File(s)**: `src/nmg_game_dev/ship/runner.py`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- AC1: `_scan_secrets` calls `scan_shippable(project_dir.parent, project_dir.name)` before any Godot command and in a dry run.
- `ship.secret_scan_failed` still wraps `GitError`, with a message about listing the files to scan and the `git -C <consumer> ls-files` remediation.

### T003: Unit tests for the scanner and the ship gate

**File(s)**: `tests/unit/secrets/test_scan.py`, `tests/unit/ship/test_runner.py`
**Type**: Modify
**Depends**: T002
**Acceptance**:
- AC1: an untracked, unignored file under `game/` with a key is reported by `scan_shippable` and stops `/ship` (also `--dry-run`) with `ship.secret_found`, masked, no Godot call; `test_a_git_consumer_scans_tracked_files_only` is replaced by this behaviour.
- AC2: untracked files covered by `.gitignore`, outside `game/`, or under `game/.godot/` do not fail the gate.
- AC3: in a non-git consumer, keys in `.env`, `.env.local`, `.claude/settings.local.json`, `.venv/`, and `node_modules/` pass the ship gate, and a key in another file under the root stops it.
- The git-failure test monkeypatches `scan_shippable` and still yields `ship.secret_scan_failed`.
- `scan_tracked` still skips untracked files (existing test kept).
- Evidence: `uv run pytest tests/unit tests/bdd -q` (`repository.tests`).

### T004: BDD scenarios for the untracked and non-git gate

**File(s)**: `tests/bdd/features/ship_secret_untracked.feature`, `tests/bdd/test_ship_secret_untracked_bdd.py`
**Type**: Create
**Depends**: T002
**Acceptance**:
- One pytest-bdd scenario per AC1–AC3, matching this spec's `feature.gherkin`, using the `make_sandbox` ship sandbox and a real `git init` repository.
- Evidence: `uv run pytest tests/unit tests/bdd -q` (`repository.tests`).

### T005: Update the ship and onboarding docs

**File(s)**: `docs/skills/ship.md`, `docs/onboarding/index.md`
**Type**: Modify
**Depends**: T002
**Acceptance**:
- FR5: both docs say the gate scans tracked files plus untracked, unignored files under `game/` (except `game/.godot/`), and keep the non-git exclusion list with the reason (keys are meant to live in `.env` and `.claude/settings.local.json`).
- The `ship.secret_found` and `ship.secret_scan_failed` rows in `docs/skills/ship.md` describe the new scope.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #296 | 2026-11-19 | Initial feature tasks |
