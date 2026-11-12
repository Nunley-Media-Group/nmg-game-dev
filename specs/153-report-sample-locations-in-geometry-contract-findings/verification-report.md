# Verification Report: Report sample locations in geometry contract findings

**Date**: 2026-11-11
**Issue**: #153
**Reviewer**: Claude (nmg-sdlc architecture-reviewer, verify worker)
**Scope**: Implementation verification against spec

**Verification head**: dc0bc756494114338caaa790cf3737991345ab4c

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
**Total Issues**: 3 (all Low, not blocking)

`geometry_findings` collects the offending elements for each of the four geometry rules. Each finding gets `count` (the full total) and `samples`: up to 5 lowest-index elements, each with its world-space position and vertex-group names, plus `coincides_with` for duplicates. Both callers, contract validation and the spatial inspector, pass the object's world matrix and vertex-group names, and they keep deform layers on the evaluated copy. Detection and `passed` are unchanged.

This re-verification runs at head `dc0bc75`. Deliver's base reconciliation merged `origin/main` at `622181d` into the branch. That brought in #208 (texture generation from the plugin root, plus queued and batched texture jobs) and #210 (`gate-ue-compile` now builds with `-NoUBA`). The earlier deliver attempt stopped because the reconciled head no longer matched the verified head `c4fc67d`. The repair is a fresh run of the full registered gate at the new head, not a replay of the earlier evidence. `git diff c4fc67d dc0bc75` shows no change under `plugins/nmg-game-dev-blender-addon/`, `tests/blender/`, or `docs/skills/`, so #153's implementation is byte-identical to the version verified before. Against `origin/main`, the branch diff is still only #153's files and the version bump to 0.23.0. All 11 registered validations recorded terminal results at the verification head: 10 passed and 1 did not apply to this change.

---

## Issue Scope

