# Verification Report: Detect and repair one-edge twist seams so geometry.normals settles

**Date**: 2026-11-19
**Issue**: #243
**Reviewer**: Claude (nmg-sdlc verify worker, gate phase)
**Scope**: Implementation verification against spec
**Verification head**: f2275466667751417085677c21775748414cd5b8

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 5 |
| Security | 5 |
| Performance | 4 |
| Testability | 4 |
| Error Handling | 5 |
| **Overall** | 4.7 |

### Implementation Status: Pass
**Total Issues**: 3 (all `info`; none above info)

The review (full mode, three lenses) passed with no finding above `info`. This gate ran the registered pre-merge validations once against the merge-queue head with the default branch integrated and the version prepared. Every applicable required validation passed and coverage is complete (11 declared, 11 recorded).

Deterministic steering artifact: `.nmg-sdlc/verification/243.json`. Ceiling: none. Coverage: `declared: 11`, `recorded: 11`, `complete: true`, nothing missing, duplicated or unknown. Identity: head `f2275466667751417085677c21775748414cd5b8`, clean tree.

---

## Issue Scope

- Active issue: #243
- Spec: `specs/243-detect-and-repair-one-edge-twist-seams-so-geometry-normals-settles`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1, AC2, AC3, AC4, AC5, AC6]; FR [FR1, FR2, FR3, FR4, FR5, FR6]; tasks [T001, T002, T003, T004, T005]; scenarios [SCN001, SCN002, SCN003, SCN004, SCN005, SCN006]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":243,"specPath":"specs/243-detect-and-repair-one-edge-twist-seams-so-geometry-normals-settles","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6"],"tasks":["T001","T002","T003","T004","T005"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Acceptance Criteria Verification

The evidence comes from the review record `.nmg-sdlc/verification/243-review.json`. Every criterion is exercised through its real entry point (`real_entry_point`). **No criterion's tests mock the path under test.**

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Cleanup repairs a twist seam with a minimal deletion | Pass | `variants_core/meshes.py` `_settle_normals` deletes the faces linked to `twist_seam_edges` before `normal_violations` runs; `tests/blender/test_twist_seams.py` SCN001 cleans `klein(32,3)` and checks that exactly the 6 seam faces are removed |
| AC2 | The repaired mesh is stable | Pass | SCN002 runs three more clean + `geometry_findings` passes: the snapshot does not change and no finding appears |
| AC3 | The validator names the seam | Pass | `contract_core/geometry.py` emits `geometry.twist_seam` with the seam-edge count and edge-midpoint samples; SCN003 asserts count 5 and no `geometry.normals` |
| AC4 | The repair is deterministic | Pass | SCN004 compares the positions, polygons and normals of two cleaned copies |
| AC5 | Meshes without a twist seam are unaffected | Pass | SCN005: a quad, an inside-out cube (6 flagged before cleanup) and the crate all report `twist_repair` faces 0 |
| AC6 | Cleanup reports the twist repair | Pass | `variants_core/cleanup.py` reports `twist_repair` `{faces, edges, samples}` in world space; SCN006 drives `cleanup_desktop` at a non-identity transform |

| FR | Status | Evidence |
|----|--------|----------|
| FR1 | Pass | `meshes.py` settle loop: twist seam deletion, then the loose-geometry pass, repeated until no seam or flagged face is left |
| FR2 | Pass | `normal_violations` returns `(faces, seam_edges)`; `geometry_findings` reports `geometry.twist_seam`; `report.py` adds its remediation |
| FR3 | Pass | Deleting flagged faces runs only when no seam edge exists; `test_clean_normals.py` SCN004 checks each deletion pass |
| FR4 | Pass | Shared `tests/blender/normals_fixtures.py` `klein()` builds the fixture; SCN001-SCN006 exist and pass |
| FR5 | Pass | `finalize_core/steps.py` passes `cleanup['objects']` (now including `twist_repair`) through to `Desktop.objects` |
| FR6 | Pass | `docs/asset-contract.md`, `docs/skills/model-asset.md` and `skills/model-asset/SKILL.md` document the rule; `tests/unit/test_geometry_rule_docs.py` checks that |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Detect and report twist seams in the contract check | Complete | `contract_core/geometry.py`, `contract_core/report.py` |
| T002 | Repair twist seams in clean_mesh | Complete | `variants_core/meshes.py` |
| T003 | Report twist repair from Desktop cleanup | Complete | `variants_core/cleanup.py` |
| T004 | Document geometry.twist_seam | Complete | docs, skill, unit doc tests |
| T005 | Add regression coverage | Complete | `tests/blender/test_twist_seams.py`, `normals_fixtures.py`, `test_clean_normals.py` |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 5 | Detection (`twist_seam_edges`) is in contract_core and repair is in variants_core |
| Open/Closed | 5 | The new rule is added to `RULES`; the change to the return type is additive for callers that ignore the value |
| Liskov Substitution | 5 | N/A beyond the unchanged `clean_mesh` contract |
| Interface Segregation | 5 | The `twist_repair` report is a small, separate per-object dict |
| Dependency Inversion | 5 | The cleanup consumes the shared contract_core detector instead of duplicating it |

