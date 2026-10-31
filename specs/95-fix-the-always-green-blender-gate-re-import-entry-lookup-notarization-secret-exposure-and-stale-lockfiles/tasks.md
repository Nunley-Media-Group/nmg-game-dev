# Tasks: Always-green Blender gate, re-import entry lookup, notarization secret exposure, and stale lockfiles

**Issue**: #95
**Date**: 2026-10-30
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/6-ship-skills-per-platform-build-sign-notarize-package/

## Implementation Tasks

### T001: Propagate Blender test failures from the gate

**File(s)**: `scripts/run-blender-tests.sh`, `tests/blender/_runner.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- `run-blender-tests.sh` runs Blender with `--background --python-exit-code 1 --python tests/blender/_runner.py -- <target>`, where `<target>` is the optional first argument and defaults to `tests/blender`.
- `_runner.main()` flushes stdout and stderr and exits with `os._exit(int(pytest_result))`.
- With a failing or erroring test the script exits non-zero; with all tests passing it exits 0 (AC1, FR1).
- The script stays shellcheck-clean.

### T002: Resolve the re-import entry script from CLAUDE_PLUGIN_ROOT, then the checkout

**File(s)**: `plugins/nmg-game-dev-blender-addon/contract_core/reimport.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- `entry_script()` returns `$CLAUDE_PLUGIN_ROOT/scripts/blender/contract_entry.py` when the variable is non-empty and that file exists; otherwise it returns `CHECKOUT_ENTRY_SCRIPT` (the add-on's `parents[3]` checkout path) when that file exists (AC2, AC3).
- When neither exists, it raises `ContractError` with code `reimport.entry_missing`, a message naming both paths it tried, and a remediation naming `CLAUDE_PLUGIN_ROOT` (AC3, FR2).
- `run_isolated` launches Blender with the path `entry_script()` returns.

### T003: Keychain-profile notarization and the password-path warning

**File(s)**: `scripts/notarize-macos.sh`, `src/nmg_game_dev/ship/targets.py`, `skills/ship/SKILL.md`, `docs/skills/ship.md`, `steering/snippets/project-tech.md`
**Type**: Modify
**Depends**: none
**Acceptance**:
- With `NOTARIZATION_KEYCHAIN_PROFILE` set, the script requires none of `NOTARIZATION_APPLE_ID`, `NOTARIZATION_APP_SPECIFIC_PASSWORD` or `NOTARIZATION_TEAM_ID`, and submits `xcrun notarytool submit <zip> --keychain-profile <profile> --wait` with no `--apple-id` or `--password` (AC4).
- Without it, the script keeps its existing required variables, submit argv and masked `RUN:` line. Before submitting it writes a stderr warning that names process-argument visibility and `NOTARIZATION_KEYCHAIN_PROFILE` (AC5).
- `--dry-run` submits nothing in either mode (AC8).
- `preflight_env(["macos"], env)` does not report `NOTARIZATION_APPLE_ID` or `NOTARIZATION_APP_SPECIFIC_PASSWORD` as missing when `NOTARIZATION_KEYCHAIN_PROFILE` is set, and still reports `NOTARIZATION_TEAM_ID`.
- `skills/ship/SKILL.md` `required_env` marks `NOTARIZATION_APPLE_ID?` and `NOTARIZATION_APP_SPECIFIC_PASSWORD?` optional and adds `NOTARIZATION_KEYCHAIN_PROFILE?`. `scripts/validate-skills.py` passes.
- `docs/skills/ship.md` lists `NOTARIZATION_KEYCHAIN_PROFILE`, recommends it, and says the Apple ID and password are needed only without it. The steering notarization env row names it (FR3).

### T004: Derive the package version from VERSION and relock every project

**File(s)**: `pyproject.toml`, `uv.lock`, `mcp-servers/finalize/uv.lock`, `mcp-servers/texture-gen/uv.lock`, `steering/snippets/project-tech.md`, `tests/unit/test_scaffold_guards.py`, `tests/bdd/features/scaffold-plugin-repo-session-start-hooks.feature`, `tests/bdd/steps/test_scaffold.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- `pyproject.toml` declares `dynamic = ["version"]` with no static `project.version`, `[tool.hatch.version]` with `path = "VERSION"` and a whole-line version pattern, and `[tool.uv] cache-keys` covering `pyproject.toml` and `VERSION` (FR4).
- `uv lock` has been run in the root, `mcp-servers/finalize` and `mcp-servers/texture-gen`. No lockfile's `nmg-game-dev` package entry has a `version` field, and `uv lock --check --offline` passes in all three (AC6, FR5).
- The steering Versioning table no longer lists `pyproject.toml`, and its Path Syntax notes that `project.version` is derived from `VERSION` (FR4).
- The scaffold version guards (unit test and BDD scenario step) assert that `project.version` is dynamic and sourced from `VERSION`, instead of comparing a static value. `nmg_game_dev.__version__` still equals `VERSION` (AC8).

### T005: Lockfile drift test

**File(s)**: `tests/unit/test_lockfiles.py`
**Type**: Create
**Depends**: T004
**Acceptance**:
- A parametrized test runs `uv lock --check --offline` in the repo root and in every `mcp-servers/*` directory that has a `pyproject.toml`. On failure its assertion message names the project directory and says to run `uv lock` there (AC7, FR6).
- A test copies a project tree into `tmp_path`, changes a dependency specifier in the copied `pyproject.toml`, and asserts that the same check reports that project as stale (AC7).
- A test asserts that no committed lockfile's `nmg-game-dev` entry records a `version`.
- A test copies the root and both MCP sub-projects into `tmp_path`, writes a new semver to the copied `VERSION`, asserts that `uv lock --check --offline` passes in all three without relocking, and asserts that `uv run --offline` in the copy reports the new `importlib.metadata.version("nmg-game-dev")` (AC6).
- Run with `pytest tests/unit/test_lockfiles.py`.

### T006: Regression tests for the Blender gate, re-import resolution and notarization

**File(s)**: `tests/unit/test_run_blender_tests.py`, `tests/blender/test_reimport_entry.py`, `tests/unit/ship/test_scripts.py`, `tests/unit/ship/test_targets.py`
**Type**: Create, Modify
**Depends**: T001, T002, T003
**Acceptance**:
- `tests/unit/test_run_blender_tests.py`:
  - With a shimmed `BLENDER_BIN` that records its argv, it asserts `--python-exit-code` is passed and that the target argument is forwarded.
  - With a real Blender (`BLENDER_BIN` or `BLENDER_APP`; skipped only when none resolves), it runs the script against a `tmp_path` suite with one failing test and asserts a non-zero exit, then against one with only passing tests and asserts exit 0 (AC1).
- `tests/blender/test_reimport_entry.py` (headless Blender):
  - With `CHECKOUT_ENTRY_SCRIPT` patched to a missing path and `CLAUDE_PLUGIN_ROOT` set to a `tmp_path` root that holds `scripts/blender/contract_entry.py`, `entry_script()` returns that file, and `run_isolated` (with `subprocess.run` captured) launches it (AC2).
  - With `CLAUDE_PLUGIN_ROOT` unset, or naming a root without the script, it returns the checkout entry (AC3).
  - With neither present, it raises `reimport.entry_missing`, and the remediation contains `CLAUDE_PLUGIN_ROOT` (AC3).
- `tests/unit/ship/test_scripts.py`:
  - With only `NOTARIZATION_KEYCHAIN_PROFILE` set (Apple ID, password and team removed), the recorded submit holds `--keychain-profile <profile>` and no `--apple-id` or `--password`, and the run exits 0 (AC4).
  - The password-path test asserts the stderr warning and that the password never appears in stdout or stderr (AC5).
  - Dry-run with the profile set records no calls (AC8).
- `tests/unit/ship/test_targets.py`: `preflight_env` accepts the profile in place of the Apple ID and password and still requires the team.
- `scripts/run-blender-tests.sh` and `pytest tests/unit/` pass.

### T007: BDD scenarios for the regression

**File(s)**: `tests/bdd/features/release_tooling_fixes.feature`, `tests/bdd/test_release_tooling_fixes_bdd.py`
**Type**: Create
**Depends**: T005, T006
**Acceptance**:
- The feature file holds the scenarios SCN001 and SCN004–SCN008 from `feature.gherkin`. They are bound in `tests/bdd/test_release_tooling_fixes_bdd.py` with the `tests/ship_fakes.py` sandbox for notarization, subprocess runs of `scripts/run-blender-tests.sh` (the real-Blender steps skip only when no Blender resolves), and `uv lock --check --offline` for the lock scenarios.
- SCN008 runs `uv run --offline --frozen --project mcp-servers/finalize python -c "import finalize_mcp.server"` and the same for `texture_gen_mcp.server`, asserting exit 0 for each. It also asserts that notarization `--dry-run` records no calls.
- SCN002 and SCN003 are realized by `tests/blender/test_reimport_entry.py` from T006.
- `pytest tests/bdd/` passes.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #95 | 2026-10-30 | Initial defect tasks |
