# Tasks: Ship skills — per-platform build, sign, notarize, package

**Issue**: #6
**Date**: 2026-10-29
**Status**: Approved
**Author**: Rich Nunley

## Implementation Tasks

### T001: Implement the mobile budget gate

**File(s)**: `src/nmg_game_dev/quality/mobile_budgets.py`, `scripts/audit-mobile-budgets.py`
**Type**: Create
**Depends**: none
**Acceptance**:
- `DEFAULT_MOBILE_BUDGETS` matches the design table; `check_mobile_budgets(project_root)` finds every `Content/**/Mobile/` folder, reads `nmg-asset.json`, merges `nmg-budgets.json` overrides, and returns a pydantic `MobileBudgetAudit` with per-asset findings (FR6)
- Over-budget, missing-report, invalid-report, and invalid-override cases produce the codes and remediation text in design § Data / Storage Changes (AC6, AC7, AC8)
- `scripts/audit-mobile-budgets.py --project-root <dir>` prints findings and exits 0 on pass, 1 on fail

### T002: Implement the cook-manifest gate script

**File(s)**: `scripts/verify-cook-manifest.sh`
**Type**: Create
**Depends**: none
**Acceptance**:
- Accepts `--variant desktop|mobile` and a directory or listing file; normalizes backslashes to forward slashes; exits 1 and prints every cross-variant `Content/` path; exits 0 when clean; exits 2 with `Remediation:` on bad args or a missing path (FR5, AC4)

### T003: Implement per-platform build scripts

**File(s)**: `scripts/build-macos.sh`, `scripts/build-ios.sh`, `scripts/build-android.sh`, `scripts/build-windows.sh`
**Type**: Create
**Depends**: none
**Acceptance**:
- Each script builds the exact UAT / ssh / scp command lines in design § API / Interface Changes (FR3, AC1, AC3, AC5)
- `--dry-run` prints `DRY-RUN:` lines with the Android keystore password shown as `***`, runs no external tool, and exits 0 (FR10)
- Outside dry-run, a missing `RunUAT.sh` or `ssh`, or an unset required variable, exits 2 with a one-line remediation naming the variable or path, not its value

### T004: Implement macOS signing and notarization scripts

**File(s)**: `scripts/sign-macos.sh`, `scripts/notarize-macos.sh`
**Type**: Create
**Depends**: none
**Acceptance**:
- `sign-macos.sh` runs the codesign sign and verify commands from the design (FR4, AC1)
- `notarize-macos.sh` zips with `ditto`, submits with `xcrun notarytool submit … --wait`, exits 1 unless the output contains `status: Accepted`, then staples; the app-specific password is never printed (FR4, AC1, AC9)
- `--dry-run` prints `DRY-RUN: notarization pass (no submission) for team <TEAM>` and exits 0 (AC2)

### T005: Implement the ship Python package

**File(s)**: `src/nmg_game_dev/ship/__init__.py`, `src/nmg_game_dev/ship/errors.py`, `src/nmg_game_dev/ship/targets.py`, `src/nmg_game_dev/ship/identity.py`, `src/nmg_game_dev/ship/artifacts.py`, `src/nmg_game_dev/ship/release_notes.py`
**Type**: Create | Modify
**Depends**: none
**Acceptance**:
- The `__init__.py` stub is replaced (not re-created elsewhere) and re-exports the public names in design § Modules
- `expand_target` and `preflight_env` implement the group order and `REQUIRED_ENV` table; a missing variable raises `ShipError` with code `ship.env_missing` naming the variable, not any value (FR1, FR2, AC9)
- `resolve_signing_identity` implements FR8 and raises `ship.signing_identity_missing` when nothing matches the team (AC9)
- `locate_artifact` / `publish_artifact` / `write_release_notes` implement FR9 (AC1)

### T006: Implement the ship runner and CLI

**File(s)**: `src/nmg_game_dev/ship/runner.py`, `src/nmg_game_dev/ship/__main__.py`
**Type**: Create
**Depends**: T001, T002, T003, T004, T005
**Acceptance**:
- `run_ship` follows the design architecture: preflight → mobile budget gate (mobile platforms only, before any build) → per-platform build → cook-manifest gate → sign/notarize (macOS) → publish → release notes (FR7, AC1, AC3, AC4, AC5, AC6)
- A failing gate or script leaves no artifact for that platform in `release/<platform>/` and raises `ShipError` with the script's remediation (AC4, AC6)
- `--dry-run` passes `--dry-run` to every script, skips the cook-manifest gate and artifact copy, writes `release/<platform>/DRY-RUN.txt`, and marks the release notes as a dry run (AC2)
- The CLI prints `ERROR [<code>]: …` / `Remediation: …` to stderr and exits 1 on `ShipError`

