# Tasks: Block commits and builds that contain API keys in consumer projects

**Issue**: #255
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley

## Implementation Tasks

### T001: Add the secret scanner and its CLI

**File(s)**: `src/nmg_game_dev/secrets/__init__.py`, `src/nmg_game_dev/secrets/scan.py`, `src/nmg_game_dev/secrets/__main__.py`
**Type**: Create
**Depends**: none
**Acceptance**:
- FR1, AC1: each pattern in design.md matches; a staged `.env` is reported; output lines carry path, line, pattern, the 4-character mask, and the fingerprint; exit 1.
- AC2: no match gives exit 0 and empty stdout and stderr.
- AC3: fingerprint and `path:pattern` allow entries suppress only their matches.
- FR4: the raw matched value never appears in any output.
- Binary and LFS-pointer content is skipped. `--staged` reads index blobs, not the working tree. `--tracked` falls back to a file walk outside a git work tree.
- `scan.py` imports only the standard library.

### T002: Install the scanner and pre-commit hook during onboarding

**File(s)**: `src/nmg_game_dev/onboard/secrets_hook.py`, `src/nmg_game_dev/onboard/runner.py`, `src/nmg_game_dev/onboard/report.py`
**Type**: Create
**Depends**: T001
**Acceptance**:
- AC5, FR2: `scripts/nmg_secret_scan.py` is synced byte-identical to `src/nmg_game_dev/secrets/scan.py`; the hook is written executable with the marker; an existing nmg hook is `unchanged`; a foreign hook yields `conflict` with `onboard.precommit_hook_conflict` and the call line as remediation, left byte-identical; outside a work tree the hook step is `skipped`.

### T003: Gate /ship on the tracked-file scan

**File(s)**: `src/nmg_game_dev/ship/runner.py`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- AC4, FR3: the scan runs before `--import` and every other gate, including in a dry run; a match raises `ship.secret_found` with masked matches and no Godot command runs; a clean consumer passes.
- Evidence: `gate-ship-smoke` (`scripts/ship-smoke.sh`).

### T004: Tests

**File(s)**: `tests/unit/secrets/__init__.py`, `tests/unit/secrets/test_scan.py`, `tests/unit/onboard/test_secrets_hook.py`, `tests/unit/onboard/test_runner.py`, `tests/unit/ship/test_runner.py`
**Type**: Create
**Depends**: T002, T003
**Acceptance**:
- AC1: one test per pattern plus `.env`, built in temporary git repositories with `git add`, checking the exit code, masked output, and that the raw value is absent from the output; the onboarded script copy blocks a real `git commit` in a temp repo.
- AC2: a clean staged change gives exit 0 and no output.
- AC3: fingerprint and `path:pattern` allow entries.
- Binary files, LFS pointers, and a key only in the working tree but not staged are not reported by `--staged`.
- AC4: `ShipSandbox` with a planted key fails `ship.secret_found` with no Godot call, also with `--dry-run`; a non-git sandbox is scanned by the file walk.
- AC5: the hook install states: none, nmg, foreign, and not a git repo.
- Evidence: `uv run pytest tests/unit -q` (`repository.tests`), `repository.lint`, `repository.format`, `repository.types`.

### T005: BDD scenarios

**File(s)**: `tests/bdd/features/secret_scan.feature`, `tests/bdd/test_secret_scan_bdd.py`
**Type**: Create
**Depends**: T004
**Acceptance**:
- SCN001–SCN005 bind AC1–AC5 using temporary git repositories, `ShipSandbox`, and the onboarding fakes.
- Evidence: `uv run pytest tests/bdd -q` (`repository.tests`).

### T006: Document the hook and the allow file

**File(s)**: `docs/onboarding/index.md`, `skills/onboard-consumer/references/install-steps.md`, `docs/skills/ship.md`, `CHANGELOG.md`
**Type**: Modify
**Depends**: T002, T003
**Acceptance**:
- FR6: `docs/onboarding/index.md` gains a "Secret scan" section covering the patterns, the hook, masked output, `.nmg/secret-scan-allow` with both entry forms, and what to do with a foreign hook; the install steps list `secret_scanner` and `precommit_hook`; `docs/skills/ship.md` lists the first gate and `ship.secret_found`.
- `CHANGELOG.md` `[Unreleased]` bullets for this issue each end with `(#255)`.
- Evidence: `plugin.validate` (`claude plugin validate .`).

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #255 | 2026-11-18 | Initial feature tasks |