### Layer Separation

Headless-safe cores remain the only place that holds the logic. The operators and the finalize step pass the results through without adding logic.

### Dependency Flow

`variants_core` → `contract_core` (existing direction). All consumers were checked (rows CON1–CON8 in the review record).

---

## Security Assessment

- [x] Authentication: N/A
- [x] Authorization: N/A
- [x] Input validation: mesh-only input; empty and open islands are handled (DP3)
- [x] Injection prevention: N/A
- [x] Data protection: N/A

## Performance Assessment

- [x] Async patterns: N/A (bmesh, synchronous)
- [x] Caching: N/A
- [x] Resource management: the settle loop ends because each pass deletes at least one face (DP4)
- [x] Query optimization: seam detection is linear in the number of edges per pass. The pass repeats a bounded number of times.

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1 | Yes (SCN001) | Yes | Yes |
| AC2 | Yes (SCN002) | Yes | Yes |
| AC3 | Yes (SCN003) | Yes | Yes |
| AC4 | Yes (SCN004) | Yes | Yes |
| AC5 | Yes (SCN005) | Yes | Yes |
| AC6 | Yes (SCN006) | Yes | Yes |

### Coverage Summary

- Feature files: 6 scenarios in `specs/243-.../feature.gherkin`, each implemented as a headless Blender test in `tests/blender/test_twist_seams.py`
- Step definitions: Implemented (Blender headless tests per steering)
- Unit tests: `tests/unit/test_geometry_rule_docs.py` (+2), `tests/unit/test_plugin_session_smoke.py` (extended)

---

## Steering Doc Verification Gates

Tier: none of the validations declare a tier (`tier: null`, `selection: null`), so every applicable required validation ran in full. No validation is marked heavy.

| Gate | Status | Evidence |
|------|--------|----------|
| repository.tests | Pass | `uv run pytest tests/unit tests/bdd -q` exited 0 |
| repository.lint | Pass | `uv run ruff check .` exited 0 |
| repository.format | Pass | `uv run ruff format --check .` exited 0 |
| repository.types | Pass | `uv run mypy src tests` exited 0 |
| gate-blender-headless | Pass | `scripts/run-blender-tests.sh` exited 0 |
| gate-godot-headless | Pass | `scripts/run-godot-tests.sh` exited 0 (applicable through the integrated default-branch paths) |
| gate-mcp-schema | Not applicable | No `mcp-servers/**` path changed; recorded as skipped |
| gate-shellcheck | Not applicable | No `scripts/**.sh` path changed; recorded as skipped |
| gate-ship-smoke | Not applicable | No ship paths changed; recorded as skipped |
| plugin.validate | Pass | `claude plugin validate .` exited 0 |
| plugin.session-smoke | Pass | plugin loaded via `--plugin-dir`; `nmg-game-dev:blender` connected |

**Gate Summary**: 8/8 applicable gates passed, 0 failed, 0 incomplete (3 not applicable). Coverage complete (11/11 recorded).

---

## Fixes Applied

| Severity | Category | Location | Original Issue | Fix Applied | Routing |
|----------|----------|----------|----------------|-------------|---------|
| — | — | — | None in this gate phase | — | — |

## Remaining Issues

### Critical Issues
None.

### High Priority
None.

### Medium Priority
None.

### Low Priority (info only)

| Field | Value |
|-------|-------|
| **F1** (info, failure-paths) | Cleanup also repairs open non-orientable sheets (for example a Mobius strip) that the validator does not report as `twist_seam`. This is consistent with FR1 and Out of Scope. `variants_core/meshes.py` |
| **F2** (info, test-quality) | No test asserts `twist_repair` inside the finalize variants step output. The value passes through by reference from `cleanup_desktop`, which SCN006 covers. `tests/blender/test_twist_seams.py` |
| **F3** (info, failure-paths) | The plugin.session-smoke reprompt heuristic (`\bto navigate\b`) could suppress a reprompt on another screen. It would fail as `missing`, not as a false pass. `steering/extensions/plugin-session-smoke.mjs` |

---

## Positive Observations

- Each fixture's expected result is computed independently on a recalculated copy, and the fixed counts (6 and 5) pin the minimal deletion.
- The determinism test compares full mesh state, not only face counts.

## Recommendations Summary

### Before PR (Must)
- None.

### Long Term (Could)
- [ ] Add a finalize-level assertion for `twist_repair` pass-through (F2).

---

## Recommendation

**Ready for PR**

The review passed with only info notes. Every applicable registered pre-merge validation passed at `f2275466667751417085677c21775748414cd5b8` with complete coverage.
