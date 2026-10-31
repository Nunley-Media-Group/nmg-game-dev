# Root Cause Analysis: Always-green Blender gate, re-import entry lookup, notarization secret exposure, and stale lockfiles

**Issue**: #95
**Date**: 2026-10-30
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/6-ship-skills-per-platform-build-sign-notarize-package/

## Root Cause

1. **Blender gate.** `scripts/run-blender-tests.sh` runs `Blender --background --python tests/blender/_runner.py -- tests/blender` without `--python-exit-code`. `_runner.py` ends with `sys.exit(pytest.main(...))`. Blender handles the `SystemExit` from a `--python` script itself and exits 0, so `gate-blender-headless`, which judges by exit code, cannot fail.
2. **Re-import entry.** `contract_core/reimport.py` fixes `ENTRY_SCRIPT` at import time as `Path(__file__).resolve().parents[3] / "scripts/blender/contract_entry.py"`. That path exists only when the add-on resolves into a framework checkout. `run_isolated` raises `reimport.entry_missing` for a copied or zip-installed add-on, and nothing consults `CLAUDE_PLUGIN_ROOT`. `src/nmg_game_dev/onboard/paths.py` already resolves from it.
3. **Notarization.** `scripts/notarize-macos.sh` builds `submit_cmd=(xcrun notarytool submit … --apple-id "$apple_id" --password "$password" …)`. Only the logged copy `shown_submit` is masked; the real argv holds the password while notarytool runs.
4. **Lockfiles.** `pyproject.toml` declares a static `project.version`, which the release bump rewrites from the steering versioning table. Each `uv.lock` records that version for the editable `nmg-game-dev` package, so every bump stales all three. Both sub-locks still record 0.13.0, and the finalize lock lacks the root's current `numpy`/`pillow` dependencies.

## Affected Code

| File | Symbol / Area | Role |
|------|---------------|------|
| `scripts/run-blender-tests.sh` | final `exec` line | Drops pytest's exit status |
| `tests/blender/_runner.py` | `main()` | Exits through `sys.exit`, which Blender swallows |
| `plugins/nmg-game-dev-blender-addon/contract_core/reimport.py` | `ENTRY_SCRIPT`, `run_isolated` | Checkout-only entry lookup |
| `scripts/notarize-macos.sh` | variable checks, `submit_cmd` | Password in argv; no profile path |
| `src/nmg_game_dev/ship/targets.py` | `REQUIRED_ENV`, `preflight_env` | Requires the Apple ID and password for macOS |
| `skills/ship/SKILL.md` | `required_env` frontmatter | Lists the Apple ID and password as required |
| `pyproject.toml` | `project.version` | Static version that every lockfile records |
| `steering/snippets/project-tech.md` | Versioning table | Tells the bump to rewrite `project.version` |
| `uv.lock`, `mcp-servers/finalize/uv.lock`, `mcp-servers/texture-gen/uv.lock` | `nmg-game-dev` package entry | Record the version |

## Fix Strategy

1. **Blender gate.**
   - `run-blender-tests.sh` passes `--python-exit-code 1` to Blender, so an unhandled exception in the runner (a pip bootstrap or add-on link failure) exits 1.
   - It accepts an optional first argument as the pytest target, defaulting to `tests/blender`.
   - `_runner.main()` flushes `sys.stdout`/`sys.stderr` and calls `os._exit(int(result))`. Pytest's exact return code (0 pass, 1 failures, 2+ errors and usage) then reaches the shell, whatever Blender does with `SystemExit`.
2. **Re-import entry.**
   - Replace the import-time constant with `entry_script() -> Path`. It returns the first existing file of:
     - `Path(os.environ["CLAUDE_PLUGIN_ROOT"]) / "scripts/blender/contract_entry.py"`, when the variable is non-empty;
     - module-level `CHECKOUT_ENTRY_SCRIPT` (the previous `parents[3]` path).
   - When neither exists, it raises `ContractError("reimport.entry_missing", …)`. The message names both paths it tried. The remediation says to set `CLAUDE_PLUGIN_ROOT` to the framework root that contains `scripts/blender/contract_entry.py`, or to run from a framework checkout.
   - `run_isolated` calls `entry_script()` and puts the result in the command.
3. **Notarization.**
   - With `NOTARIZATION_KEYCHAIN_PROFILE` non-empty, `notarize-macos.sh` requires no Apple ID, password or team variable. It submits `xcrun notarytool submit "$zip" --keychain-profile "$profile" --wait` and logs that command; the profile name is not secret.
   - Otherwise it keeps the current checks, argv and masked log line. Before submitting it prints to stderr `WARNING: the app-specific password is visible in process arguments while notarytool runs; set NOTARIZATION_KEYCHAIN_PROFILE (xcrun notarytool store-credentials) to avoid it.`
   - `--dry-run` is unchanged and submits nothing.
   - `preflight_env` drops `NOTARIZATION_APPLE_ID` and `NOTARIZATION_APP_SPECIFIC_PASSWORD` from the macOS requirement when `NOTARIZATION_KEYCHAIN_PROFILE` is set. `NOTARIZATION_TEAM_ID` stays required because signing-identity lookup uses it.
