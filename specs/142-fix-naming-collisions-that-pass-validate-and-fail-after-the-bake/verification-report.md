# Verification Report: Naming collisions pass validate and fail after the bake

**Date**: 2026-11-11
**Issue**: #142
**Reviewer**: Claude (nmg-sdlc verify worker, architecture-reviewer)
**Scope**: Implementation verification against spec

**Verification head**: 0cabb159c5da7537f16927d733c386ee4a63c431

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 4 |
| Security | 5 |
| Performance | 5 |
| Testability | 4 |
| Error Handling | 4 |
| **Overall** | 4.5 |

### Implementation Status: Pass
**Total Issues**: 4 (all low; none block delivery)

All six #142 acceptance criteria are met at head `0cabb15`. That head is the merge of `origin/main` (`50f43f3`) into the issue branch. The full registered gate ran again at this head. Coverage is complete: 11 declared, 11 recorded. 10 validations applied and passed, and 1 (`gate-ship-smoke`) did not apply. The ceiling is `null`.

The fix has three parts:

- The bake moves any image already holding a contract output name aside to `<name>_Src…` before it loads the baked PNG. The output then takes the exact contract name.
- Export names each mesh datablock after its object's export name, then restores every name in the existing `finally`.
- Validate reports `naming.mesh_data` for a mesh datablock that two or more objects of one variant share. The `authored=True` run reports it too.

---

## Issue Scope

- Active issue: #142
- Spec: `specs/142-fix-naming-collisions-that-pass-validate-and-fail-after-the-bake`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1, AC2, AC3, AC4, AC5, AC6]; FR [FR1, FR2, FR3, FR4, FR5, FR6, FR7]; tasks [T001, T002, T003, T004, T005, T006]; scenarios [SCN001, SCN002, SCN003, SCN004, SCN005, SCN006]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":142,"specPath":"specs/142-fix-naming-collisions-that-pass-validate-and-fail-after-the-bake","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6","FR7"],"tasks":["T001","T002","T003","T004","T005","T006"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Bake outputs take the contract names when source images already hold them | Pass | `bake_core/rewire.py` `_free_contract_name` is called first in `_image_node`. `tests/blender/test_bake_unique.py::test_issue142_bake_outputs_take_the_contract_names` checks that the rewired material samples exactly `T_Crate_Body_BC/N/ORM`, and that `validate_asset(..., authored=False)` after variants has no `naming.texture` finding (gate-blender-headless passed) |
| AC2 | Authored materials keep their source images | Pass | `_free_contract_name` renames the holder in place, so its users, pixels and packing stay. The same test asserts that `M_Crate_Body_Authoring` samples `T_Crate_Body_*_Src` with pixels equal to the pre-bake arrays. `_Src2`, `_Src3`, … are used when `_Src` is taken |
| AC3 | Re-running the bake does not accumulate suffixed images | Pass | `test_issue142_repeated_bake_leaves_no_suffixed_contract_image` checks for exactly one image per contract name, no `^T_Crate_Body_(BC|N|ORM)\.\d+$` name, and that `_Src2` exists after the second bake |
| AC4 | Export names mesh datablocks after their objects | Pass | `variants_core/export.py` `_name_meshes` runs on the Desktop objects before the Desktop FBX. Desktop meshes move to temp names with their objects. `_name_meshes` then runs on the Mobile objects after `_unsuffixed`, which covers the static LOD group and the rigged per-LOD jobs (the same object list). Names are restored in reverse in `finally`. `tests/blender/test_variants.py::test_issue142_mesh_datablocks_export_under_their_object_names` re-imports the Desktop and Mobile FBX and asserts `obj.data.name == obj.name`, and that session names are unchanged. `tests/unit/test_unreal_import.py::test_build_import_code_expects_each_desktop_part_under_its_object_name` covers the import side |
| AC5 | A mesh datablock shared between parts is a validate finding | Pass | `contract_core/validate.py` `_shared_mesh_findings` runs per variant. `naming.mesh_data` is not matched by any `_EXPORT_ONLY_RULES` prefix. `contract_core/report.py` has `RULES["naming.mesh_data"]` with the Make Single User > Object & Data remediation. `test_issue142_shared_mesh_data_is_one_naming_finding[True/False]` checks the target, both object names and the remediation |
| AC6 | Existing behavior is preserved | Pass | `_free_contract_name` returns early when no image holds the name. `_name_meshes` skips meshes already named after their object. The new rule fires only on shared datablocks. All existing bake, variants and validate Blender tests pass (252 passed), as do 1129 unit and BDD tests |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Free contract image names before the bake creates its outputs | Complete | `bake_core/rewire.py` |
| T002 | Export mesh datablocks under their objects' export names | Complete | `variants_core/export.py` |
| T003 | Report mesh data shared between parts | Complete | `contract_core/validate.py`, `contract_core/report.py`. The signature is `_shared_mesh_findings(objects)` rather than the design's `(variant, objects)`; the behavior is the same |
| T004 | Document the mesh-data rule | Complete | `docs/asset-contract.md` section 1, two bullets |
| T005 | Blender headless regression tests | Complete | `test_bake_unique.py` (2 tests), `test_variants.py` (1), `test_contract_validate.py` (1, parametrized ×2) |
| T006 | Unit check that the snapshot part maps to the exported mesh name | Complete | `tests/unit/test_unreal_import.py` |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 5 | Each fix is one small private helper in the module that owns the concern: bake rewire, export, and validate |
| Open/Closed | 4 | The new rule plugs into the existing `finding`/`RULES` catalogue. The export rename reuses the `restores` mechanism |
| Liskov Substitution | 4 | N/A, no type hierarchies changed |
| Interface Segregation | 4 | No public API changes |
| Dependency Inversion | 4 | These are Blender cores that use `bpy` directly, as their layer is meant to |

