# Tasks: Batch finalize with lock wait, Unreal MCP timeout retry, and a PIE preflight

**Issue**: #149
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley

## Implementation Tasks

### T001: Atomic lock with optional wait

**File(s)**: `src/nmg_game_dev/pipeline/jobs.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- Lock claims are atomic (`O_CREAT | O_EXCL`), store `{"pid", "job_id"}`, read legacy plain-PID locks, and clear stale locks on every attempt.
- Without wait, a live holder raises `finalize.job_running` naming the holder job id (AC6).
- With `wait_for_lock`:
  - the job starts `waiting` and its `run-job` process polls every 2–5 s with jitter until it claims the lock, then runs;
  - when `lock_wait_s` expires first, the job fails with `finalize.job_running` naming the holder (AC5, FR5).

### T002: Batch jobs

**File(s)**: `src/nmg_game_dev/pipeline/jobs.py`, `src/nmg_game_dev/finalize/service.py`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- `start_batch` validates every request before writing anything. Invalid entries raise `finalize.invalid_batch` listing each zero-based index and reason (FR10).
- The batch runs items in order under one lock held for the whole batch, each in `items/<index>-<collection>/`.
- `status.json` `batch` reports total, completed, current collection and index, and per-item state (AC2, FR2).
- Failed items do not stop the batch; `fail_fast` marks the rest `skipped`. The final `result.batch` lists every item with state and, for failures, code, message, remediation, and stage, plus counts. A batch with any failure ends `failed` with `finalize.batch_failed` (AC3, AC4, FR3, FR4).

### T003: CLI batch and wait options

**File(s)**: `src/nmg_game_dev/finalize/__main__.py`
**Type**: Modify
**Depends**: T002, T005
**Acceptance**:
- Repeated `--collection` and `--batch FILE` run a batch in order and block until it ends (AC1).
- `--fail-fast`, `--wait`, `--wait-limit`, `--pie`, and `--pie-wait-limit` pass through.
- A batch prints per-item lines, or `{"batch": ...}` with `--json`, and exits 1 when any item failed (AC3).
- A single `--collection` keeps today's output, JSON, and exit codes.

### T004: Unreal MCP timeout retry

**File(s)**: `src/nmg_game_dev/pipeline/clients/unreal_mcp.py`, `src/nmg_game_dev/unreal/retry.py`, `src/nmg_game_dev/unreal/import_asset.py`
**Type**: Create, Modify
**Depends**: none
**Acceptance**:
- Timeouts raise `UnrealTimeoutError` with code `import_ue.failed`. Other failures keep their types and codes.
- `call_with_retry` retries only `UnrealTimeoutError`, up to `NMG_GAME_DEV_UE_RETRIES` (default 4) times. Before each retry it sleeps `NMG_GAME_DEV_UE_RETRY_DELAY_S` (default 20) × the retry number, then pings with a 10 s timeout, and re-sends only after a successful ping (FR6–FR8).
- `import_variant` uses it and adds `attempts` to its result (AC7). Exhaustion raises `import_ue.failed` stating the attempts and total seconds (AC8).
- The re-sent import code is identical, and `check_pivots` runs once on the successful result (AC9).

### T005: PIE preflight

**File(s)**: `src/nmg_game_dev/unreal/preflight.py`, `src/nmg_game_dev/pipeline/engine.py`, `src/nmg_game_dev/pipeline/request.py`
**Type**: Create, Modify
**Depends**: T004
**Acceptance**:
- `FinalizeRequest` gains `pie_mode` (`wait` | `refuse`, default `wait`) and `pie_wait_seconds` (default 600), outside every cache-settings hash.
- `_run_import` calls `ensure_not_in_pie` before each variant import, using a 10 s check timeout. A timed-out check counts as busy. `refuse` fails at once, and `wait` polls every 5 s up to the limit. Both fail with `import_ue.editor_busy` and the stop-PIE remediation, and no import request is sent while PIE is reported (AC10, FR9).

### T006: MCP tool parameters

**File(s)**: `src/nmg_game_dev/finalize/mcp_tools.py`, `mcp-servers/finalize/src/finalize_mcp/server.py`, `mcp-servers/finalize/tools.json`
**Type**: Modify
**Depends**: T002, T005
**Acceptance**:
- `finalize_asset` accepts `requests` (exclusive with `collection`), `fail_fast`, `wait_for_lock`, `lock_wait_seconds`, `pie_mode`, and `pie_wait_seconds`.
- `run_finalize_step` accepts the wait and PIE parameters.
- `get_finalize_job` returns `batch`. The single-collection calls keep their result shape (AC2, AC5).
- The tool descriptions name batch input, the summary, the wait option, the retry limits, and `import_ue.editor_busy` (AC11).
- `uv run python scripts/validate-mcp-tools.py` (`gate-mcp-schema`) passes.

### T007: Documentation

**File(s)**: `docs/mcp/finalize.md`, `skills/finalize-asset/SKILL.md`
**Type**: Modify
**Depends**: T003, T006
**Acceptance**:
- Both documents describe batch input (CLI and MCP), the per-collection summary and exit code, fail-fast, `--wait` / `wait_for_lock` and its limit, the retry defaults and environment overrides, and the PIE preflight with `import_ue.editor_busy` (AC11, FR11).
- They no longer tell the caller to wait and rerun by hand after `finalize.job_running`.
- `claude plugin validate .` (`plugin.validate`) passes.

### T008: Tests

**File(s)**: `tests/unit/pipeline/test_jobs.py`, `tests/unit/pipeline/test_batch.py`, `tests/unit/test_finalize_cli.py`, `tests/unit/test_finalize_mcp_tools.py`, `tests/unit/test_unreal_retry.py`, `tests/unit/test_pie_preflight.py`, `tests/unit/test_finalize_docs.py`
**Type**: Create, Modify
**Depends**: T001, T002, T003, T004, T005, T006, T007
**Acceptance**:
- Every test uses in-process job launchers, fake Unreal clients, and injected sleep and clock functions. None launches or connects to a live Blender or Unreal editor.
- SCN001 (AC1): `--collection A --collection B --collection C`, and `--batch` with three entries, run A, B, C in that order and exit after C.
- SCN002 (AC2): `finalize_asset(requests=[...])` returns a job id, and `get_finalize_job` reports `batch.current` and `completed`/`total` while the items run.
- SCN003 (AC3): a batch with one failing item reports each item's state, the failure's code, message, and stage, and exits 1 with the same summary under `--json`.
- SCN004 (AC4): without fail-fast, the items after a failure run; with fail-fast, they are `skipped`.
- SCN005 (AC5):
  - a second job with wait starts `waiting`, runs after the first releases the lock, and clears a stale lock left by a dead PID;
  - with an expired limit, it fails `finalize.job_running` naming the holder job id.
- SCN006 (AC6): without wait, a second start raises `finalize.job_running` at once.
- SCN007 (AC7): a fake client that times out twice then succeeds gives `attempts == 3`, with sleeps of 20 s and 40 s and a ping before each re-send. The environment overrides change the retry count and delay.
- SCN008 (AC8): a client that always times out fails `import_ue.failed`, stating 5 attempts and the total seconds. HTTP errors, `mcp.unreal.unreachable`, and editor-reported failures are not retried (FR8).
- SCN009 (AC9): when the first send times out and the retry succeeds, the re-sent code equals the first, the template keeps `replace_existing = True` and material-instance reuse, and `check_pivots` passes once.
- SCN010 (AC10):
  - with PIE reported for three polls, the import is sent only after PIE ends;
  - PIE persisting past the limit, and refuse mode, fail `import_ue.editor_busy` with no import code sent;
  - a timed-out PIE check counts as busy.
- FR10: a batch with invalid entries at indexes 1 and 3 fails `finalize.invalid_batch` naming both indexes, and writes no job directory.
- SCN011 (AC11): `tests/unit/test_finalize_docs.py` asserts that both documents and `tools.json` name the batch input, `wait_for_lock`, the retry defaults, and `import_ue.editor_busy`.
- `uv run pytest tests/unit tests/bdd -q` (`repository.tests`), `repository.lint`, `repository.format`, and `repository.types` pass.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #149 | 2026-11-11 | Initial feature tasks |
