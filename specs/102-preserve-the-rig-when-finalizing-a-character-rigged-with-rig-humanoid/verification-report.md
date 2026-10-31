# Verification Report: Finalize keeps the rig of a character rigged with rig_humanoid

**Date**: 2026-10-31
**Issue**: #102
**Reviewer**: Claude (nmg-sdlc verify worker)
**Scope**: Implementation verification against spec

**Verification head**: ff63bce75580f470bfafd0c76d55479ce4207950

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 4 |
| Security | 5 |
| Performance | 4 |
| Testability | 4 |
| Error Handling | 4 |
| **Overall** | 4.3 |

### Implementation Status: Pass
**Total Issues**: 1 (Low, informational; no blocker)

All five acceptance criteria are implemented and covered by tests. Variant cleanup now keeps the
Armature modifier and the vertex groups. Desktop exports one skinned FBX. Mobile builds three skinned
LODs from the rest mesh and writes one FBX per LOD. The re-import check loads every LOD file and
reports `reimport.skin_missing`. UE import code takes a Skeletal Mesh path that reuses the Desktop
skeleton and physics asset for Mobile. All five manifest-registered validations passed at the
verification head. The Blender headless suite (`gate-blender-headless`) passed 148/148.

---

## Issue Scope

- Active issue: #102
- Spec: `specs/102-preserve-the-rig-when-finalizing-a-character-rigged-with-rig-humanoid`
- Manifest: `implicit single issue`
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1, AC2, AC3, AC4, AC5]; FR [FR1, FR2, FR3, FR4, FR5]; tasks [T001, T002, T003, T004, T005, T006]; scenarios [SCN001, SCN002, SCN003, SCN004, SCN005]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":102,"specPath":"specs/102-preserve-the-rig-when-finalizing-a-character-rigged-with-rig-humanoid","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5"],"tasks":["T001","T002","T003","T004","T005","T006"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

