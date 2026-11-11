# Verification Report: Meshy a-pose arm raise destroys legs on stylized characters

**Date**: 2026-11-11
**Issue**: #135
**Reviewer**: Claude Code (nmg-sdlc architecture-reviewer, execute verify worker)
**Scope**: Implementation verification against spec
**Verification head**: 1e39c819473e41ca473c593133265afcbdc0193c

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 4 |
| Security | 5 |
| Performance | 4 |
| Testability | 5 |
| Error Handling | 4 |
| **Overall** | 4.5 |

### Implementation Status: Pass
**Total Issues**: 2 (both Low, neither blocks delivery)

The fixed-proportion shoulder pivot and the angular selection window are gone. `scripts/blender/meshy_session.py` now finds each shoulder from horizontal slices of the mesh (armpit detection), tracks the arm down from the armpit, limits selection to the arm's length, and reports `detected`, `shoulder`, and `hand_tip` per side. An undetected side moves no vertex. `raise_arms` turns the raise off end to end, through `GenerateRequest`, the job runner, `MeshySession.import_glb`, the `generate_model` MCP tool, and the CLI flag `--no-arm-raise`. The work adds a stylized-character fixture and a fused-arm fixture. This report re-verifies the branch at merge commit `1e39c81`, which merged origin/main (`f9bdb45`, #172) into the #135 branch to make PR #174 mergeable. The merge brought in only main's changes. No #135 file changed between `3358361` and `1e39c81`, and the branch's diff against origin/main is exactly the #135 change plus its CHANGELOG entry under `[Unreleased]`. All 11 registered validations were recorded at `1e39c81`, and every applicable one passed, including 196 headless Blender tests and the UE compile.

---

## Issue Scope

