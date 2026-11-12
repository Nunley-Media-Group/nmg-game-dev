# Verification Report: Texture generation from the plugin root, with queued and batched jobs

**Date**: 2026-11-11
**Issue**: #143
**Reviewer**: Claude (nmg-sdlc verify worker, architecture-reviewer)
**Scope**: Implementation verification against spec

**Verification head**: bfb2b707a0f94961398f92642ab547e60eb20cd9

---

## Executive Summary

The branch implements all eight acceptance criteria. The root project carries mflux and hf_transfer as Apple Silicon floors. A `find_spec` probe turns a missing mflux or mlx into `texture.dependencies_missing`, both before any work starts and in `status` / `texture_backends`. A worker that cannot import a module now names that module in its `texture.worker_failed` remediation. `texture.job_running` is gone: jobs go into a FIFO queue that one detached `run-queue` runner drains under the existing PID lock. Batches (`generate_textures(requests=…)` and `generate --batch FILE`) are validated as a whole and run one worker per backend.

All 11 manifest-registered validations have results. Coverage is complete: 10 applicable required gates passed, and `gate-ship-smoke` does not apply. No findings needed a fix. The remaining notes are low priority and outside the spec.

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 4 |
| Security | 5 |
| Performance | 4 |
| Testability | 5 |
| Error Handling | 4 |
| **Overall** | 4.5 |

### Implementation Status: Pass
**Total Issues**: 4 (all Low or informational; none block delivery)

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

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

- Runner: `sdlc-verify-steering.mjs --project . --issue 143 --spec specs/143-… --base main --controller-run-id 408c5465-26a2-44d9-bc7c-b3bfa24066cb`
- Artifact: `.nmg-sdlc/verification/143.json`. Head `bfb2b707a0f94961398f92642ab547e60eb20cd9`, clean tree. Steering hash `sha256:795f9897…`, spec hash `sha256:7d8d383e…`.
- Coverage: `declared: 11`, `recorded: 11`, `complete: true`. Nothing is missing, duplicated or unknown.
- Ceiling: none. Every applicable required validation passed, and `gate-ship-smoke` does not apply to this change.

---

## Acceptance Criteria Verification

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
- Targeted run: `uv run pytest tests/unit/texture tests/unit/test_pyproject_texture_deps.py tests/bdd/test_texture_queue_batch_bdd.py tests/bdd/test_texture_bdd.py -q` gave 152 passed.
- Full registered suite (`repository.tests`): 1172 passed, 9 skipped.

### Manual exercise (no live editors)

- Root project: `uv run --project <root>` finds `mflux` and `mlx`. `status` reports `not_installed` on this host because no weights are downloaded here.
- Missing `mlx` (hidden through `sys.modules`): the real CLI `status` and `generate` behave as AC2 requires, with no output or jobs directory created.
- Real detached queue: two `jobs.start` calls (one single, one 2-request batch) with dummy weights and `HF_HUB_OFFLINE=1`. Both were `queued`. The real `run-queue` process ran them in FIFO order, both ended `failed` / `texture.worker_failed` (expected, since the weights are dummies), the batch's `total` was 2, and the lock was removed.

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| repository.tests | Pass | `uv run pytest tests/unit tests/bdd -q`: 1172 passed, 9 skipped |
| repository.lint | Pass | `ruff check .`: All checks passed |
| repository.format | Pass | `ruff format --check .`: 336 files already formatted |
| repository.types | Pass | `mypy src tests`: no issues in 214 source files |
| gate-blender-headless | Pass | `scripts/run-blender-tests.sh`: 247 passed (applies because the version bump touched `blender_manifest.toml`) |
| gate-ue-compile | Pass | DogfoodEditor compiled against UE 5.8 (applies because the version bump touched `nmg-game-dev.uplugin`) |
| gate-mcp-schema | Pass | MCP tools match tools.json for every server under mcp-servers/ |
| gate-shellcheck | Pass | `shellcheck -S style` exited 0 |
| gate-ship-smoke | Not applicable | No ship paths changed |
| plugin.validate | Pass | `claude plugin validate .` exited 0 |
| plugin.session-smoke | Pass | Plugin loaded with `--plugin-dir`; `nmg-game-dev:blender` connected |

**Gate Summary**: 10/10 applicable gates passed, 0 failed, 0 incomplete (1 not applicable)

Environment note: the release-tooling SCN008 test in `repository.tests` runs `uv` offline with `--frozen` against the finalize and meshy projects. Before the gate ran, both `.venv`s were synced locally (`uv sync --project mcp-servers/finalize` and `--project mcp-servers/meshy`). This is a host preparation step, not a code change.

---

## Review Note: finalize and meshy lockfiles

