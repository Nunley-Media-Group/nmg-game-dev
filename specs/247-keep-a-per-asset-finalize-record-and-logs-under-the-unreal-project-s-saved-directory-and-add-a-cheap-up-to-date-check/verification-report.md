# Verification Report: Per-asset finalize records and an up-to-date check

**Date**: 2026-11-19
**Issue**: #247
**Reviewer**: Claude (nmg-sdlc verify worker, gate phase)
**Scope**: Pre-merge gate on the merge-queue head (default branch integrated, version 0.38.0 prepared)

**Verification head**: 13631c5165d31df7d9364fb8a35b6603808fbd6e

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 4 |
| Security | 5 |
| Performance | 5 |
| Testability | 4 |
| Error Handling | 5 |
| **Overall** | 4.7 |

### Implementation Status: Pass
**Total Issues**: 0 above info (4 info notes from the review)

The review of source head `e06fb7a` passed with no findings above `info`. It covered every AC, FR, design path and consumer. The head that will merge is `13631c5`, which integrates `origin/main` (`b131f7d`) and prepares version 0.38.0. The pre-merge gate on that head passed. All 9 applicable required validations passed, and 2 did not apply. Coverage is complete: 11 validations declared, 11 recorded. The deterministic ceiling in `.nmg-sdlc/verification/247.json` is `null`, so no cap applies. Both defects from the previous failed gate (the changelog-section test and the header comment naming the retired engine) are fixed: `repository.tests` now reports 2651 passed, 24 skipped and 0 failed.

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

- Local verification: Pass
- PR evidence: Not required

---

## Acceptance Criteria Verification

Every row comes from the passed review record (`.nmg-sdlc/verification/247-review.md`, reviewed head `e06fb7a`, full mode). Each criterion was exercised through its real entry point: `jobs.run_job`, the CLI `main(argv)`, or the MCP tool functions. The tests replace only Blender and Godot with fakes. **No criterion's tests mock the path under test.**

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | A finished run writes a per-asset record | Pass | `pipeline/records.py` `write_record` via jobs `_record_run`; test_records.py; SCN001 |
| AC2 | Logs kept beside the record | Pass | `records._copy_logs` staging + `os.replace`; job-dir deletion test; SCN002 |
| AC3 | Each batch item gets its own record | Pass | jobs `_run_item`; test_batch.py record-order and fail-fast tests; SCN003 |
| AC4 | A new run replaces the last record | Pass | logs-dir replace + atomic record write; SCN004 |
| AC5 | CLI check | Pass | `finalize/__main__.py` `check` (text/--json, exit 0/1/2); test_finalize_cli.py; SCN005 |
| AC6 | MCP `check_finalized` | Pass | mcp_tools.py, server.py, tools.json; test_finalize_mcp_tools.py; SCN006 |
| AC7 | Up to date = clean full run newer than source | Pass | `records.check` ordered rule; prop and terrain round-trip tests; SCN007 |
| AC8 | Every other case not up to date, with reason | Pass | one test per reason + reachability test; SCN008 outline |
| AC9 | Check is cheap, no side effects | Pass | lock-held + tree snapshot test; SCN009 |
| AC10 | Record writing never changes a run's result | Pass | `finalize.record_not_written` warning; unwritable/unresolvable tests; probe for the failed-run path |
| AC11 | Batches can skip up-to-date assets | Pass | `skip_up_to_date` in CLI/MCP/service; single collection refused; SCN011 |
| AC12 | Record and check documented | Pass | docs/mcp/finalize.md section, SKILL.md; test_finalize_docs.py; SCN012 |
| AC13 | Onboarding ignores `.nmg/` | Pass | onboard/gitignore.py `RECORDS_LINE`; test_gitignore.py; SCN013 |

All 12 FRs (FR1-FR12), design paths DP1-DP8 and consumers C1-C7 also pass in the review record.

---

## Task Completion

| Task | Description | Status |
|------|-------------|--------|
| T001 | Records module | Complete |
| T002 | Records from jobs + batch skip | Complete |
| T003 | Check CLI, MCP tool, batch flag | Complete |
| T004 | Git-ignore `.nmg/` during onboarding | Complete |
| T005 | Documentation | Complete |
| T006 | Tests | Complete |

---

## Architecture Assessment

The scores come from the review lenses. Records live in their own module, `pipeline/records.py`. The CLI, the MCP tool and the batch runner call that module and do not repeat its logic (SOLID 4). The check reads only metadata (`stat`, `is_file`, `json.loads`). It takes no lock and writes nothing (Performance 5). Writes are atomic: a temp file plus `os.replace`, and a staged logs directory. A failed write becomes a warning and never changes the run's result (Error Handling 5). No secrets or new external surfaces are involved (Security 5). The tests drive the real entry points with fakes for Blender and Godot. Testability is 4 because no test covers the failed-run warning path; a review probe covered it instead (I2).

---

## Steering Doc Verification Gates

Every result is from `.nmg-sdlc/verification/247.json` at head `13631c5`, with a clean tree. The project declares no tiers, so every result records `tier: null` and `selection: null`. No heavy-pool slots were used.

| Gate | Status | Tier / Selection | Evidence |
|------|--------|------------------|----------|
| repository.tests | Pass | null / null | 2651 passed, 24 skipped in 630.94 s (`.nmg-sdlc/verification/247/repository.tests.log`) |
| repository.lint | Pass | null / null | `ruff check .` exited 0 |
| repository.format | Pass | null / null | `ruff format --check .` exited 0 |
| repository.types | Pass | null / null | `mypy src tests` exited 0 |
| gate-blender-headless | Pass | null / null | `scripts/run-blender-tests.sh` exited 0 |
| gate-godot-headless | Pass | null / null | `scripts/run-godot-tests.sh` exited 0 |
| gate-mcp-schema | Pass | null / null | `validate-mcp-tools.py` exited 0 (covers the `check_finalized` server/tools.json parity) |
| gate-shellcheck | Skipped (not applicable) | null / null | no `scripts/**.sh` changed |
| gate-ship-smoke | Skipped (not applicable) | null / null | no ship paths changed |
| plugin.validate | Pass | null / null | `claude plugin validate .` exited 0 |
| plugin.session-smoke | Pass | null / null | plugin loaded via `--plugin-dir`; nmg-game-dev:blender connected |

**Gate Summary**: 9/9 applicable passed, 0 failed, 0 incomplete; 2 not applicable. Coverage: declared 11, recorded 11, complete.

---

## Fixes Applied

None in this phase; the gate does not edit source. Implementation fixed the two defects from the previous gate (`28d3bd4`) in `e06fb7a`, and the passed review confirmed them.

## Remaining Issues

None above info. The info notes from the review:

- I1: With `skip_up_to_date`, the check judges the `.blend` named in the record, not the batch entry's `.blend`. This matches AC7 and is documented as a caveat in docs/mcp/finalize.md.
- I2: No test covers the `finalize.record_not_written` warning on a failed single run or a failed batch item. A one-off probe confirmed that path behaves correctly.
- I3: A hard kill between the log copy and the record write leaves the old record naming the new logs. The check does not read logs, so its answers are unaffected.
- I4: The stale failed report has been replaced by this report for the current head.

---

## Recommendation

**Ready to merge.** All applicable required gates pass on the exact head that will merge.
