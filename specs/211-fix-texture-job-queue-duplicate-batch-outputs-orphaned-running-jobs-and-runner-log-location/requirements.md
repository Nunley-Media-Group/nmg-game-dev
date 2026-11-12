# Defect Report: The texture job queue overwrites duplicate batch outputs, strands orphaned running jobs, and writes runner output into one job's log

**Issue**: #211
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/143-make-texture-generation-work-from-the-plugin-root-and-queue-or-batch-texture-jobs/

## Reproduction

1. Submit a batch with two requests whose `name` (or, without a name, whose prompt) slugify to the same output name, through `python -m nmg_game_dev.texture generate --batch FILE` or `generate_textures(requests=...)`. Both write into `<output root>/<name>/`, and the later request overwrites the earlier one's images and manifest.
2. Kill the queue runner while a job is `running`, then start another texture job. The new runner replaces the stale lock, but the killed job's `status.json` stays `running` forever.
3. Start several texture jobs. The runner's output for every job goes to the `job.log` of the job whose `start` spawned it.

## Expected vs Actual

| | Description |
|---|-------------|
| **Expected** | A batch with a duplicate output name is refused before anything is queued or generated. A job whose runner died is marked failed, and the queue moves on. Runner output has its own log, and each `job.log` holds only that job's output. |
| **Actual** | Duplicate output names overwrite each other silently. An orphaned job reports `running` indefinitely. Runner output for every job lands in one unrelated job's `job.log`. |

## Acceptance Criteria

### AC1: Duplicate output names in a batch are rejected

**Given** a batch whose requests resolve to the same output name
**When** it is submitted through the CLI `--batch` or `generate_textures(requests=...)`
**Then** the whole batch is rejected with `texture.invalid_request` naming the duplicate output and the request indexes, before anything is queued or generated

### AC2: A job orphaned by a dead runner is marked failed

**Given** a job whose `status.json` says `running` but whose runner PID is no longer alive
**When** the next runner starts (stale-lock recovery)
**Then** that job is marked `failed` with a code and message stating the runner exited mid-job, and queued jobs after it still run in FIFO order

### AC3: The runner log has its own file

**Given** the queue runner processes several jobs
**When** its log is inspected
**Then** runner output is written to a runner log under the jobs root, and each job's `job.log` holds only that job's output

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | Batch validation rejects duplicate resolved output names with `texture.invalid_request` (indexes + name) | Must |
| FR2 | Stale-lock recovery marks a `running` job whose runner PID is dead as `failed` with a runner-exited error, then continues the FIFO queue | Must |
| FR3 | The queue runner logs to its own file under the jobs root, not a job's `job.log` | Must |
| FR4 | Unit tests cover FR1–FR3 with fakes (no model weights, no GPU) | Must |

## Out of Scope

- Duplicate output names across separate jobs or across a job and earlier output on disk.
- Cancelling, retrying, or reprioritizing queued jobs.
- Rotating or truncating `runner.log`.
- Changing the shape of `status.json` or the `get_texture_job` result.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #211 | 2026-11-11 | Initial defect report |
