# Verification Report: Add a /model-asset skill that self-reviews Blender modeling with multi-view renders and spatial checks

**Date**: 2026-11-01
**Issue**: #127
**Reviewer**: Claude (nmg-sdlc verify worker, controller run 32da2d4c-0100-441a-bdc0-c56e0ce96516)
**Scope**: Implementation verification against spec
**Verification head**: 6e00e5c65067753fee4e708c3cb36203e3fea217

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 4 |
| Architecture (SOLID) | 4 |
| Security | 5 |
| Performance | 4 |
| Testability | 4 |
| Error Handling | 4 |
| **Overall** | 4.2 |

### Implementation Status: Fail
**Total Issues**: 2 (1 blocking gate failure, 1 medium)

The implementation of the skill, the spatial inspection core, the operator, the API reference, and the docs meets every acceptance criterion in substance. `gate-blender-headless` (SCN003–SCN007), lint, format, types, and `plugin.validate` all pass. The required gate `repository.tests` fails on one test, and two more gates are deferred as a result, so overall status is **Fail**.

The failing test is `tests/unit/test_model_asset_skill.py::test_changelog_unreleased_cites_127`. The delivery commit `6e00e5c` bumped the version to 0.21.0 and moved the #127 CHANGELOG entry from `## [Unreleased]` to `## [0.21.0] - 2026-11-01`. The test still requires the entry under `[Unreleased]`, so it now fails.

---

## Issue Scope

