# Verification Report: geometry.normals rejects correctly facing open surfaces

**Date**: 2026-11-11
**Issue**: #144
**Reviewer**: Claude (nmg-sdlc architecture-reviewer, verify stage)
**Scope**: Defect-fix verification against the approved spec

**Verification head**: a02f2faba229351783d7446e3b87188099c27818

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
**Total Issues**: 0 blocking, 3 low-severity observations (no action required for this issue)

`geometry.normals` now judges each edge-connected island separately. Open islands are checked only for consistent winding, counting the minority of faces. Closed islands keep the outward recalculation, limited to that island. All 8 acceptance criteria are met. The defect no longer reproduces in headless Blender 5.2.3. Every registered validation that applies passed at the verification head after the `origin/main` merge (`a02f2fa`).

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

- Artifact: `.nmg-sdlc/verification/144.json` (runner `sdlc-verify-steering.mjs --base main`, controller run `1037e9d5-5477-436b-b2fc-e0c25cc0dbca`, generated 2026-11-12T03:39:17Z)
- Identity: head `a02f2faba229351783d7446e3b87188099c27818`, clean tree, steering `sha256:795f9897…c0e4`, spec `sha256:4ca5853c…3473`
- Coverage: declared 11, recorded 11, complete `true`, no missing, duplicate, or unknown ids
- Ceiling: none (`ok: true`)

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | A correctly facing single open quad passes wherever it sits | Pass | `contract_core/geometry.py` `_normal_violations` → `_winding_violations` (never compares with an outside direction); `tests/blender/test_geometry_normals.py` SCN001: 500 axis-aligned and 500 tilted seeded placements, plus the issue quad |
| AC2 | A consistently wound open sheet passes regardless of facing | Pass | SCN002: floor plus back wall (facing the room and facing away), and a welded 8×8 ground sheet (facing up and down) |
| AC3 | Inconsistent winding inside an open sheet is still reported | Pass | SCN003: a reversed wall, an interior grid cell, and a corner grid cell each give a count of 1 with the unchanged message shape |
| AC4 | Closed islands still face outward | Pass | `_outward_violations` runs `recalc_face_normals` on that island only. SCN004: each of the 6 single flipped faces gives 1, and an inside-out box gives 6 |
| AC5 | Islands are judged independently | Pass | `_islands` flood-fills across shared edges. SCN005: a correct box, the floor quad the old check flagged, and a box with one flipped face give exactly 1 |
| AC6 | Welded touching closed primitives pass | Pass | SCN006: boxes touching at a vertex, along an edge, across part of a face, and across part of a face with a shared edge, plus 200 seeded welded arrangements |
| AC7 | Remediation text fits open surfaces | Pass | `contract_core/report.py` `RULES["geometry.normals"]` matches design.md's text. SCN007 checks the text and that the finding carries it |
| AC8 | The authoring rule is documented | Pass | `docs/asset-contract.md` §3, `skills/model-asset/SKILL.md` "Geometry rules for `environment_piece`", and `docs/skills/model-asset.md`; checked by `tests/unit/test_geometry_rule_docs.py` (SCN008) |

### Reproduction check (defect path)

I re-ran the reproduction at the verification head in headless background Blender 5.2.3 (`--factory-startup`, no live editor). The script compares the old whole-mesh `_flipped_faces` logic with the shipped `geometry_findings`, loaded from this checkout, on identical meshes:

| Case | Pre-fix | Post-fix |
|------|---------|----------|
| 2,000 random upward floor quads within ±10 m (seed 20261111) | 393 / 2,000 flagged | 0 / 2,000 flagged |
| Floor + back wall facing into the room | 2 faces counted | 0 findings |
| Issue quad (3.37, -2.11, 0.4)–(7.9, 1.63, 0.4) | 0 (this exact placement does not trip) | 0 findings |

The defect no longer reproduces.

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Judge normals per island | Complete | `_normal_violations`, `_islands`, `_winding_violations`, `_walk_direction`, `_loop_on_edge`, `_outward_violations` in `contract_core/geometry.py`; rule id, target, and message unchanged; bmesh copy freed in `finally` |
| T002 | Update the geometry.normals remediation | Complete | `contract_core/report.py` |
| T003 | Add behavioral regression coverage | Complete | `tests/blender/test_geometry_normals.py` (SCN001–SCN007 plus a test that both callers stay compatible) |
| T004 | Document the environment-piece authoring rule | Complete | Three documents plus `tests/unit/test_geometry_rule_docs.py`; §6 budget table unchanged |

---

## Architecture Assessment (defect path: blast radius)

