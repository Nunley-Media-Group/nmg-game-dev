# Verification Report: The texture job queue overwrites duplicate batch outputs, strands orphaned running jobs, and writes runner output into one job's log

**Date**: 2026-11-12
**Issue**: #211
**Reviewer**: Claude (nmg-sdlc architecture-reviewer, verify stage)
**Scope**: Defect-fix verification against the approved spec

**Verification head**: f568afba52741f7d322f898a7fbcc374d1975200

---

## Executive Summary

This is a re-verification after deliver merged `origin/main` (`19f4c1f`) into the branch as `f568afb`. The merge changed none of the #211 source, test, or doc files; it brought in #214, #216, #186 and #217 and the version files. The fix addresses all three defects. Batch validation now rejects requests that share an output name. A queue runner that claims the lock marks any job left `running` by a dead runner as `failed` with `texture.runner_exited`. The detached runner writes to `<jobs root>/runner.log`, and each `job.log` holds only that job's lines. Every registered validation that applies passed at the verification head, the reproduction steps no longer reproduce, and the three `@regression` scenarios have passing fake-only tests.

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 5 |
| Security | 5 |
| Performance | 4 |
| Testability | 5 |
| Error Handling | 5 |
| **Overall** | 4.8 |

### Implementation Status: Pass
**Fix Type**: defect fix
**Total Issues**: 3 (all Low; none block delivery)

---

## Issue Scope

- Active issue: #211
- Spec: `specs/211-fix-texture-job-queue-duplicate-batch-outputs-orphaned-running-jobs-and-runner-log-location`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1, AC2, AC3]; FR [FR1, FR2, FR3, FR4]; tasks [T001, T002, T003, T004, T005]; scenarios [SCN001, SCN002, SCN003]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":211,"specPath":"specs/211-fix-texture-job-queue-duplicate-batch-outputs-orphaned-running-jobs-and-runner-log-location","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3"],"functionalRequirements":["FR1","FR2","FR3","FR4"],"tasks":["T001","T002","T003","T004","T005"],"scenarios":["SCN001","SCN002","SCN003"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

- Runner: `sdlc-verify-steering.mjs --base main --controller-run-id 42fc9d51-eb25-4ca7-83e7-80418c11a275` (run 2026-11-12T06:46:55Z)
- Artifact: `.nmg-sdlc/verification/211.json`
- Identity: head `f568afba52741f7d322f898a7fbcc374d1975200`, clean tree, steering `sha256:6db9aabc…d74474d4`, spec `sha256:fe54e070…8eee204`
- Coverage: declared 11, recorded 11, complete `true`; no missing, duplicate, or unknown results
- Ceiling: none

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Duplicate output names in a batch are rejected before anything is queued or generated | Pass | `src/nmg_game_dev/texture/generate.py` `validate_batch` groups indexes by `slugify(request.name or request.prompt)` and adds `requests <i>, <j>: output name '<name>' is used more than once` to the one `texture.invalid_request`. Both entry points validate first: `run_batch` (CLI `--batch`) and `jobs.start` (the `generate_textures(requests=...)` path). Tests: `test_validate_batch_refuses_requests_that_share_an_output_name`, `test_run_batch_refuses_shared_output_names_before_any_worker_or_folder`, `test_a_batch_with_a_shared_output_name_exits_one_and_names_the_indexes`, `test_a_batch_with_a_shared_output_name_is_refused_before_a_job_exists` |
| AC2 | A job orphaned by a dead runner is marked failed; queued jobs still run FIFO | Pass | `src/nmg_game_dev/texture/jobs.py`: `run_job` writes `runner.json` (`{"pid": …}`) atomically before its first `running` status. `_recover_orphans` runs each time `run_queue` claims the lock, before draining, and rewrites dead-runner `running` jobs as `failed` / `texture.runner_exited`, keeping `completed` and `total`. Tests: `test_a_job_orphaned_by_a_dead_runner_is_marked_failed_and_the_queue_moves_on`, `test_a_running_job_whose_runner_is_alive_is_left_running`, `test_a_running_job_with_no_runner_record_is_marked_failed_with_an_unknown_pid`, `test_run_job_records_the_pid_of_the_process_that_ran_it` |
| AC3 | The runner log has its own file; each `job.log` holds only that job's output | Pass | `jobs.start` passes `<jobs root>/runner.log` (append) as the runner's stdout and stderr. `run_queue` writes started/running/final/recovered/idle lines to `runner.log`. `run_job` writes only its own start line, final line, and traceback to `job.log`. Tests: `test_the_runner_writes_its_own_log_and_each_job_log_holds_only_its_job`, `test_a_crashed_job_writes_its_traceback_to_its_own_job_log` |

