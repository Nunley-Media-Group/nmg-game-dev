# Tasks: Keep a per-asset finalize record and logs in the consumer project and add a cheap up-to-date check

**Issue**: #247
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley

## Implementation Tasks

### T001: Add the records module

**File(s)**: `src/nmg_game_dev/pipeline/records.py`
**Type**: Create
**Depends**: none
**Acceptance**:
- FR1/FR2/FR3/FR9: `record_path`, `write_record`, and `check` exist as in design.md; the record has every field in design.md, is written atomically, and the logs directory is replaced as a whole
- FR6/AC9: `check` reads only the record and file metadata and does not import or touch the cache lock
- AC7/AC8: the check rule returns each reason in design.md

### T002: Write records from finalize jobs and add the batch skip option

**File(s)**: `src/nmg_game_dev/pipeline/jobs.py`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- AC1/AC2: `_run_single` writes the record and logs at `succeeded` and `failed`
- AC3: `_run_item` writes each item's record before the next item starts; fail-fast `skipped` items write nothing
- AC10/FR7: record failures add `finalize.record_not_written` and leave `state`, `result`, and `error` unchanged
- AC11/FR8: with `skip_up_to_date`, an item that passes the check gets state `up_to_date`, runs no step, keeps its record, and is counted under `up_to_date`; without it, behavior is unchanged
- A job that gives up waiting for the lock writes no record

### T003: Add the check CLI subcommand, the MCP tool, and the batch flag

**File(s)**: `src/nmg_game_dev/finalize/__main__.py`, `src/nmg_game_dev/finalize/mcp_tools.py`, `src/nmg_game_dev/finalize/service.py`, `mcp-servers/finalize/src/finalize_mcp/server.py`, `mcp-servers/finalize/tools.json`
**Type**: Modify
**Depends**: T001, T002
**Acceptance**:
- AC5/FR4: `check` prints the text line or `--json` object and exits 0, 1, or 2
- AC6/FR5: `check_finalized` returns the `assets` list for one asset or a list; both or neither form returns `finalize.invalid_request`
- AC11: `--skip-up-to-date` and `skip_up_to_date` reach the batch job; with one collection they return `finalize.invalid_request`
- `uv run python scripts/validate-mcp-tools.py` passes (`gate-mcp-schema`)

### T004: Git-ignore .nmg/ during onboarding

**File(s)**: `src/nmg_game_dev/onboard/gitignore.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- AC13/FR12: `ensure_gitignore_env` ensures `.nmg/` alongside `.env` and `<game>/.godot/`, and reports `unchanged` when all three are present

### T005: Document the record, check, and batch option

**File(s)**: `docs/mcp/finalize.md`, `skills/finalize-asset/SKILL.md`, `CHANGELOG.md`
**Type**: Modify
**Depends**: T002, T003, T004
**Acceptance**:
- AC12/FR11: `docs/mcp/finalize.md` has a section on the record (path, fields, logs, replacement), the check (CLI, MCP, rule, reasons, exit codes), the modification-time caveat, how it differs from the step cache, and `skip_up_to_date`; its tool table lists `check_finalized`, and its error table lists `finalize.record_not_written`
- `skills/finalize-asset/SKILL.md` tells the agent to call `check_finalized` before re-finalizing an asset and names the record location
- `CHANGELOG.md` `[Unreleased]` has an `### Added` bullet describing finalize records and the up-to-date check that ends with `(#247)`
- `claude plugin validate .` passes (`plugin.validate`)

### T006: Tests for records, the check, jobs, CLI, MCP, onboarding, and docs

**File(s)**: `tests/unit/pipeline/test_records.py`, `tests/unit/pipeline/test_jobs.py`, `tests/unit/pipeline/test_batch.py`, `tests/unit/test_finalize_cli.py`, `tests/unit/test_finalize_mcp_tools.py`, `tests/unit/onboard/test_gitignore.py`, `tests/unit/test_finalize_docs.py`, `tests/bdd/features/finalize_records.feature`, `tests/bdd/test_finalize_records_bdd.py`
**Type**: Create
**Depends**: T001, T002, T003, T004, T005
**Acceptance**:
- FR10: every test uses temporary directories, a temp `project.godot`, and the existing fake step runner; none starts Godot or Blender
- AC1–AC4: record fields, the log copies surviving deletion of the job directory, the per-item ordering, and replacement are asserted
- AC5–AC8: each reason, the text and JSON output, and exit codes 0, 1, and 2 are asserted
- AC9: the check succeeds while a lock file is held and leaves the directory tree byte-identical (snapshot of paths, sizes, and mtimes before and after)
- AC10: an unwritable `.nmg/finalize/` (a file in its place) and an unresolvable project each give the warning and an unchanged run state
- AC11: skip-up-to-date batches report `up_to_date` items, run no steps for them, and keep their records
- AC12 and AC13: the doc strings and the `.gitignore` line are asserted
- `tests/bdd/features/finalize_records.feature` carries SCN001–SCN013 from this spec's `feature.gherkin`, bound in `tests/bdd/test_finalize_records_bdd.py`
- `uv run pytest tests/unit tests/bdd -q` passes (`repository.tests`); `repository.lint`, `repository.format`, and `repository.types` pass

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #247 | 2026-11-18 | Initial feature tasks |