- **Other callers on the changed path**: `contract_core/validate.py` `validate_asset` (finalize validate step, export pre-check, `nmggamedev.validate_contract`) and `inspect_core/spatial.py` `inspect_asset`. Both call `geometry_findings(name, mesh)` unchanged, and `test_callers_report_no_normals_finding_for_a_floor_quad` exercises both.
- **Public contract change**: none. `geometry_findings`' signature, the rule id `geometry.normals`, the target, and the message shape are identical. Only `_flipped_faces` (private) was replaced. The remediation string changed as the spec requires.
- **Silent data changes**: none. The check still runs on a caller-owned bmesh copy that is freed. `recalc_face_normals` on a closed island rewinds faces only in that copy, and the islands share no edges, so one island's rewinding cannot affect another's count.
- **Minimal-change check**: `git diff origin/main...HEAD` touches only the files listed in the spec, the regression and doc tests, the verification report, and the delivery-prep version bump (`VERSION`, `CHANGELOG.md`, `.claude-plugin/plugin.json`, `blender_manifest.toml`, `nmg-game-dev.uplugin`). There is no unrelated refactor.

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 5 | Island grouping, winding and outward counting are separate small functions |
| Open/Closed | 5 | Other geometry rules untouched |
| Liskov Substitution | 5 | N/A (no type hierarchy) |
| Interface Segregation | 5 | Public surface unchanged |
| Dependency Inversion | 5 | Pure function of a bmesh; no new dependencies beyond `collections.deque` |

## Security Assessment

No new input sources, I/O, subprocesses, or credentials. The function only reads mesh data it is given.

## Performance Assessment

The island flood fill and winding propagation are linear in faces times edges per face. `_loop_on_edge` scans the loops of one face, which is bounded by polygon size. `recalc_face_normals` runs once per closed island rather than once per mesh, which costs a little more on meshes with very many tiny islands but stays well within authoring budgets. The 1,200-mesh regression file finishes inside the 191 s full headless suite. Score 4 only because of the per-island bmesh op calls.

## Error Handling

The `try/finally` in `geometry_findings`, which frees the bmesh, is preserved. The helpers have no failure modes beyond the bmesh API's own.

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Test | Passes |
|---------------------|-------------|----------|--------|
| AC1 | SCN001 | `test_scn001_*` (3) | Yes |
| AC2 | SCN002 | `test_scn002_*` (4 params) | Yes |
| AC3 | SCN003 | `test_scn003_*` (3) | Yes |
| AC4 | SCN004 | `test_scn004_*` (8) | Yes |
| AC5 | SCN005 | `test_scn005_*` | Yes |
| AC6 | SCN006 | `test_scn006_*` (5) | Yes |
| AC7 | SCN007 | `test_scn007_*` | Yes |
| AC8 | SCN008 | `tests/unit/test_geometry_rule_docs.py` (3) | Yes |