- Active issue: #135
- Spec: `specs/135-fix-meshy-a-pose-arm-raise-destroying-legs-on-stylized-characters`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1–AC9]; FR [FR1–FR10]; tasks [T001–T007]; scenarios [SCN001–SCN009]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":135,"specPath":"specs/135-fix-meshy-a-pose-arm-raise-destroying-legs-on-stylized-characters","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6","AC7","AC8","AC9"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6","FR7","FR8","FR9","FR10"],"tasks":["T001","T002","T003","T004","T005","T006","T007"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006","SCN007","SCN008","SCN009"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

- Runner: `sdlc-verify-steering.mjs --project . --issue 135 --spec specs/135-… --base main --controller-run-id 19e2a512-9706-4211-a7c9-1364e8659be3`, exit 0 (generated 2026-11-11T21:43:50Z)
- Artifact: `.nmg-sdlc/verification/135.json` (schema with `identity`, `coverage`, `results`). Its `ceiling` is `null`, and every applicable result has `effectiveStatus: passed` with `treeState: clean` at the head below.
- Coverage: 11 declared, 11 recorded, `complete: true`, with no missing, duplicate, or unknown results.
- Identity: head `1e39c819473e41ca473c593133265afcbdc0193c`, tree clean, spec hash `sha256:1cbeef8b…`, steering hash `sha256:119992c8…`
- Base drift: origin/main has since advanced to `12f12cf` (spec-approval docs for #138, #151, #155). It merges cleanly with `1e39c81` (`git merge-tree`), touches no #135 path, and delivery rechecks mergeability at the exact head.
- First run at this head: `gate-ue-compile` failed with `clang++: error: no such file or directory: …/fixtures/Plugins/VibeUE/Intermediate/Build/…/Module.VibeUE.gen.cpp.o`. Diagnosis: the lane's `fixtures/Plugins` was a symlink into the main checkout, shared with other parallel lane worktrees. Their concurrent UE builds deleted and rebuilt VibeUE's `Intermediate/` and `Binaries/` while this build was linking. This is an environment race, not a code defect: the branch changes no UE source. Repair: `fixtures/Plugins` (gitignored) became a lane-local directory, and `scripts/install-vibeue.sh` cloned VibeUE there (branch 5-8, commit `42df27b`). The full gate was then rerun, and `gate-ue-compile` passed. The tracked tree stayed clean.

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Legs, boots, skirt, torso, and head stay put on a stylized character | Pass | `_raise_side` selection (tracked intervals below the armpit plus the shoulder cap), `scripts/blender/meshy_session.py`. `test_a_stylized_a_pose_moves_only_arm_vertices` (tests/blender) passed in gate-blender-headless. BDD SCN020 |
| AC2 | Raised from the detected shoulder: before 55±3°, after 48±0.5° | Pass | `_drop_deg(shoulder, tip)`, then rotation by the excess. `test_a_stylized_arm_drops_from_the_detected_shoulder` passed. SCN021 |
| AC3 | Shoulder from the armpit, within 0.03·H of the true shoulder | Pass | `_find_armpit` (highest slice that stays separate for `ARMPIT_RUN`) and the line fit in `_raise_side`. `test_a_stylized_shoulder_is_found_at_the_armpit` passed. SCN022 |
| AC4 | Selection follows the arm and is limited by its length | Pass | `_track_arm` stops on no overlap, on several overlaps, or on growth beyond `ARM_GROWTH`. The `math.dist(...) <= length` filter. `test_detached_boxes_stay_and_moved_vertices_lie_within_the_arm_length` passed. SCN023 |
| AC5 | `detected`, `shoulder`, and `hand_tip` reported after the raise, inside the bounding box | Pass | The `report` dict in `_raise_side`, with points rounded to 6 decimals and the tip taken after the move. `test_the_detected_landmarks_are_reported` passed. The fake `ARM_RAISE` carries the fields. SCN024 and SCN018 updated |
| AC6 | A side with no detectable shoulder is untouched and reports `no_armpit` | Pass | `_undetected()` and the early return with an empty move set. `test_a_fused_arm_is_left_untouched` passed. SCN025 |
| AC7 | The raise can be skipped (`raise_arms` false, `--no-arm-raise`) | Pass | Covered in `request.py`, `jobs.py` (stored and replayed), `session.py` (payload key only when false), `server.py` and `tools.json`, `__main__.py`, and the `_import_glb` gate. Unit tests in `test_request`, `test_jobs` (pose_mode still `a-pose`, `arm_raise` null), `test_session`, `test_mcp_server`, and `test_cli`. Blender `test_raise_arms_false_skips_the_raise`. SCN026 |
| AC8 | Realistic humanoids still import correctly | Pass | Existing #106 tests updated to the new report shape: 48±0.5°, and a 45° side keeps every vertex and reports `detected` true with its shoulder. Counts, connectivity, and normals test passed. SCN027 and SCN019 (neutral-pose check about the reported shoulders) |
| AC9 | Other poses are unchanged | Pass | The `_import_glb` gate is `pose == "a-pose" and raise_arms`. `test_compliant_or_non_a_pose_imports_move_no_vertex` passed. SCN028 |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Detect shoulders and track arms in the session arm raise | Complete | `SHOULDER_HEIGHT`, `SHOULDER_HALF_WIDTH`, `ARM_CONE_EXTRA_DEG`, and `_hand_tip` are removed. Slice, armpit, tracking, and selection helpers are added, and the module docstring is updated |
| T002 | Add the `raise_arms` skip option end to end | Complete | gate-mcp-schema passed |
| T003 | Add stylized and fused-arm fixtures | Complete | `stylized_parts`, `stylized_shoulder`, `stylized_hand_tip`, `stylized_body_points`, `build_stylized`. `raise_arm_landmarks` accepts per-side pivots |
| T004 | Blender regression coverage | Complete | 7 new #135 Blender tests. The suite passed with 186 tests. The "fails against #106" property was not re-run here, but every assertion checks behavior the #106 pivot rule cannot meet (a shoulder within 0.03·H of 1.08 m, while #106 put it at 1.458 m) |
| T005 | Unit coverage for the skip option | Complete | repository.tests passed |
| T006 | BDD scenarios for #135 | Complete | SCN020–SCN028 map to spec SCN001–SCN009, and the mapping comment is in the feature file. The geometry steps bind to the Blender tests through `_blender_covers` |
| T007 | Document detection, report fields, and the skip option | Complete | `docs/mcp/meshy.md` updates Tools, Pose, Arm raise (4-step method plus the field table), Status document, and CLI |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 4 | Each slice, armpit, tracking, and union helper does one thing. `_raise_side` combines selection, shoulder fit, and rotation in about 80 lines. It is readable, but it would split cleanly into a selection step and an apply step |
| Open/Closed | 4 | The tuning constants are named module constants. The new behavior sits behind an optional payload key that defaults to the previous on-state |
| Liskov Substitution | 5 | `FakeSession` mirrors the real `raise_arms` and `arm_raise` contract |
| Interface Segregation | 5 | `raise_arms` is added only where it is needed (generate path), and retexture is untouched |
| Dependency Inversion | 4 | The job runner reaches Blender only through the `MeshySession` abstraction. The geometry helpers are pure functions over point tuples |

### Layer Separation

The change follows the structure steering. Vertex math stays in the Blender-side session script (`scripts/blender/`). Request and job orchestration stay in `src/nmg_game_dev/meshy/`. The MCP server only forwards the parameter, with no added logic. Skill and CLI layers do not touch sockets.

### Dependency Flow

MCP and CLI pass the value to `GenerateRequest`, then to `jobs.start_generate`, which stores it in `request.json`. `_run_generate` reads it back and passes it to `MeshySession.import_glb`, which sends the `import_glb` payload. The flow is one-directional, and stored jobs written without the key default to `True` (`stored.get("raise_arms", True)`).

---

## Security Assessment

- [x] Authentication: unchanged. The Meshy key path is not touched.
- [x] Authorization: N/A
- [x] Input validation: `raise_arms` is a typed boolean in the MCP schema and is coerced with `bool()` on replay. The session payload treats only an explicit falsy value as a skip.
- [x] Injection prevention: no new shell, path, or eval surface. The payload is JSON into the existing session script.
- [x] Data protection: no new logging of secrets.

---

## Performance Assessment

- [x] Async patterns: unchanged. The import still runs inside the existing job runner.
- [x] Caching: N/A
- [x] Resource management: the slicing buckets each triangle into only the slices it straddles, so cost is about (triangles × slices spanned) plus several O(V) passes over the vertices. Roughly 200 slices at `0.005·H`.
- [x] Query optimization: N/A. Pure-Python vertex math on dense Meshy meshes (100k+ triangles) was not timed in this verification. See Remaining Issues.

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1 | Yes (SCN020) | Yes | Yes |
| AC2 | Yes (SCN021) | Yes | Yes |
| AC3 | Yes (SCN022) | Yes | Yes |
| AC4 | Yes (SCN023) | Yes | Yes |
| AC5 | Yes (SCN024) | Yes | Yes |
| AC6 | Yes (SCN025) | Yes | Yes |
| AC7 | Yes (SCN026) | Yes | Yes |
| AC8 | Yes (SCN027) | Yes | Yes |
| AC9 | Yes (SCN028) | Yes | Yes |

### Coverage Summary

- Feature files: 9 new #135 scenarios in `tests/bdd/features/meshy.feature`, plus SCN018 and SCN019 updated
- Step definitions: implemented in `tests/bdd/test_meshy_bdd.py`
- Unit tests: 7 new #135 unit tests (request, jobs ×2, session, mcp_server ×2, cli)
- Blender tests: 7 new #135 headless tests, plus 3 updated #106 tests. The full Blender suite passed with 186 tests.

---

## Exercise Test Results

| Field | Value |
|-------|-------|
| **Reason** | Not applicable. The diff touches no nmg-sdlc `workflows/` or `agents/` files. The Claude Code plugin surface (`.claude-plugin/plugin.json` version bump) is covered by `plugin.validate` and `plugin.session-smoke` |
| **Recommendation** | None |

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| repository.tests | Pass | `uv run pytest tests/unit tests/bdd -q`: 985 passed, 9 skipped |
| repository.lint | Pass | `uv run ruff check .`: All checks passed |
| repository.format | Pass | `uv run ruff format --check .`: 310 files already formatted |
| repository.types | Pass | `uv run mypy src tests`: no issues in 197 source files |
| gate-blender-headless | Pass | `scripts/run-blender-tests.sh`: 196 passed in 301 s (186 before the merge, plus #172's variants tests) |
| gate-ue-compile | Pass | `Build.sh DogfoodEditor Mac Development` against UE 5.8: `Result: Succeeded` (621 s, a clean build with the lane-local VibeUE). It applies because the diff against the local `main` ref includes plugin manifest paths |
| gate-mcp-schema | Pass | `validate-mcp-tools.py`: MCP tools match tools.json for every server |
| gate-shellcheck | Not applicable | No `scripts/**.sh` changed |
| gate-ship-smoke | Not applicable | No ship paths changed |
| plugin.validate | Pass | `claude plugin validate .`: Validation passed (with warnings) |
| plugin.session-smoke | Pass | Plugin loaded via `--plugin-dir` in an ephemeral herdr session. `nmg-game-dev:blender` connected |

**Gate Summary**: 9/9 applicable gates passed, 0 failed, 0 incomplete (2 not applicable)

---

## Fixes Applied

| Severity | Category | Location | Original Issue | Fix Applied | Routing |
|----------|----------|----------|----------------|-------------|---------|
| — | Environment | `fixtures/Plugins` (gitignored, not tracked) | `gate-ue-compile` failed at `1e39c81` when VibeUE objects were deleted mid-link by other lanes' builds through the shared `fixtures/Plugins` symlink | Replaced the symlink with a lane-local clone from `scripts/install-vibeue.sh` and reran the full gate. No tracked file changed | `direct` |

## Remaining Issues

### Critical Issues
None.

### High Priority
None.

### Medium Priority
None.

### Low Priority

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Error Handling |
| **Location** | `scripts/blender/meshy_session.py` `_raise_arms` |
| **Issue** | The `if not points or height <= 0` guard runs after `max(zs) - min(zs)`. An empty vertex list would raise `ValueError` before the guard. |
| **Impact** | Not reachable in practice. A GLB mesh with no vertices fails in `_normalize` before the raise runs, so the empty-points half of the guard is dead code. The `height <= 0` half works. |
| **Reason Not Fixed** | Cosmetic, with no behavior change. Verification does not commit code, and changing it would invalidate the green gate at this head. |

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Performance |
| **Location** | `scripts/blender/meshy_session.py` `_slice_mesh`, `_raise_side` |
| **Issue** | The slice analysis is pure Python over every triangle and vertex. Its runtime on a dense production Meshy mesh was not measured. |
| **Impact** | It may add seconds to an `a-pose` import on very dense meshes. The import runs inside the background job, not inside a single Blender MCP call, so the 180 s MCP limit is not at risk. |
| **Reason Not Fixed** | Out of spec scope. Time it in the next live Meshy run. |

---

## Positive Observations

- Each side is computed against the original normalized positions, and the moves are applied once at the end. The #106 code changed points in place between sides.
- The undetected path fails safe: no movement, an explicit `reason`, and the import still succeeds.
- The fixtures expose the true landmarks and per-part vertex sets, so the Blender assertions are exact rather than heuristic.
- The docs explain why the measured drop can differ by a few degrees (arm taper), which matches the test tolerances.

---

## Recommendations Summary

### Before PR (Must)
- None

### Short Term (Should)
- Time the arm raise on a dense production Meshy `a-pose` character during the next live run.

### Long Term (Could)
- Move the empty-mesh guard in `_raise_arms` above the bounding computation.
- Split `_raise_side` into a selection step and an apply step.

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `scripts/blender/meshy_session.py` | 2 (Low) | Core fix |
| `src/nmg_game_dev/meshy/request.py` | 0 | |
| `src/nmg_game_dev/meshy/jobs.py` | 0 | |
| `src/nmg_game_dev/meshy/session.py` | 0 | |
| `src/nmg_game_dev/meshy/__main__.py` | 0 | |
| `mcp-servers/meshy/src/meshy_mcp/server.py`, `mcp-servers/meshy/tools.json` | 0 | |
| `tests/meshy_arm_geometry.py`, `tests/blender/meshy_fixtures.py` | 0 | |
| `tests/blender/test_meshy_session.py` | 0 | |
| `tests/meshy_fakes.py`, `tests/unit/meshy/*` | 0 | |
| `tests/bdd/features/meshy.feature`, `tests/bdd/test_meshy_bdd.py` | 0 | |
| `docs/mcp/meshy.md` | 0 | |
| `CHANGELOG.md` | 0 | #135 entry under `[Unreleased]`. `VERSION` and the manifests equal origin/main (0.21.2), and delivery's prepare-version applies the patch bump |

---

## Recommendation

**Ready for PR**

All nine acceptance criteria and ten functional requirements are implemented and covered by passing Blender, unit, and BDD tests. Every applicable registered gate passed at `1e39c819473e41ca473c593133265afcbdc0193c`, the merge commit that makes PR #174 mergeable. The two remaining findings are Low and do not affect behavior.
