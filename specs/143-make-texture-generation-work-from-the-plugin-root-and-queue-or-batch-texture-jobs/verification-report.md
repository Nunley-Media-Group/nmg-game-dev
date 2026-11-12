# Verification Report: Texture generation from the plugin root, with queued and batched jobs

**Date**: 2026-11-11
**Issue**: #143
**Reviewer**: Claude (nmg-sdlc verify worker, architecture-reviewer)
**Scope**: Re-verification after the `CHANGELOG.md` repair (`ed0663f`) and the base merge of `origin/main` at `e4705ff` (`2d14e05`)

**Verification head**: 2d14e05a04baaa2f7f108d633fa2d60e23777793

---

## Executive Summary

This run re-verifies #143 at `2d14e05`. Two commits landed since the last report, which failed at `0f34811`:

- `ed0663f` repaired the `CHANGELOG.md` defect H1. `git diff origin/main...HEAD -- CHANGELOG.md` now shows one change: the #143 bullet under `## [Unreleased]` / `### Changed`. Main's released sections are unchanged.
- `2d14e05` merged `origin/main` at `e4705ff`, which brings in #183 (ElevenLabs audio import) and the #204 spec. The merge changed no texture source, texture test, texture schema or texture doc. The only changes under `mcp-servers/` are the finalize server's new audio tools and the three server lockfiles, which now include #183's `miniaudio` and are consistent with the merged root `pyproject.toml`.

All 8 acceptance criteria still hold. All 11 registered validations were recorded at the exact head, so coverage is complete. All 10 that apply passed, and `gate-ship-smoke` does not apply. No finding blocks delivery.

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
**Total Issues**: 4 (3 Low and 1 informational, none blocking; H1 is resolved)

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

- Runner: `sdlc-verify-steering.mjs --project . --issue 143 --spec specs/143-… --base main --controller-run-id 0c0f8eb7-d4a6-48ea-848f-456893a057bd` (exit 0, `ok: true`)
- Artifact: `.nmg-sdlc/verification/143.json`. Head `2d14e05a04baaa2f7f108d633fa2d60e23777793`, clean tree. Steering hash `sha256:98aa7bb7…`, spec hash `sha256:7d8d383e…`.
- Coverage: `declared: 11`, `recorded: 11`, `complete: true`. Nothing is missing, duplicated or unknown.
- Ceiling: `null`. Every applicable required validation passed.

---

## Base Reconciliation Review