### Layer Separation

Changes stay inside the step-implementation layer (`plugins/nmg-game-dev-blender-addon/*_core/`). The pipeline and MCP layers are untouched. Validate stays read-only: it reports a shared datablock and does not fix it, matching the rejected "permanently rename in validate" alternative.

### Dependency Flow

There are no new imports across cores. `export.py` reuses its own `_to_temp`. `validate.py` reuses `finding`.

---

## Security Assessment

- [x] Authentication: N/A
- [x] Authorization: N/A
- [x] Input validation: names come from Blender datablocks. There is no shell, path or eval use
- [x] Injection prevention: N/A
- [x] Data protection: no credentials touched

---

## Performance Assessment

- [x] Async patterns: N/A, synchronous in background Blender as before
- [x] Caching: the bake cache is unchanged. The repeated-bake test asserts `cache_hit is False` on a forced second run
- [x] Resource management: name freeing is O(k) per output image, where k is the number of existing `_Src` names. Mesh renaming is O(objects)
- [x] Query optimization: dictionary lookups on `bpy.data` collections only

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1 | Yes (SCN001) | Yes (Blender headless test) | Yes |
| AC2 | Yes (SCN002) | Yes | Yes |
| AC3 | Yes (SCN003) | Yes | Yes |
| AC4 | Yes (SCN004) | Yes (+ unit test) | Yes |
| AC5 | Yes (SCN005) | Yes (authored True/False) | Yes |
| AC6 | Yes (SCN006) | Existing suites | Yes |

### Coverage Summary

- Feature file: 6 scenarios, run as Blender headless tests, as `steering/tech.md` specifies for the Blender add-on layer
- New tests: 5 Blender headless test runs and 1 unit test
- `repository.tests`: 1129 passed, 9 skipped
- `gate-blender-headless`: 252 passed

---

## Exercise Test Results

Not applicable. The branch changes no nmg-sdlc `workflows/` or `agents/`. Plugin load was proved by `plugin.validate` and `plugin.session-smoke` (below).

---

## Steering Doc Verification Gates

