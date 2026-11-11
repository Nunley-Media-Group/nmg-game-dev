# Requirements: Batch finalize with lock wait, Unreal MCP timeout retry, and a PIE preflight

**Issue**: #149
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley

## User Story

**As a** developer or agent finalizing many assets with nmg-game-dev
**I want** finalize to accept a list of collections, wait for the job lock, retry a briefly busy Unreal editor, and check that the editor is not in Play In Editor (PIE) before importing
**So that** I can finalize a whole project's assets in one unattended run, without a hand-written shell loop that polls and retries

## Background

Only one finalize job may run per cache root. `src/nmg_game_dev/pipeline/jobs.py` raises `finalize.job_running` when a live job holds `<cache_root>/jobs/lock`. The CLI (`src/nmg_game_dev/finalize/__main__.py`) and the MCP tools `finalize_asset` / `run_finalize_step` (`src/nmg_game_dev/finalize/mcp_tools.py`) take one collection, and their `wait_seconds` only waits for the caller's own job.

`src/nmg_game_dev/pipeline/clients/unreal_mcp.py` (`DEFAULT_TIMEOUT_S = 120.0`) turns a timeout into `import_ue.failed` on the first occurrence. `src/nmg_game_dev/unreal/import_asset.py` imports without checking whether PIE is running.

## Acceptance Criteria

### AC1: Batch finalize through the CLI

**Given** a list of collections supplied to the finalize CLI (repeated `--collection` values or a `--batch <file.json>` array of finalize requests)
**When** the developer runs the command once
**Then** every collection is finalized one at a time, in the order given, and the command exits only after the last one finishes

### AC2: Batch finalize through the MCP tool

**Given** `finalize_asset` is called with a list of finalize requests in its `requests` argument
**When** the batch runs
**Then** the collections are finalized one at a time in the order given
**And** `get_finalize_job` reports the collection that is running and how many are completed out of the total

### AC3: Per-asset result summary

**Given** a batch in which some collections succeed and some fail
**When** the batch finishes
**Then** the result lists every collection with its state (`succeeded`, `failed`, or `skipped`), and each failure carries its error code, message, and failing step
**And** the CLI exits non-zero when any collection failed, and prints the same summary as JSON with `--json`

### AC4: One failed asset does not stop the batch

**Given** a batch in which one collection fails any step
**When** the batch runs
**Then** the remaining collections are still finalized
**And** with the fail-fast option (`--fail-fast` or `fail_fast: true`), the remaining collections are reported as `skipped` instead

### AC5: Wait for the lock instead of failing

**Given** a finalize job is already running for the cache root
**When** a second finalize (single or batch) is started with `--wait` (CLI) or `wait_for_lock: true` (MCP)
**Then** the second request waits until the lock is free and then runs, instead of returning `finalize.job_running`
**And** when a wait limit (`--wait-limit` / `lock_wait_seconds`) expires first, the request fails with `finalize.job_running` naming the job id that still holds the lock

### AC6: Default lock behavior is unchanged

**Given** a finalize job is already running
**When** a second finalize is started without the wait option
**Then** it fails immediately with `finalize.job_running`, as it does today

### AC7: Unreal MCP timeouts are retried with back-off

**Given** the Unreal editor does not answer an `import_ue` request within the request timeout
**When** the step runs
**Then** the request is retried up to the retry limit, with an increasing delay before each retry
**And** the step succeeds when a retry succeeds, and the import result for that variant records `attempts`

### AC8: Retries are bounded

**Given** the editor stays unresponsive for every attempt
**When** the retry limit is reached
**Then** the step fails with `import_ue.failed`, and the message states the number of attempts and the total seconds waited

### AC9: A retry does not duplicate or corrupt an import

**Given** an import request timed out but the editor completed it afterwards
**When** the retry runs
**Then** the import result is the same as a single successful import: no duplicate assets, and the pivot and bounds checks still pass

### AC10: PIE preflight before import

**Given** the editor is in a PIE session when `import_ue` is about to start
**When** the preflight runs
**Then** by default the step waits for PIE to end, up to the PIE wait limit, and then imports
**And** when PIE is still running at the limit, or the refuse mode is chosen, the step fails with `import_ue.editor_busy`, whose remediation says to stop PIE and rerun
**And** no import request is sent while PIE is active

### AC11: Documentation

**Given** the changes above
**When** a developer reads `docs/mcp/finalize.md`, `skills/finalize-asset/SKILL.md`, and the finalize MCP tool descriptions
**Then** they describe:
- batch input and the result summary;
- the wait option;
- the retry behavior and its limits;
- the PIE preflight and its error code

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | The finalize CLI accepts a list of collections and finalizes them one at a time in order. | Must |
| FR2 | `finalize_asset` accepts a list of requests as one batch; job status reports the current collection and completed/total counts. | Must |
| FR3 | A batch produces a per-collection summary (state, and for failures the error code, message, and step); the CLI exit code is non-zero when any collection failed. | Must |
| FR4 | A batch continues past a failed collection by default; a fail-fast option stops it and marks the rest `skipped`. | Must |
| FR5 | A wait option (CLI `--wait`, MCP `wait_for_lock`) waits for the cache-root lock instead of raising `finalize.job_running`, with an optional limit. Without it, behavior is unchanged. | Must |
| FR6 | Unreal MCP request timeouts in `import_ue` are retried a bounded number of times with back-off; the attempt count is recorded in the step result. | Must |
| FR7 | Retry count and delays have documented defaults (4 retries; 20 s × retry number) and can be overridden with `NMG_GAME_DEV_UE_RETRIES` and `NMG_GAME_DEV_UE_RETRY_DELAY_S`. | Should |
| FR8 | Only timeouts are retried. HTTP errors, an unreachable editor (`mcp.unreal.unreachable`), and import or pivot failures reported by the editor are not retried. | Must |
| FR9 | Before `import_ue` sends an import request, a preflight checks whether PIE is running and waits (default limit 600 s) or refuses with `import_ue.editor_busy`. | Must |
| FR10 | A batch is validated before any work starts; an invalid entry rejects the whole batch with `finalize.invalid_batch`, naming the zero-based index of each invalid entry. | Must |
| FR11 | Docs, the finalize-asset skill, and the MCP tool descriptions cover the new options and error codes. | Must |

## Out of Scope

- Running two finalize jobs concurrently on one cache root.
- Cancelling or reordering collections in a running batch.
- Detecting editor activity other than PIE in the preflight; the timeout retry covers these.
- Queueing or batching texture jobs (#143).
- Fixes to the import itself (#141, #145, #146).
- Retrying `asset not found` errors reported by the editor.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #149 | 2026-11-11 | Initial feature spec |
