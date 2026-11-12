# Verification Report: Batch finalize with lock wait, Unreal MCP timeout retry, and a PIE preflight

**Date**: 2026-11-12
**Issue**: #149
**Reviewer**: Claude (nmg-sdlc verify worker, architecture-reviewer)
**Scope**: Implementation verification against spec (re-verification after merging `origin/main` at `19f4c1f`)
**Verification head**: e12ccc5da796f9f059ec427236949cb1edb23105

---

## Executive Summary

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
**Total Issues**: 5 (all Low, none blocking)

All 11 acceptance criteria and 8 tasks are implemented, and each has unit tests that use fakes only. This re-verification covers the head after a fourth `chore: merge origin/main` commit (`e12ccc5`), which brings in #148 material variants (#186), #203 rename/consolidate checks (#217), the texture queue (#208), and the UBA-free UE compile gate (#210). The merge keeps #149's retry wiring in `import_variant`: it now takes `material_variants` and also `retry`/`sleep`/`clock` and records `attempts`. #217's refused-rename and refused-consolidate checks stay in the import template, and a re-sent import over existing assets still goes through the consolidate path, so AC9 holds. Batch entries gain `material_variants_path`. The CLI rejects `--material-variants` for a batch, and the MCP docs say the top-level parameter applies to one collection only. `pipeline/jobs.py`, `unreal/retry.py`, and `unreal/preflight.py` are unchanged by the merge. Every applicable registered steering validation passed at the verification head (10 of 10). `gate-ship-smoke` does not apply.

---

## Issue Scope

