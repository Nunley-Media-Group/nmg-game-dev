# Verification Report: Ship skills — per-platform build, sign, notarize, package

**Date**: 2026-10-30
**Issue**: #6
**Reviewer**: Claude (nmg-sdlc verify worker)
**Scope**: Implementation verification against spec

**Verification head**: e8e7490eabfb8a5589743b481897d89cfee1ed59

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 4 |
| Security | 4 |
| Performance | 4 |
| Testability | 5 |
| Error Handling | 4 |
| **Overall** | 4.3 |

### Implementation Status: Pass

**Total Issues**: 1 (Low, not blocking)

The previous run (head `078a854`) failed AC3 because the Android keystore password went on UAT's
command line, which UE 5.8's AutomationTool logs at startup. Commits `e177198` and `e8e7490` fix it:

- `scripts/build-android.sh` no longer passes `KeyStorePassword` on the command line. For the run
  only, it writes the password into the project's `Config/UserEngine.ini` between
  `; BEGIN/END nmg-game-dev ship` markers, with `umask 077`, and restores the file's previous state
  on exit (an `EXIT` trap, plus `INT`/`TERM` handlers).
- UAT's stdout and stderr go through a literal-match `redact` filter before they are echoed.
- Every run, dry or real, first removes a block that an interrupted run left behind.
- In a git repo, a real run refuses (exit 2, with `Remediation:`) to write a `UserEngine.ini` that
  git tracks or does not ignore.

I checked the fix against the installed UE 5.8 source:

- UBT's `ConfigHierarchy.cs:1022` loads `{PROJECT}/Config/User{TYPE}.ini` as the last config layer,
  so the override reaches `UEDeployAndroid.cs:3970`
  (`Ini.GetString(... "KeyStorePassword" ...)`).
- `Engine/Config/BaseGame.ini:141` (`+IniKeyDenylist=KeyStorePassword`) keeps the key out of staged
  config, so the password does not get into the `.aab`.

The test shim now prints `Parsing command line: <argv>` the way real UAT does, so the no-leak tests
cover the path that failed before. All five registered validations pass at the verification head on
a clean tree. The stale lockfiles from the previous report are fixed: `uv.lock` and
`mcp-servers/finalize/uv.lock` now say `0.13.0`.

---

## Issue Scope