### T007: Add the ship smoke script

**File(s)**: `scripts/ship-smoke.sh`
**Type**: Create
**Depends**: T006
**Acceptance**:
- Runs the dry-run `all` ship against `fixtures/dogfood.uproject` with placeholder credentials in a temp release dir, cleans up, and exits 0 when the ship succeeds (FR11, AC10)

### T008: Add the ship skill and consumer docs

**File(s)**: `skills/ship/SKILL.md`, `docs/skills/ship.md`, `CHANGELOG.md`
**Type**: Create | Modify
**Depends**: T006
**Acceptance**:
- `SKILL.md` follows the structure-steering skill template with `name: ship`, `required_mcp: []`, `required_env` listing the per-platform variables, and `unattended_safe: true`; its flow invokes `uv run --project "${CLAUDE_PLUGIN_ROOT}" python -m nmg_game_dev.ship <target> --project <uproject>` and lists the failure codes with remediation (FR12, AC11)
- `docs/skills/ship.md` leads with the ship flow, then targets, env vars, the `nmg-asset.json` / `nmg-budgets.json` formats, and `release/` layout
- `CHANGELOG.md` `[Unreleased]` gets a bullet for the ship skill ending with `(#6)`
- The registered `plugin.validate` validation passes

### T009: Unit tests for the mobile budget gate

**File(s)**: `tests/unit/quality/test_mobile_budgets.py`
**Type**: Create
**Depends**: T001
**Acceptance**:
- Covers AC6 (over-budget `standard_prop` with 4,200 tris fails with the overage), AC7 (missing report → `ship.budget_report_missing` naming `Props/Lamp`), AC8 (override 5,000 passes), and invalid report/override codes
- Passes under the `repository.tests` validation (`uv run pytest tests/unit tests/bdd -q`)

### T010: Unit tests for the ship package and scripts

**File(s)**: `tests/unit/ship/__init__.py`, `tests/unit/ship/conftest.py`, `tests/unit/ship/test_targets.py`, `tests/unit/ship/test_identity.py`, `tests/unit/ship/test_artifacts.py`, `tests/unit/ship/test_scripts.py`, `tests/unit/ship/test_runner.py`, `tests/unit/ship/test_ship_smoke.py`, `tests/unit/ship/test_skill.py`
**Type**: Create
**Depends**: T006, T007, T008
**Acceptance**:
- `conftest.py` provides a temp `UE_ROOT` with a stub `RunUAT.sh`, plus stub `codesign`, `security`, `xcrun`, `ditto`, `ssh`, `scp` on `PATH`. Each stub logs its argv to a file; the stubs create the archive outputs and `Saved/Cooked/<Platform>/<Project>/Content/...` files, with a switch to inject a cross-variant path
- Covers AC1 (UAT flags, codesign identity, notarytool `--team-id`, staple, `.app` in `release/macos/`, rerun replaces it, SHA-256 in release notes), AC2 (no stub invoked, `DRY-RUN:` lines, `DRY-RUN.txt`), AC3 (`.ipa` / `.aab`, password absent from output), AC4 (mobile and desktop leaks exit non-zero, no release artifact), AC5 (ssh RunUAT.bat `-platform=Win64`, `.exe` in `release/windows/`), AC9 (each missing variable and the no-identity case fail before UAT, no secret value in output)
- `test_ship_smoke.py` runs `scripts/ship-smoke.sh` and asserts exit 0 (AC10); `test_skill.py` parses `skills/ship/SKILL.md` frontmatter and asserts the AC11 fields
- Passes under the `repository.tests` validation and the `repository.types` / `repository.lint` validations

### T011: BDD acceptance scenarios for ship

**File(s)**: `tests/bdd/features/ship.feature`, `tests/bdd/test_ship_bdd.py`
**Type**: Create
**Depends**: T010
**Acceptance**:
- `ship.feature` contains the eleven scenarios from this spec's `feature.gherkin` (`@SCN001`–`@SCN011`), each bound with `@scenario` and implemented with the T010 stub fixtures
- Passes under the `repository.tests` validation

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #6 | 2026-10-29 | Initial feature tasks |
