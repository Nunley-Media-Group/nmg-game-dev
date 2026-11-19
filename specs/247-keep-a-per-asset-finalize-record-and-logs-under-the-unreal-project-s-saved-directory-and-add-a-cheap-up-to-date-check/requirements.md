# Requirements: Keep a per-asset finalize record and logs in the consumer project and add a cheap up-to-date check

**Issue**: #247
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley

## User Story

**As a** game developer running a long queue of finalize jobs into a Godot game project
**I want** finalize to keep each asset's last result and logs inside the consumer project, and to tell me cheaply whether an asset is already up to date
**So that** a queue runner can skip finished assets instead of re-importing them, and a failed run can still be diagnosed days later

## Background

Finalize job files live under `<cache_root>/jobs/<job_id>/` (`request.json`, `status.json`, `job.log`, `blender-<step>.log`). The cache root is per user and defaults to `~/.cache/nmg-game-dev`, and job directories are named by random job ids. Nothing finds the last run by asset name. A successful full run only marks the asset `finalized` in `docs/design/backlog.json`, with no time, result, or log. Learning whether an asset needs work means starting a finalize job, which takes the cache lock and hashes the asset in Blender.

This change writes a per-asset record and log copy inside the consumer project, at `<consumer>/.nmg/finalize/<Category>/<Name>.json`, where `<consumer>` is the parent of the directory holding `project.godot`. It adds a read-only up-to-date check as a CLI subcommand and an MCP tool, and an opt-in batch option that skips assets that pass the check.

## Acceptance Criteria

### AC1: A finished run writes a per-asset record in the consumer project

**Given** a finalize run for one collection whose Godot project resolves through `find_project(export_root)`
**When** the run reaches `succeeded` or `failed`
**Then** `<consumer>/.nmg/finalize/<Category>/<Name>.json` exists and holds `schema_version`, `category`, `collection`, `job_id`, `state`, `started_at`, `ended_at`, `nmg_game_dev_version`, `full_run`, `steps` (each with `step` and `cache_hit`), `source` (`blend` path and `mtime`, or `null`), `imported` (the `res://` paths of the imported variants and clips), `content_hash` (or `null`), `logs`, and `error` (`code`, `message`, `remediation`, or `null`)

### AC2: The run's logs are kept beside the record

**Given** the same run
**When** it finishes
**Then** `<consumer>/.nmg/finalize/<Category>/<Name>.logs/` holds a copy of `job.log` and every `blender-<step>.log` from the run's directory, and the record's `logs` names them
**And** the copies remain after the job directory under the cache root is deleted

### AC3: Each batch item gets its own record

**Given** a batch of several collections
**When** each item finishes
**Then** that item's record and logs are written before the next item starts
**And** an item skipped by fail-fast leaves its earlier record unchanged

### AC4: A new run replaces the last record

**Given** an asset that already has a record and logs
**When** it is finalized again
**Then** the record describes the latest run and `<Name>.logs/` holds only the latest run's logs

### AC5: The CLI answers "is this asset up to date?"

**Given** an asset with a record
**When** `python -m nmg_game_dev.finalize check --category Props --collection Crate` runs
**Then** it prints `Props/Crate: up to date` or `Props/Crate: not up to date (<reason>)`, or with `--json` an object with `up_to_date`, `reason`, and `record`
**And** it exits 0 when up to date and 1 when not

### AC6: The same check is an MCP tool

**Given** the finalize MCP server
**When** an agent calls `check_finalized` with one `category`/`collection` or an `assets` list
**Then** it returns `{"assets": [...]}` with, per asset, `category`, `collection`, `up_to_date`, `reason`, and `record` (`state`, `ended_at`, `error_code`, or `null` without a record)

### AC7: Up to date means a clean full run that is newer than the source

**Given** a record with `state: succeeded` and `full_run: true`
**And** its source `.blend` exists with a modification time no later than the record's `started_at`
**And** every `res://` path in `imported` exists under the Godot project with its `.import` file beside it
**When** the check runs
**Then** it reports `up_to_date: true` with reason `up_to_date`