`sdlc-verify-steering.mjs --issue 102 --base main --controller-run-id 1d8c53d8-6b3c-4e22-a1d5-e8a4c8a68d96` → `ok: true`, `ceiling: null`.
`.nmg-sdlc/verification/102.json` coverage: declared 5, recorded 5, `complete: true`, no missing, duplicate, or unknown results. Every result is bound to head `ff63bce`, clean tree.

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Desktop rigged export and import | Pass | Skin kept through cleanup: `variants_core/cleanup.py` `_apply_modifiers`/`_is_rig_skin`. Desktop exported with `_RIG_FBX_OPTIONS` and the rig renamed `Armature`: `variants_core/export.py`. Skeletal import with `create_physics_asset`, `import_animations=False`, and `MI_` binding on skeletal slots: `src/nmg_game_dev/unreal/import_asset.py` `_skeletal_options`, `_import_skeletal`, `_bind_materials`. Tests: `tests/blender/test_variants_rigged.py` (FBX re-imported: `Armature`, 26 bones, skinned mesh); `tests/unit/test_unreal_import.py` |
| AC2 | Mobile rigged LODs | Pass | Rigged LOD chain built from the rest mesh (LOD1 at `lod0//2`, LOD2 at `lod0//4`), each mesh parented and skinned to `SK_<Name>`: `variants_core/mobile.py` `_build_rigged_chain`, `_bind_to_rig`. One FBX per LOD: `export.py` `_rigged_mobile_jobs`. Mobile skeleton and physics asset reused from `skeleton_dest`, LODs added with `SkeletalMeshEditorSubsystem.import_lod`: `import_asset.py`. Engine passes the Desktop destination and imports Desktop first: `pipeline/engine.py`. Tests: `test_variants_rigged.py` (three files, LOD ratios), `test_unreal_import.py`, `tests/unit/pipeline/test_engine.py` |
| AC3 | Cleanup keeps the skin | Pass | `cleanup.py`: non-skin modifiers are applied; the Armature modifier on `SK_<Name>` and the vertex groups stay; the rest mesh is evaluated with the skin hidden. Test: `test_variants_rigged.py` (AC3 case) |
| AC4 | Unrigged assets unchanged | Pass | `rig is None` keeps `_FBX_OPTIONS`, the single Mobile FBX, `_build_lod_group`, and `import_as_skeletal = False` / the static path. Tests: existing `tests/blender/test_variants.py` and `test_contract_reimport.py` pass; `test_unreal_import.py` unrigged case |
| AC5 | Re-import check covers rigged variants | Pass | `contract_core/reimport.py` `_variant_fbx_files` (imports LOD1/LOD2 when present) and `_skin_findings`; `reimport.skin_missing` remediation added in `contract_core/report.py`. Test: `tests/blender/test_contract_reimport.py` (rigged pass + skin-missing) |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Keep skin through cleanup; skinned Mobile LODs | Complete | `assets.asset_armature`, `cleanup.py`, `mobile.py` |
| T002 | Skinned Desktop + per-LOD Mobile FBX | Complete | Rig name restored in `finally`. `variants.armature_name_taken` is raised before any write (also checked in `generate_variants`). Sidecar `rigged` + `mobile.lod_files` |
| T003 | Re-import check for rigged variants | Complete | |
| T004 | UE Skeletal Mesh import | Complete | `skeleton_dest` wired; `_STEP_VERSION = "3"`; `check_pivots` matches `skeletal_meshes` and skips rigged `_LOD[1-9]` |
| T005 | Docs | Complete | `docs/asset-contract.md` §5 and §7 updated; the #33 deferral sentence removed. The CHANGELOG Fixed bullet ends with `(#102)`. The delivery version bump moved it from `[Unreleased]` into `[0.15.2]` |
| T006 | Regression coverage | Complete | All listed test files exist and pass |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 4 | Rig detection lives once in `asset_armature`. Cleanup, Mobile build, export, and re-import each handle only their own part. `import_asset.py` keeps growing as one large generated-code template |
| Open/Closed | 4 | The rigged path branches off `rig is None` and leaves the static path unchanged |
| Liskov Substitution | 5 | N/A — no new hierarchies |
| Interface Segregation | 4 | `skeleton_dest` is an optional keyword, so existing callers are unaffected |
| Dependency Inversion | 4 | UE access still goes through the injected client protocol |

### Layer Separation

Steps stay in the step-implementation layers (`variants_core`, `contract_core`, `src/nmg_game_dev/unreal`). The pipeline engine only computes `skeleton_dest`. No skill touches MCP sockets.

### Dependency Flow

Unchanged. The pipeline depends on the unreal step module, and the Blender cores stay headless-safe.

---

## Security Assessment

- [x] Authentication: N/A
- [x] Authorization: N/A
- [x] Input validation: params are JSON-encoded into the UE template (`json.dumps` twice), so no code injection from asset names
- [x] Injection prevention: same as above; no shell use
- [x] Data protection: no secrets touched

## Performance Assessment

- [x] Async patterns: unchanged; long Blender work still runs in background jobs
- [x] Caching: `_STEP_VERSION` bumped to invalidate results cached before rigging was supported
- [x] Resource management: export renames are restored in `finally`; modifier visibility is restored in `finally`
- [x] Query optimization: N/A. Two extra decimations per rigged Mobile asset fit the character budget

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

### Coverage Summary

- Feature files: `tests/bdd/features/rigged_finalize.feature` (5 scenarios), bound in `tests/bdd/test_rigged_finalize_bdd.py`
- Step definitions: Implemented
- Unit + BDD: `uv run pytest tests/unit tests/bdd -q` — passed (registered `repository.tests`)
- Blender headless: `scripts/run-blender-tests.sh` — **148 passed**, 0 failed (80.9 s). It ran against this checkout: the user add-on path is a symlink to `plugins/nmg-game-dev-blender-addon`
- Live UE API probe (read-only, UE 5.8 editor via the Unreal MCP): confirmed that the APIs the generated code uses exist. Checked: `FbxImportUI.{import_as_skeletal, mesh_type_to_import, import_animations, create_physics_asset, skeleton, physics_asset}`, `FBXImportType.FBXIT_SKELETAL_MESH`, `SkeletalMeshEditorSubsystem.import_lod`, `SkeletalMesh.get_bounds`, and `SkeletalMaterial.{material_interface, material_slot_name}`

