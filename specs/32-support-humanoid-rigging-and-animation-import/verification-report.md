# Verification Report: Humanoid rigging and animation import

**Date**: 2026-10-30
**Issue**: #32
**Reviewer**: Claude (nmg-sdlc verify worker, run 40468ffe-0554-4b4f-b7a9-4cdbd44bd3ba)
**Scope**: Implementation verification against spec
**Verification head**: 5f7080bafeaa2131ae5123d52113b40be3a02bd7

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 4.6 |
| Security | 5 |
| Performance | 4 |
| Testability | 5 |
| Error Handling | 4 |
| **Overall** | 4.6 |

### Implementation Status: Pass

**Total Issues**: 3 (all Low, none in delivered behavior)

All four acceptance criteria are implemented and covered by Blender headless tests that pass on
Blender 5.2.3 LTS. All five manifest-registered validations passed at the verification head,
with complete coverage (declared 5, recorded 5, `complete: true`, ceiling `null`).

---

## Deterministic Steering Artifact and Ceiling

- Runner: `sdlc-verify-steering.mjs --issue 32 --base main --controller-run-id 40468ffe-0554-4b4f-b7a9-4cdbd44bd3ba`
- Artifact: `.nmg-sdlc/verification/32.json`
- Identity: head `5f7080bafeaa2131ae5123d52113b40be3a02bd7`, tree clean, spec
  `sha256:46a19450…5e1d`, steering `sha256:c53014e6…d209c3`
- Coverage: declared 5, recorded 5, missing 0, duplicate 0, unknown 0, complete `true`
- Ceiling: none

---

## Issue Scope

- Active issue: #32
- Spec: `specs/32-support-humanoid-rigging-and-animation-import`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1, AC2, AC3, AC4]; FR [FR1–FR8]; tasks [T001–T007]; scenarios [SCN001–SCN005]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":32,"specPath":"specs/32-support-humanoid-rigging-and-animation-import","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6","FR7","FR8"],"tasks":["T001","T002","T003","T004","T005","T006","T007"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Humanoid rigging uses local Blender tooling | Pass | `rig_core/rig.py` (`rig_humanoid`, `_build`, transactional set-aside/commit/rollback); `rig_core/skeleton.py` (26 `MANNY_BONES`); tests `test_ac1_rig_builds_manny_skeleton_without_network`, `test_ac1_rerun_replaces_rig`, `test_ac1_failed_rerun_keeps_the_original_rig_and_weights` |
| AC2 | Animation import is library-based | Pass | `rig_core/library.py` (`load`, `BONE_MAPS`), `rig_core/retarget.py` (rest-relative rotation transfer, scaled pelvis location, provenance), `rig_core/export.py` (`add_leaf_bones=False`, temporary `Armature` rename, sorted-key sidecar); tests `test_ac2_library_clips_bake_and_export_with_provenance`, `test_ac2_fresh_blender_reimport_has_mannequin_bones_and_matching_thigh` |
| AC3 | Unsupported shapes fail honestly | Pass | `rig_core/landmarks.py` (`validate` check order), `rig_core/outcome.py` (`fail` appends `MIXAMO_FALLBACK_NOTE` to every fallback), `rig_core/retarget.py` (`anim.text_motion_unsupported`, `anim.clip_not_found`); tests `test_ac3_unsupported_rigs_report_status_and_leave_scene_unchanged` (parametrized), `test_ac3_failed_first_rig_leaves_the_scene_unchanged`, `test_ac3_text_motion_request_is_a_spike`, `test_ac3_unknown_clip_names_the_clip` |
| AC4 | Operators share the implementation | Pass | `operators/rig_humanoid.py`, `operators/import_animations.py`, `operators/export_rigged.py`, `operators/_common.py` (`store_rig_result`); tests in `tests/blender/test_rig_operators.py` (5 pass) |