All eight scenarios in `feature.gherkin` are tagged `@regression`. The Blender scenarios are designer-facing Gherkin backed by pytest in headless Blender, as tech steering's testing table prescribes for the add-on layer.

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` | Pass | `uv run pytest tests/unit tests/bdd -q`: 1131 passed, 9 skipped |
| `repository.lint` | Pass | `ruff check .`: All checks passed |
| `repository.format` | Pass | `ruff format --check .`: 334 files already formatted |
| `repository.types` | Pass | `mypy src tests`: no issues in 211 source files |
| `gate-blender-headless` | Pass | `scripts/run-blender-tests.sh`: 273 passed (includes the 4 blender-mcp coexistence tests) |
| `gate-ue-compile` | Pass | DogfoodEditor compiled against UE 5.8 |
| `gate-mcp-schema` | Pass | `validate-mcp-tools.py` exited 0 |
| `gate-shellcheck` | Pass | `shellcheck -S style` on `scripts/**.sh` exited 0 |
| `gate-ship-smoke` | Not applicable | No ship paths changed (`applicable: false`) |
| `plugin.validate` | Pass | `claude plugin validate .`: passed with warnings |
| `plugin.session-smoke` | Pass | Plugin loaded via `--plugin-dir`; `nmg-game-dev:blender` connected |

**Gate Summary**: 10/10 applicable gates passed, 0 failed, 0 incomplete (1 not applicable)

### Gate diagnosis: cross-lane Blender add-on link race

The first runner pass at this head recorded `gate-blender-headless` as **failed**: 4 tests in `tests/blender/test_finalize_core.py` raised `TypeError: validate_asset() got an unexpected keyword argument 'material_variants_path'`. The later gates were deferred as incomplete. The cause is environmental, not this change:

- `tests/blender/_runner.py` links the add-on into Blender's single, shared user add-ons folder (`~/Library/Application Support/Blender/5.2/scripts/addons/nmg_game_dev_blender_addon`).
- Lanes 3 and 5 were running their own Blender suites at the same time. Their runners repointed that link mid-run, so this lane's process lazily imported lane-3's `finalize_core/steps.py` alongside its already-loaded `validate_asset`.
- I confirmed both concurrent processes and their working directories with `ps` and `lsof`. The link pointed at lane-3, then lane-5, while this run was in progress.

Repair: I reran the full registered runner with `BLENDER_BIN` pointing at a scratchpad wrapper. The wrapper runs the same Blender 5.2.3 binary with `BLENDER_USER_SCRIPTS` set to a folder only this lane uses. That folder links this checkout's add-on and the installed blender-mcp host add-on. The suite, the runner script, and the code under test are unchanged. The isolated run passed all 273 tests with no skips.

---

## Fixes Applied

| Severity | Category | Location | Original Issue | Fix Applied | Routing |
|----------|----------|----------|----------------|-------------|---------|
| — | Environment | Gate host (not the repository) | Shared Blender user add-ons link raced with concurrent lanes and failed `gate-blender-headless` | Gate re-run with a lane-isolated `BLENDER_USER_SCRIPTS` via `BLENDER_BIN` wrapper; no repository change | direct |

No code fixes were needed.

## Remaining Issues

### Low Priority

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Testing (infrastructure) |
| **Location** | `tests/blender/_runner.py` `_install_addon_link` |
| **Issue** | The runner always links the add-on into the shared Blender user add-ons folder, so parallel checkouts race on it. |
| **Impact** | `gate-blender-headless` can fail intermittently for reasons that have nothing to do with the change when lanes verify at the same time. |
| **Reason Not Fixed** | Out of #144's scope. A follow-up could have the runner set a per-checkout `BLENDER_USER_SCRIPTS` itself. |

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Delivery prep |
| **Location** | `CHANGELOG.md` `[0.21.5]` |
| **Issue** | After the `origin/main` merge, the prepared `[0.21.5]` section has two `### Fixed` subsections: main's #141 entry and this issue's #144 entry. |
| **Impact** | Cosmetic only. |
| **Reason Not Fixed** | Version files are owned by the controller's prepare-version step, which re-runs at delivery. Verify's publication scope is limited to this report. |

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Correctness (edge case) |
| **Location** | `contract_core/geometry.py` `_winding_violations` |
| **Issue** | Propagation follows a spanning tree and does not re-check edges that close cycles, so a non-orientable open sheet (for example a Möbius strip) gets a count of 0. |
| **Impact** | Negligible for game assets. The spec's ACs only require counting faces that disagree with their neighbours on orientable sheets, and that is covered. |
| **Reason Not Fixed** | Outside the spec's ACs; would need a spec change. |

---

## Positive Observations

- The fix is small and private. Only `_flipped_faces` was replaced, and both callers are protected by a test that exercises them.
- The regression coverage is strong. It uses seeded randomized placements and seeded random touching-box arrangements, and it pins exact floats for a placement the old check flagged.
- The minority count makes the open-sheet answer independent of which face seeds propagation and which way the sheet faces.

## Recommendations Summary

### Before PR (Must)
- None.

### Short Term (Should)
- Make `tests/blender/_runner.py` isolate the add-on link per checkout (separate issue).

### Long Term (Could)
- Consider detecting non-orientable open sheets if they ever appear in practice.

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `plugins/nmg-game-dev-blender-addon/contract_core/geometry.py` | 0 (1 low edge-case note) | Per-island normals check |
| `plugins/nmg-game-dev-blender-addon/contract_core/report.py` | 0 | Remediation text |
| `tests/blender/test_geometry_normals.py` | 0 | SCN001–SCN007, callers |
| `tests/unit/test_geometry_rule_docs.py` | 0 | SCN008 |
| `docs/asset-contract.md`, `skills/model-asset/SKILL.md`, `docs/skills/model-asset.md` | 0 | AC8 authoring rule |
| `CHANGELOG.md`, `VERSION`, plugin manifests | 0 (1 low cosmetic note) | Delivery prep |

## Recommendation

**Ready for PR**

All 8 acceptance criteria pass, the defect no longer reproduces, and all 10 applicable registered gates passed at `a02f2faba229351783d7446e3b87188099c27818` with complete coverage and no ceiling.