- **CHANGELOG.md**: H1 is fixed. The branch adds only `### Changed` / `- Make texture generation work from the plugin root and queue or batch texture jobs (#143)` under `## [Unreleased]`. The empty `## [0.22.0] - 2026-11-11` heading directly above `## [0.21.5]` comes from main (`git show origin/main:CHANGELOG.md`). This branch did not add it, and it is outside this issue's scope.
- **Version files**: `VERSION` is `0.22.0`, the same as `origin/main`. The plugin manifests follow main.
- **Locks**: `uv lock --check` passes for the root, `mcp-servers/texture-gen`, `mcp-servers/finalize` and `mcp-servers/meshy`.
- **Texture paths**: `git diff 0f34811 HEAD` shows no change under `src/nmg_game_dev/texture/`, `docs/onboarding/texture-models.md`, `mcp-servers/texture-gen/{src,tools.json}`, `tests/unit/texture/`, `tests/texture_fakes.py`, or the texture BDD features and steps.
- `origin/main` has since moved to `31dd95b` (#198). Delivery's base reconciliation handles that.

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Root project carries the generation dependencies on Apple Silicon | Pass | `pyproject.toml` `[project] dependencies` adds `mflux>=0.24.0` and `hf_transfer>=0.1.9`, each with marker `sys_platform == 'darwin' and platform_machine == 'arm64'`. The `texture-ai` extra uses the same floors, with no `==` pins. `mcp-servers/texture-gen/pyproject.toml` is unchanged. `uv lock --check` passes for all four projects at this head. Covered by `tests/unit/test_pyproject_texture_deps.py` and SCN001. |
| AC2 | Missing dependencies fail fast with an accurate error | Pass | `src/nmg_game_dev/texture/deps.py`: `missing_module` uses `importlib.util.find_spec` and never imports. `require_dependencies` raises `texture.dependencies_missing` with the module name and the `uv run --project <root> python -m nmg_game_dev.texture generate …` remediation. `generate` and `jobs.start` call it before any mkdir, spawn or enqueue. `hardware.availability` returns `dependencies_missing`. Covered by SCN002, `test_deps.py`, `test_hardware.py` and `test_jobs.py`. |
| AC3 | Worker import failures report the real cause | Pass | `src/nmg_game_dev/texture/batch.py` `_worker_remediation` matches `No module named '<m>'` and names that module and the plugin-root command. Any other failure keeps the models/memory text and the stderr tail. Covered by SCN003 and `test_batch.py`. |
| AC4 | A second request is queued, not rejected | Pass | `src/nmg_game_dev/texture/jobs.py`: `start` writes `queued` with `submitted_ns` and spawns `run-queue`. `run_queue` claims the PID lock, recovers a stale lock, drains in `(submitted_ns, job_id)` order, then releases and re-checks the queue. `texture.job_running` no longer appears anywhere under `src/`, `mcp-servers/`, `docs/` or `tests/`. Covered by SCN004, updated SCN017 and the `test_jobs.py` queue tests. |
| AC5 | Batch through the MCP tool | Pass | `mcp-servers/texture-gen/src/texture_gen_mcp/server.py` accepts `requests` and rejects calls with both or neither of `prompt` and `requests`. `generate` builds one `Batch` per backend, so progress `total` counts every image. The result is `{"results": [...]}` in request order. Covered by SCN005 (one worker start, 3 items, `completed == total == 3`). |
| AC6 | Batch through the CLI | Pass | `src/nmg_game_dev/texture/__main__.py`: `--batch FILE` is mutually exclusive with `--prompt`, and misuse exits 2. The command prints `{"results": [...]}`. Covered by SCN006 and `test_cli.py`. |
| AC7 | Invalid batch rejected before work starts | Pass | `generate.validate_batch` collects `request {i}: {reason}` for each failure and raises one `texture.invalid_request` before any selection, spawn or enqueue. Covered by SCN007 (indices 1 and 3, no spawn, no job directory). |
| AC8 | Single-request forms unchanged | Pass | `generate.run` keeps its signature and `TextureResult.as_json()` keys, and `run-job` is kept. Covered by SCN008 and the existing `texture_generation.feature` scenarios. |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Platform-marked generation dependencies | Complete | `pyproject.toml`, `uv.lock` (+ texture-gen, finalize, meshy locks) |
| T002 | Dependency probe and availability state | Complete | `texture/deps.py`, `hardware.py`, `generate.py` |
| T003 | Cause-aware worker failure remediation | Complete | `texture/batch.py` |
| T004 | Batch generation | Complete | `validate_batch`, `run_batch`, `BatchResult`; contact sheet refreshed once per batch |
| T005 | FIFO job queue | Complete | `jobs.start`, `run_queue`, `_next_queued`; CLI `run-queue`, `generate --batch` |
| T006 | MCP tool and schema | Complete | `server.py`, `tools.json`; `gate-mcp-schema` passed |
| T007 | Documentation | Complete | `docs/onboarding/texture-models.md` |
| T008 | Tests | Complete | Unit and BDD; `texture_queue_batch.feature` SCN001–SCN008 bound |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 4 | `deps.py` owns the probe and its remediation. `jobs.py` owns the queue and the lock. `generate._generate` is long but its phases are distinct. |
| Open/Closed | 4 | `run` and `run_batch` share `_generate`, and a single request is the one-element case. |
| Liskov Substitution | 5 | `BatchResult` and `TextureResult` keep distinct shapes. |
| Interface Segregation | 4 | The MCP tool takes either `prompt` or `requests`, never both. |
| Dependency Inversion | 5 | The probe, spawn, facts, env and registry are injected, and the probe is looked up at call time. |

### Layer Separation

The MCP server stays a thin wrapper over `nmg_game_dev.texture`. FR10 holds: a grep for `import`/`from` of `mflux` or `mlx` under `src/` and `mcp-servers/*/src` finds only `texture/worker.py`.

### Dependency Flow

`deps` ← `hardware` ← `generate` ← `jobs` ← CLI and MCP. There are no cycles.

---

## Security Assessment

- [x] Authentication: not applicable (local tooling)
- [x] Authorization: not applicable
- [x] Input validation: batch items are strictly typed, and the whole batch is validated before any work
- [x] Injection prevention: the runner is spawned from an argv list (no shell), and the remediation path is quoted with `shlex.quote`
- [x] Data protection: no secrets; logs go only to `job.log` and stderr

---

## Performance Assessment

- [x] Async patterns: a detached runner drains the queue, so callers never poll in a loop
- [x] Caching: each backend's model loads once per batch
- [x] Resource management: worker batch files live in a `TemporaryDirectory`, and the lock is released in `finally`
- [x] Query optimization: `_next_queued` is O(jobs) per job, which is fine at local scale

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
- Step definitions: implemented in `tests/bdd/test_texture_queue_batch_bdd.py`.
- Full registered suite (`repository.tests`) at `2d14e05`: 1268 passed, 10 skipped.

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| repository.tests | Pass | `uv run pytest tests/unit tests/bdd -q`: 1268 passed, 10 skipped |
| repository.lint | Pass | `ruff check .`: All checks passed |
| repository.format | Pass | `ruff format --check .`: 356 files already formatted |
| repository.types | Pass | `mypy src tests`: no issues found in 233 source files |
| gate-blender-headless | Pass | `scripts/run-blender-tests.sh`: 269 passed, 4 skipped |
| gate-ue-compile | Pass | DogfoodEditor compiled against UE 5.8 |
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
| High | Delivery artifacts | `CHANGELOG.md` | H1 from the previous report: the base merge put #143 under main's released 0.21.5 section | Fixed in implementation (`ed0663f`) and confirmed here | Implementation |

## Remaining Issues

### Critical Issues
None.

### High Priority
None.

### Medium Priority
None.

### Low Priority

These carry over from earlier reports. They are outside the spec and do not block delivery.

- **Error Handling**, `src/nmg_game_dev/texture/generate.py` (`_generate`): if two batch requests resolve to the same slug, the later one silently overwrites the earlier one's PNGs and `textures.json`. **Reason not fixed**: outside the spec. A follow-up could reject duplicate output names in `validate_batch`.
- **Error Handling**, `src/nmg_game_dev/texture/jobs.py` (`run_queue`): if the runner is killed partway through a job, that job stays `running`. Stale-lock recovery drains the queue but never marks the orphaned job failed. **Reason not fixed**: the old single-job runner behaved the same way, so this is not a regression.
- **Error Handling**, `src/nmg_game_dev/texture/jobs.py` (`start`): the runner logs to the `job.log` of the job that spawned it. **Reason not fixed**: this only affects where diagnostics go, so it is low impact.
- **Informational**, `mcp-servers/finalize/uv.lock` and `mcp-servers/meshy/uv.lock` carry the marked mflux stack, because FR1 makes it a core dependency on Apple Silicon.

---

## Positive Observations

- The dependency probe never imports `mlx` or `mflux`, so `status` stays cheap and FR10 holds.
- The whole batch is validated before anything is queued, so a bad batch leaves nothing behind.
- The CHANGELOG repair keeps main's released sections exactly as they are on main.

---

## Recommendations Summary

### Before PR (Must)
- None.

### Short Term (Should)
- [ ] Reject duplicate output names in a batch.

### Long Term (Could)
- [ ] Mark orphaned `running` jobs failed when a stale lock is recovered.

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `CHANGELOG.md` | 0 | H1 resolved |
| `pyproject.toml`, `uv.lock`, `mcp-servers/*/uv.lock` | 0 | Locks consistent |
| `src/nmg_game_dev/texture/deps.py` | 0 | |
| `src/nmg_game_dev/texture/generate.py` | 1 Low | Duplicate slug |
| `src/nmg_game_dev/texture/jobs.py` | 2 Low | Orphaned job; log target |
| `src/nmg_game_dev/texture/batch.py`, `hardware.py`, `__main__.py` | 0 | |
| `mcp-servers/texture-gen/src/texture_gen_mcp/server.py`, `tools.json` | 0 | |
| `docs/onboarding/texture-models.md` | 0 | |

---

## Recommendation

**Ready for PR**

All eight acceptance criteria pass. H1 is resolved, and all 10 applicable registered gates passed at `2d14e05a04baaa2f7f108d633fa2d60e23777793` with complete coverage and no ceiling.
