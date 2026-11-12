# Verification Report: geometry.normals rejects correctly facing open surfaces

**Date**: 2026-11-11
**Issue**: #144
**Reviewer**: Claude (nmg-sdlc architecture-reviewer, verify stage)
**Scope**: Defect-fix verification against the approved spec

**Verification head**: a9b9a6f63280dbec83b1e00558e4e68f0be5940a

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 5 |
| Security | 5 |
| Performance | 4 |
| Testability | 5 |
| Error Handling | 5 |
| **Overall** | 4.8 |

### Implementation Status: Pass
**Change type**: defect fix
**Total Issues**: 0 blocking, 2 low-severity observations (no action required)

`geometry.normals` now judges each edge-connected island on its own: open islands are checked only for consistent winding (minority count), closed islands keep the outward recalculation, scoped to the island. All 8 acceptance criteria are met, every registered validation that applies passed at the verification head, and the reported defect no longer reproduces.

---

## Issue Scope

- Active issue: #144
- Spec: `specs/144-fix-geometry-normals-rejecting-correctly-facing-open-surfaces-on-environment-pieces`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1–AC8]; FR [FR1–FR8]; tasks [T001–T004]; scenarios [SCN001–SCN008]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":144,"specPath":"specs/144-fix-geometry-normals-rejecting-correctly-facing-open-surfaces-on-environment-pieces","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6","AC7","AC8"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6","FR7","FR8"],"tasks":["T001","T002","T003","T004"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006","SCN007","SCN008"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

- Artifact: `.nmg-sdlc/verification/144.json` (runner `sdlc-verify-steering.mjs`, controller run `3f44abd9-80aa-4372-a332-17191813f1e1`)
- Identity: head `a9b9a6f63280dbec83b1e00558e4e68f0be5940a`, clean tree, steering `sha256:795f9897…c0e4`, spec `sha256:4ca5853c…3473`
- Coverage: declared 11, recorded 11, complete `true`, no missing, duplicate, or unknown ids
- Ceiling: none (`ok: true`)

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | A correctly facing single open quad passes wherever it sits | Pass | `contract_core/geometry.py` `_normal_violations` → `_winding_violations` (no outside comparison); `tests/blender/test_geometry_normals.py` SCN001: 500 axis-aligned, 500 tilted seeded placements, and the issue quad |
| AC2 | A consistently wound open sheet passes regardless of facing | Pass | SCN002: floor plus back wall (facing room and facing away) and welded 8×8 ground sheet (up and down) |
| AC3 | Inconsistent winding inside an open sheet is still reported | Pass | SCN003: reversed wall, interior grid cell, and corner grid cell each give count 1 |
| AC4 | Closed islands still face outward | Pass | `_outward_violations` runs `recalc_face_normals` on the island; SCN004: each of 6 single flipped faces gives 1, inside-out box gives 6 |
| AC5 | Islands are judged independently | Pass | `_islands` flood fill across shared edges; SCN005: correct box + previously-flagged floor quad + box with one flipped face gives exactly 1 |
| AC6 | Welded touching closed primitives pass | Pass | SCN006: vertex, edge, partial-face, partial-face-shared-edge cases plus 200 seeded welded arrangements |
| AC7 | Remediation text fits open surfaces | Pass | `contract_core/report.py` `RULES["geometry.normals"]` is design.md's text; SCN007 checks it and that the finding carries it |
| AC8 | The authoring rule is documented | Pass | `docs/asset-contract.md` §3, `skills/model-asset/SKILL.md` "Geometry rules for environment_piece", `docs/skills/model-asset.md`; `tests/unit/test_geometry_rule_docs.py` (SCN008) |

### Reproduction check (defect path)

Re-ran the reproduction in headless background Blender 5.2 (no live editor), comparing the pre-fix whole-mesh `_flipped_faces` logic with the new `_normal_violations` on identical meshes:

| Case | Pre-fix count | Post-fix count |
|------|---------------|----------------|
| 2,000 random upward floor quads within ±10 m | 434 / 2,000 flagged | 0 / 2,000 flagged |
| Floor + back wall facing into the room | 2 | 0 |
| Issue quad (3.37, -2.11, 0.4)–(7.9, 1.63, 0.4) | 0 (this exact placement happened not to trip) | 0 |

The bug no longer reproduces. The test suite pins a placement the pre-fix code did flag (`FLAGGED_FLOOR`) so SCN005 would fail against the old code.

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Judge normals per island | Complete | `_islands`, `_winding_violations`, `_walk_direction`, `_loop_on_edge`, `_outward_violations`; rule id, target, message unchanged; bmesh still freed in `finally` |
| T002 | Update the geometry.normals remediation | Complete | Text matches design.md verbatim |
| T003 | Add behavioral regression coverage | Complete | `tests/blender/test_geometry_normals.py` (SCN001–SCN007 and the two-caller FR5 test) |
| T004 | Document the environment-piece authoring rule | Complete | Three documents updated; §6 budget table unchanged; `tests/unit/test_geometry_rule_docs.py` |

---

## Architecture Assessment (defect path: blast radius)

- **Other callers sharing the path**: `contract_core/validate.py` (`validate_asset`: finalize validate step, export pre-check, `nmggamedev.validate_contract`) and `inspect_core/spatial.py` (`inspect_asset` per-part `geometry`). Neither caller changed; the FR5 test exercises both with a Crate plus a floor quad.
- **Public contract change**: none. `geometry_findings(name, mesh)` signature, return shape, rule id, target, and message wording are unchanged. Only the remediation string changed, per AC7.
- **Silent data changes**: none. The check operates on the caller's bmesh copy; `recalc_face_normals` now mutates only that copy's closed islands, and the copy is freed. The scene is never touched. Closed islands produce the same counts as before; open islands can only lose false positives, apart from inconsistent winding, which is still reported.
- **Minimal-change check**: `git diff origin/main...HEAD` touches only the files listed in the spec plus the deliver-stage version files (`VERSION`, `CHANGELOG.md`, `.claude-plugin/plugin.json`, `blender_manifest.toml`, `nmg-game-dev.uplugin`). No unrelated refactors.

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 5 | Island grouping, winding, and outward checks are separate small helpers |
| Open/Closed | 5 | Change contained behind `geometry_findings` |
| Liskov Substitution | 5 | N/A, no type hierarchies |
| Interface Segregation | 5 | Callers see the same single function |
| Dependency Inversion | 5 | Pure bmesh logic on a caller-owned copy |

### Security, Performance, Error Handling

- Security: no input from untrusted sources, no I/O, no new dependencies.
- Performance: island flood fill and winding propagation are linear in faces and edges, in Python. One `recalc_face_normals` call per closed island instead of one per mesh. Acceptable for contract validation; see the low-severity observation below.
- Error handling: no new failure paths; the existing `try/finally: bm.free()` still guarantees the bmesh is released.

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps / Tests | Passes |
|---------------------|-------------|-----------|--------|
| AC1 | SCN001 | Yes (`tests/blender/test_geometry_normals.py`) | Yes |
| AC2 | SCN002 | Yes | Yes |
| AC3 | SCN003 | Yes | Yes |
| AC4 | SCN004 | Yes | Yes |
| AC5 | SCN005 | Yes | Yes |
| AC6 | SCN006 | Yes | Yes |
| AC7 | SCN007 | Yes | Yes |
| AC8 | SCN008 | Yes (`tests/unit/test_geometry_rule_docs.py`) | Yes |

All scenarios in `feature.gherkin` are tagged `@regression`, as the defect path requires.

### Coverage Summary

- `repository.tests`: 1092 passed, 9 skipped
- `gate-blender-headless`: 273 passed (includes `tests/blender/test_geometry_normals.py`)

---

## Exercise Test Results

| Field | Value |
|-------|-------|
| **Reason** | Not applicable: the change does not touch nmg-sdlc `workflows/` or `agents/`. The shipped `skills/model-asset/SKILL.md` change is documentation only and is covered by `plugin.validate` and `plugin.session-smoke`. |

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| repository.tests | Pass | `uv run pytest tests/unit tests/bdd -q` exited 0 (1092 passed, 9 skipped) |
| repository.lint | Pass | `uv run ruff check .`: All checks passed |
| repository.format | Pass | `uv run ruff format --check .`: 331 files already formatted |
| repository.types | Pass | `uv run mypy src tests`: no issues in 208 source files |
| gate-blender-headless | Pass | `scripts/run-blender-tests.sh` exited 0 (273 passed) |
| gate-ue-compile | Pass | DogfoodEditor compiled against `/Users/Shared/Epic Games/UE_5.8` |
| gate-mcp-schema | Pass | MCP tools match tools.json for every server |
| gate-shellcheck | Pass | `shellcheck -S style` on every `scripts/**.sh` exited 0 |
| gate-ship-smoke | Not applicable | No ship paths changed (`applicable: false`) |
| plugin.validate | Pass | `claude plugin validate .` exited 0 |
| plugin.session-smoke | Pass | Plugin loaded via `--plugin-dir`; `nmg-game-dev:blender` connected |

**Gate Summary**: 10/10 applicable gates passed, 0 failed, 0 incomplete (1 not applicable)

---

## Fixes Applied

| Severity | Category | Location | Original Issue | Fix Applied | Routing |
|----------|----------|----------|----------------|-------------|---------|
| — | — | — | No findings required a fix during verification | — | — |

## Remaining Issues

### Critical / High / Medium Priority
None.

### Low Priority

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Performance |
| **Location** | `plugins/nmg-game-dev-blender-addon/contract_core/geometry.py` `_islands`, `_winding_violations` |
| **Issue** | Island grouping and winding propagation run as Python loops over bmesh faces and loops, so very dense meshes cost more than the old single C-level recalc. |
| **Impact** | Linear extra time in validation; well within finalize budgets for contract-sized assets. |
| **Reason Not Fixed** | No measured regression; optimizing would add complexity without evidence. |

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Architecture |
| **Location** | `plugins/nmg-game-dev-blender-addon/contract_core/geometry.py` `_winding_violations` |
| **Issue** | For a non-orientable open sheet (Möbius-like), the spanning-tree minority count is a lower bound, not an exact count of faces to flip. |
| **Impact** | Such a sheet is still reported when the propagated orientation disagrees; exact counts are not part of any AC. |
| **Reason Not Fixed** | Out of scope for the approved spec; not a realistic authoring case. |

---

## Positive Observations

- The fix follows design.md step by step, and each helper has a docstring that explains why position cannot matter.
- Tests pin a placement the pre-fix code actually flagged, so the regression suite would fail against the old code rather than passing vacuously.
- Seeded randomized coverage (1,000 quads, 200 welded arrangements) guards the position-independence requirement (FR4).
- Both callers are exercised end to end (FR5) without a live editor.

---

## Recommendations Summary

### Before PR (Must)
- None.

### Short Term (Should)
- None.

### Long Term (Could)
- Profile `geometry_findings` on a dense hero mesh if validation time becomes a concern.

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `plugins/nmg-game-dev-blender-addon/contract_core/geometry.py` | 2 (low) | Per-island normals check |
| `plugins/nmg-game-dev-blender-addon/contract_core/report.py` | 0 | Remediation text |
| `tests/blender/test_geometry_normals.py` | 0 | SCN001–SCN007, FR5 callers |
| `tests/unit/test_geometry_rule_docs.py` | 0 | SCN008 |
| `docs/asset-contract.md` | 0 | §3 rule |
| `skills/model-asset/SKILL.md` | 0 | Environment-piece rules |
| `docs/skills/model-asset.md` | 0 | Per-island description and rules |

---

## Recommendation

**Ready for PR**

Every acceptance criterion passes with direct test evidence, the defect no longer reproduces, the blast radius is limited to the two unchanged callers, and every applicable registered validation passed at `a9b9a6f63280dbec83b1e00558e4e68f0be5940a`.
