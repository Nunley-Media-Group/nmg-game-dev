# Verification Report: Ship skills — per-platform build, sign, notarize, package

**Issue**: #6
**Date**: 2026-10-30
**Verification head**: 078a85412515e97685a3b7af17f2e6c160f2f13d

## Verification Report

### Implementation Status: Fail

### Executive Summary

The ship package, scripts, skill, and docs implement every task (T001–T011), and all five
registered validations pass at the verification head. One confirmed defect fails the run: a real
Android ship prints the keystore password. `scripts/build-android.sh` puts
`KeyStorePassword=<secret>` in UAT's `-ini:` override. UE 5.8's AutomationTool logs its full
command line, without redaction, at startup
(`Engine/Source/Programs/AutomationTool/Program.cs:320`:
`Logger.LogInformation("Parsing command line: {CommandLine}", ...)`). The runner then echoes the
script's stdout (`src/nmg_game_dev/ship/runner.py`, `_run_script`). The script masks the password
only in the `RUN:` line it prints itself, so the secret reaches the ship's output. This breaks AC3
("the Android keystore password never appears in the command output") and the "never echoed to
logs" security rule in tech steering. The stub `RunUAT.sh` in `tests/ship_fakes.py` does not echo its
arguments the way real UAT does, so the tests do not catch it.

The verify worker's publication scope covers only this report, so the fix goes back to
implementation.

### Issue Scope