No source file imports `socket`, `urllib`, `http`, or `requests`, and none enables Rigify or any
other add-on (grep across `rig_core/` and `operators/`). The tests also block connections
through the `network_blocked` fixture.

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Pure-Python skeleton, landmarks, library, outcome modules | Complete | No `bpy` imports in these modules |
| T002 | Rig build | Complete | Rollback restores the previous rig and its weights on `rig.weights_failed` |
| T003 | Library retargeting | Complete | Input checks run before any import |
| T004 | Rigged export | Complete | Name restored in `finally` |
| T005 | Operators and panel | Complete | `last_result` already existed in `pipeline_props.py`, so the file did not change ("added only if absent") |
| T006 | Docs and changelog | Complete | See Remaining Issues: there is no project markdownlint config |
| T007 | Blender headless tests | Complete | 21 rig tests and 7 registration tests pass on Blender 5.2.3 |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 5 | Separate modules for validation (pure), skeleton layout (pure), library parsing (pure), rig build, retarget, and export |
| Open/Closed | 4 | Custom `bone_map` in `library.json` extends retargeting without code changes. Body types are a closed set by design |
| Liskov Substitution | 5 | N/A beyond a uniform result-dict contract |
| Interface Segregation | 5 | Three small public functions; operators are thin wrappers |
| Dependency Inversion | 4 | Blender is used directly, as the add-on layer requires. The pure modules have no `bpy` dependency |

### Layer Separation

Matches the steering's step-implementation layer. The `rig_core` functions are agent-callable
through `execute_blender_code`. Operators only adapt inputs and store results, so the operator
path and the direct path cannot drift apart (AC4).

### Dependency Flow

`operators/ → rig_core/ → (landmarks, skeleton, library, outcome)`. `export.py` reuses
`variants_core.textures` for PNG writing instead of duplicating it. No cycles.

---

## Security Assessment

- [x] Authentication: N/A. No external services.
- [x] Authorization: N/A
- [x] Input validation: landmarks need finite `[x, y, z]` values inside the mesh bounds;
  `library.json` is validated (`anim.library_invalid`, `anim.bone_map_incomplete`)
- [x] Injection prevention: no shell or eval. File paths come from the library or the operator
  property
- [x] Data protection: no network code paths (FR4). Clip files are recorded with their SHA-256
  for provenance

## Performance Assessment

- [x] Async patterns: N/A. Synchronous in-session Blender work
- [x] Caching: N/A
- [x] Resource management: temporary imports, actions, and data blocks are removed in `finally` /
  `_discard`
- [ ] Per-frame retarget calls `view_layer.update()` once per bone per frame. That is fine at
  library clip lengths (rig tests run in under 4 s), but it scales linearly with bones × frames
  (Low, see Remaining Issues)

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1 | Yes (SCN001, SCN002) | Yes (`test_rig_humanoid.py`) | Yes |
| AC2 | Yes (SCN003) | Yes (`test_rig_animation.py`) | Yes |
| AC3 | Yes (SCN004 outline) | Yes (`test_rig_humanoid.py`, `test_rig_animation.py`) | Yes |
| AC4 | Yes (SCN005) | Yes (`test_rig_operators.py`) | Yes |

The steering's Blender add-on layer is tested with pytest in headless Blender (`tests/blender/`),
so each Gherkin scenario maps to a headless test rather than to a pytest-bdd step file.

### Coverage Summary

- Feature file: 5 scenarios (`specs/32-…/feature.gherkin`)
- `test_rig_humanoid.py`: 9 passed
- `test_rig_animation.py`: 7 passed (includes a fresh `--factory-startup` Blender re-import subprocess)
- `test_rig_operators.py`: 5 passed
- `test_addon_registration.py`: 7 passed
- Full `scripts/run-blender-tests.sh` (Blender 5.2.3 LTS): 116 passed, 2 failed. Both failures
  are in `test_coexistence.py`, outside this diff (see Remaining Issues)
- `repository.tests` (`pytest tests/unit tests/bdd`): passed

---

## Exercise Test Results

| Field | Value |
|-------|-------|
| **Reason** | Not applicable. The diff touches no nmg-sdlc `workflows/` or `agents/` files. Plugin-level behavior is covered by the registered `plugin.validate` and `plugin.session-smoke` validations, which passed |
| **Recommendation** | None |

---

## Steering Doc Verification Gates

