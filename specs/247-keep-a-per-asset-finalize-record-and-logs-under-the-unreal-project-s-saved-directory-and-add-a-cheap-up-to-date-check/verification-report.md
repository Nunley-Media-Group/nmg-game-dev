# Verification Report: Per-asset finalize records and an up-to-date check

**Date**: 2026-11-19
**Issue**: #247
**Reviewer**: Claude (nmg-sdlc verify worker, gate phase)
**Scope**: Pre-merge gate on the merge-queue head (default branch integrated, version 0.37.0 prepared)

**Verification head**: 28d3bd44955e209702204a894733648d0e87592f

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 4 |
| Architecture (SOLID) | 4 |
| Security | 5 |
| Performance | 5 |
| Testability | 3 |
| Error Handling | 5 |
| **Overall** | 4.3 |

### Implementation Status: Fail
**Total Issues**: 2 (both cause the required `repository.tests` gate to fail)

The review of source head `0851463` passed with no findings above `info`. The pre-merge gate on the version-prepared head `28d3bd4` failed. `repository.tests` failed with 3 failed, 2620 passed and 24 skipped. Because a required local validation failed, `plugin.session-smoke` was deferred and is recorded as incomplete. Coverage is complete: 11 validations declared, 11 recorded. The deterministic ceiling from `.nmg-sdlc/verification/247.json` is `Incomplete`. The failed required result caps the status at **Fail**.

---

## Issue Scope