- Active issue: #149
- Spec: `specs/149-add-batch-finalize-with-lock-wait-unreal-mcp-timeout-retry-and-a-pie-preflight`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1–AC11]; FR [FR1–FR11]; tasks [T001–T008]; scenarios [SCN001–SCN011]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":149,"specPath":"specs/149-add-batch-finalize-with-lock-wait-unreal-mcp-timeout-retry-and-a-pie-preflight","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6","AC7","AC8","AC9","AC10","AC11"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6","FR7","FR8","FR9","FR10","FR11"],"tasks":["T001","T002","T003","T004","T005","T006","T007","T008"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006","SCN007","SCN008","SCN009","SCN010","SCN011"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

- Artifact: `.nmg-sdlc/verification/149.json` (base `main`, head `e12ccc5da796f9f059ec427236949cb1edb23105`, clean tree, run id `9cee569d-e9c4-4ac1-b8fb-e1f80a089c9e`, generated 2026-11-12T06:58:07Z)
- Coverage: declared 11, recorded 11, complete `true`; no missing, duplicate, or unknown ids
- Ceiling: none (`null`)
- Note: the local `main` ref in this lane worktree lags `origin/main`, so the runner's changed-path set is wider than #149's own diff. That made `gate-shellcheck`, `gate-blender-headless`, and `gate-ue-compile` applicable, and all three passed. Applicability only grew, so no gate was skipped.

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | CLI batch (repeated `--collection` / `--batch`) runs in order and blocks until the last | Pass | `src/nmg_game_dev/finalize/__main__.py` (`_run_batch_command`, `_load_batch_file`); `FinalizeService.run_batch` waits with no timeout; tests `test_repeated_collections_run_in_order_and_exit_after_the_last`, `test_a_batch_file_runs_its_entries_in_order` |
| AC2 | MCP `finalize_asset(requests=…)`; `get_finalize_job` reports current collection and completed/total | Pass | `src/nmg_game_dev/finalize/mcp_tools.py` (`requests` branch, `_JOB_FIELDS` adds `batch`); `jobs._run_item` sets `batch.current` / `current_index`; tests in `tests/unit/test_finalize_mcp_tools.py` (assert `current == "Beta"`, `completed == 1`, `total == 2`) and `test_status_reports_the_running_collection_and_the_completed_count` |
| AC3 | Per-item summary with state and error code, message, and step; CLI exits non-zero, `--json` summary | Pass | `jobs._run_batch` writes `result.batch` with items and counts; `_print_batch`; tests `test_a_failed_item_is_reported_with_its_code_message_and_stage`, `test_batch_json_names_each_failed_item_and_exits_one`, `test_a_failed_item_prints_its_code_and_step_in_the_summary` |
| AC4 | A failure does not stop the batch; fail-fast marks the rest `skipped` | Pass | `jobs._run_batch` `stop = fail_fast and …`; tests `test_without_fail_fast_the_items_after_a_failure_still_run`, `test_with_fail_fast_the_items_after_a_failure_are_skipped`, `test_fail_fast_reports_the_rest_of_the_batch_as_skipped` |
| AC5 | `--wait` / `wait_for_lock` waits in the job process; an expired limit fails `finalize.job_running` naming the holder | Pass | `jobs._submit` (job starts `waiting`), `jobs._wait_for_lock` (2–5 s jitter, deadline), `run_job` failure naming `_holder_text(holder)`; tests `test_a_waiting_job_starts_waiting_and_runs_once_the_lock_is_free`, `test_a_waiting_job_polls_with_jitter_until_the_holder_releases`, `test_an_expired_wait_limit_fails_naming_the_holder_and_leaves_its_lock`, `test_a_waiting_job_clears_a_stale_lock_left_by_a_dead_pid`, `test_a_batch_waiting_for_the_lock_fails_when_its_limit_expires_first` |
| AC6 | Without wait, a second start fails at once with `finalize.job_running` | Pass | `jobs._submit` → `_claim` → `_job_running(holder)`; tests `test_a_live_job_refuses_a_second_start_with_job_running`, `test_a_refused_start_names_the_holder_job_and_keeps_its_lock`, `test_a_legacy_plain_pid_lock_still_refuses_a_live_holder`, `test_a_held_lock_without_wait_fails_the_batch_at_once` |
| AC7 | Timeouts retried with growing delay; result records `attempts` | Pass | `src/nmg_game_dev/unreal/retry.py` `call_with_retry` (sleep `base_delay_s * k`, ping, re-send); `import_variant` sets `result["attempts"]`; test `test_two_timeouts_then_success_takes_three_attempts_with_back_off` (sleeps 20 s and 40 s, 3 attempts) |
| AC8 | Retries are bounded; failure states attempts and total seconds | Pass | `call_with_retry` raises `import_ue.failed` "Unreal MCP did not answer after N attempts over S s"; tests `test_a_client_that_always_times_out_fails_after_five_attempts`, `test_http_errors_and_an_unreachable_editor_are_not_retried`, `test_an_editor_reported_failure_is_not_retried` (FR8) |
| AC9 | A retry does not duplicate or corrupt an import | Pass | Re-sent code is byte-identical; template keeps `task.replace_existing = True` and `_instance` reuse; `check_pivots` runs once on the successful reply; test `test_a_retried_import_sends_the_identical_code_and_checks_pivots_once` |
| AC10 | PIE preflight waits or refuses with `import_ue.editor_busy`; no import is sent during PIE | Pass | `src/nmg_game_dev/unreal/preflight.py` `ensure_not_in_pie`; `engine._run_import` calls it before each `import_variant`; tests in `tests/unit/test_pie_preflight.py` (wait-then-import, limit reached, refuse, timed-out check counts as busy, 10 s check timeout, job-level refusal sends no import, PIE options outside cache hashes) |
| AC11 | Docs, skill, and tool descriptions cover batch, summary, wait, retry limits, `import_ue.editor_busy` | Pass | `docs/mcp/finalize.md`, `skills/finalize-asset/SKILL.md`, `mcp-servers/finalize/tools.json`, `server.py` docstrings; `tests/unit/test_finalize_docs.py` |

### Functional Requirements

| FR | Status | Evidence |
|----|--------|----------|
| FR1 | Pass | CLI repeated `--collection` / `--batch` (AC1) |
| FR2 | Pass | `finalize_asset(requests)`, `status.json` `batch` (AC2) |
| FR3 | Pass | `result.batch` items and counts; exit 1 on any failure (AC3) |
| FR4 | Pass | continue by default, `fail_fast` → `skipped` (AC4) |
| FR5 | Pass | `wait_for_lock` / `--wait`, `lock_wait_s` / `--wait-limit`; default unchanged (AC5, AC6) |
| FR6 | Pass | `call_with_retry`, `attempts` in the import result (AC7) |
| FR7 | Pass | `retry_settings()` reads `NMG_GAME_DEV_UE_RETRIES` (4) and `NMG_GAME_DEV_UE_RETRY_DELAY_S` (20); invalid values are refused; tests `test_environment_overrides_change_the_retry_count_and_the_delay`, `test_the_documented_defaults_apply_when_the_environment_is_silent`, `test_an_invalid_retry_setting_is_refused` |
| FR8 | Pass | Only `UnrealTimeoutError` is retried; HTTP, `mcp.unreal.unreachable`, and editor-reported failures propagate |
| FR9 | Pass | `ensure_not_in_pie` before each variant import, default limit 600 s |
| FR10 | Pass | `service.build_batch` validates every entry first and lists `index N: reason`; `test_invalid_entries_are_all_named_and_no_job_directory_is_written` |
| FR11 | Pass | Docs, skill, and tool descriptions updated; docs test |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Atomic lock with optional wait | Complete | `O_CREAT \| O_EXCL` claim, JSON `{pid, job_id}`, legacy PID read, stale clearing on each attempt, `_release_lock` keyed by job id |
| T002 | Batch jobs | Complete | `start_batch`, `_run_batch`, `_run_item` under `items/<index>-<collection>/`, `finalize.batch_failed` |
| T003 | CLI batch and wait options | Complete | `--collection` (append), `--batch`, `--fail-fast`, `--wait`, `--wait-limit`, `--pie`, `--pie-wait-limit`; single form unchanged |
| T004 | Unreal MCP timeout retry | Complete | `UnrealTimeoutError` (code `import_ue.failed`), per-call timeout, `retry.py` |
| T005 | PIE preflight | Complete | `preflight.py`, `FinalizeRequest.pie_mode` / `pie_wait_seconds`, outside cache settings |
| T006 | MCP tool parameters | Complete | `mcp_tools.py`, `server.py`, `tools.json`; `gate-mcp-schema` passed |
| T007 | Documentation | Complete | `docs/mcp/finalize.md`, `skills/finalize-asset/SKILL.md`; `plugin.validate` passed |
| T008 | Tests | Complete | New: `test_batch.py`, `test_unreal_retry.py`, `test_pie_preflight.py`, `test_finalize_docs.py`; extended: `test_jobs.py`, `test_finalize_cli.py`, `test_finalize_mcp_tools.py`, `tests/finalize_fakes.py`. No live editors are used |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 4 | Retry (`unreal/retry.py`) and PIE preflight (`unreal/preflight.py`) are separate small modules; batch validation is in `service.build_batch`. `jobs.py` grows to cover lock, single, and batch lifecycle. It is cohesive but large. |
| Open/Closed | 4 | Single and batch jobs share `_submit` and `run_job`, branching on `job.kind`. |
| Liskov Substitution | 5 | `UnrealTimeoutError` subclasses `PipelineError` and keeps code `import_ue.failed`, so existing handlers are unaffected. |
| Interface Segregation | 5 | `TimeoutAwareClient` / `UnrealPythonClient` protocols expose only `execute_python_code(code, *, timeout)`. |
| Dependency Inversion | 5 | Sleep, clock, launcher, runner, and retry settings are injected, which makes every timing path testable without real waits. |

### Layer Separation

This follows the steering layer table. Skill and docs describe the tools. `mcp_tools.py` and `server.py` add no pipeline logic: they validate and delegate to `FinalizeService`. Orchestration (lock, batch) lives in `pipeline/jobs.py`, and the Unreal steps (retry, preflight, import) live in `src/nmg_game_dev/unreal/`. No skill opens an MCP socket.

### Dependency Flow

`unreal/preflight.py` and `unreal/retry.py` depend on `pipeline.clients.unreal_mcp` (for the timeout type) and `pipeline.errors`. `pipeline/engine.py` depends on `unreal/preflight`, as it already did on `unreal/import_asset`. There are no new cycles, and mypy and ruff are clean.

---

## Security Assessment

- [x] Authentication: N/A (local loopback MCP only; no new credentials)
- [x] Authorization: N/A
- [x] Input validation: batch entries are checked against an allow-list of keys, built through `FinalizeRequest` (PascalCase collection, so `items/<index>-<collection>` cannot traverse paths), with a non-negative lock wait and `pie_mode` enum; invalid input is a structured error
- [x] Injection prevention: PIE and ping code are constants; the import code is unchanged and re-sent byte-identical
- [x] Data protection: no secrets logged; errors go to stderr through the existing MCP logging

---

## Performance Assessment

- [x] Async patterns: lock waiting runs in the detached job process, so MCP calls return at once (within the 150 s cap)
- [x] Caching: per-item step caching is preserved; PIE options are kept out of cache-settings hashes (tested)
- [x] Resource management: the lock is released in `run_job`'s `finally`, keyed by job id so one job never drops another's lock
- [x] Query optimization: lock polling uses 2–5 s jitter, PIE polling 5 s, back-off 20 s × k; all bounded

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1 (SCN001) | Yes | Yes (unit tests named in the feature header) | Yes |
| AC2 (SCN002) | Yes | Yes | Yes |
| AC3 (SCN003) | Yes | Yes | Yes |
| AC4 (SCN004) | Yes | Yes | Yes |
| AC5 (SCN005) | Yes | Yes | Yes |
| AC6 (SCN006) | Yes | Yes | Yes |
| AC7 (SCN007) | Yes | Yes | Yes |
| AC8 (SCN008) | Yes | Yes | Yes |
| AC9 (SCN009) | Yes | Yes | Yes |
| AC10 (SCN010) | Yes | Yes | Yes |
| AC11 (SCN011) | Yes | Yes | Yes |

### Coverage Summary

- Feature file: `specs/149-…/feature.gherkin`, 11 scenarios mapped to unit tests in `tests/unit/pipeline/test_batch.py`, `tests/unit/pipeline/test_jobs.py`, `tests/unit/test_unreal_retry.py`, `tests/unit/test_pie_preflight.py`, `tests/unit/test_finalize_cli.py`, `tests/unit/test_finalize_mcp_tools.py`, `tests/unit/test_finalize_docs.py`
- `repository.tests`: 1432 passed, 10 skipped (`uv run pytest tests/unit tests/bdd -q`)
- `gate-blender-headless`: 338 passed, 4 skipped
- All timing uses injected sleep and clock; no live Blender or Unreal editor is contacted

---

## Exercise Test Results

| Field | Value |
|-------|-------|
| **Reason** | No `workflows/` or `agents/` changes, so no nmg-sdlc skill exercise applies. The changed `skills/finalize-asset/SKILL.md` is covered by `plugin.validate` and the real `plugin.session-smoke` (plugin loaded via `--plugin-dir`, MCP servers connected). |
| **Recommendation** | None |

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` | Pass | `uv run pytest tests/unit tests/bdd -q` exited 0; 1432 passed, 10 skipped |
| `repository.lint` | Pass | `uv run ruff check .`: All checks passed |
| `repository.format` | Pass | `uv run ruff format --check .`: 376 files already formatted |
| `repository.types` | Pass | `uv run mypy src tests`: no issues found in 245 source files |
| `gate-blender-headless` | Pass | `scripts/run-blender-tests.sh` exited 0; 338 passed, 4 skipped |
| `gate-ue-compile` | Pass | DogfoodEditor compiled against `/Users/Shared/Epic Games/UE_5.8` (`-NoUBA`) |
| `gate-mcp-schema` | Pass | `uv run python scripts/validate-mcp-tools.py`: MCP tools match tools.json |
| `gate-shellcheck` | Pass | `find scripts -name *.sh -exec shellcheck -S style {} +` exited 0 with no findings |
| `gate-ship-smoke` | Not applicable | No ship paths changed (runner applicability) |
| `plugin.validate` | Pass | `claude plugin validate .`: validation passed (with warnings) |
| `plugin.session-smoke` | Pass | Plugin loaded via `--plugin-dir` in an ephemeral Herdr project; `nmg-game-dev:blender` connected (real run, not replayed) |

**Gate Summary**: 10/10 applicable gates passed, 0 failed, 0 incomplete (1 not applicable; coverage 11/11 complete)

---

## Fixes Applied

| Severity | Category | Location | Original Issue | Fix Applied | Routing |
|----------|----------|----------|----------------|-------------|---------|
| — | — | — | No fixes were needed | — | — |

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
| **Location** | `src/nmg_game_dev/pipeline/jobs.py` `_hand_lock_to` |
| **Issue** | It reads the lock, then rewrites it. If the spawned job finished and another job claimed the lock in between, the rewrite could overwrite the new holder's record. |
| **Impact** | The window is a few microseconds right after spawn and needs a sub-millisecond job, so it is practically unreachable. |
| **Reason Not Fixed** | Outside this verify stage's writable scope (report only). A future hardening pass can write the record before spawn or hand over by rename. |

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Error Handling |
| **Location** | `src/nmg_game_dev/pipeline/jobs.py` `_run_item` (`else:` clause) |
| **Issue** | `_mark_backlog` runs in the `try`'s `else`, so an exception other than `OSError`/`ValueError` from the backlog write would escape the item and end the batch process. The job would then be reported as `finalize.job_crashed`. |
| **Impact** | It only happens on an unexpected backlog error, and that error is still reported as a structured crash. |
| **Reason Not Fixed** | Outside writable scope; non-blocking. |

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Error Handling |
| **Location** | `src/nmg_game_dev/unreal/preflight.py` `is_in_pie` |
| **Issue** | If the PIE check reply has no `NMG_RESULT` line, `parse_nmg_result` raises `import_ue.failed` rather than counting the check as busy. |
| **Impact** | Fails closed: no import is sent. Only the error code differs. |
| **Reason Not Fixed** | Consistent with the spec, which defines only a timed-out check as busy. |

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Error Handling |
| **Location** | `src/nmg_game_dev/finalize/mcp_tools.py` `finalize_asset` (`requests` branch) |
| **Issue** | With `requests`, a top-level `material_variants_path` is silently ignored. It is not one of the batch defaults. The CLI instead rejects `--material-variants` for a batch with a usage error. |
| **Impact** | A caller who sets the top-level path on a batch gets no material variants and no warning. `docs/mcp/finalize.md` and the tool description say the top-level parameter applies to one collection only. |
| **Reason Not Fixed** | Outside this verify stage's writable scope (report only). A follow-up could return `finalize.invalid_request` when both are given. |

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Testing |
| **Location** | `tests/unit/pipeline/test_batch.py`, `tests/unit/test_finalize_cli.py` |
| **Issue** | The merge glue that lets batch entries carry `material_variants_path`, and the CLI rejection of `--material-variants` with a batch, has no dedicated test. Verification checked it by hand: `build_batch` keeps a per-entry path and reports a missing one as `finalize.invalid_batch` at index 0. |
| **Impact** | A regression in the #148/#149 interaction would not be caught automatically. |
| **Reason Not Fixed** | Outside writable scope; this is not a #149 acceptance criterion. |

---

## Positive Observations

- Lock waiting moved into the detached job, which avoids the 150 s MCP cap and gives the CLI and MCP one mechanism.
- Lock release is keyed by job id, so a batch never drops its lock between items and one job cannot release another's.
- A distinct `UnrealTimeoutError` type keeps FR8 exact: only timeouts are retried.
- Thorough fake-based tests for every timing path, including jitter, deadlines, ping timeouts, and environment overrides.
- Batch validation finishes before anything is written, and it names every invalid zero-based index.

---

## Recommendations Summary

### Before PR (Must)
- None.

### Short Term (Should)
- None.

### Long Term (Could)
- [ ] Make the lock handover in `_hand_lock_to` atomic.
- [ ] Wrap `_mark_backlog` in `_run_item` so any backlog error becomes an item warning.
- [ ] Reject a top-level `material_variants_path` combined with `requests` in `finalize_asset`, and add batch material-variant tests.

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `src/nmg_game_dev/pipeline/jobs.py` | 2 (Low) | Lock, wait, batch lifecycle |
| `src/nmg_game_dev/finalize/service.py` | 0 | `build_batch`, `start_batch`, `run_batch` |
| `src/nmg_game_dev/finalize/__main__.py` | 0 | CLI batch and flags |
| `src/nmg_game_dev/finalize/mcp_tools.py` | 1 (Low) | MCP parameters; batch ignores top-level `material_variants_path` |
| `mcp-servers/finalize/src/finalize_mcp/server.py` | 0 | Tool signatures and descriptions |
| `mcp-servers/finalize/tools.json` | 0 | Schema |
| `src/nmg_game_dev/pipeline/clients/unreal_mcp.py` | 0 | `UnrealTimeoutError`, per-call timeout |
| `src/nmg_game_dev/unreal/retry.py` | 0 | Bounded retry |
| `src/nmg_game_dev/unreal/preflight.py` | 1 (Low) | PIE preflight |
| `src/nmg_game_dev/unreal/import_asset.py` | 0 | Retry wiring, `attempts`; #217 rename/consolidate checks preserved |
| `src/nmg_game_dev/pipeline/engine.py` | 0 | Preflight call |
| `src/nmg_game_dev/pipeline/request.py` | 0 | PIE fields |
| `docs/mcp/finalize.md`, `skills/finalize-asset/SKILL.md` | 0 | AC11 |
| `tests/**` (listed above) | 0 | Fakes only |

---

## Recommendation

**Ready for PR**

All delivery ACs, FRs, tasks, and scenarios are implemented and tested. The deterministic steering artifact shows complete coverage with no ceiling, and every applicable required validation passed at `e12ccc5da796f9f059ec427236949cb1edb23105`. The five Low findings do not block delivery.