Manifest-registered validations (authoritative; `.nmg-sdlc/verification/32.json`):

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` | Pass | `uv run pytest tests/unit tests/bdd -q` |
| `repository.lint` | Pass | `uv run ruff check .` |
| `repository.types` | Pass | `uv run mypy src tests` |
| `plugin.validate` | Pass | `claude plugin validate .` |
| `plugin.session-smoke` | Pass | `project.plugin-session-smoke`, expectConnected `blender` |

**Gate Summary**: 5/5 passed, 0 failed, 0 incomplete

Supplementary checks (not manifest-registered):

| Check | Result |
|-------|--------|
| `ruff format --check .` | Pass (161 files already formatted) |
| `scripts/run-blender-tests.sh` | 116 passed, 2 environmental failures in `test_coexistence.py`; every #32 test passes |
| `markdownlint docs/ steering/ *.md` | No project config. Under markdownlint-cli defaults the repo already fails (MD013 line length, CHANGELOG MD024, MD060). The new `docs/rigging-and-animation.md` adds only MD013 hits |

---

## Fixes Applied

None. Verification found no defects in the #32 implementation.

## Remaining Issues

### Low Priority

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Testing (environment) |
| **Location** | `tests/blender/test_coexistence.py:61` |
| **Issue** | `test_both_addons_load` and `test_disabling_nmg_leaves_host_functional` fail. The local Blender user add-ons folder has two copies of the same blender-mcp add-on (`blender_mcp.py` and `blender-mcp-addon.py`, identical size, both dated 2026-10-30). Both register the same `BLENDERMCP_*` classes, so enabling `blender_mcp` collides with the copy that is already enabled (`unregister_class … missing bl_rna`) |
| **Impact** | None on #32. The file and the host add-on detection are unchanged by this diff |
| **Reason Not Fixed** | Host environment outside the repo and outside this verify step's publication scope. Remove the duplicate add-on file from `~/Library/Application Support/Blender/5.2/scripts/addons/` to restore the suite |

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Documentation tooling |
| **Location** | repository root (no `.markdownlint*` config) |
| **Issue** | T006 asks for `markdownlint docs/ steering/ *.md` to pass, but the repo has no project config and the default rules already fail repo-wide |
| **Impact** | A non-registered gate cannot be evaluated as specified |
| **Reason Not Fixed** | Repo-wide pre-existing condition outside #32's scope. Add a project markdownlint config (or register the gate in the manifest) in a follow-up |

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Performance / Error Handling |
| **Location** | `plugins/nmg-game-dev-blender-addon/rig_core/retarget.py` (`_retarget_frame`, `_sample`) |
| **Issue** | One `view_layer.update()` per bone per frame. An unexpected (non-`RigError`) exception during sampling would leave the `__nmg_tmp_<clip>` action assigned to `SK_<Name>` |
| **Impact** | Slower bakes on very long clips. The leak is only possible on unexpected Blender errors |
| **Reason Not Fixed** | Not a spec violation. A follow-up can tighten it |

---

## Positive Observations

- Rig rebuilds are transactional: the previous rig and its vertex groups are set aside and
  restored when a rerun fails the weight check, and a test covers this.
- Every `fallback required` remediation gets the Mixamo note automatically in `outcome.fail`, so
  FR4's wording cannot drift between call sites.
- AC2 is checked in a fresh `--factory-startup` Blender re-import, not only in the session that
  wrote the FBX.

## Recommendations Summary

### Before PR (Must)

- None

### Short Term (Should)

- Remove the duplicate blender-mcp add-on file from the local Blender config so the coexistence
  suite runs green again.
- Add a project markdownlint config.

### Long Term (Could)

- Batch the per-bone depsgraph updates in retargeting and clear the temporary action in a
  `finally`.

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `plugins/nmg-game-dev-blender-addon/rig_core/*.py` | 1 (Low) | |
| `plugins/nmg-game-dev-blender-addon/operators/{rig_humanoid,import_animations,export_rigged,_common}.py` | 0 | |
| `plugins/nmg-game-dev-blender-addon/panels/main_panel.py`, `__init__.py` | 0 | |
| `tests/blender/rig_fixtures.py`, `test_rig_*.py` | 0 | |
| `docs/asset-contract.md`, `docs/rigging-and-animation.md`, `CHANGELOG.md` | 0 | |

---

## Recommendation

**Ready for PR**

Every delivery AC, FR, task, and scenario is implemented and covered by passing headless Blender
tests. The registered gate is complete and green at the verification head. The remaining items
are host-environment or repo-wide tooling conditions outside #32's scope.