FR1 adds mflux and hf_transfer to the root project's core `[project] dependencies`. `mcp-servers/finalize` and `mcp-servers/meshy` depend on the root package as an editable path. As a result, their `uv.lock` files must also resolve the marked mflux stack (mflux, mlx, mlx-metal, huggingface-hub, opencv-python, matplotlib, and so on). That accounts for about 700 added lines each.

The diff only adds lines, every new entry applies only on `darwin`/`arm64`, and no existing pinned version changed. No source in either server changed. Without the regeneration, `uv lock --check` would fail for those projects.

This is therefore a mechanical consequence of the spec as written (FR1 puts the dependencies in core), not a change to the finalize or meshy servers that the Out of Scope list forbids. The trade-off is a heavier install for those two servers on Apple Silicon. If that matters, a follow-up issue could move the dependencies behind a dependency group.

---

## Fixes Applied

| Severity | Category | Location | Original Issue | Fix Applied | Routing |
|----------|----------|----------|----------------|-------------|---------|
| — | — | — | No defects needing a fix were found | — | — |

## Remaining Issues

### Critical Issues
None.

### High Priority
None.

### Medium Priority
None.

### Low Priority

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Error Handling |
| **Location** | `src/nmg_game_dev/texture/generate.py` (`_generate`) |
| **Issue** | Two batch requests whose `name`, backend, seed and resolution resolve to the same slug write to the same PNG paths and the same `textures.json`, so the later request overwrites the earlier one. |
| **Impact** | Silent overwrite inside a malformed batch. Separate single requests had the same behavior before this change. |
| **Reason Not Fixed** | Not covered by the spec. Verify publication scope is limited to the report. Candidate follow-up: reject duplicate output names in `validate_batch`. |

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Error Handling |
| **Location** | `src/nmg_game_dev/texture/jobs.py` (`run_queue`) |
| **Issue** | If a queue runner is killed partway through a job, that job stays `running`. The next start replaces the stale lock and drains the queued jobs, but the orphaned job is never marked failed. |
| **Impact** | `get_texture_job` shows `running` indefinitely for that one job. The same was true of the old single-job runner. |
| **Reason Not Fixed** | Existing behavior, not covered by #143. |

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Error Handling |
| **Location** | `src/nmg_game_dev/texture/jobs.py` (`start`) |
| **Issue** | The runner's stdout and stderr go to the `job.log` of the job that spawned it, but that runner may go on to run later jobs. The `texture.job_crashed` remediation points at the crashed job's own `job.log`. |
| **Impact** | Diagnostics for a crash may sit in a different job's log. |
| **Reason Not Fixed** | Cosmetic, and not covered by the spec. |

| Field | Value |
|-------|-------|
| **Severity** | Informational |
| **Category** | Architecture |
| **Location** | `mcp-servers/finalize/uv.lock`, `mcp-servers/meshy/uv.lock` |
| **Issue** | The marked mflux stack is now in these lockfiles (see the review note above). |
| **Impact** | A heavier `uv sync` for those servers on Apple Silicon. |
| **Reason Not Fixed** | Required by FR1 as written. |

---

## Positive Observations

- The probe never imports `mlx`, and a test guards this with an assertion on `sys.modules`.
- The queue closes the release/start race by re-scanning after the lock is released. The job is written before its runner is spawned.
- One `_generate` serves both single and batch runs, so the single-request shape cannot drift.
- Every external effect (probe, spawn, hardware, env) is injectable, which keeps the tests hermetic on Linux CI.

---

## Recommendations Summary

### Before PR (Must)
- [ ] None

### Short Term (Should)
- [ ] Reject duplicate output names in a batch.

### Long Term (Could)
- [ ] Mark orphaned `running` jobs failed when a stale lock is recovered.
- [ ] Move the mflux stack behind a dependency group if the finalize and meshy install size matters.

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `pyproject.toml`, `uv.lock` | 0 | Floors and markers match FR1 |
| `mcp-servers/{texture-gen,finalize,meshy}/uv.lock` | 1 (info) | Additions only, under the arm64 marker |
| `src/nmg_game_dev/texture/deps.py` | 0 | New |
| `src/nmg_game_dev/texture/hardware.py` | 0 | |
| `src/nmg_game_dev/texture/batch.py` | 0 | |
| `src/nmg_game_dev/texture/generate.py` | 1 | Duplicate-name batch overwrite |
| `src/nmg_game_dev/texture/jobs.py` | 2 | Orphaned running job; runner log location |
| `src/nmg_game_dev/texture/__main__.py` | 0 | |
| `mcp-servers/texture-gen/src/texture_gen_mcp/server.py`, `tools.json` | 0 | |
| `docs/onboarding/texture-models.md` | 0 | |
| `tests/**` (texture unit, BDD) | 0 | |

---

## Recommendation

**Ready for PR**

Every AC, FR, task and scenario is implemented and evidenced. All 10 applicable registered gates passed at `bfb2b707a0f94961398f92642ab547e60eb20cd9` with complete coverage. The remaining items are low priority and outside the spec.