- Active issue: #6
- Spec: `specs/6-ship-skills-per-platform-build-sign-notarize-package`
- Manifest: `implicit single issue`
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1–AC11]; FR [FR1–FR12]; tasks [T001–T011]; scenarios [SCN001–SCN011]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":6,"specPath":"specs/6-ship-skills-per-platform-build-sign-notarize-package","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6","AC7","AC8","AC9","AC10","AC11"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6","FR7","FR8","FR9","FR10","FR11","FR12"],"tasks":["T001","T002","T003","T004","T005","T006","T007","T008","T009","T010","T011"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006","SCN007","SCN008","SCN009","SCN010","SCN011"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

### Delivery Validation

- Local verification: Not complete (AC3 fails)
- PR evidence: Not required

### Deterministic Steering Artifact

- Runner: `sdlc-verify-steering.mjs --base main --controller-run-id 40468ffe-0554-4b4f-b7a9-4cdbd44bd3ba`
- Artifact: `.nmg-sdlc/verification/6.json`, `ok: true`, `ceiling: null`
- Coverage: declared 5, recorded 5, complete `true`; no missing, duplicate, or unknown results
- Identity: head `078a85412515e97685a3b7af17f2e6c160f2f13d`, spec hash
  `sha256:3721071c…e37`, steering hash `sha256:c53014e6…09c3`
- Tree state at gate time: dirty, with only `uv.lock` and `mcp-servers/finalize/uv.lock` modified
  (see Remaining Issues)

### Acceptance Criteria

- [x] AC1: macOS package, sign, notarize, release — `scripts/build-macos.sh`, `scripts/sign-macos.sh`,
  `scripts/notarize-macos.sh`, `src/nmg_game_dev/ship/runner.py`, `artifacts.py`, `release_notes.py`;
  tested in `tests/unit/ship/test_runner.py` and SCN001
- [x] AC2: Dry run reports the plan without building — the runner sends `--dry-run` to every script,
  skips the gate and the copy, and writes `DRY-RUN.txt`; `identity.py` runs nothing in a dry run; SCN002
- [ ] AC3: Mobile produces an `.ipa` and an `.aab` — **Fail**. Both artifacts and the cook gates are
  correct, but the password-never-in-output clause fails against real UAT (see Executive Summary).
  The stubbed test passes because the stub `RunUAT.sh` does not echo its argv.
- [x] AC4: Cook-manifest gate blocks cross-variant leaks — `scripts/verify-cook-manifest.sh` (desktop
  and mobile regexes, backslash normalization); the runner clears `release/<platform>/` before the
  build; SCN004
- [x] AC5: Windows remote build — `scripts/build-windows.sh` (ssh `RunUAT.bat` `-platform=Win64`,
  remote listing for the gate, scp copy-back); `_cook_targets` gates the listing as desktop; SCN005
- [x] AC6: The budget gate blocks before any build — `_gate_mobile_budgets` runs before the platform
  loop; `quality/mobile_budgets.py` reports the overage; SCN006
- [x] AC7: A missing report fails with `ship.budget_report_missing` naming `Props/Lamp`; SCN007
- [x] AC8: `nmg-budgets.json` overrides apply; SCN008
- [~] AC9: Missing prerequisites fail fast — preflight (`targets.preflight_env`) and identity
  resolution (`identity.py`) name the variable or identity before UAT and print no secret values;
  SCN009 passes. The clause "no secret value appears in the output" holds for preflight failures,
  but the AC3 leak shows that a real run's UAT output is not redacted.
- [x] AC10: `scripts/ship-smoke.sh` dry-runs `all` against `fixtures/dogfood.uproject` with
  placeholder credentials; `tests/unit/ship/test_ship_smoke.py`
- [x] AC11: `skills/ship/SKILL.md` frontmatter has `name: ship`, `required_mcp: []`, `required_env`,
  and `unattended_safe: true`; the flow invokes `python -m nmg_game_dev.ship`;
  `tests/unit/ship/test_skill.py`

### Tasks

T001–T011 each produced the listed files (all present in the `main...HEAD` diff, see the artifact's
`changedPaths`). `src/nmg_game_dev/ship/__init__.py` replaces the stub in place.

### Architecture Review

| Area | Score (1-5) |
|------|-------------|
| SOLID Principles | 4 |
| Security | 2 |
| Performance | 4 |
| Testability | 4 |
| Error Handling | 4 |

**Average**: 3.6

- **SOLID**: Clear split of targets / identity / artifacts / release notes / runner. Each script is one
  tool, and the runner only orchestrates.
- **Security**: Preflight and the scripts' own printed commands mask secrets correctly. However, the
  Android password goes through UAT, which logs it, and the runner echoes it (confirmed defect). The
  secrets also sit in process argv (`KeyStorePassword=` for UAT, `--password` for `notarytool`), where
  other local users can see them through `ps`. `notarytool --keychain-profile` would avoid the second.
- **Performance**: Streaming SHA-256 in 1 MiB chunks; no redundant builds.
- **Testability**: PATH shims for every tool and injectable `run` for identity. One gap: the stub UAT
  does not echo its command line, which is how the AC3 leak got past the tests.
- **Error handling**: Structured `ShipError` codes with remediation; scripts exit 2 with a
  `Remediation:` line; a failing gate leaves no artifact.

### Test Coverage

- BDD scenarios: 11/11 acceptance criteria covered (`tests/bdd/features/ship.feature`, SCN001–SCN011)
- Step definitions: Implemented (`tests/bdd/test_ship_bdd.py`)
- Test execution: Pass (`uv run pytest tests/unit tests/bdd -q`)

### Registered Validations

| Validation | Provider | Status |
|------------|----------|--------|
| `repository.tests` | builtin.command (`uv run pytest tests/unit tests/bdd -q`) | Pass |
| `repository.lint` | builtin.command (`uv run ruff check .`) | Pass |
| `repository.types` | builtin.command (`uv run mypy src tests`) | Pass |
| `plugin.validate` | builtin.command (`claude plugin validate .`) | Pass |
| `plugin.session-smoke` | project.plugin-session-smoke | Pass |

**Gate Summary**: 5/5 passed, 0 failed, 0 incomplete

### Fixes Applied

None. The verify publication scope allows only this report.

### Remaining Issues

| Severity | Category | Location | Issue | Reason Not Fixed |
|----------|----------|----------|-------|------------------|
| High | security | `scripts/build-android.sh`, `src/nmg_game_dev/ship/runner.py` (`_run_script`) | UE 5.8 UAT logs `Parsing command line: …KeyStorePassword=<secret>`, and the runner echoes it to stdout. Fails AC3. Fix: pass the password without putting it on UAT's command line (for example, a temporary ini or the project's `DefaultEngine.ini` override), or redact it in UAT's output before echoing. Also make the stub `RunUAT.sh` echo `Parsing command line:` with its argv, so the existing no-leak test covers it. | Outside verify publication scope |
| Low | security | `scripts/build-android.sh`, `scripts/notarize-macos.sh` | Secrets in process argv are visible through `ps` (`KeyStorePassword=`, `notarytool --password`) | Outside scope; design choice to revisit with the fix above |
| Low | correctness | `uv.lock`, `mcp-servers/finalize/uv.lock` | Committed lockfiles still say `nmg-game-dev` version `0.12.0`, but `pyproject.toml` is `0.13.0`. Every `uv run` rewrites them, leaving the tree dirty. Commit the refreshed lockfiles. | Outside verify publication scope |

### Recommendation

Needs fixes for remaining items. Route to implementation: keep the Android keystore password out of
the ship's output from a real UAT run, add a test stub that echoes like real UAT, commit the
refreshed lockfiles, then rerun the full registered gate.