### Reproduction check (defect path)

A new scratch script (`validate_batch` on `burlap` / `stone` / `Burlap`; a killed `sleep` PID written to `runner.json` and the lock, then `jobs.run_queue`) ran against the merged head `f568afb`:

- **AC1**: `validate_batch` on `burlap` / `stone` / `Burlap` raises `texture.invalid_request | The batch is invalid, so nothing was generated or queued: requests 0, 2: output name 'burlap' is used more than once`. Before the fix this batch validated, and request 2 overwrote request 0's folder.
- **AC2**: a `sleep` process was started and killed, and its real PID was written to a job's `runner.json` and to the queue lock. `jobs.run_queue` then left that job `failed` with `texture.runner_exited`, keeping `completed` 1 and `total` 4. Before the fix the job stayed `running`.
- **AC3**: that run's `runner.log` held `runner <pid> started / job job-a marked failed: runner <dead pid> exited / runner <pid> idle`, and the orphaned job got no `job.log` at all.

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Reject duplicate output names in batch validation | Complete | `generate.py` `validate_batch` |
| T002 | Mark jobs orphaned by a dead runner as failed | Complete | `RUNNER_NAME`, `_runner_pid`, `_recover_orphans`, `runner.json` written in `run_job`; `status.json` keys unchanged |
| T003 | Give the queue runner its own log | Complete | `RUNNER_LOG_NAME`, `_append_log`, `start` / `run_queue` / `run_job` log routing |
| T004 | Document the duplicate-name rule, the orphan code, and the runner log | Complete | `docs/onboarding/texture-models.md` batch-validation and queue paragraphs |
| T005 | Unit tests with fakes for AC1–AC3 | Complete | `tests/unit/texture/test_generate.py`, `test_cli.py`, `test_jobs.py`; no weights, GPU, Blender, Unreal, or real worker |

---

## Architecture Assessment (defect path: blast radius)

- **Other callers on the changed paths**: `validate_batch` is called by `generate.run_batch` and `jobs.start`. Both are meant to get the new check. `validate_request` (single requests) is unchanged. `run_queue` and `run_job` are called by the `run-queue` and `run-job` CLI subcommands, which the texture-gen MCP server and the CLI start. Their signatures are unchanged.
- **Public contract changes**: no function signature or return type changed. `status.json` keeps its keys and state values. The new things are the error code `texture.runner_exited` and the internal files `runner.json` and `runner.log`. A batch that used to overwrite outputs silently is now refused, which is the intended fix.
- **Silent data changes**: none. Orphan recovery keeps the job's last `completed` and `total`, and skips jobs whose runner PID is alive, so a direct `run-job` process that holds no queue lock is left alone.
- **Minimal-change check**: `git diff origin/main...HEAD` touches only the files in the design's Changes table, plus the CHANGELOG entry. After the merge, `VERSION` and the three plugin manifests equal `origin/main` (0.23.0), so deliver's prepare-version still has to apply this issue's bump. There are no unrelated refactors.
- **Layering**: the changes stay inside the texture package. The MCP server still wraps `jobs` without adding logic, as structure steering requires.

| Area | Score | Notes |
|------|-------|-------|
| SOLID | 5 | Small single-purpose helpers (`_runner_pid`, `_recover_orphans`, `_append_log`). `run_job` routes every exit through one `finish` closure. |
| Security | 5 | No new inputs from outside. Paths come from the jobs root and job ids. `runner.json` is parsed defensively (non-dict or non-int PID becomes `None`). |
| Performance | 4 | `_recover_orphans` reads every job's `status.json` once per lock claim. That cost grows with the history kept in `.jobs/` (see Remaining Issues). |
| Testability | 5 | Every AC has deterministic fake-only tests, including the case where the runner is alive and the case with no `runner.json`. |
| Error Handling | 5 | Unreadable status or runner files are skipped or treated as unknown. The orphan error has a code, a message, and a remediation that names `runner.log`. Crash tracebacks now go to the job's own `job.log`, so the existing `texture.job_crashed` remediation points at the right file. |

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Tests | Passes |
|---------------------|-------------|-----------|--------|
| AC1 | Yes (SCN001 `@regression`) | Yes (unit, fakes) | Yes |
| AC2 | Yes (SCN002 `@regression`) | Yes (unit, fakes) | Yes |
| AC3 | Yes (SCN003 `@regression`) | Yes (unit, fakes) | Yes |

### Coverage Summary

