# Verification Report: Consumer onboarding, asset contract install, and local texture generation

**Date**: 2026-10-30
**Issue**: #7
**Reviewer**: Claude (nmg-sdlc verify worker, run 40468ffe-0554-4b4f-b7a9-4cdbd44bd3ba)
**Scope**: Implementation verification against spec

**Verification head**: 10df08ff0b77a668a57f9eaa063cccb09789e6c9

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 4 |
| Architecture (SOLID) | 4 |
| Security | 4 |
| Performance | 4 |
| Testability | 5 |
| Error Handling | 4 |
| **Overall** | 4.2 |

### Implementation Status: Fail

**Total Issues**: 4 (1 high, 1 medium, 2 low)

The implementation covers every approved AC, and 594 of 595 unit and BDD tests pass. The required
`repository.tests` validation fails on one test. The version-bump commit `10df08f` ("feat: deliver
issue #7") moved the two #7 CHANGELOG entries from `## [Unreleased]` into `## [0.14.0]`, but
`tests/unit/onboard/test_docs_and_skill.py::test_changelog_has_both_unreleased_entries_ending_with_issue`
still expects them under `## [Unreleased]`. Because of that failure, the steering runner deferred
`plugin.session-smoke` (status `incomplete`). The overall status is therefore Fail. The fix is
outside this verify worker's publication scope, which only allows writing the report, so the work
goes back to implementation.

---

## Issue Scope

- Active issue: #7
- Spec: `specs/7-consumer-onboarding-onboard-consumer-skill-asset-contract-install-and-onboarding-docs`
- Manifest: `implicit single issue`
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1–AC20]; FR [FR1–FR19]; tasks [T001–T015]; scenarios [SCN001–SCN020]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":7,"specPath":"specs/7-consumer-onboarding-onboard-consumer-skill-asset-contract-install-and-onboarding-docs","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6","AC7","AC8","AC9","AC10","AC11","AC12","AC13","AC14","AC15","AC16","AC17","AC18","AC19","AC20"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6","FR7","FR8","FR9","FR10","FR11","FR12","FR13","FR14","FR15","FR16","FR17","FR18","FR19"],"tasks":["T001","T002","T003","T004","T005","T006","T007","T008","T009","T010","T011","T012","T013","T014","T015"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006","SCN007","SCN008","SCN009","SCN010","SCN011","SCN012","SCN013","SCN014","SCN015","SCN016","SCN017","SCN018","SCN019","SCN020"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Not complete (`repository.tests` failed; `plugin.session-smoke` deferred)
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

Runner: `sdlc-verify-steering.mjs --project . --issue 7 --spec specs/7-… --base main --controller-run-id 40468ffe-0554-4b4f-b7a9-4cdbd44bd3ba`
Artifact: `.nmg-sdlc/verification/7.json` (head `10df08ff0b77a668a57f9eaa063cccb09789e6c9`; tree state `dirty`, because `uv.lock` was rewritten, see Remaining Issues)

| Coverage | Value |
|----------|-------|
| declared | 5 |
| recorded | 5 |
| complete | true |
| ceiling | **Incomplete** (runner); the required `failed` result lowers the cap to **Fail** |

| Validation | Provider | Required | Status | Summary |
|------------|----------|----------|--------|---------|
| `repository.tests` | builtin.command (`uv run pytest tests/unit tests/bdd -q`) | yes | **failed** | command exited 1 — 1 failed, 594 passed |
| `repository.lint` | builtin.command (`uv run ruff check .`) | yes | passed | command exited 0 |
| `repository.types` | builtin.command (`uv run mypy src tests`) | yes | passed | command exited 0 |
| `plugin.validate` | builtin.command (`claude plugin validate .`) | yes | passed | command exited 0 |
| `plugin.session-smoke` | project.plugin-session-smoke | yes | **incomplete** | deferred until required local validations pass |

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Fresh onboarding installs the framework files | Pass | `src/nmg_game_dev/onboard/runner.py` (start scripts, hooks, contract, instructions), `files.py`, `settings.py`, `instructions.py`; SCN001 passes |
| AC2 | Unreal plugins are installed and enabled | Pass | `src/nmg_game_dev/onboard/unreal.py` (`ensure_vibeue`, `enable_plugins`, `ensure_mcp_autostart`); SCN002 passes |
| AC3 | Blender add-on linked into extensions | Pass | `src/nmg_game_dev/onboard/blender.py` (`link_addon`, `BLENDER_EXTENSIONS_DIR`); SCN003 passes |
| AC4 | Texture models installed on the chosen disk | Pass | `src/nmg_game_dev/onboard/textures.py` (`install_models`), `settings.merge_env`; SCN004 passes |
| AC5 | Texture prerequisites fail before anything changes | Pass | `runner.py` `_check_prerequisites` runs before the first write; SCN005 passes |
| AC6 | The skill asks which disk to use | Pass | `skills/onboard-consumer/SKILL.md`, `onboard/volumes.py`; SCN006 passes |
| AC7 | Install scope does not change the result | Pass | `runner.py` resolves the framework from `CLAUDE_PLUGIN_ROOT`; SCN007 passes |
| AC8 | Re-running is idempotent | Pass | `files.sync_file/sync_tree`, `settings.merge_session_hooks`; SCN008 passes |
| AC9 | Drift is reported and `--refresh` repairs it | Pass | `files.py`, `unreal.ensure_vibeue(refresh=…)`; SCN009 passes |
| AC10 | Onboarding docs exist and are linked | Pass | `docs/onboarding/{index,first-asset,first-ship,upgrading,texture-models}.md`; links in `CLAUDE.md`, `README.md`, `templates/consumer/README.md`; SCN010 passes |
| AC11 | onboard-consumer skill is the entry point | Pass | `skills/onboard-consumer/SKILL.md` + `references/install-steps.md`; SCN011 passes |
| AC12 | Registry holds exactly the two pinned models | Pass | `src/nmg_game_dev/texture/registry.py`; SCN012 passes |
| AC13 | Only the pinned models load | Pass | `registry.py` allowlist; SCN013 passes |
| AC14 | Missing weights point at onboarding | Pass | `texture/hardware.py`, `texture/errors.py`; SCN014 passes |
| AC15 | Hardware check refuses unfit backends | Pass | `texture/hardware.py`; SCN015 passes |
| AC16 | Each backend batch runs in one isolated process | Pass | `texture/batch.py` `default_spawn` / `run_backend_batches`, `texture/worker.py`; SCN016 passes |
| AC17 | Models never run concurrently | Pass | `batch.py` runs batches one after another; `texture/jobs.py` PID lock (`_claim_lock`); SCN017 passes |
| AC18 | Outputs tile seamlessly | Pass | `texture/seamless.py`; SCN018 passes |
| AC19 | Derived PBR maps are seamless | Pass | `texture/maps.py`; SCN019 passes |
| AC20 | Agent generates textures through CLI and MCP | Pass | `texture/__main__.py`, `texture/generate.py`, `mcp-servers/texture-gen/` (`generate_textures`, `get_texture_job`), `.mcp.json`; SCN020 passes |

Every AC is implemented. The overall status is still Fail because a required registered validation
failed (see the gates section).

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Onboard package foundations | Complete | `onboard/{__init__,errors,paths,commands,report,files}.py` |
| T002 | Settings and agent-instruction merges | Complete | `onboard/settings.py`, `onboard/instructions.py` |
| T003 | Unreal setup | Complete | `onboard/unreal.py` |
| T004 | Blender add-on link | Complete | `onboard/blender.py` |
| T005 | Texture models and volume listing | Complete | `onboard/textures.py`, `onboard/volumes.py` |
| T006 | Onboard runner and CLI | Complete | `onboard/runner.py`, `onboard/__main__.py` |
| T007 | Skill, references, docs, and links | Complete | `skills/onboard-consumer/`, `docs/onboarding/`, README/CLAUDE links |
| T008 | Unit tests for onboarding | Complete, with a defect | `tests/unit/onboard/`; one test is out of date after the version bump |
| T009 | BDD scenarios | Complete | `tests/bdd/features/onboard_consumer.feature`, `texture_generation.feature`; all pass |
| T010 | Texture registry, errors, paths, hardware | Complete | `texture/{registry,errors,paths,hardware}.py` |
| T011 | Seamless post-process and derived maps | Complete | `texture/{seamless,maps}.py` |
| T012 | Worker process and sequential batch runner | Complete | `texture/{worker,batch}.py` |
| T013 | Generate entry point, jobs, CLI | Complete | `texture/{generate,jobs,sheet,__main__}.py` |
| T014 | texture-gen MCP server, MCP config, tool validator | Complete | `mcp-servers/texture-gen/`, `.mcp.json`, `scripts/validate-mcp-tools.py` |
| T015 | Texture unit tests and opt-in real-model test | Complete | `tests/unit/texture/`, `tests/e2e/test_texture_models_e2e.py` |

No `verify-skip:` notes in `tasks.md`.

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 4 | Each install step has its own module; `runner.py` handles preflight and step order only |
| Open/Closed | 4 | The texture registry is deliberately closed (spec); the step list is plain data |
| Liskov Substitution | 5 | Injected `Runner`/`Which`/`Spawn`/`HostFacts` fakes swap in cleanly |
| Interface Segregation | 4 | Small callable protocols instead of broad service objects |
| Dependency Inversion | 4 | Side effects (`subprocess`, disk, host facts) are injected with production defaults |

### Layer Separation

The skill calls `python -m nmg_game_dev.onboard install`. The texture-gen MCP server wraps
`nmg_game_dev.texture` without adding logic of its own, which matches the MCP-server layer rule in
structure steering.

### Dependency Flow

The onboard package depends on the texture package only for path and env-var constants
(`texture.paths`). Nothing depends back on onboard, so there is no cycle.

---

## Security Assessment

- [x] Authentication: no external credentials handled
- [x] Authorization: N/A (local tooling)
- [x] Input validation: `.uproject`, models directory, consumer directory, and framework sources are all resolved and checked before any write (`runner.py`)
- [x] Injection prevention: subprocesses run from argv lists with no `shell=True` (`onboard/commands.py`, `texture/batch.py`, `texture/jobs.py`)
- [x] Data protection: `TEXTURE_GEN_MODELS_DIR` / `HF_HOME` are written to the gitignored `.claude/settings.local.json`; FR8 keeps `fixtures/` and `.mcp.json` out of every consumer write

---

## Performance Assessment

- [x] Async patterns: long texture jobs run as detached `Popen` jobs; the MCP tools start a job and poll it
- [x] Caching: each model loads once per backend batch (FR14)
- [x] Resource management: backends run strictly one after another, with one job at a time under the PID lock and a RAM reserve for Blender
- [x] Query optimization: N/A

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1–AC11 | Yes (SCN001–SCN011) | Yes (`tests/bdd/test_onboard_bdd.py`) | Yes |
| AC12–AC20 | Yes (SCN012–SCN020) | Yes (`tests/bdd/test_texture_bdd.py`) | Yes |

### Coverage Summary

- Feature files: 20 #7 scenarios, all passing
- Step definitions: Implemented
- Unit + BDD run: 595 tests, 594 passed, **1 failed**
- Opt-in real-model e2e: `tests/e2e/test_texture_models_e2e.py` (runs only when both models are installed; not part of the registered gate)

Failing test:

```text
FAILED tests/unit/onboard/test_docs_and_skill.py::test_changelog_has_both_unreleased_entries_ending_with_issue
```

`CHANGELOG.md` at HEAD has an empty `## [Unreleased]` section, and the two #7 entries now sit under
`## [0.14.0] - 2026-10-31`. The test splits on `## [Unreleased]` and asserts two bullets, so it
fails after any release bump.

---

## Exercise Test Results

Not applicable. This change touches no nmg-sdlc `workflows/` or `agents/`; it is a consumer plugin
change, and the registered `plugin.validate` and `plugin.session-smoke` validations cover it.

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` | Fail | `uv run pytest tests/unit tests/bdd -q` → 1 failed, 594 passed |
| `repository.lint` | Pass | `uv run ruff check .` exit 0 |
| `repository.types` | Pass | `uv run mypy src tests` exit 0 |
| `plugin.validate` | Pass | `claude plugin validate .` exit 0 |
| `plugin.session-smoke` | Incomplete | deferred until required local validations pass |

**Gate Summary**: 3/5 passed, 1 failed, 1 incomplete

---

## Fixes Applied

None. The verify publication scope (`NMG_SDLC_PUBLICATION.allowedPaths`) only allows writing this
report, so both fixable findings are left for implementation.

## Remaining Issues

### High Priority

| Field | Value |
|-------|-------|
| **Severity** | High |
| **Category** | Testing |
| **Location** | `tests/unit/onboard/test_docs_and_skill.py:88` |
| **Issue** | `test_changelog_has_both_unreleased_entries_ending_with_issue` only reads `## [Unreleased]`; the version bump in `10df08f` moved the #7 entries into `## [0.14.0]` |
| **Impact** | The required `repository.tests` validation fails, and the session smoke cannot run |
| **Reason Not Fixed** | Outside the verify publication scope (only the report is writable). Suggested fix: read the #7 entries from `## [Unreleased]` or, when that section is empty, from the first released section, so the assertion holds before and after `/sdlc-open-pr` bumps the version |

### Medium Priority

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Category** | Architecture (release hygiene) |
| **Location** | `uv.lock:1608` |
| **Issue** | `10df08f` bumped `pyproject.toml` to 0.14.0 but left the committed `uv.lock` at `version = "0.13.0"` for the editable `nmg-game-dev` package. Every `uv run` rewrites it, which makes the tree dirty (the steering artifact records `treeState: dirty`) |
| **Impact** | Verification and finalization run against a dirty tree; the lock does not match the version |
| **Reason Not Fixed** | Outside the verify publication scope. Suggested fix: commit the regenerated `uv.lock`, and have the version bump also refresh `uv.lock` (for example, `uv lock` after the bump) |

### Low Priority

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Code quality |
| **Location** | `src/nmg_game_dev/onboard/runner.py:1` |
| **Issue** | The module docstring has line breaks in the middle of sentences ("…before the\nfirst\nconsumer write") |
| **Impact** | Readability only |
| **Reason Not Fixed** | Outside the verify publication scope |

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Error Handling |
| **Location** | `src/nmg_game_dev/texture/batch.py:82` |
| **Issue** | `_parse_timings` calls `json.loads` on any worker stdout line starting with `{`, so a non-JSON line from mflux would raise a raw `JSONDecodeError` instead of a `TextureGenError` |
| **Impact** | An unstructured error on an unlikely path |
| **Reason Not Fixed** | Outside the verify publication scope; low risk |

---

## Positive Observations

- Preflight resolves everything and fails with `OnboardError(code, message, remediation)` before any consumer write (AC5, FR2).
- Side effects are injected throughout, so tests use stub `git`, `mflux-save`, `uv`, and fake workers, with no real models or network.
- The texture job lock is taken atomically with `O_CREAT | O_EXCL` and clears stale holders.

---

## Recommendations Summary

### Before PR (Must)

- [ ] Make the CHANGELOG test pass after a version bump (`tests/unit/onboard/test_docs_and_skill.py:88`)
- [ ] Commit the regenerated `uv.lock` so the tree is clean at 0.14.0
- [ ] Re-run the full registered gate, including `plugin.session-smoke`

### Short Term (Should)

- [ ] Make the version bump refresh `uv.lock`

### Long Term (Could)

- [ ] Clean up the `runner.py` docstring; wrap the `_parse_timings` decode error

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `src/nmg_game_dev/onboard/runner.py` | 1 | Docstring formatting |
| `src/nmg_game_dev/texture/batch.py` | 1 | Decode error not wrapped |
| `src/nmg_game_dev/texture/jobs.py` | 0 | |
| `tests/unit/onboard/test_docs_and_skill.py` | 1 | Out of date after the version bump |
| `CHANGELOG.md` | 0 | Correct after the bump |
| `uv.lock` | 1 | Version drift |

---

## Recommendation

**Needs fixes**

The feature is implemented and every AC passes, but a required registered validation fails at
`10df08ff0b77a668a57f9eaa063cccb09789e6c9`. Return to implementation: fix the out-of-date CHANGELOG
test and commit the synced `uv.lock`, then run the full gate again.