Artifact: `.nmg-sdlc/verification/142.json` at head `0cabb159c5da7537f16927d733c386ee4a63c431` (tree clean). Coverage is complete (11/11) and the ceiling is `null`.

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` | Pass | `uv run pytest tests/unit tests/bdd -q`: 1129 passed, 9 skipped |
| `repository.lint` | Pass | `uv run ruff check .`: All checks passed |
| `repository.format` | Pass | `uv run ruff format --check .`: 332 files already formatted |
| `repository.types` | Pass | `uv run mypy src tests`: no issues in 210 source files |
| `gate-blender-headless` | Pass | `scripts/run-blender-tests.sh`: 252 passed |
| `gate-ue-compile` | Pass | `DogfoodEditor` compiled against UE 5.8 |
| `gate-mcp-schema` | Pass | MCP tools match `tools.json` for every server |
| `gate-shellcheck` | Pass | `shellcheck -S style` exited 0 |
| `gate-ship-smoke` | Not applicable | No ship paths changed |
| `plugin.validate` | Pass | `claude plugin validate .` passed, with warnings |
| `plugin.session-smoke` | Pass | Plugin loaded with `--plugin-dir`; `nmg-game-dev:blender` connected |

**Gate Summary**: 10/10 applicable gates passed, 0 failed, 0 incomplete (1 not applicable)

---

## Fixes Applied

| Severity | Category | Location | Original Issue | Fix Applied | Routing |
|----------|----------|----------|----------------|-------------|---------|
| — | — | — | None this pass. The verify scope allows writing only this report | — | — |

## Remaining Issues

### Critical Issues
None.

### High Priority
None.

### Medium Priority
None.

### Low Priority

| Severity | Category | Location | Issue | Reason Not Fixed |
|----------|----------|----------|-------|------------------|
| Low | Testing | `tests/blender/test_variants.py` | The AC4 regression uses a parts asset, which exports without a Mobile LOD chain. LOD1 and LOD2 mesh naming and the rigged per-LOD files are covered by the code path (`_name_meshes(mobile_objects)` runs over every Mobile object before any Mobile FBX), not by a dedicated re-import assertion | Behavior is correct by construction. A follow-up test could add a rigged or LOD-chain case |
| Low | Resource management | `tests/blender/_runner.py` `_install_addon_link` | `tempfile.mkdtemp` creates one private add-on link directory per run and never removes it | Test-only. It holds one symlink, and the OS clears it from the temp directory |
| Low | Spec drift | `contract_core/validate.py` `_shared_mesh_findings` | The signature takes only `objects`, not the design's `(variant, objects)` | Behavior matches AC5; the variant is implicit in the per-variant call |
| Low | Scope | `steering/extensions/plugin-session-smoke.mjs`, `tests/blender/_runner.py`, `tests/bdd/steps/test_scaffold.py` | The branch carries gate-infrastructure repairs that are not in the spec's Changes table: trust-dialog handling after `herdr agent start`, a per-checkout add-on link for headless Blender, and launcher timing isolated from the plugin scan | These were needed to get the registered gate green in a multi-lane host. They are self-contained and pass every gate |

---

## Positive Observations

- Both renames follow the same idea: move the current holder aside, then take the exact name. Everything is restored in reverse in the existing `finally`, so the session is never left changed, even when export raises.
- Validate reports the shared datablock and leaves it unchanged, consistent with validate staying read-only.
- The tests check pixel-level preservation of the authored sources, not just their names.

---

## Recommendations Summary

### Before PR (Must)
- None.

### Short Term (Should)
- [ ] Add a LOD-chain or rigged-Mobile case to the AC4 re-import test.

### Long Term (Could)
- [ ] Clean up the `_runner.py` temp link directory at exit.

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `plugins/nmg-game-dev-blender-addon/bake_core/rewire.py` | 0 | `_free_contract_name` |
| `plugins/nmg-game-dev-blender-addon/variants_core/export.py` | 0 | `_name_meshes`, Desktop mesh temp rename |
| `plugins/nmg-game-dev-blender-addon/contract_core/validate.py` | 1 | Signature drift only |
| `plugins/nmg-game-dev-blender-addon/contract_core/report.py` | 0 | `RULES["naming.mesh_data"]` |
| `docs/asset-contract.md` | 0 | FR7 |
| `tests/blender/test_bake_unique.py`, `test_variants.py`, `test_contract_validate.py` | 1 | LOD-chain coverage gap |
| `tests/unit/test_unreal_import.py` | 0 | T006 |
| `tests/blender/_runner.py`, `tests/bdd/steps/test_scaffold.py`, `steering/extensions/plugin-session-smoke.mjs` | 2 | Gate-infrastructure repairs |
| `CHANGELOG.md` | 0 | Entry under `[Unreleased]` / Fixed |

---

## Recommendation

**Ready for PR**

Every delivery AC, FR and task is implemented and tested. The full registered gate passed at the exact head `0cabb159c5da7537f16927d733c386ee4a63c431`, with complete coverage and no ceiling. The remaining items are low-severity follow-ups.