- `specs/.../feature.gherkin`: 3 scenarios, all tagged `@regression`. Their target file is `tests/unit/texture/test_jobs.py`, as tech steering allows for fake-backed unit coverage of this defect.
- Full `repository.tests`: 1345 passed, 10 skipped.

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` | Pass | `uv run pytest tests/unit tests/bdd -q` exited 0 (1345 passed, 10 skipped) |
| `repository.lint` | Pass | `uv run ruff check .` exited 0 |
| `repository.format` | Pass | `uv run ruff format --check .` exited 0 |
| `repository.types` | Pass | `uv run mypy src tests` exited 0 |
| `gate-blender-headless` | Pass | `scripts/run-blender-tests.sh` exited 0 |
| `gate-ue-compile` | Pass | DogfoodEditor compiled against UE 5.8 (`Build.sh … -NoUBA`) |
| `gate-mcp-schema` | Pass | `uv run python scripts/validate-mcp-tools.py` exited 0 |
| `gate-shellcheck` | Pass | `shellcheck -S style` on every `scripts/**.sh` exited 0 |
| `gate-ship-smoke` | Not applicable | No ship paths changed (runner recorded `applicable: false`) |
| `plugin.validate` | Pass | `claude plugin validate .` exited 0 |
| `plugin.session-smoke` | Pass | Plugin loaded via `--plugin-dir`; `nmg-game-dev:blender` connected |

**Gate Summary**: 10/10 applicable gates passed, 0 failed, 0 incomplete (1 not applicable)

---

## Exercise Test Results

Not applicable. The change does not touch `workflows/` or `agents/`.

---

## Fixes Applied

| Severity | Category | Location | Original Issue | Fix Applied | Routing |
|----------|----------|----------|----------------|-------------|---------|
| — | — | — | No verification-time fixes were needed. The merge left the #211 implementation unchanged, so the repair for this attempt was a full rerun of the registered gate at the new head | — | — |

## Remaining Issues

### Low Priority

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Performance |
| **Location** | `src/nmg_game_dev/texture/jobs.py` `_recover_orphans` |
| **Issue** | Each lock claim scans every directory under `.jobs/`, and finished jobs are never pruned. |
| **Impact** | Runner start-up gets slower as job history grows. It is negligible at the job counts expected in authoring use. |
| **Reason Not Fixed** | Job pruning and rotation are out of scope (requirements Out of Scope: no rotating or truncating). |

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Error Handling |
| **Location** | `src/nmg_game_dev/texture/jobs.py` `_recover_orphans` |
| **Issue** | Liveness is checked by PID alone. If the OS reuses a dead runner's PID, that orphan stays `running` until the PID exits. |
| **Impact** | Rare, and it heals on a later lock claim. The behavior matches the existing PID-lock design. |
| **Reason Not Fixed** | This is the approach the approved design chose. Adding process start-time identity would widen the fix. |

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Delivery metadata |
| **Location** | `CHANGELOG.md` |
| **Issue** | After the merge, the branch's earlier prepared heading `## [0.22.1] - 2026-11-12` (#211 Fixed) sits directly under `## [Unreleased]`, ahead of main's unreleased `### Added` (#148) entry. `VERSION` is 0.23.0 (main's value), so the heading is stale. |
| **Impact** | None on the fix. If prepare-version does not rewrite the heading, the release notes will carry a stale 0.22.1 section. |
| **Reason Not Fixed** | `CHANGELOG.md` and version files belong to deliver's prepare-version step and are outside the verify write scope. |

---

## Positive Observations

- Duplicate-name failures share the per-request failure list, so a batch reports every problem in one error.
- `runner.json` keeps the `status.json` document the MCP tool returns unchanged, as the design's alternatives table intended.
- Tests cover the boundary cases: a live runner PID, a missing `runner.json`, and real FIFO order after recovery.

---

## Recommendations Summary

### Before PR (Must)
- None

### Short Term (Should)
- [ ] At deliver, confirm prepare-version replaces the stale `[0.22.1]` CHANGELOG heading with this release's version.

### Long Term (Could)
- [ ] Consider pruning finished jobs under `.jobs/` in a separate issue.

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `src/nmg_game_dev/texture/generate.py` | 0 | Duplicate-output-name check |
| `src/nmg_game_dev/texture/jobs.py` | 2 (Low) | Orphan recovery, runner log, per-job log |
| `docs/onboarding/texture-models.md` | 0 | Documents all three behaviors |
| `tests/unit/texture/test_generate.py` | 0 | AC1 |
| `tests/unit/texture/test_cli.py` | 0 | AC1 via CLI |
| `tests/unit/texture/test_jobs.py` | 0 | AC1–AC3 |

---

## Recommendation

**Ready for PR**

All three acceptance criteria and every task are met, the reproduction steps no longer reproduce, the `@regression` scenarios pass, and every applicable registered gate passed at `f568afba52741f7d322f898a7fbcc374d1975200`.
