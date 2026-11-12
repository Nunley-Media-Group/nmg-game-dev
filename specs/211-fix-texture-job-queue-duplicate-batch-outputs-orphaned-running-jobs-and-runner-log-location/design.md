# Root Cause Analysis: The texture job queue overwrites duplicate batch outputs, strands orphaned running jobs, and writes runner output into one job's log

**Issue**: #211
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/143-make-texture-generation-work-from-the-plugin-root-and-queue-or-batch-texture-jobs/

## Root Cause

1. **Batch output collisions.** `generate.validate_batch()` calls `validate_request()` on each request alone. It never compares the output names that `_generate()` later derives as `slugify(request.name or request.prompt)`. Two requests that slugify alike get the same `base / name` folder, and the second request's images and `manifest.json` overwrite the first's.
2. **Orphaned running jobs.** `run_job()` writes `running` statuses but records no runner identity. `run_queue()` only drains jobs whose state is `queued`. After a runner is killed mid-job, the next runner takes over the stale lock and never looks at the job left `running`, so that job never reaches a final state.
3. **Runner log location.** `jobs.start()` opens `<job_dir>/job.log` and passes it as stdout and stderr of the detached `run-queue` process. That one runner goes on to run every queued job, so all of its output lands in the starting job's `job.log`.

## Affected Code

| File | Symbol / Area | Role |
|------|---------------|------|
| `src/nmg_game_dev/texture/generate.py` | `validate_batch` | Validates requests one at a time; no output-name check |
| `src/nmg_game_dev/texture/jobs.py` | `run_queue`, `run_job` | No runner identity per job; no recovery of `running` jobs |
| `src/nmg_game_dev/texture/jobs.py` | `start` | Sends runner stdout/stderr to the starting job's `job.log` |

## Fix Strategy

1. **Duplicate names (FR1).** After the per-request checks, `validate_batch()` groups request indexes by `slugify(request.name or request.prompt)`. For each name used by two or more requests, it adds the failure `requests <i>, <j>[, …]: output name '<name>' is used more than once` to the same list that per-request failures use. Indexes are zero-based and ascending, and the name comes from `repr`. The existing `_invalid_batch()` then raises one `texture.invalid_request`. Both entry points already validate before work starts: `run_batch()` (CLI `--batch`) and `jobs.start()` (the `generate_textures(requests=...)` path). So the rejection happens before any job directory, worker, or output folder exists.
2. **Orphan recovery (FR2).** Add `RUNNER_NAME = "runner.json"` to `jobs.py`.
   - Before `run_job()` writes its first `running` status, it writes `<job_dir>/runner.json` atomically as `{"pid": os.getpid()}`. This holds for the queue runner and for `run-job` alike.
   - Add `_recover_orphans(jobs)`. For every job directory whose `status.json` state is `running`, it reads `runner.json`. If the file is missing or unreadable, or its `pid` is not alive under `_pid_alive`, it rewrites `status.json` as `{"job_id", "state": "failed", "completed": <last completed>, "total": <last total>, "error": {"code": "texture.runner_exited", "message": "The texture queue runner (PID <pid>, or 'unknown') exited while this job was running.", "remediation": "Start the job again. Read <jobs root>/runner.log for the runner's last output."}}`.
   - `run_queue()` calls `_recover_orphans(jobs)` each time it claims the lock, before it drains `_next_queued()`. Queued jobs therefore still run oldest-first after recovery. The status document keeps its existing keys.
3. **Runner log (FR3).** Add `RUNNER_LOG_NAME = "runner.log"`.
   - `start()` opens `<jobs root>/runner.log` in append mode for the detached runner's stdout and stderr, instead of the job's `job.log`.
   - `run_queue()` appends timestamped lines to `runner.log`: `runner <pid> started`, `job <id> running`, `job <id> <final state>`, `job <id> marked failed: runner <pid> exited`, and `runner <pid> idle`.
   - `run_job()` appends to its own `<job_dir>/job.log` only: a `job <id> started` line, a `job <id> <final state>` line, and on a crash the formatted traceback. The existing `texture.job_crashed` remediation, which points at `job.log`, now names a file that holds that job's traceback.

## Changes

| File | Change | Behavioral reason |
|------|--------|-------------------|
| `src/nmg_game_dev/texture/generate.py` | Duplicate-output-name check in `validate_batch` | AC1, FR1 |
| `src/nmg_game_dev/texture/jobs.py` | `runner.json`, `_recover_orphans`, `texture.runner_exited`, `runner.log`, per-job `job.log` lines | AC2, AC3, FR2, FR3 |
| `docs/onboarding/texture-models.md` | Batch-validation paragraph names the duplicate-output rule; queue paragraph names `texture.runner_exited` and `<output root>/.jobs/runner.log` | AC1–AC3 |
| `tests/unit/texture/test_generate.py`, `tests/unit/texture/test_cli.py`, `tests/unit/texture/test_jobs.py` | Fake-only tests for AC1–AC3 | FR4 |

## Blast Radius

Batches whose output names are all distinct validate and run as before. A batch that used to overwrite outputs silently is now refused. `status.json` keeps its keys and state values. Only the new `texture.runner_exited` code and the new `runner.json` and `runner.log` files are added. The PID lock, FIFO ordering, and single-job results are unchanged.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Record the runner PID in a per-job `runner.json` | Selected | Keeps the `status.json` document the MCP tool returns unchanged, and covers `run-job` too |
| Add `runner_pid` to `status.json` | Rejected | Changes the tool's status document for internal bookkeeping |
| Treat every `running` job as orphaned whenever the lock is claimed | Rejected | A job run directly through `run-job` holds no lock and may still be alive |
| Suffix duplicate output names automatically | Rejected | The issue asks for rejection, and silent renames would hide the clash |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #211 | 2026-11-11 | Initial defect design |
