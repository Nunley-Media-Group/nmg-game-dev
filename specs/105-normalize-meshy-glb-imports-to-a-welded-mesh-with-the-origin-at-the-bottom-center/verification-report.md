# Verification Report: Normalize Meshy GLB imports to a welded mesh with the origin at the bottom center

**Date**: 2026-10-31
**Issue**: #105
**Reviewer**: Claude (nmg-sdlc verify worker)
**Scope**: Implementation verification against spec

**Verification head**: 2023d4d12d5548f3d185e5f7022ccb5efa524544

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 5 |
| Security | 5 |
| Performance | 5 |
| Testability | 5 |
| Error Handling | 4 |
| **Overall** | 4.8 |

### Implementation Status: Pass
**Total Issues**: 1 (low, informational; nothing blocking)

---

## Issue Scope

- Active issue: #105
- Spec: `specs/105-normalize-meshy-glb-imports-to-a-welded-mesh-with-the-origin-at-the-bottom-center`
- Manifest: `implicit single issue`
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1, AC2, AC3, AC4]; FR [FR1, FR2, FR3, FR4]; tasks [T001, T002, T003]; scenarios [SCN001, SCN002, SCN003, SCN004]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":105,"specPath":"specs/105-normalize-meshy-glb-imports-to-a-welded-mesh-with-the-origin-at-the-bottom-center","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4"],"functionalRequirements":["FR1","FR2","FR3","FR4"],"tasks":["T001","T002","T003"],"scenarios":["SCN001","SCN002","SCN003","SCN004"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

`sdlc-verify-steering.mjs --issue 105 --base main --controller-run-id 1d8c53d8-6b3c-4e22-a1d5-e8a4c8a68d96` wrote `.nmg-sdlc/verification/105.json`. The run returned `ok: true` with `ceiling: null` and coverage `declared: 5, recorded: 5, complete: true` (no missing, duplicate, or unknown IDs). Every result's identity is head `2023d4d12d5548f3d185e5f7022ccb5efa524544` with a clean tree.

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Welded single mesh; face count, corner UVs, material slots unchanged | Pass | `scripts/blender/meshy_session.py` `_weld` (`bmesh.ops.remove_doubles`, dist `WELD_DISTANCE = 1e-5`); `tests/blender/test_meshy_session.py::test_seam_split_vertices_are_welded_and_the_topology_is_kept` checks 8 verts, 1 island, 12 faces, equal sorted UVs, and 1 slot |
| AC2 | Identity transforms; bbox X/Y center and min Z within 1e-3 of 0 | Pass | `_normalize` bakes `matrix_world` into the mesh and sets identity; `_recenter` translates by `(-cx, -cy, -minz)`; `test_the_origin_moves_to_the_bottom_center_with_identity_transforms` uses a cube at (2, 3, 4) |
| AC3 | No custom normals, smooth with >30° sharp, outward face normals | Pass | `_fix_normals` (`customdata_custom_splitnormals_clear`, `shade_smooth_by_angle(30°, keep_sharp_edges=True)`), and `recalc_face_normals` in `_weld`; `test_custom_normals_are_cleared_and_faces_smooth_with_outward_normals` builds the source with inward faces, so the outward fix is exercised |
| AC4 | `merged_vertices` + `origin_offset` in the import and generate-job results | Pass | `_import_glb` return `**normalized`; `src/nmg_game_dev/meshy/jobs.py` `_run_generate` copies both keys; `test_the_import_result_reports_the_weld_and_the_origin_offset`, `tests/unit/meshy/test_jobs.py::test_a_loaded_generate_job_copies_the_import_normalization`, `test_an_unreachable_import_adds_no_normalization_keys`, BDD `@SCN015` |

| FR | Status | Evidence |
|----|--------|----------|
| FR1 | Pass | `_weld`, AC1 test |
| FR2 | Pass | `_normalize` / `_recenter`, AC2 test |
| FR3 | Pass | `_fix_normals`, AC3 test |
| FR4 | Pass | `jobs.py` and the `docs/mcp/meshy.md` "Imported mesh" section and status document |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Normalize the imported mesh | Complete | Normalization failures return `meshy.session_failed`; the module docstring lists the new keys; other ops are unchanged |
| T002 | Surface the normalization in the job result and docs | Complete | `jobs.py`, the `tests/meshy_fakes.py` `IMPORT_NORMALIZATION`, `docs/mcp/meshy.md`, and a CHANGELOG Added bullet ending `(#105)`. The delivery commit moved it from `[Unreleased]` into `[0.17.0]`, and the version bump is in sync across all four version files |
| T003 | Tests | Complete | 4 new headless Blender tests plus the updated exact-dict test, 2 unit tests, and 1 BDD scenario |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 5 | `_weld`, `_recenter`, and `_fix_normals` each do one step, and `_normalize` runs them in order |
| Open/Closed | 5 | Additive result keys; existing ops are untouched |
| Liskov Substitution | 5 | N/A beyond the fake session matching the real result shape |
| Interface Segregation | 5 | The result contract only gains two documented keys |
| Dependency Inversion | 5 | The job runner consumes the session result through the existing `run_session_op` seam |

### Layer Separation

The geometry work stays in the session script, which is the step implementation. The pipeline (`jobs.py`) only passes the values through and adds no logic. This matches `steering/structure.md` Layer Responsibilities.