4. **Lockfiles.**
   - `pyproject.toml` replaces `version = …` with `dynamic = ["version"]` and adds `[tool.hatch.version] path = "VERSION"` and `pattern = "(?P<version>\\S+)"`.
   - It adds `[tool.uv] cache-keys = [{ file = "pyproject.toml" }, { file = "VERSION" }]`, so a `VERSION` change rebuilds the editable install and the installed package reports the new version.
   - Relock the root and both sub-projects. The `nmg-game-dev` entry then carries no `version` field, and the sub-locks pick up the current root dependencies.
   - Remove the `pyproject.toml` row from the steering versioning table, and add a Path Syntax note that `project.version` is derived from `VERSION` by hatchling.
5. **Coexistence assertion.**
   - `addon_utils.check(name)` returns `(loaded_default, loaded_state)`. The suite enables the host with `default_set=False`, so `loaded_default` is always False. Once the host add-on is installed and the gate reports failures (step 1), the suite fails although the host is loaded.
   - `test_both_addons_load` and `test_disabling_nmg_leaves_host_functional` assert the second value instead.
6. **Unrunnable gates.**
   - `gate-skill-schema` names `scripts/validate-skills.py`, which was never written, and `gate-markdown-lint` has no installed tool or project config. Earlier issues (#32, #67, #69) recorded both as not runnable.
   - Remove both rows from the Verification Gates table, the `markdownlint` line from the Markdown standards, and the `validate-skills.py` line from the repository layout.
7. **Changelog guard.**
   - `test_changelog_has_both_unreleased_entries_ending_with_issue` (#7) looks for its entries only in `[Unreleased]` or the first versioned section. This issue's release bump adds a 0.14.1 section above 0.14.0, so the guard fails on any release after the one that shipped #7.
   - Search every section after `[Unreleased]` for the first one that holds `(#7)` entries.

## Changes

| File | Change | Behavioral reason |
|------|--------|-------------------|
| `scripts/run-blender-tests.sh` | `--python-exit-code 1`; optional target argument | AC1, FR1 |
| `tests/blender/_runner.py` | flush, then `os._exit(int(result))` | AC1, FR1 |
| `plugins/nmg-game-dev-blender-addon/contract_core/reimport.py` | `entry_script()` resolver, `CHECKOUT_ENTRY_SCRIPT`, remediation | AC2, AC3, FR2 |
| `scripts/notarize-macos.sh` | profile branch, password-path warning, header comment | AC4, AC5, FR3 |
| `src/nmg_game_dev/ship/targets.py` | profile-aware macOS preflight | AC4, FR3 |
| `skills/ship/SKILL.md` | Apple ID and password marked optional (`?`), `NOTARIZATION_KEYCHAIN_PROFILE?` added | AC4, FR3 |
| `docs/skills/ship.md` | `NOTARIZATION_KEYCHAIN_PROFILE` row, recommended over the password | FR3 |
| `steering/snippets/project-tech.md` | Versioning table row removed with a Path Syntax note; notarization env row mentions `NOTARIZATION_KEYCHAIN_PROFILE` | FR3, FR4 |
| `pyproject.toml` | dynamic version from `VERSION`; uv cache-keys | AC6, FR4 |
| `uv.lock`, `mcp-servers/finalize/uv.lock`, `mcp-servers/texture-gen/uv.lock` | relocked | AC6, FR5 |
| `tests/unit/test_scaffold_guards.py`, `tests/bdd/features/scaffold-plugin-repo-session-start-hooks.feature`, `tests/bdd/steps/test_scaffold.py` | version guards assert that `project.version` is dynamic and sourced from `VERSION` | AC8, FR4 |
| `tests/blender/test_coexistence.py` | assert the loaded state from `addon_utils.check()` | AC9, FR7 |
| `steering/snippets/project-tech.md`, `steering/snippets/project-structure.md` | remove `gate-skill-schema`, `gate-markdown-lint`, and the `validate-skills.py` entry | AC10, FR8 |
| `tests/unit/onboard/test_docs_and_skill.py` | changelog guard searches every section for the #7 entries | AC11, FR9 |

## Blast Radius

- `run-blender-tests.sh` is invoked only by `gate-blender-headless` and by contributors. Existing Blender tests that were silently failing will now fail the gate.
- `run_isolated` is called by `operators/reimport_check.py` and `tests/blender/test_contract_reimport.py`. The command shape is unchanged.
- `src/nmg_game_dev/ship/runner.py` calls `notarize-macos.sh` with and without `--dry-run`. Existing ship tests set the Apple ID and password, so they take the password path and see the new stderr warning.
- `nmg_game_dev.__version__` already reads `importlib.metadata.version("nmg-game-dev")` with a `VERSION` fallback.
- The `finalize` and `texture-gen` servers launch through `uv run --project …/mcp-servers/<name>`, which resolves from the relocked sub-locks.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Rely on `--python-exit-code` alone | Rejected | It covers only unhandled exceptions; Blender still handles `SystemExit(1)` from `sys.exit` |
| `os._exit` plus `--python-exit-code 1` | Selected | Exact pytest code, and bootstrap exceptions also fail |
| Have the release bump relock all three projects | Rejected | Leaves the lock tied to a value every bump changes, and needs network on each bump |
| Dynamic version from `VERSION` | Selected | uv omits the version for a dynamic local package, which was verified with uv 0.10.2 |
| Keep `--team-id` with `--keychain-profile` | Rejected | The profile stores the team; AC4 needs no other notarization variable |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #95 | 2026-10-30 | Initial defect design |
| #95 | 2026-10-30 | Amended: coexistence assertion fix and removal of the unrunnable skill-schema and markdown-lint gates |
| #95 | 2026-10-31 | Amended: changelog guard survives later release bumps |