- Active issue: #6
- Spec: `specs/6-ship-skills-per-platform-build-sign-notarize-package`
- Manifest: `implicit single issue`
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1–AC11]; FR [FR1–FR12]; tasks [T001–T011]; scenarios [SCN001–SCN011]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":6,"specPath":"specs/6-ship-skills-per-platform-build-sign-notarize-package","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6","AC7","AC8","AC9","AC10","AC11"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6","FR7","FR8","FR9","FR10","FR11","FR12"],"tasks":["T001","T002","T003","T004","T005","T006","T007","T008","T009","T010","T011"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006","SCN007","SCN008","SCN009","SCN010","SCN011"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

## Deterministic Steering Artifact

- Runner: `sdlc-verify-steering.mjs --base main --controller-run-id 40468ffe-0554-4b4f-b7a9-4cdbd44bd3ba`
- Artifact: `.nmg-sdlc/verification/6.json`, `ok: true`, `ceiling: null`
- Coverage: declared 5, recorded 5, complete `true`; no missing, duplicate, or unknown results
- Identity: head `e8e7490eabfb8a5589743b481897d89cfee1ed59`, tree state `clean`, spec hash
  `sha256:3721071c…e37`, steering hash `sha256:c53014e6…09c3`

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | macOS package, sign, notarize, release | Pass | `scripts/build-macos.sh`, `scripts/sign-macos.sh`, `scripts/notarize-macos.sh`, `src/nmg_game_dev/ship/runner.py`, `artifacts.py`, `release_notes.py`; `tests/unit/ship/test_runner.py`, SCN001 |
| AC2 | Dry run reports the plan without building | Pass | The runner sends `--dry-run` to every script, skips the gate and the copy, and writes `DRY-RUN.txt`; `identity.py` runs nothing in a dry run; SCN002 |
| AC3 | Mobile produces `.ipa` and `.aab`; the keystore password never appears in output | Pass | `scripts/build-android.sh` (UserEngine.ini override plus `redact`); `tests/unit/ship/test_scripts.py` (`test_build_android_masks_the_keystore_password_in_output`, `…_redacts_the_password_from_uat_output`, restore and leftover-block tests); SCN003 |
| AC4 | Cook-manifest gate blocks cross-variant leaks | Pass | `scripts/verify-cook-manifest.sh` (desktop and mobile regexes, backslash normalization); the runner clears `release/<platform>/`; SCN004 |
| AC5 | Windows remote build | Pass | `scripts/build-windows.sh` (ssh `RunUAT.bat -platform=Win64`, remote listing, scp copy-back); SCN005 |
| AC6 | Budget gate blocks before any build | Pass | `_gate_mobile_budgets` runs before the platform loop; `quality/mobile_budgets.py` reports the overage; SCN006 |
| AC7 | A missing report fails with `ship.budget_report_missing` | Pass | `quality/mobile_budgets.py`; SCN007 |
| AC8 | `nmg-budgets.json` overrides apply | Pass | SCN008 |
| AC9 | Missing prerequisites fail fast without leaking secrets | Pass | `targets.preflight_env` and `identity.py` fail before UAT; with the AC3 fix, a real run's UAT output is redacted too; SCN009 |
| AC10 | Ship smoke dry run succeeds | Pass | `scripts/ship-smoke.sh` exits 0 (rerun here); `tests/unit/ship/test_ship_smoke.py` |
| AC11 | The ship skill is the single entry point | Pass | `skills/ship/SKILL.md` frontmatter and flow; `tests/unit/ship/test_skill.py`; `plugin.validate` passes |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Mobile budget gate | Complete | `quality/mobile_budgets.py`, `scripts/audit-mobile-budgets.py` |
| T002 | Cook-manifest gate script | Complete | `scripts/verify-cook-manifest.sh` |
| T003 | Per-platform build scripts | Complete | The Android script now keeps the password off UAT's command line |
| T004 | macOS sign and notarize scripts | Complete | |
| T005 | Ship Python package | Complete | The `__init__.py` stub is replaced in place |
| T006 | Runner and CLI | Complete | |
| T007 | Ship smoke script | Complete | |
| T008 | Skill and consumer docs | Complete | `docs/skills/ship.md` documents the UserEngine.ini behavior |
| T009 | Budget gate unit tests | Complete | |
| T010 | Ship package and script unit tests | Complete | The shim echoes `Parsing command line:` like real UAT |
| T011 | BDD scenarios | Complete | SCN001–SCN011 in `tests/bdd/features/ship.feature` |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 4 | targets, identity, artifacts, release notes, and runner are separate; each script drives one tool |
| Open/Closed | 4 | Targets come from table-driven `REQUIRED_ENV` and group expansion |
| Liskov Substitution | 5 | N/A beyond the injectable `run` callable |
| Interface Segregation | 4 | Each script has its own CLI contract |
| Dependency Inversion | 4 | Tests inject the tools through PATH shims and an injectable runner |

### Layer Separation

The ship layer touches no content; content is frozen by the time it runs, per structure steering. The
skill only calls `python -m nmg_game_dev.ship`.

---

## Security Assessment

- [x] Secrets via env only; preflight names variables, never values
- [x] Printed commands mask the Android password and the notarization credentials as `***`
- [x] The Android password is off UAT's command line, and UAT's output is redacted (prior High
  finding fixed)
- [x] The temporary `UserEngine.ini` is written `umask 077`, restored on exit, cleaned up after an
  interrupted run, and refused when git would commit it
- [x] The password is not staged into the package (`IniKeyDenylist=KeyStorePassword` in UE's
  `BaseGame.ini`)
- [ ] `notarytool --password` still passes the app-specific password in process argv, where `ps`
  can see it. notarytool does not echo it, so it does not reach the output (Low; see Remaining
  Issues)

## Performance Assessment

- [x] Streaming SHA-256 in 1 MiB chunks
- [x] No redundant builds; groups expand to unique platforms
- [x] The `redact` line filter is linear in UAT's output, which is fine for build logs

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1–AC11 | Yes (SCN001–SCN011) | Yes | Yes |

### Coverage Summary

- Feature files: 11 scenarios (`tests/bdd/features/ship.feature`)
- Step definitions: Implemented (`tests/bdd/test_ship_bdd.py`)
- Ship and budget subset rerun here: 87 passed
- Full `uv run pytest tests/unit tests/bdd -q`: pass (registered `repository.tests`)

---

## Exercise Test Results

| Field | Value |
|-------|-------|
| **Reason** | Not applicable: the diff changes no nmg-sdlc `workflows/` or `agents/` files. The consumer skill is covered by `plugin.validate`, `plugin.session-smoke`, and `test_skill.py`. |

---

## Registered Validations

| Validation | Provider | Status | Evidence |
|------------|----------|--------|----------|
| `repository.tests` | builtin.command (`uv run pytest tests/unit tests/bdd -q`) | Pass | exit 0 at `e8e7490`, clean tree |
| `repository.lint` | builtin.command (`uv run ruff check .`) | Pass | exit 0 |
| `repository.types` | builtin.command (`uv run mypy src tests`) | Pass | exit 0 |
| `plugin.validate` | builtin.command (`claude plugin validate .`) | Pass | exit 0 |
| `plugin.session-smoke` | project.plugin-session-smoke | Pass | `blender` connected |

**Gate Summary**: 5/5 passed, 0 failed, 0 incomplete

Supporting checks run here (not registered): `shellcheck -S style` on all ship scripts is clean;
`scripts/ship-smoke.sh` exits 0.

---

## Fixes Applied

None in this verification run. The prior report's High finding (keystore password in UAT output)
and Low finding (stale lockfiles) were fixed in implementation commits `e177198` and `e8e7490`.

## Remaining Issues

### Low Priority

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Security |
| **Location** | `scripts/notarize-macos.sh:71` |
| **Issue** | `xcrun notarytool submit … --password "$password"` puts the app-specific password in process argv |
| **Impact** | Other local users can see it through `ps` while the submission runs. It is not printed to output. |
| **Reason Not Fixed** | Outside the verify publication scope. Follow-up: support `--keychain-profile` |

---

## Positive Observations

- The leak fix is defense in depth: the password is kept off the command line, UAT's output is
  redacted, the ini is restored, leftover blocks are cleaned up, and a git-tracked ini is refused.
- The test shim now behaves like real UAT, including failing an Android build that has no keystore
  password, so it would have caught the original defect.

## Recommendation

**Ready for PR**

Every AC passes with code and test evidence, and all five registered validations pass at
`e8e7490` on a clean tree. The one remaining issue is Low and does not block the PR.