### Dependency Flow

Unchanged. The script imports only `bpy`, `bmesh`, `mathutils`, and the stdlib.

---

## Security Assessment

- [x] Authentication: N/A. No API or key handling changed.
- [x] Authorization: N/A.
- [x] Input validation: the GLB path still comes from the job's own download; an empty mesh is caught by `_recenter`.
- [x] Injection prevention: no new subprocess or eval surface.
- [x] Data protection: the Meshy key is not touched.

## Performance Assessment

- [x] Async patterns: N/A. This is a synchronous in-session op, as before.
- [x] Caching: N/A.
- [x] Resource management: `bmesh` is freed in a `finally` block.
- [x] Query optimization: weld and recenter are O(V); this is fine for Meshy-sized meshes inside the 180 s MCP window.

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1 (SCN001) | Yes (headless Blender test, per the gherkin file header) | Yes | Yes |
| AC2 (SCN002) | Yes (headless Blender test) | Yes | Yes |
| AC3 (SCN003) | Yes (headless Blender test) | Yes | Yes |
| AC4 (SCN004) | Yes (`tests/bdd/features/meshy.feature` `@SCN015`) | Yes | Yes |

### Coverage Summary

- Feature files: 1 new pytest-bdd scenario (spec SCN004 is tagged `@SCN015` in `tests/bdd/features/meshy.feature` because #98 already uses SCN004 there; a comment in the file says so)
- Step definitions: Implemented
- Unit tests: 2 new
- Headless Blender tests: 4 new, 1 updated; the full suite passes

### Test Results

| Command | Result |
|---------|--------|
| `uv run pytest tests/unit tests/bdd -q` (registered `repository.tests`) | passed |
| `uv run ruff check .` (registered `repository.lint`) | passed |
| `uv run ruff format --check .` | 279 files already formatted |
| `uv run mypy src tests` (registered `repository.types`) | passed |
| `claude plugin validate .` (registered `plugin.validate`) | passed |
| `project.plugin-session-smoke` (registered `plugin.session-smoke`, expects `blender` connected) | passed |
| `BLENDER_APP=… scripts/run-blender-tests.sh tests/blender/test_meshy_session.py` | 15 passed |
| `BLENDER_APP=… scripts/run-blender-tests.sh` (full `gate-blender-headless`) | 152 passed |

---

## Exercise Test Results

| Field | Value |
|-------|-------|
| **Reason** | Not applicable. The diff does not touch nmg-sdlc `workflows/` or `agents/`, and no skill changed. |
| **Recommendation** | None |

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| repository.tests | Pass | `.nmg-sdlc/verification/105.json`, effectiveStatus `passed` |
| repository.lint | Pass | effectiveStatus `passed` |
| repository.types | Pass | effectiveStatus `passed` |
| plugin.validate | Pass | effectiveStatus `passed` |
| plugin.session-smoke | Pass | effectiveStatus `passed` (real Blender session) |
| gate-python-lint (tech steering) | Pass | ruff check and format check exit 0 |
| gate-python-types | Pass | mypy exit 0 |
| gate-python-unit / gate-python-bdd | Pass | pytest exit 0 |
| gate-blender-headless | Pass | `scripts/run-blender-tests.sh`: 152 passed |
| gate-shellcheck, gate-mcp-schema, gate-ue-automation, gate-ship-smoke | N/A | The diff touches no `*.sh`, `mcp-servers/**`, UE `Source/**`, or `skills/build-*`/`ship` |

**Gate Summary**: 5/5 registered validations passed, 0 failed, 0 incomplete

---

## Fixes Applied

None. No findings required a fix.

## Remaining Issues

### Low Priority

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Error Handling |
| **Location** | `scripts/blender/meshy_session.py` `_import_glb` |
| **Issue** | When normalization fails, the imported `<Name>` collection stays in the open file, so a retry needs a manual delete. The error message and remediation say so explicitly. |
| **Impact** | One manual step on a rare failure; nothing is lost or corrupted |
| **Reason Not Fixed** | The behavior is documented and matches T001; automatic rollback is beyond the spec |

---

## Positive Observations

- The test source cube has reversed faces, custom normals, and a non-identity location, so one fixture covers every AC branch.
- The job result copies the keys only when the import succeeded; the unreachable-session path is tested.
- The docs state exactly when the new keys are present.

## Recommendations Summary

### Before PR (Must)
- [x] None

### Long Term (Could)
- [ ] Consider rolling back the collection on a normalization failure

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `scripts/blender/meshy_session.py` | 1 (low) | Normalization steps |
| `src/nmg_game_dev/meshy/jobs.py` | 0 | Passes the keys through |
| `docs/mcp/meshy.md` | 0 | Imported mesh section, status document |
| `tests/blender/test_meshy_session.py` | 0 | |
| `tests/unit/meshy/test_jobs.py` | 0 | |
| `tests/bdd/features/meshy.feature`, `tests/bdd/test_meshy_bdd.py` | 0 | |
| `tests/meshy_fakes.py` | 0 | |
| `CHANGELOG.md`, `VERSION`, manifests | 0 | Version bump in sync across all four files |

---

## Recommendation

**Ready for PR**

All four ACs, four FRs, and three tasks are implemented and tested. All five registered validations passed with complete coverage at the verification head, and the headless Blender suite passes in full.