- Active issue: #247
- Spec: `specs/247-keep-a-per-asset-finalize-record-and-logs-under-the-unreal-project-s-saved-directory-and-add-a-cheap-up-to-date-check`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1-AC13]; FR [FR1-FR12]; tasks [T001-T006]; scenarios [SCN001-SCN013]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":247,"specPath":"specs/247-keep-a-per-asset-finalize-record-and-logs-under-the-unreal-project-s-saved-directory-and-add-a-cheap-up-to-date-check","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6","AC7","AC8","AC9","AC10","AC11","AC12","AC13"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6","FR7","FR8","FR9","FR10","FR11","FR12"],"tasks":["T001","T002","T003","T004","T005","T006"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006","SCN007","SCN008","SCN009","SCN010","SCN011","SCN012","SCN013"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Not complete (repository.tests failed)
- PR evidence: Not required

---

## Acceptance Criteria Verification

All rows come from the passed review record (`.nmg-sdlc/verification/247-review.md`, reviewed head `0851463`). No criterion's tests mock the path under test.

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | A finished run writes a per-asset record | Pass | `src/nmg_game_dev/pipeline/records.py` record write; jobs.py `_record_run`; test_records.py, SCN001 |
| AC2 | Logs kept beside the record | Pass | records.py staged copy + `os.replace`; test_records.py, SCN002 |
| AC3 | Each batch item gets its own record | Pass | jobs.py `_run_item`; test_batch.py, SCN003 |
| AC4 | A new run replaces the last record | Pass | records.py logs-dir replace; test_records.py, SCN004 |
| AC5 | CLI check | Pass | `finalize/__main__.py` `check`; test_finalize_cli.py, SCN005 |
| AC6 | MCP `check_finalized` | Pass | mcp_tools.py, server.py, tools.json; test_finalize_mcp_tools.py, SCN006 |
| AC7 | Up to date = clean full run newer than source | Pass | records.py `check` with native-resource sidecar exemption; prop and terrain round-trip tests |
| AC8 | Every other case not up to date, with reason | Pass | records.py ordered rule; SCN008 outline |
| AC9 | Check is cheap, no side effects | Pass | test_records.py lock + tree snapshot; SCN009 |
| AC10 | Record writing never changes a run's result | Pass | `finalize.record_not_written` warning; SCN010 |
| AC11 | Batches can skip up-to-date assets | Pass | test_batch.py `skip_up_to_date` |
| AC12 | Record and check documented | Partial at gate | docs/mcp/finalize.md and SKILL.md are correct, but `test_the_changelog_unreleased_section_has_the_records_bullet` fails after version preparation (see Remaining Issues) |
| AC13 | Onboarding ignores `.nmg/` | Pass | onboard/gitignore.py; test_gitignore.py; onboarding docs |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Records module | Complete | |
| T002 | Records from jobs + batch skip | Complete | |
| T003 | Check CLI, MCP tool, batch flag | Complete | |
| T004 | Git-ignore `.nmg/` during onboarding | Complete | |
| T005 | Documentation | Complete | |
| T006 | Tests | Incomplete | Two new test artifacts fail on the merge head (see Remaining Issues) |

---

## Architecture Assessment

Scores come from the review lenses. Records live in their own module (`pipeline/records.py`), and the CLI, MCP and batch layers call that module without duplicating its logic. The check reads metadata only. Writes are atomic. Write failures turn into warnings instead of changing the run result. Testability scores 3 because the two failures below are test artifacts that break under normal delivery: one depends on changelog layout before the release, and one names the retired engine.

---

## Steering Doc Verification Gates

| Gate | Status | Tier / Selection | Evidence |
|------|--------|------------------|----------|
| repository.tests | **Fail** | null / null | 3 failed, 2620 passed, 24 skipped (`.nmg-sdlc/verification/247/repository.tests.log`) |
| repository.lint | Pass | null / null | ruff check clean |
| repository.format | Pass | null / null | ruff format --check clean |
| repository.types | Pass | null / null | mypy src tests clean |
| gate-blender-headless | Pass | null / null | scripts/run-blender-tests.sh |
| gate-godot-headless | Pass | null / null | scripts/run-godot-tests.sh |
| gate-mcp-schema | Pass | null / null | validate-mcp-tools.py |
| gate-shellcheck | Skipped (not applicable) | null / null | no `scripts/**.sh` changed |
| gate-ship-smoke | Skipped (not applicable) | null / null | no ship paths changed |
| plugin.validate | Pass | null / null | claude plugin validate . |
| plugin.session-smoke | Incomplete | null / null | deferred until required local validations pass |

**Gate Summary**: 7/9 applicable passed, 1 failed, 1 incomplete; 2 not applicable.

---

## Fixes Applied

None. The gate phase does not edit source.

## Remaining Issues

### High Priority

| Field | Value |
|-------|-------|
| **Severity** | High |
| **Category** | Testing |
| **Location** | `tests/unit/test_finalize_docs.py:251-256` |
| **Issue** | `test_the_changelog_unreleased_section_has_the_records_bullet` requires the #247 bullet under `## [Unreleased]`. Version preparation moved that bullet to `## [0.37.0] - 2026-11-19`, which leaves `[Unreleased]` empty, so the test fails on the head that will merge. |
| **Impact** | The required repository.tests gate fails, and the test would fail on main after any release. |
| **Fix** | Find the #247 bullet in any section of the changelog (`[Unreleased]` or a released version) instead of only in `[Unreleased]`. |

| Field | Value |
|-------|-------|
| **Severity** | High |
| **Category** | Testing |
| **Location** | `tests/bdd/features/finalize_records.feature:2` |
| **Issue** | The header comment `# Generated from: specs/247-keep-a-per-asset-finalize-record-and-logs-under-the-unreal-project-...` contains the retired engine's name, so `tests/unit/test_no_unreal_references.py::test_no_tracked_file_references_the_retired_engine` and `tests/bdd/test_godot_engine_bdd.py::test_scn014_the_retired_engine_is_gone` fail. |
| **Impact** | The required repository.tests gate fails. |
| **Fix** | Shorten the header comment so it no longer names the engine, for example `# Generated from: specs/247-*/feature.gherkin` or the issue number alone. Do not add a skip to the retired-engine scan. |

### Low Priority

- I1 (info, from review): `check()` judges against the source `.blend` named in the record, not the batch entry's `.blend`. This is documented as a caveat in docs/mcp/finalize.md.

---

## Recommendation

**Needs fixes.** Repair the two test defects above, then run the full registered gate again on the new head.