### AC8: Every other case is not up to date, with a reason

**Given** the check
**When** there is no record, the record cannot be parsed, the last run failed, the last run was not a full run, the record has no source `.blend`, the `.blend` is missing, the `.blend` is newer than the run, an imported file or its `.import` is missing, or the Godot project cannot be resolved
**Then** it reports `up_to_date: false` with the reason `no_record`, `record_unreadable`, `last_run_failed`, `not_full_run`, `no_source_blend`, `source_missing`, `source_newer`, `import_missing`, or `project_missing` respectively

### AC9: The check is cheap and has no side effects

**Given** the check
**When** it runs, including while another finalize job holds the cache lock
**Then** it answers without starting Blender or Godot, without reading or taking the cache lock, and without writing any file

### AC10: Record writing never changes a run's result

**Given** a run whose Godot project cannot be resolved, or whose `.nmg/finalize/` directory cannot be written
**When** the run finishes
**Then** its `state`, `result`, and `error` are what they would be without records, and it carries a `finalize.record_not_written` warning that names the reason

### AC11: Batches can skip up-to-date assets

**Given** a batch run with `--skip-up-to-date` (CLI) or `skip_up_to_date: true` (MCP `finalize_asset` with `requests`)
**When** an item passes the AC7 check
**Then** the item's state is `up_to_date`, no step runs for it, its record is unchanged, and the batch result counts it under `up_to_date`
**And** without the option, every item runs as before

### AC12: The record and the check are documented

**Given** `docs/mcp/finalize.md` and `skills/finalize-asset/SKILL.md`
**When** a consumer builds a queue runner
**Then** the docs give the record's location and fields, the log copies, the check's CLI and MCP forms, its rule and reasons, the batch option, that a changed modification time without changed content reports not up to date while the step cache makes the rerun a full hit, and how the check differs from the step cache

### AC13: Onboarding ignores the records

**Given** `/onboard-consumer`
**When** its `gitignore_env` step runs
**Then** the consumer `.gitignore` contains `.nmg/`

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | Resolve `<consumer>` as `find_project(export_root).parent` and write the record at `<consumer>/.nmg/finalize/<Category>/<Name>.json` | Must |
| FR2 | Write the record at every terminal state of a single run and of each batch item, atomically (temporary file, then `os.replace`) | Must |
| FR3 | Copy the run's `job.log` and `blender-<step>.log` files into `<Name>.logs/`, replacing the previous run's logs | Must |
| FR4 | `python -m nmg_game_dev.finalize check` with `--category`, `--collection`, optional `--export-root`, and `--json`; exit 0 up to date, 1 not, 2 invalid invocation | Must |
| FR5 | MCP tool `check_finalized` taking one asset or an `assets` list | Must |
| FR6 | The check reads only the record and file metadata: no Blender, Godot, cache lock, or writes | Must |
| FR7 | A record that cannot be written adds a `finalize.record_not_written` warning and never fails the run | Must |
| FR8 | `--skip-up-to-date` / `skip_up_to_date` for batches, off by default, with item state `up_to_date` | Should |
| FR9 | The record stores the run's asset content hash when the job recorded one | Could |
| FR10 | Record writing, project resolution, and the check are tested with temporary directories and fakes, without Godot or Blender | Must |
| FR11 | `docs/mcp/finalize.md` and `skills/finalize-asset/SKILL.md` document the record, logs, check, and batch option | Must |
| FR12 | `/onboard-consumer` git-ignores `.nmg/` | Must |

## Out of Scope

- Changing the step cache, its keys, or its location
- Moving job directories out of the cache root
- A queue runner or scheduler inside nmg-game-dev
- Records for texture-gen, Meshy, `reduce_asset`, or `import_audio` jobs
- Verifying imported assets through Godot

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #247 | 2026-11-18 | Initial feature spec |
