# Design: Batch finalize with lock wait, Unreal MCP timeout retry, and a PIE preflight

**Issue**: #149
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley

## Overview

Four changes:

1. A batch is one finalize job that runs its items in order under one cache-root lock.
2. Lock waiting moves into the job's own background process, so an MCP call returns at once while the job waits.
3. `import_ue` retries only Unreal MCP timeouts, with bounded back-off, and pings the editor before re-sending.
4. A short PIE check runs before each variant import.

The single-collection CLI and MCP forms keep their parameters and result shapes.

## Architecture

### Lock (`src/nmg_game_dev/pipeline/jobs.py`)

- Claiming `<cache_root>/jobs/lock` becomes atomic (`os.open(..., O_CREAT | O_EXCL)`). The lock holds JSON `{"pid": int, "job_id": str}`.
- A legacy plain-PID lock is still read.
- A lock whose PID is dead or unreadable is removed and the claim is retried (stale-lock recovery), on every attempt.
- **Without wait.** `start` claims the lock before spawning, as today, and fails with `finalize.job_running` naming the holder's job id and PID (AC6).
- **With wait** (`wait_for_lock=True`, optional `lock_wait_s`):
  - `start` writes the job with state `waiting` and its status message naming the holder job, then spawns `run-job` without claiming.
  - `run-job` polls for the claim every 2–5 s with random jitter, with stale-lock recovery on each poll, then runs.
  - When `lock_wait_s` expires first, the job ends `failed` with `finalize.job_running` naming the holder job id (AC5).
  - A `waiting` job whose process died is reported `finalize.job_crashed` by `status`, as running jobs are today.
- `TERMINAL_STATES` is unchanged. `waiting` is non-terminal, so `wait()` and the CLI keep blocking.

### Batch (`jobs.py`, `src/nmg_game_dev/finalize/service.py`)

- `start_batch(requests, steps, *, force, fail_fast, wait_for_lock, lock_wait_s)` creates one job directory with `job.json` `{"kind": "batch", "items": [request dicts], ...}` and spawns `run-job`.
- `run-job` claims the lock once and keeps it for the whole batch. It runs each item through the same engine path a single job uses, in its own `items/<index>-<collection>/` directory, so step caching and backlog marking work per item.
- Per-item lock release inside `run_job` must not drop the batch's lock.
- After each item, `status.json` gains `batch`:
  - `{"total": n, "completed": k, "current": "<collection>" | null, "current_index": i | null, "items": [...]}`;
  - each item is `{"index", "collection", "state": "pending" | "running" | "succeeded" | "failed" | "skipped", "error": null | {"code", "message", "remediation", "stage"}}`.
- **Failure handling.**
  - A failed item does not stop the batch (AC4).
  - With `fail_fast`, the remaining items are `skipped`.
  - The batch job's state is `succeeded` when every item succeeded. Otherwise it is `failed`, with error `finalize.batch_failed` whose message gives the failed and skipped counts.
  - `result.batch` holds the final item list and the `succeeded` / `failed` / `skipped` counts (AC3).
- **Validation (FR10).** Every request is built with `build_request` before the job starts. Any failure raises `finalize.invalid_batch`, whose message lists `index N: <reason>` for each invalid entry. Nothing is written.

### CLI (`src/nmg_game_dev/finalize/__main__.py`)

- `--collection` may repeat. The other asset arguments apply to every collection.
- `--batch FILE` takes a JSON array of request objects with the `finalize_asset` keys. It is mutually exclusive with `--collection`.
- `--fail-fast`, `--wait`, `--wait-limit SECONDS`, `--pie {wait,refuse}`, and `--pie-wait-limit SECONDS` (default 600) are added.
- One collection without `--batch` keeps today's output and exit codes.
- A batch prints one line per item (`<collection>: <state>` plus `[code] message (step)` for failures) or, with `--json`, `{"batch": result.batch}`. It exits 0 when all items succeeded and 1 otherwise.

### MCP (`src/nmg_game_dev/finalize/mcp_tools.py`, `mcp-servers/finalize/src/finalize_mcp/server.py`, `mcp-servers/finalize/tools.json`)

- `finalize_asset` gains:
  - `requests: list[object] | None`, mutually exclusive with `collection`;
  - `fail_fast: bool = false`, `wait_for_lock: bool = false`, `lock_wait_seconds: number | null`;
  - `pie_mode: "wait" | "refuse" = "wait"`, `pie_wait_seconds: number = 600`.
