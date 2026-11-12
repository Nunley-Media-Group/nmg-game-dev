# Verification Report: Texture generation from the plugin root, with queued and batched jobs

**Date**: 2026-11-12
**Issue**: #143
**Reviewer**: Claude (nmg-sdlc verify worker, architecture-reviewer)
**Scope**: Re-verification after base reconciliation (merge of `origin/main` at `df1f1cd` into the issue branch)

**Verification head**: 0f348119c32b0ebbcbf76fedd7496a006ed61670

---

## Executive Summary

This run re-verifies #143 after the base merge `0f34811`. That merge brought in #144 (geometry.normals) and #192 (Blender test runner isolation) from main. It did not touch any texture source, test, schema or doc. The feature itself is unchanged since the last Pass at `bfb2b70`, and all eight acceptance criteria still hold. All 11 registered validations were recorded at the new head with complete coverage. All 10 that apply passed, and `gate-ship-smoke` does not apply.

The status is **Fail** because the merge resolved `CHANGELOG.md` wrongly. It breaks the lane rule to keep main's released sections unchanged and to put this issue's entry under `## [Unreleased]`. If delivered as is, the controller's version preparation would publish a duplicate `## [0.22.0]` heading. It would also list #143 in two releases, including main's already-released 0.21.5 notes (see High finding H1). The fix is two deleted lines in `CHANGELOG.md`. Verify's publication scope covers only this report, so the fix goes back to implementation.

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 4 |
| Security | 5 |
| Performance | 4 |
| Testability | 5 |
| Error Handling | 4 |
| **Overall** | 4.5 |

### Implementation Status: Fail
**Total Issues**: 5 (1 High: CHANGELOG merge defect; 3 Low and 1 informational carried over, none blocking)

---

## Issue Scope