---

## Exercise Test Results

| Field | Value |
|-------|-------|
| **Reason** | Not applicable. The diff does not touch `workflows/` or `agents/` (nmg-sdlc plugin skill files), so exercise testing is not triggered |
| **Recommendation** | None |

---

## Steering Doc Verification Gates

Manifest-registered validations (`.nmg-sdlc/verification/102.json`):

| Gate | Status | Evidence |
|------|--------|----------|
| repository.tests | Pass | `uv run pytest tests/unit tests/bdd -q` at ff63bce |
| repository.lint | Pass | `uv run ruff check .` |
| repository.types | Pass | `uv run mypy src tests` |
| plugin.validate | Pass | `claude plugin validate .` |
| plugin.session-smoke | Pass | project.plugin-session-smoke, `expectConnected: [blender]` |

Prose gates in tech steering that apply to this diff, run in addition:

| Gate | Status | Evidence |
|------|--------|----------|
| gate-blender-headless | Pass | `scripts/run-blender-tests.sh` → 148 passed |
| gate-python-lint / types / unit / bdd | Pass | Covered by the registered results above |
| gate-ue-automation, gate-mcp-schema, gate-shellcheck, gate-ship-smoke | N/A | Diff touches no UE C++, `mcp-servers/`, `*.sh`, or ship/build skills |

**Gate Summary**: 5/5 registered passed, 0 failed, 0 incomplete

---

## Fixes Applied

| Severity | Category | Location | Original Issue | Fix Applied | Routing |
|----------|----------|----------|----------------|-------------|---------|
| — | — | — | None needed | — | — |

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
| **Category** | Testing |
| **Location** | `src/nmg_game_dev/unreal/import_asset.py` |
| **Issue** | The UE Skeletal Mesh import (AC1/AC2 UE half) is checked against the generated code with a fake client, plus a live API-existence probe. A full end-to-end `finalize_asset` of a rigged character into the running editor was not run in this verification |
| **Impact** | Runtime-only UE behavior is not proven by a full run, such as the `import_lod` slot order or the struct write-back of skeletal material slots |
| **Reason Not Fixed** | The approved T006 defines unit and fake-client coverage for the UE side. A live end-to-end run is a recommended manual follow-up, not a blocker |

---

## Positive Observations

- The rig rename is restored in `finally`, and a name clash fails before any file is written.
- Mobile LODs are built from the undeformed rest mesh, so no pose is baked into the Mobile copy.
- `_copy_vertex_groups` avoids doubling groups when the copied mesh already carries the names.
- The step-version bump keeps results cached before rigging was supported from being reused.

---

## Recommendations Summary

### Before PR (Must)
- (none)

### Short Term (Should)
- [ ] Run one live `finalize_asset` of a `rig_humanoid` character into UE 5.8, then confirm Mobile shows 3 LODs on the Desktop skeleton.

### Long Term (Could)
- [ ] Split `import_asset.py`'s UE template into static and skeletal sections or files as it grows.

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| plugins/nmg-game-dev-blender-addon/variants_core/{assets,cleanup,mobile,export,__init__}.py | 0 | |
| plugins/nmg-game-dev-blender-addon/contract_core/{reimport,report}.py | 0 | |
| src/nmg_game_dev/unreal/import_asset.py | 1 (Low) | live E2E not run |
| src/nmg_game_dev/pipeline/{engine,steps}.py | 0 | |
| docs/asset-contract.md, CHANGELOG.md | 0 | |
| tests/** (new/changed) | 0 | |

---

## Recommendation

**Ready for PR**

Every AC, FR, task, and scenario is implemented and tested, and every registered validation passed at the exact verification head. The Blender headless gate passed, and the UE APIs the import code uses exist in the running UE 5.8 editor.
