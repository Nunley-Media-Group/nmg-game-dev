# Tasks: The texture job queue overwrites duplicate batch outputs, strands orphaned running jobs, and writes runner output into one job's log

**Issue**: #211
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/143-make-texture-generation-work-from-the-plugin-root-and-queue-or-batch-texture-jobs/

## Implementation Tasks

### T001: Reject duplicate output names in batch validation

**File(s)**: `src/nmg_game_dev/texture/generate.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- `validate_batch()` groups request indexes by `slugify(request.name or request.prompt)`. For each name shared by two or more requests, it adds `requests <i>, <j>[, …]: output name '<name>' is used more than once` (zero-based ascending indexes) to the failures. It raises one `texture.invalid_request` through `_invalid_batch()`, alongside any per-request failures (AC1, FR1).
- Batches with distinct output names validate as before.

### T002: Mark jobs orphaned by a dead runner as failed

**File(s)**: `src/nmg_game_dev/texture/jobs.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- `run_job()` writes `<job_dir>/runner.json` as `{"pid": <its PID>}` atomically, before its first `running` status (FR2).
- Each time `run_queue()` claims the lock, it checks every job left `running` before draining the queue. A job whose `runner.json` is missing or unreadable, or whose `pid` is not alive, is rewritten as `state: "failed"`, keeping its last `completed` and `total`. Its `error.code` is `texture.runner_exited`, the message states that the texture queue runner (with its PID, or `unknown`) exited while the job was running, and the remediation says to start the job again and names `<jobs root>/runner.log` (AC2, FR2).
- A `running` job whose runner PID is alive is left alone. Queued jobs then run oldest-first as before (AC2).
- The keys of `status.json` are unchanged.

### T003: Give the queue runner its own log

**File(s)**: `src/nmg_game_dev/texture/jobs.py`
**Type**: Modify
**Depends**: T002
**Acceptance**:
- `start()` passes `<jobs root>/runner.log`, opened in append mode, as the detached runner's stdout and stderr, never a job's `job.log` (AC3, FR3).
- `run_queue()` appends `runner <pid> started`, `job <id> running`, `job <id> <final state>`, `job <id> marked failed: runner <pid> exited`, and `runner <pid> idle` lines to `runner.log` (AC3).
- `run_job()` appends only its own `job <id> started` and `job <id> <final state>` lines, plus a crash traceback when one occurs, to `<job_dir>/job.log` (AC3).

### T004: Document the duplicate-name rule, the orphan code, and the runner log

**File(s)**: `docs/onboarding/texture-models.md`
**Type**: Modify
**Depends**: T001, T002, T003
**Acceptance**:
- The batch-validation paragraph says that requests resolving to the same output name are refused with `texture.invalid_request`, naming the name and the indexes (AC1).
- The queue paragraph says that a job left `running` by a runner that exited is marked `failed` with `texture.runner_exited` when the next runner starts. It also says that the runner logs to `<output root>/.jobs/runner.log` and each job's `job.log` holds only that job's output (AC2, AC3).

### T005: Unit tests with fakes for AC1–AC3

**File(s)**: `tests/unit/texture/test_generate.py`, `tests/unit/texture/test_cli.py`, `tests/unit/texture/test_jobs.py`
**Type**: Modify
**Depends**: T001, T002, T003
**Acceptance**:
- AC1 (`test_generate.py`): `validate_batch` on requests named `burlap`, `stone`, and `Burlap` raises `texture.invalid_request` whose message contains `requests 0, 2: output name 'burlap' is used more than once`. `run_batch` on that batch raises the same error with the fake spawn never called and no `burlap` folder created.
- AC1 (`test_cli.py`): `generate --batch` on that batch file exits 1 with `texture.invalid_request` naming `'burlap'` and `requests 0, 2`.
- AC1 (`test_jobs.py`): `jobs.start` on that batch raises `texture.invalid_request`, creates no job directory, and the `spawned` fixture records no runner spawn.
- AC2 (`test_jobs.py`): three jobs are started with the `spawned` fixture. The first is set to `running` with `runner.json` PID `999999` (dead), and a stale lock holds PID `999999`. `run_queue` with `fake_spawn` leaves the first job `failed` with `error.code == "texture.runner_exited"` and a message naming PID 999999. The other two are `succeeded`, and the fake worker log shows their backends started in submission order.
- AC2 (`test_jobs.py`): a `running` job whose `runner.json` holds the test process's own (live) PID is left `running`. A `running` job with no `runner.json` is marked `texture.runner_exited` with PID `unknown`.
- AC2 (`test_jobs.py`): after `run_job` runs, `runner.json` in its directory holds the PID of the process that ran it.
- AC3 (`test_jobs.py`): the `spawned` fixture records that `start` passed a stdout handle for `<jobs root>/runner.log`. After `run_queue` runs two queued jobs, `runner.log` names both job ids. Each job's `job.log` names only its own id and never the other's.
- No test loads model weights, uses the GPU, or starts Blender, Unreal, or a real worker process. Passes under `repository.tests` (`uv run pytest tests/unit tests/bdd -q`), and the changed files pass `repository.lint`, `repository.format`, and `repository.types`.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #211 | 2026-11-11 | Initial defect tasks |