- Active issue: #153
- Spec: `specs/153-report-sample-locations-in-geometry-contract-findings`
- Manifest: `implicit single issue`
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1, AC2, AC3, AC4, AC5, AC6, AC7]; FR [FR1, FR2, FR3, FR4, FR5, FR6, FR7]; tasks [T001, T002, T003, T004]; scenarios [SCN001, SCN002, SCN003, SCN004, SCN005, SCN006, SCN007]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":153,"specPath":"specs/153-report-sample-locations-in-geometry-contract-findings","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6","AC7"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6","FR7"],"tasks":["T001","T002","T003","T004"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006","SCN007"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

- Artifact: `.nmg-sdlc/verification/153.json` (from `sdlc-verify-steering.mjs --base main --controller-run-id 36e69283-b400-4e48-9fde-c558720014fd`, generated 2026-11-12T05:46:25Z)
- Identity: head `dc0bc756494114338caaa790cf3737991345ab4c`, tree clean, spec hash `sha256:d37c7240…`, steering hash `sha256:6db9aabc…` (changed by #210's `-NoUBA` edit to `steering/extensions/ue-compile.mjs` and `project-tech.md`)
- Coverage: declared 11, recorded 11, complete `true`; no missing, duplicate, or unknown results
- Ceiling: none

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | The duplicate-vertex finding locates duplicates (world position, index, `coincides_with`, both boxes' groups) | Pass | `contract_core/geometry.py` `_duplicate_sample` (the pairs come from `find_doubles` `targetmap`, sorted by duplicate index; the groups are the union of both vertices). `tests/blender/test_contract_validate.py::test_scn001_duplicate_samples_locate_the_shared_vertex` uses a translated, rotated, and scaled object: count 1, index 8, `coincides_with` 7, `["Lower", "Upper"]`, position = `matrix_world @ co` within 1e-5 |
| AC2 | The zero-area and normals findings give face index, world face center, and groups | Pass | `_face_sample` uses `matrix_world @ face.calc_center_median()` and the groups of the face's vertices. After the merge with #144, `_normal_violations` returns the flagged faces sorted by index: each open island's minority faces from `_winding_violations` and each closed island's turned faces from `_outward_violations`. The count is the list's length, so the totals match #144's. `test_scn002_face_samples_locate_zero_area_and_flipped_faces` |
| AC3 | The loose-vertex finding locates the vertices | Pass | `_vertex_sample`; `test_scn003_loose_samples_locate_the_vertices` (indices [8, 9], world positions, `["Stray"]`) |
| AC4 | Samples are capped at 5 and deterministic | Pass | `SAMPLE_LIMIT = 5`. Offending lists follow bmesh index order and duplicate pairs are sorted explicitly. `test_scn004_samples_are_capped_at_the_five_lowest_indices`: count 7, samples [8..12], identical across two runs |
| AC5 | Elements outside any vertex group get an empty group list | Pass | `_group_names` returns `[]` when the mesh has no deform layer. `test_scn005_samples_without_vertex_groups_have_empty_group_lists` also checks that the full key set is present |
| AC6 | The spatial inspector carries the same detail | Pass | `inspect_core/spatial.py::_measure` passes `obj.matrix_world` and the group names, and keeps the deform layers. `tests/blender/test_inspect_spatial.py::test_scn006_part_geometry_matches_contract_validation` compares `count` and `samples` for every part against `validate_asset` on a transformed part |
| AC7 | Clean meshes are unchanged | Pass | Findings are emitted only for non-empty offending lists. `test_scn007_clean_mesh_emits_no_geometry_findings` (contract) and `test_scn007_clean_part_has_no_geometry_findings` (inspector) both find `passed` is True and no geometry entries |

### Functional Requirements

| FR | Status | Evidence |
|----|--------|----------|
| FR1 | Pass | `_located` returns `finding(...)` merged with `{"count", "samples"}`, keeping `rule`, `target`, `message`, and `remediation` (SCN005 asserts the key set) |
| FR2 | Pass | Samples carry `index`, `position` (3 floats rounded to 6 places), and sorted unique `vertex_groups` |
| FR3 | Pass | `coincides_with` is set and the groups cover both vertices of the pair |
| FR4 | Pass | The cap is 5 and the lowest indices come first |
| FR5 | Pass | The message keeps the count and appends `; first at (x, y, z).` with 4 decimals (asserted in SCN001) |
| FR6 | Pass | The inspector makes the same call as contract validation (SCN006) |
| FR7 | Pass | `docs/skills/model-asset.md` documents `count`, `samples`, each sample field, and the cap of 5 lowest indices |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Located samples in geometry findings | Complete | `contract_core/geometry.py`. Positional `(name, mesh)` calls still work because the new parameters default to identity and no groups |
| T002 | Pass world matrix and group names from both callers | Complete | `validate.py::_mesh_findings`, `texel.evaluated_copy` (which replaced #153's `_evaluated_copy` in the merge with #151), and `spatial.py::_measure`. Both copies use `preserve_all_data_layers=True`, and annotations widen to `dict[str, Any]` |
| T003 | Documentation | Complete | `docs/skills/model-asset.md` |
| T004 | Blender tests | Complete | SCN001–SCN005 and SCN007 are in `tests/blender/test_contract_validate.py`; SCN006 and the inspector's SCN007 are in `tests/blender/test_inspect_spatial.py`. All ran under `gate-blender-headless` (headless background Blender, no live session) |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 5 | Detection stays in `geometry_findings`. Sample construction (`_vertex_sample`, `_face_sample`, `_duplicate_sample`), position formatting, group resolution, and message assembly (`_located`) are small single-purpose helpers |
| Open/Closed | 5 | The change only adds fields. The `finding()` shape and `report.py` are untouched, and existing consumers keep working |
| Liskov Substitution | 5 | N/A (no class hierarchy). The widened return type stays compatible for callers |
| Interface Segregation | 5 | The core takes the matrix and a list of group names, not the `bpy.types.Object`, so it stays independent of the scene |
| Dependency Inversion | 5 | The caller supplies the transform and group names, and both callers share one implementation |

### Layer Separation

The change stays inside the Blender add-on's headless-safe `contract_core` and `inspect_core`, which matches the structure steering for step implementations. The geometry module still touches no scene state: it reads only the mesh the caller owns and the values passed in.

### Dependency Flow

`inspect_core.spatial` → `contract_core.geometry` was an existing dependency direction and is unchanged. No new cross-module imports beyond `mathutils`, which is already available in Blender.

---

## Security Assessment

No external input, credentials, network, file I/O, or shell. The new data comes from mesh geometry and vertex-group names and is serialized as plain JSON.

- [x] Authentication: N/A
- [x] Authorization: N/A
- [x] Input validation: an out-of-range deform group index is ignored and does not raise an `IndexError`
- [x] Injection prevention: N/A (no command or query construction)
- [x] Data protection: N/A

---

## Performance Assessment

- [x] Async patterns: N/A (synchronous bmesh pass, same as before)
- [x] Caching: N/A
- [x] Resource management: the bmesh is still freed in `finally`. The evaluated copies are still removed by their callers. `preserve_all_data_layers=True` adds deform and other custom layers to each temporary copy: a small, bounded memory cost per checked object
- [x] Query optimization: detection stays a linear pass per rule. Building samples is bounded at 5 per rule, and the duplicate sort is O(d log d) on the duplicate count only

---

## Error Handling Assessment

- `_located` indexes `samples[0]`. It is safe only because each call site guards on a non-empty offending list, and that precondition is implicit (Low, see Remaining Issues).
- `_group_names` silently drops group indices outside `group_names`. That is defensive and reasonable, but the omission is not reported (Low).

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1 | Yes (SCN001) | Yes (`test_scn001_*`) | Yes |
| AC2 | Yes (SCN002) | Yes (`test_scn002_*`) | Yes |
| AC3 | Yes (SCN003) | Yes (`test_scn003_*`) | Yes |
| AC4 | Yes (SCN004) | Yes (`test_scn004_*`) | Yes |
| AC5 | Yes (SCN005) | Yes (`test_scn005_*`) | Yes |
| AC6 | Yes (SCN006) | Yes (`test_scn006_*`) | Yes |
| AC7 | Yes (SCN007) | Yes (`test_scn007_*` x2) | Yes |

### Coverage Summary

- Feature file: `specs/153-report-sample-locations-in-geometry-contract-findings/feature.gherkin`, 7 scenarios, all tagged and mapped to headless Blender tests (the tech steering puts Blender add-on acceptance tests in `tests/blender/`)
- Blender headless suite: 292 passed, 4 skipped (`gate-blender-headless`). The 4 skips are the host-add-on tests in `tests/blender/test_coexistence.py`, which do not touch #153
- #144's normals tests in `tests/blender/test_geometry_normals.py` still pass. They compare each message without the location suffix, check that the count is in the message, and check the flagged face's sample index
- Python unit and BDD suites: 1272 passed, 10 skipped (`repository.tests`; the count now includes #208's merged texture tests)
- No live Blender or Unreal editor was used

---

## Exercise Test Results

Exercise testing was not applicable. The change touches no nmg-sdlc plugin `workflows/` or `agents/` paths. `plugin.validate` and `plugin.session-smoke` still checked this repo's Claude Code plugin surface.

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` | Pass | `uv run pytest tests/unit tests/bdd -q`: 1272 passed, 10 skipped |
| `repository.lint` | Pass | `uv run ruff check .`: All checks passed |
| `repository.format` | Pass | `uv run ruff format --check .`: 358 files already formatted |
| `repository.types` | Pass | `uv run mypy src tests`: no issues found in 234 source files |
| `gate-blender-headless` | Pass | `scripts/run-blender-tests.sh`: 292 passed, 4 skipped (host-only coexistence tests) |
| `gate-ue-compile` | Pass | `Build.sh DogfoodEditor Mac Development -WaitMutex -NoUBA` (the gate as changed by #210): compiled `DogfoodEditor` against `/Users/Shared/Epic Games/UE_5.8`. The gate applies because the version bump changes the `.uplugin` file |
| `gate-mcp-schema` | Pass | `uv run python scripts/validate-mcp-tools.py`: MCP tools match tools.json for every server. The gate applies because the runner diffs against local `main`, which is behind `origin/main`, so MCP changes other lanes merged count as changed paths |
| `gate-shellcheck` | Pass | `find scripts -name *.sh -exec shellcheck -S style {} +` exited 0. The gate applies for the same base-ref reason |
| `gate-ship-smoke` | Not applicable | No ship paths changed |
| `plugin.validate` | Pass | `claude plugin validate .` exited 0 (passed with warnings) |
| `plugin.session-smoke` | Pass | Real Herdr smoke: plugin loaded via `--plugin-dir` in an ephemeral project; `nmg-game-dev:blender` connected; tab closed afterwards |

**Gate Summary**: 10/10 applicable gates passed, 0 failed, 0 incomplete; 1 not applicable (`gate-ship-smoke`). Coverage complete (11/11 recorded).

---

## Fixes Applied

None. Verification found no defects that needed a code change.

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
| **Location** | `plugins/nmg-game-dev-blender-addon/contract_core/geometry.py` (`_located`) |
| **Issue** | `_located` reads `samples[0]` and relies on every caller passing a non-empty list |
| **Impact** | None today: all four call sites guard on a non-empty offending list. A future rule added without that guard would raise `IndexError` |
| **Reason Not Fixed** | Correct as written, and outside the spec's acceptance surface. An optional hardening |

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Testing |
| **Location** | `tests/blender/test_contract_validate.py::_geometry`, `tests/blender/test_inspect_spatial.py::_contract_geometry` |
| **Issue** | Two identical helpers that filter geometry findings by target |
| **Impact** | Minor duplication in test code only |
| **Reason Not Fixed** | Cosmetic. Could move into a shared fixture module later |

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Documentation |
| **Location** | `CHANGELOG.md` (`## [0.23.0]` section) |
| **Issue** | The base reconciliation's auto-merge left no blank line between this issue's `- Report sample locations ... (#153)` entry and main's `## [0.21.6]` heading. Main's own CHANGELOG already has out-of-order and adjacent headings (`## [0.21.6]` above `## [0.22.0]`, which sits directly on `## [0.21.5]`) |
| **Impact** | Cosmetic. The Markdown renders correctly, and the version files agree on 0.23.0 |
| **Reason Not Fixed** | `CHANGELOG.md` is outside the verify publication scope, which allows writing only `verification-report.md`. Deliver's prepare-version step owns the CHANGELOG |

---

## Positive Observations

- The change only adds fields. Signature defaults keep `(name, mesh)` callers working, and `finding()` and `report.py` are unchanged.
- Determinism is explicit: duplicate pairs are sorted by index, and the other lists follow bmesh index order.
- The tests use non-identity transforms (translated, rotated, and scaled), so they would catch a local-space position.
- SCN006 checks the inspector against contract validation part by part, instead of repeating literal expectations.

---

## Recommendations Summary

### Before PR (Must)
- None.

### Short Term (Should)
- None.

### Long Term (Could)
- [ ] Make the non-empty precondition of `_located` explicit, or derive the message position defensively.
- [ ] Share the geometry-findings test helper between the two Blender test modules.

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `plugins/nmg-game-dev-blender-addon/contract_core/geometry.py` | 1 (Low) | Core change |
| `plugins/nmg-game-dev-blender-addon/contract_core/validate.py` | 0 | Caller passes the world matrix and group names |
| `plugins/nmg-game-dev-blender-addon/contract_core/texel.py` | 0 | `evaluated_copy` keeps all data layers |
| `tests/blender/test_geometry_normals.py` | 0 | #144's tests adjusted for the location suffix and the sample indices |
| `plugins/nmg-game-dev-blender-addon/inspect_core/spatial.py` | 0 | Caller and evaluated copy keep their deform layers |
| `docs/skills/model-asset.md` | 0 | FR7 |
| `tests/blender/test_contract_validate.py` | 1 (Low) | SCN001–SCN005, SCN007 |
| `tests/blender/test_inspect_spatial.py` | 0 | SCN006, SCN007 |
| `CHANGELOG.md`, `VERSION`, `.claude-plugin/plugin.json`, `blender_manifest.toml`, `nmg-game-dev.uplugin` | 1 (Low) | Version 0.23.0 (minor; main is at 0.22.0); the merge added a CHANGELOG spacing nit |

---

## Recommendation

**Ready for PR**

All 7 acceptance criteria, 7 functional requirements, and 4 tasks are implemented and covered by passing headless Blender tests. Every applicable registered gate passed at head `dc0bc756494114338caaa790cf3737991345ab4c`, after base reconciliation with `origin/main` `622181d` (#208, #210), with complete coverage. The three remaining findings are Low and do not block.
