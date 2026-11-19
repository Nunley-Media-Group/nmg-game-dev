# Design: Keep a per-asset finalize record and logs in the consumer project and add a cheap up-to-date check

**Issue**: #247
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley

## Overview

A new module, `src/nmg_game_dev/pipeline/records.py`, owns record paths, record writing, log copying, and the up-to-date check. `pipeline/jobs.py` calls `write_record` at each terminal state, the same way it calls `_mark_backlog`: errors become warnings. The CLI, the MCP layer, and the batch runner call `check`. Nothing changes in the step cache or the job directory layout.

## Architecture

```text
jobs._run_single / jobs._run_item (terminal)
   └─ records.write_record(request, steps, run_dir, job_id, started_at, ended_at, state, result, error)
         ├─ consumer = find_project(request.export_root).parent
         ├─ <consumer>/.nmg/finalize/<Category>/<Name>.logs/   (copy job.log + blender-*.log; replace dir)
         └─ <consumer>/.nmg/finalize/<Category>/<Name>.json    (tmp + os.replace)
       on OSError/PipelineError → warning finalize.record_not_written (run unchanged)

finalize CLI `check` ─┐
MCP check_finalized ──┼─► records.check(category, collection, export_root) ─► CheckResult
jobs._run_batch (skip_up_to_date) ┘
```

## API / Interface Changes

| Interface | Input | Output / Error | Behavior |
|-----------|-------|----------------|----------|
| `records.record_path(export_root: Path, category: str, collection: str) -> Path` | export root, names | path | `find_project(export_root).parent / ".nmg/finalize" / category / f"{collection}.json"`; raises `PipelineError` `import_godot.project_missing` |
| `records.write_record(...) -> list[dict[str, str]]` | request, steps, run dir, job id, start/end times, state, `FinalizeResult \| None`, error dict | warnings (empty on success) | Writes logs, then the record. Any `OSError` or `PipelineError` returns one `finalize.record_not_written` warning with the reason in `message` and remediation `Check that <consumer>/.nmg/finalize is writable and that export_root is inside the Godot project.` |
| `records.check(category: str, collection: str, export_root: Path) -> CheckResult` | names, export root | `CheckResult(up_to_date: bool, reason: str, record: dict \| None)` | Applies the rule below; never raises for missing or bad data |
| `python -m nmg_game_dev.finalize check --category C --collection N [--export-root P] [--json]` | — | text line, or JSON `{"category", "collection", "up_to_date", "reason", "record"}`; exit 0 / 1 / 2 | Default `export_root` as for finalize (`<project>/game/assets`) |
| MCP `check_finalized(category=None, collection=None, assets=None, export_root=None)` | one asset or `assets: [{category, collection}]` | `{"assets": [{category, collection, up_to_date, reason, record: {state, ended_at, error_code} \| None}]}`; both or neither form → `finalize.invalid_request` error | Registered in `server.py` and `tools.json` |
| `finalize_asset(..., skip_up_to_date: bool = False)` and CLI `--skip-up-to-date` | batch only (with `requests`, `--batch`, or several `--collection`); with one collection → `finalize.invalid_request` | batch items may have state `up_to_date`; `result.batch.up_to_date` count | Stored as `skip_up_to_date` in `job.json` |

### Record (`schema_version: 1`)

```json
{
  "schema_version": 1,
  "category": "Props",
  "collection": "Crate",
  "job_id": "…",
  "state": "succeeded",
  "started_at": "2026-11-18T10:00:00.000000+00:00",
  "ended_at": "2026-11-18T10:01:12.000000+00:00",
  "nmg_game_dev_version": "0.27.0",
  "full_run": true,
  "steps": [{"step": "validate", "cache_hit": false}],
  "source": {"blend": "/abs/path/Crate.blend", "mtime": 1763460000.0},
  "imported": ["res://assets/Props/Crate/Desktop/Crate.glb", "res://assets/Props/Crate/Mobile/Crate.glb"],
  "content_hash": "…",
  "logs": {"job": "Crate.logs/job.log", "steps": {"bake": "Crate.logs/blender-bake.log"}},
  "error": null
}
```

- `full_run` is `steps == STEP_ORDER`. `source` is `null` when the request has no `blend`. `source.mtime` is read at run start.
- `imported` holds `desktop_resource_path`, `mobile_resource_path`, and each `animations` clip `asset_path`, when present.
- `content_hash` is read from the run directory's `hash.json` when it exists, otherwise `null`.
- Log paths are relative to the record's directory. Logs are copied to a temporary sibling directory, which then replaces `<Name>.logs/`.
- `started_at` is captured when the single run or batch item begins. A job that gives up waiting for the cache lock never calls `write_record`.

### Check rule (first match wins)

1. `export_root` resolves to no Godot project → `project_missing`
2. No record file → `no_record`
3. JSON or schema invalid → `record_unreadable`
4. `state != "succeeded"` → `last_run_failed`
5. `full_run` false → `not_full_run`
6. `source` null → `no_source_blend`
7. `.blend` missing → `source_missing`
8. `.blend` mtime > `started_at` → `source_newer`
9. Any `imported` path (under the project directory) or its `.import` missing → `import_missing`
10. Otherwise → `up_to_date`

The check uses `Path.stat`/`is_file` and `json.loads` only. It never imports the cache-lock code.

### jobs.py changes

- `_run_single` and `_run_item` record a UTC start time, then call `write_record` after setting the terminal state. The returned warnings go to `result.warnings` on success, or to `current["warnings"]` / `item["warnings"]` on failure.
- `_run_batch`, when `job["skip_up_to_date"]` is true, calls `records.check` before each item. When the check is `up_to_date`, it sets `item["state"] = "up_to_date"` and runs nothing. `_ITEM_DONE_STATES` gains `up_to_date`, and the batch result adds an `up_to_date` count. The batch succeeds when `failed == 0` and `skipped == 0`.

### Onboarding

`onboard/gitignore.py::ensure_gitignore_env` adds `.nmg/` to its wanted lines.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Keep the last N runs' logs | Rejected | The issue's goal is the latest result; one replaceable directory is simplest and bounded |
| Compare the content hash in the check | Rejected | Hashing needs Blender; the record stores the hash for a later stricter check (FR9) |
| Treat open-session runs as up to date | Rejected | Without a saved `.blend` the check cannot tell whether the source changed |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #247 | 2026-11-18 | Initial feature design |