- `collection` and `export_root` are no longer schema-required. The function requires exactly one of `collection` or `requests`, and `export_root` for the single form.
- `run_finalize_step` gains `wait_for_lock`, `lock_wait_seconds`, `pie_mode`, and `pie_wait_seconds`.
- `get_finalize_job` adds `batch` to its returned fields.

### Retry (`src/nmg_game_dev/pipeline/clients/unreal_mcp.py`, new `src/nmg_game_dev/unreal/retry.py`)

- **Timeout type.** The client raises `UnrealTimeoutError`, a `PipelineError` subclass that keeps code `import_ue.failed`, for both timeout branches in `_post`. Every other failure keeps its current type and code.
- **Retry loop.** `call_with_retry(client, code, *, retries, base_delay_s, sleep, clock)` runs `client.execute_python_code(code)` and retries only `UnrealTimeoutError`.
  - Before retry `k` (1-based) it sleeps `base_delay_s * k`.
  - It sends a ping, `print("NMG_PING")`, with a 10 s timeout. A ping timeout consumes that retry.
  - It re-sends the import only after a successful ping.
- **Defaults.** `retries = NMG_GAME_DEV_UE_RETRIES` (default 4), `base_delay_s = NMG_GAME_DEV_UE_RETRY_DELAY_S` (default 20).
- **Exhausted.** The loop raises `import_ue.failed` with "Unreal MCP did not answer after N attempts over S s".
- **Attempts recorded.** `import_variant` uses it and adds `attempts` to its result (AC7, AC8, FR8).
- **Re-send safety (AC9).** The import template already imports textures with `replace_existing=True`, reuses existing material instances (`_instance`), and re-imports meshes over existing assets. Re-sending is therefore safe. A test asserts the re-sent code is byte-identical and that `check_pivots` runs on the final result only.

### PIE preflight (new `src/nmg_game_dev/unreal/preflight.py`)

- `ensure_not_in_pie(client, *, mode, wait_s, poll_s=5.0, sleep, clock)` runs UE Python that prints `NMG_RESULT {"pie": bool}`, using `unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).is_in_play_in_editor()`, with a 10 s request timeout.
- A timed-out check counts as busy.
- `refuse` mode fails at once with `import_ue.editor_busy` when PIE is running.
- `wait` mode polls until PIE ends or `wait_s` elapses, then fails with `import_ue.editor_busy`. The remediation is "Stop the Play In Editor session, then rerun finalize."
- `engine._run_import` calls it before each variant's `import_variant`, so no import is sent during PIE (AC10).
- `pie_mode` and `pie_wait_seconds` are new `FinalizeRequest` fields with defaults `wait` / 600. They are not part of any step's cache settings.

## API / Interface Changes

| Interface | Input | Output / Error | Behavior |
|-----------|-------|----------------|----------|
| CLI `all` / steps | `--collection` (repeatable), `--batch FILE`, `--fail-fast`, `--wait`, `--wait-limit S`, `--pie wait\|refuse`, `--pie-wait-limit S` | exit 0 / 1 (any failed) / 2 (prerequisite, single form); batch summary text or `--json` | AC1, AC3–AC6, AC10 |
| MCP `finalize_asset` | `requests`, `fail_fast`, `wait_for_lock`, `lock_wait_seconds`, `pie_mode`, `pie_wait_seconds` | `{job_id, status}`; `finalize.invalid_batch` | AC2, AC5, AC10 |
| MCP `run_finalize_step` | `wait_for_lock`, `lock_wait_seconds`, `pie_mode`, `pie_wait_seconds` | unchanged shape | AC5, AC10 |
| MCP `get_finalize_job` | `job_id` | adds `batch` | AC2 |
| `import_ue` result per variant | — | adds `attempts` | AC7 |
| Errors | — | `finalize.job_running` (names holder job id), `finalize.invalid_batch`, `finalize.batch_failed`, `import_ue.editor_busy`, `import_ue.failed` (attempts and seconds) | AC5, AC8, AC10, FR10 |

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Wait for the lock inside the job process | Selected | MCP calls return at once; one mechanism serves CLI and MCP |
| Wait in the caller (MCP server) | Rejected | MCP calls are capped at 150 s |
| ghost1 defaults (2–5 s jittered poll, 4 retries from 20 s, 600 s PIE wait) | Selected | Proven over a 70-asset consumer run; back-off grows linearly to satisfy "increasing delay" |
| Retry `asset not found` too | Rejected | The issue scopes it to the PIE preflight; any other cause is a separate bug |
| Batch resume state | Rejected | Step caching already makes reruns cheap |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #149 | 2026-11-11 | Initial feature design |