- Active issue: #143
- Spec: `specs/143-make-texture-generation-work-from-the-plugin-root-and-queue-or-batch-texture-jobs`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1–AC8]; FR [FR1–FR10]; tasks [T001–T008]; scenarios [SCN001–SCN008]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":143,"specPath":"specs/143-make-texture-generation-work-from-the-plugin-root-and-queue-or-batch-texture-jobs","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6","AC7","AC8"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6","FR7","FR8","FR9","FR10"],"tasks":["T001","T002","T003","T004","T005","T006","T007","T008"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006","SCN007","SCN008"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Not complete (the release notes in `CHANGELOG.md` are corrupted)
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

- Runner: `sdlc-verify-steering.mjs --project . --issue 143 --spec specs/143-… --base main --controller-run-id 408c5465-26a2-44d9-bc7c-b3bfa24066cb`
- Artifact: `.nmg-sdlc/verification/143.json`. Head `0f348119c32b0ebbcbf76fedd7496a006ed61670`, clean tree. Steering hash `sha256:795f9897…`, spec hash `sha256:7d8d383e…`.
- Coverage: `declared: 11`, `recorded: 11`, `complete: true`. Nothing is missing, duplicated or unknown.
- Ceiling: none from the gate. The overall status is Fail because of finding H1, not because of any gate result.

---

## Base Reconciliation Review

The merge `0f34811` changed these files relative to the last verified report commit `4f4920d`: `contract_core/geometry.py` and `report.py`, `scripts/run-blender-tests.sh`, `tests/blender/_runner.py`, and new and updated tests for #144 and #192. It also changed docs and skills for geometry normals, specs for #202 and #203, and the version files. No path under `src/nmg_game_dev/texture/`, `mcp-servers/texture-gen/`, `pyproject.toml`, `uv.lock` or `docs/onboarding/texture-models.md` changed. The AC evidence below therefore still applies, and the fresh registered suite re-runs every texture test at the new head.

The version files took main's values (`VERSION`, `.claude-plugin/plugin.json`, `blender_manifest.toml` and `nmg-game-dev.uplugin` are all `0.21.5`), which is correct. `CHANGELOG.md` did not (see H1).

---

## Acceptance Criteria Verification

Evidence collected at `bfb2b70`. The texture code has not changed since, and the registered suite re-ran every bound scenario at the new head.

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Root project carries the generation dependencies on Apple Silicon | Pass | `pyproject.toml` `[project] dependencies` adds `mflux>=0.24.0` and `hf_transfer>=0.1.9`, each with marker `sys_platform == 'darwin' and platform_machine == 'arm64'`. The `texture-ai` extra uses the same floors, with no `==` pins. `mcp-servers/texture-gen/pyproject.toml` is unchanged. `uv lock --check` passes for the root, texture-gen, finalize and meshy projects. `uv lock --upgrade-package mflux --upgrade-package hf-transfer --dry-run` reports no lockfile changes, so 0.24.0 and 0.1.9 are the latest compatible versions. Exercised: `uv run --project <root> python -c find_spec(...)` finds both `mflux` and `mlx`. `tests/unit/test_pyproject_texture_deps.py`; SCN001. |
| AC2 | Missing dependencies fail fast with an accurate error | Pass | `src/nmg_game_dev/texture/deps.py` (`missing_module` uses `find_spec` and never imports; `require_dependencies`). `generate._generate` and `jobs.start` call it after backend selection and before any mkdir, spawn or enqueue. `hardware.availability` returns `dependencies_missing` after the platform, memory and weights checks. Exercised through the real CLI with `mlx` hidden: `status` printed `dependencies_missing` for both backends. `generate` exited 1 with `ERROR [texture.dependencies_missing]: The mlx module is not installed…` and remediation `uv run --project '<root>' python -m nmg_game_dev.texture generate …`. It created no `out/` or `.jobs/` directory. SCN002; `test_deps.py`, `test_hardware.py`, `test_jobs.py::test_start_refuses_missing_dependencies_before_anything_is_queued`. |
| AC3 | Worker import failures report the real cause | Pass | `src/nmg_game_dev/texture/batch.py` `_worker_remediation` matches `No module named '([^']+)'` and names that module and the plugin-root command. Any other failure keeps the models/memory text and the stderr tail. Exercised: a real worker run against dummy weights failed with the original models/memory remediation, as expected for a failure that is not an import error. SCN003; `test_batch.py`. |
| AC4 | A second request is queued, not rejected | Pass | `src/nmg_game_dev/texture/jobs.py`: `start` always writes `queued` with `submitted_ns` and spawns `run-queue`. `run_queue` claims the PID lock, drains in `(submitted_ns, job_id)` order, releases the lock and re-scans. `texture.job_running` no longer appears in `src/nmg_game_dev/texture` or texture-gen. Exercised with the real detached runner: two `jobs.start` calls (single, then batch) both returned `queued`. The runner finished them in submission order, about 4.9 s apart, and released the lock. SCN004; updated texture_generation SCN017 step; `test_jobs.py` queue tests, including the live-holder and stale-lock cases. |
| AC5 | Batch through the MCP tool | Pass | `mcp-servers/texture-gen/src/texture_gen_mcp/server.py` accepts `requests` and rejects both or neither of `prompt` and `requests`. `generate._generate` builds one `Batch` per backend with batch-wide image indices, and `owners` maps each timing back to its request. `BatchResult.as_json()` returns `{"results": [...]}`. Progress `total` counts every image. SCN005 asserts one worker start with 3 items, `completed == total == 3`, and results in request order. |
| AC6 | Batch through the CLI | Pass | `src/nmg_game_dev/texture/__main__.py`: `--batch FILE` is mutually exclusive with `--prompt`, and argparse exits 2 on misuse. `load_batch_file` → `run_batch` prints `{"results": [...]}`. SCN006; `test_cli.py`. |
| AC7 | Invalid batch rejected before work starts | Pass | `generate.validate_batch` and `batch_from_items` collect `request {i}: {reason}` for every failure and raise a single `texture.invalid_request` before selection, spawn or enqueue. An empty batch is also rejected. SCN007 (indices 1 and 3, no spawn, no job dir). |
| AC8 | Single-request forms unchanged | Pass | `generate.run` keeps its signature. The only additions are `deps_probe` and `spawn` now defaulting to `None`, which resolves to `default_spawn`. The `TextureResult.as_json()` keys are the same. The single-job `run-job` subcommand is kept. SCN008; existing `texture_generation.feature` scenarios still pass. |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Platform-marked generation dependencies | Complete | `pyproject.toml`, `uv.lock` (+ texture-gen, finalize, meshy locks re-resolved) |
| T002 | Dependency probe and availability state | Complete | `texture/deps.py` (new), `hardware.py`, `generate.py` |
| T003 | Cause-aware worker failure remediation | Complete | `texture/batch.py` |
| T004 | Batch generation | Complete | `validate_batch`, `run_batch`, `BatchResult`. The contact sheet is refreshed once per batch. |
| T005 | FIFO job queue | Complete | `jobs.start`, `run_queue`, `_next_queued`; CLI `run-queue` and `generate --batch` |
| T006 | MCP tool and schema | Complete | `server.py`, `tools.json` (`requests` added, `prompt` no longer required); `gate-mcp-schema` passed |
| T007 | Documentation | Complete | `docs/onboarding/texture-models.md` covers the plugin-root command, `dependencies_missing`, the FIFO queue, `--batch` and `requests` |
| T008 | Tests | Complete | Autouse probe fixtures in unit and BDD; `test_deps.py`, `test_pyproject_texture_deps.py`, the queue/batch tests, and `texture_queue_batch.feature` SCN001–SCN008 bound |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 4 | `deps.py` owns the probe and remediation. `jobs.py` owns the queue and lock. `generate._generate` is long because it plans, groups, runs and finishes requests, but each phase is separate and readable. |
| Open/Closed | 4 | `run` and `run_batch` share `_generate`. The single-request path is the one-element case and was not forked. |
| Liskov Substitution | 5 | `BatchResult` and `TextureResult` keep separate shapes, so no substitution is implied. |
| Interface Segregation | 4 | The MCP tool takes `prompt` or `requests` and rejects calls that pass both or neither. |
| Dependency Inversion | 5 | `deps_probe`, `spawn`, `facts`, `env` and `registry` are all injected. The probe is looked up at call time, so the fixtures can patch it. |

### Layer Separation

The MCP server stays a thin wrapper over `nmg_game_dev.texture.jobs` and `generate`, as tech steering requires. FR10 holds: only `texture/worker.py` imports `mflux` or `mlx`.

### Dependency Flow

`deps` ← `hardware` ← `generate` ← `jobs` ← CLI and MCP. `batch.py` imports only `run_command` from `deps`. There are no cycles.

---

## Security Assessment

- [x] Authentication: not applicable (local tooling)
- [x] Authorization: not applicable
- [x] Input validation: batch items are strictly typed. Unknown fields and wrong types are rejected, and `seeds` must be real ints. The whole batch is validated before any work.
- [x] Injection prevention: the runner is spawned with an argv list (no shell). The remediation command quotes the path with `shlex.quote`. Output folders still come from the existing `slugify`.
- [x] Data protection: no secrets are touched. Logs go to job.log and stderr only.

---

## Performance Assessment

- [x] Async patterns: a detached runner drains the queue, so callers never wait in a loop.
- [x] Caching: each backend's model loads once per batch (FR6), down from once per request.
- [x] Resource management: worker batch files moved to a `TemporaryDirectory`, so nothing is left in the output folder. The lock is released in `finally`.
- [x] Query optimization: `_next_queued` scans the jobs directory once per job. That is O(jobs) and fine at local scale.

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1 | Yes (SCN001) | Yes | Yes |
| AC2 | Yes (SCN002) | Yes | Yes |
| AC3 | Yes (SCN003) | Yes | Yes |
| AC4 | Yes (SCN004) | Yes | Yes |
| AC5 | Yes (SCN005) | Yes | Yes |
| AC6 | Yes (SCN006) | Yes | Yes |
| AC7 | Yes (SCN007) | Yes | Yes |
| AC8 | Yes (SCN008) | Yes | Yes |

### Coverage Summary

- Feature files: `tests/bdd/features/texture_queue_batch.feature` has 8 scenarios. `texture_generation.feature` SCN017 was updated to expect queueing.
- Step definitions: Implemented (`tests/bdd/test_texture_queue_batch_bdd.py`)
- Targeted run (recorded at `bfb2b70`; the texture code has not changed since): `uv run pytest tests/unit/texture tests/unit/test_pyproject_texture_deps.py tests/bdd/test_texture_queue_batch_bdd.py tests/bdd/test_texture_bdd.py -q` gave 152 passed.
- Full registered suite (`repository.tests`) at `0f348119c32b0ebbcbf76fedd7496a006ed61670`: 1183 passed, 10 skipped.

### Manual exercise (no live editors)

- Root project: `uv run --project <root>` finds `mflux` and `mlx`. `status` reports `not_installed` on this host because no weights are downloaded here.
- Missing `mlx` (hidden through `sys.modules`): the real CLI `status` and `generate` behave as AC2 requires, with no output or jobs directory created.
- Real detached queue: two `jobs.start` calls (one single, one 2-request batch) with dummy weights and `HF_HUB_OFFLINE=1`. Both were `queued`. The real `run-queue` process ran them in FIFO order, both ended `failed` / `texture.worker_failed` (expected, since the weights are dummies), the batch's `total` was 2, and the lock was removed.

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| repository.tests | Pass | `uv run pytest tests/unit tests/bdd -q`: 1183 passed, 10 skipped |
| repository.lint | Pass | `ruff check .`: All checks passed |
| repository.format | Pass | `ruff format --check .`: 339 files already formatted |
| repository.types | Pass | `mypy src tests`: no issues found in 216 source files |
| gate-blender-headless | Pass | `scripts/run-blender-tests.sh`: 269 passed, 4 skipped (applies through the merged runner and `blender_manifest.toml` changes) |
| gate-ue-compile | Pass | DogfoodEditor compiled against UE 5.8: `Result: Succeeded` |
| gate-mcp-schema | Pass | MCP tools match tools.json for every server under mcp-servers/ |
| gate-shellcheck | Pass | `shellcheck -S style` exited 0 |
| gate-ship-smoke | Not applicable | No ship paths changed |
| plugin.validate | Pass | `claude plugin validate .`: Validation passed with warnings |
| plugin.session-smoke | Pass | Plugin loaded with `--plugin-dir`; `nmg-game-dev:blender` connected |

**Gate Summary**: 10/10 applicable gates passed, 0 failed, 0 incomplete (1 not applicable)

---

## Fixes Applied

| Severity | Category | Location | Original Issue | Fix Applied | Routing |
|----------|----------|----------|----------------|-------------|---------|
| High | Delivery artifacts | `CHANGELOG.md` | Base merge put #143 into main's released 0.21.5 section and left an empty `## [0.22.0]` heading | Not applied. Verify publication scope is limited to this report | Implementation |

## Remaining Issues

### Critical Issues
None.

### High Priority

**H1: The base merge corrupted CHANGELOG.md**

| Field | Value |
|-------|-------|
| **Severity** | High |
| **Category** | Delivery artifacts (release notes) |
| **Location** | `CHANGELOG.md` lines 9 and 19 (merge commit `0f34811`) |
| **Issue** | Line 9 is an empty `## [0.22.0] - 2026-11-12` heading directly above main's `## [0.21.5] - 2026-11-12`. Line 19 adds `- Make texture generation work from the plugin root and queue or batch texture jobs (#143)` inside main's already-released 0.21.5 `### Changed` section. `git diff origin/main HEAD -- CHANGELOG.md` shows exactly these two added lines. |
| **Impact** | Running the controller's `updateChangelog` (copied from `sdlc-deliver.mjs` 4.10.1) on this tree with version `0.22.0` and issue 143 gives `## [Unreleased]`, a new `## [0.22.0]` with the #143 entry, the stray empty `## [0.22.0]` again, and then `## [0.21.5]`, which still lists #143. Merging that would ship a duplicate release heading and claim that #143 shipped in 0.21.5. |
| **Fix** | In `CHANGELOG.md`, delete line 9 (`## [0.22.0] - 2026-11-12`) and line 19 (the #143 bullet under 0.21.5), so that `git diff origin/main HEAD -- CHANGELOG.md` is empty. Leave `## [Unreleased]` empty (version preparation adds the #143 entry), or put the single #143 bullet under `## [Unreleased]` / `### Changed`. Keep `VERSION` and the manifests at main's `0.21.5`. Then rerun the full registered gate. |
| **Reason Not Fixed** | Verify may publish only `verification-report.md`. |

### Medium Priority
None.

### Low Priority

These carry over unchanged from the previous verification. They are outside the spec and do not block delivery.

- **Error Handling**, `src/nmg_game_dev/texture/generate.py` (`_generate`): two batch requests that resolve to the same slug write to the same PNG paths and `textures.json`, so the later one silently overwrites the earlier one. Candidate follow-up: reject duplicate output names in `validate_batch`.
- **Error Handling**, `src/nmg_game_dev/texture/jobs.py` (`run_queue`): a runner killed partway through a job leaves that job `running`. Stale-lock recovery drains the queued jobs but never marks the orphaned one failed. The old single-job runner behaved the same way.
- **Error Handling**, `src/nmg_game_dev/texture/jobs.py` (`start`): the runner logs to the `job.log` of the job that spawned it, which may not be the job that crashed.
- **Informational**, `mcp-servers/finalize/uv.lock` and `mcp-servers/meshy/uv.lock`: these now carry the marked mflux stack, as FR1 (core dependencies) requires.

---

## Recommendations Summary

### Before PR (Must)
- [ ] Fix H1: restore main's `CHANGELOG.md` release sections and drop the empty `## [0.22.0]` heading, then rerun the full registered gate.

### Short Term (Should)
- [ ] Reject duplicate output names in a batch.

### Long Term (Could)
- [ ] Mark orphaned `running` jobs failed when a stale lock is recovered.
- [ ] Move the mflux stack behind a dependency group if the finalize and meshy install size matters.

---

## Recommendation

**Needs fixes**

The #143 implementation is complete and all 10 applicable registered gates passed at `0f348119c32b0ebbcbf76fedd7496a006ed61670` with complete coverage. Delivery has to wait for the two-line `CHANGELOG.md` repair (H1), because merging now would corrupt main's release notes.