- Active issue: #127
- Spec: `specs/127-add-a-model-asset-skill-that-self-reviews-blender-modeling-with-multi-view-renders-and-spatial-checks`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1–AC8]; FR [FR1–FR7]; tasks [T001–T008]; scenarios [SCN001–SCN008]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":127,"specPath":"specs/127-add-a-model-asset-skill-that-self-reviews-blender-modeling-with-multi-view-renders-and-spatial-checks","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6","AC7","AC8"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6","FR7"],"tasks":["T001","T002","T003","T004","T005","T006","T007","T008"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006","SCN007","SCN008"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Not complete (`repository.tests` failed; `gate-ue-compile` and `plugin.session-smoke` deferred)
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

- Runner: `sdlc-verify-steering.mjs --base main --controller-run-id 32da2d4c-0100-441a-bdc0-c56e0ce96516`
- Artifact: `.nmg-sdlc/verification/127.json`, identity head `6e00e5c65067753fee4e708c3cb36203e3fea217`, clean tree
- Coverage: declared 11, recorded 11, complete true
- Runner ceiling: Incomplete. A required `failed` result caps the report at **Fail**.

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Skill discoverable, declares contract | Pass | `skills/model-asset/SKILL.md:1-7` (`name: model-asset`, one-line description naming freeform + Blender MCP, `required_mcp: [blender]`, `unattended_safe: true`); unit tests SCN001 pass |
| AC2 | Autonomous plan → blockout → inspect → fix loop | Pass | `skills/model-asset/SKILL.md` Flow steps 1–8 in the required order; no approval waits; no asset-type recipe; SCN002 unit tests pass |
| AC3 | Inspection reports relationships, manifoldness, budget | Pass | `plugins/nmg-game-dev-blender-addon/inspect_core/spatial.py:72-142,177-254`; `tests/blender/test_inspect_spatial.py` SCN003 passes under `gate-blender-headless` |
| AC4 | Clean asset passes | Pass | `spatial.py:138,141` (`passed`, `headroom`); SCN004 passes, including the Array-modifier case through evaluated meshes (`spatial.py:147`) |
| AC5 | Structured errors, no changes | Pass | `spatial.py:84-101`; SCN005 passes with a scene-snapshot check |
| AC6 | Callable from the live session; operator | Pass | SKILL.md inspection snippet; `operators/inspect_spatial.py`; registered in `__init__.py` `REGISTER_CLASSES` and the main panel; SCN006 passes |
| AC7 | API reference snippets run headless | Pass | `skills/model-asset/references/blender-api.md` (bmesh, modifiers + apply, Geometry Nodes, shader nodes by type, "Changes since Blender 4.x"); `tests/blender/test_model_asset_api_reference.py` passes under `gate-blender-headless` |
| AC8 | Consumer docs + CHANGELOG | Pass (content) / test Fail | `docs/skills/model-asset.md` covers the loop, fields, blocking rules, and failure codes; `CHANGELOG.md` has the entry, now under `[0.21.0]`. SCN008's changelog test fails because it reads only `[Unreleased]` |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Spatial inspection core | Complete | |
| T002 | Operator and registration | Complete | |
| T003 | Blender API reference | Complete | |
| T004 | model-asset skill | Complete | |
| T005 | Consumer docs and CHANGELOG | Complete | The entry moved to `[0.21.0]` in the delivery version bump |
| T006 | Headless Blender tests | Complete | Pass under `gate-blender-headless` |
| T007 | API reference snippet test | Complete | Pass under `gate-blender-headless` |
| T008 | Skill and docs unit tests | Incomplete | `test_changelog_unreleased_cites_127` fails after the version bump |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 4 | Measurement, pair relation, component grouping, and report shaping are separate functions |
| Open/Closed | 4 | Rules and remediations live in the `INSPECT_RULES` table |
| Liskov Substitution | 5 | N/A; no inheritance beyond the bpy Operator |
| Interface Segregation | 4 | One public entry, `inspect_asset`, re-exported from `inspect_core` |
| Dependency Inversion | 4 | Reuses `geometry_findings`, `triangle_count`, and `resolve_budget` instead of duplicating them |

### Layer Separation

The core lives in the add-on (`inspect_core/`), and the operator is a thin wrapper that stores the result. The skill invokes the core through `execute_blender_code` and opens no sockets. This matches the structure steering.

### Dependency Flow

`inspect_core` → `contract_core` and `utils.budgets`; `operators` → `inspect_core`. No cycles.

---

## Security Assessment

- [x] Authentication: N/A
- [x] Authorization: N/A
- [x] Input validation: asset class and collection are validated before any evaluation
- [x] Injection prevention: no shell or eval in the core
- [x] Data protection: the inspection is read-only; evaluated mesh copies are removed in `finally`

## Performance Assessment

- [x] Resource management: `bmesh.free()` and `meshes.remove()` run in `finally` blocks
- [ ] Pairwise cost: `_relate` is O(parts²) with per-vertex BVH queries, and `_components` is O(n²). This is acceptable for authored assets with tens of parts. Not a finding.

## Error Handling

- Structured `ContractError` with `code`, `message`, and `remediation` for both `inspect.*` codes and budget-override errors.
- Gap: a collection with no mesh parts crashes (see Remaining Issues).

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
| AC7 | Yes (SCN007) | Yes | Yes |
| AC8 | Yes (SCN008) | Yes | **No** (changelog test) |

### Coverage Summary

- `uv run pytest tests/unit tests/bdd -q`: 950 passed, 1 failed
- Headless Blender suite (`scripts/run-blender-tests.sh`): passed

---

## Exercise Test Results

| Field | Value |
|-------|-------|
| **Reason** | The change adds a project skill under `skills/`, not nmg-sdlc `workflows/` or `agents/`. No `/sdlc-*` exercise applies. `plugin.session-smoke` covers plugin load and was deferred by the gate runner. |
| **Recommendation** | Re-run after `repository.tests` passes |

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| repository.tests | **Fail** | command exited 1; `FAILED tests/unit/test_model_asset_skill.py::test_changelog_unreleased_cites_127` (`assert '### Added' in '\n'`) |
| repository.lint | Pass | command exited 0 |
| repository.format | Pass | command exited 0 |
| repository.types | Pass | command exited 0 |
| gate-blender-headless | Pass | command exited 0 |
| gate-ue-compile | Incomplete | deferred until required local validations pass (applies because `nmg-game-dev.uplugin` VersionName changed) |
| gate-mcp-schema | Not applicable | no `mcp-servers/**` change |
| gate-shellcheck | Not applicable | no `scripts/**.sh` change |
| gate-ship-smoke | Not applicable | no ship paths changed |
| plugin.validate | Pass | command exited 0 |
| plugin.session-smoke | Incomplete | deferred until required local validations pass |

**Gate Summary**: 6/8 applicable gates passed, 1 failed, 2 incomplete (3 not applicable)

---

## Fixes Applied

None. The publication scope for this step allows writing only `verification-report.md`, so code and test fixes go back to implementation.

## Remaining Issues

### Critical Issues

| Field | Value |
|-------|-------|
| **Severity** | Critical (blocks the required gate) |
| **Category** | Testing |
| **Location** | `tests/unit/test_model_asset_skill.py:109-115` |
| **Issue** | `test_changelog_unreleased_cites_127` requires the #127 entry under `## [Unreleased]`. The delivery version bump (`6e00e5c`) moved it to `## [0.21.0] - 2026-11-01`, leaving `[Unreleased]` empty. |
| **Impact** | `repository.tests` fails, which defers `gate-ue-compile` and `plugin.session-smoke`. |
| **Suggested fix** | Make the test find the entry in `[Unreleased]` or the newest released section, for example the first `## [` section after `[Unreleased]` that is non-empty, or search the whole changelog for `/model-asset` together with `(#127)` under an `### Added` heading. |
| **Reason Not Fixed** | The verify publication scope permits only the report file. |

### Medium Priority

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Category** | Error Handling |
| **Location** | `plugins/nmg-game-dev-blender-addon/inspect_core/spatial.py:206` |
| **Issue** | When collection `<Name>` exists but holds no mesh parts with vertices, `_components(0, …)` returns `[]` and `min(components, …)` raises a bare `ValueError` instead of returning a report or a structured `inspect.*` error. |
| **Impact** | Running the inspection before the blockout, or on a collection of empties, crashes with an unstructured error. No AC covers this case. |
| **Suggested fix** | Return early from `_findings` when `parts` is empty, or raise a structured `inspect.empty_asset` error that mirrors `render.empty_asset`. |
| **Reason Not Fixed** | Out of verify publication scope; not required by an AC. |

---

## Positive Observations

- Evaluated-mesh copies are always removed, and SCN005 and SCN006 assert the read-only guarantee with scene snapshots.
- Triangle shrinking keeps flush or edge-touching parts from counting as interpenetration.
- The float32 `gap_tolerance` round-trip from the operator is handled explicitly.
- The docs, SKILL.md, and core agree on field names and blocking rules.

## Recommendations Summary

### Before PR (Must)
- [ ] Fix `test_changelog_unreleased_cites_127` so it accepts the released-section entry, then re-run the full registered gate.

### Short Term (Should)
- [ ] Handle a collection with no mesh parts in `inspect_asset`.

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `plugins/nmg-game-dev-blender-addon/inspect_core/spatial.py` | 1 | Empty-collection crash |
| `plugins/nmg-game-dev-blender-addon/operators/inspect_spatial.py` | 0 | |
| `plugins/nmg-game-dev-blender-addon/__init__.py`, `operators/__init__.py`, `panels/main_panel.py` | 0 | |
| `skills/model-asset/SKILL.md` | 0 | |
| `skills/model-asset/references/blender-api.md` | 0 | |
| `docs/skills/model-asset.md` | 0 | |
| `CHANGELOG.md`, `VERSION` | 0 | Entry moved by the version bump |
| `tests/unit/test_model_asset_skill.py` | 1 | Changelog test |
| `tests/blender/*` (inspect, API reference, registration) | 0 | |

## Recommendation

**Needs fixes**

The feature is implemented and its Blender-side acceptance tests pass. One stale unit test fails the required `repository.tests` gate after the version bump. Fix it and re-run the full gate, including the deferred `gate-ue-compile` and `plugin.session-smoke`.
