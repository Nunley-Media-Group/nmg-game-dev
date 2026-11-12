# Verification Report: Reduce a generated high-poly asset to its Desktop budget and bake its look onto the reduced mesh

**Date**: 2026-11-12
**Issue**: #139
**Reviewer**: Claude (nmg-sdlc architecture-reviewer, verify worker)
**Scope**: Implementation verification against spec
**Verification head**: 2e1acd70c2b9269c2e64439a679e82bb70b7063e

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
**Total Issues**: 5 (0 critical, 0 high, 1 medium, 4 low). None blocks delivery.

All 14 acceptance criteria, 12 functional requirements and 7 tasks are implemented. This is a re-verification after the branch merged `origin/main` again (`34dd816`, bringing in #186 for #148, material variants), kept #148's `material_variant.*` remediation line in `skills/finalize-asset/SKILL.md` (`2d91c0e`), and bumped the version to 0.24.0 (`2e1acd7`). The merge conflicts were all in shared entry-point files: `finalize_mcp/server.py`, `finalize/__init__.py`, `finalize/__main__.py`, `finalize/mcp_tools.py` and `skills/finalize-asset/SKILL.md`. Each was resolved as a union. `reduce_asset` and `list_material_variants` are both registered on the server, exported from the package, listed in `tools.json`, and given CLI subcommands, and `gate-mcp-schema` passed. No file under `reduce_core/` or `bake_core/`, no reduce host module and no reduce test changed since the previous verification. The registered gate ran at the verification head with complete coverage: 11 validations declared, 11 recorded. Ten required validations passed, including 1381 unit and BDD tests and 350 headless Blender tests, which cover the reduce suites alongside #148's material-variant suites. `gate-ship-smoke` does not apply because the change touches none of its paths. The ceiling is `null`.

---

## Issue Scope

- Active issue: #139
- Spec: `specs/139-add-a-reduce-to-budget-step-that-bakes-a-generated-high-poly-asset-onto-an-in-budget-mesh`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1–AC14]; FR [FR1–FR12]; tasks [T001–T007]; scenarios [SCN001–SCN012]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":139,"specPath":"specs/139-add-a-reduce-to-budget-step-that-bakes-a-generated-high-poly-asset-onto-an-in-budget-mesh","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6","AC7","AC8","AC9","AC10","AC11","AC12","AC13","AC14"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6","FR7","FR8","FR9","FR10","FR11","FR12"],"tasks":["T001","T002","T003","T004","T005","T006","T007"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006","SCN007","SCN008","SCN009","SCN010","SCN011","SCN012"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

- Artifact: `.nmg-sdlc/verification/139.json` (from `sdlc-verify-steering.mjs --base main`, controller run `b2903612-167d-4d93-93fe-3faef18dd9c1`, generated 2026-11-12T06:40:27Z)
- Identity: head `2e1acd70c2b9269c2e64439a679e82bb70b7063e`, clean tree, spec `sha256:2dc809e4…c605`, steering `sha256:6db9aabc…74d4`
- Coverage: declared 11, recorded 11, complete `true`; nothing missing, duplicated or unknown
- Ceiling: `null`. No required validation failed or was incomplete.

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Over-budget asset reduced to the Desktop budget; names, transforms, origins and parents kept | Pass | `reduce_core/core.py` (`_reduce`, `split_budget` → `decimate.fit_copy`, `reduce.unreachable_target` guard); `reduce_core/decimate.py` (`make_copy`, `link_parent`); `commit.py` renames copies to part names. Tested in `tests/blender/test_reduce.py::test_over_budget_asset_reduces_into_budget_with_names_and_parents` (matrices, parents, total ≤ 3,000 with an `nmg-budgets.json` override) |
| AC2 | Originals in hidden top-level `<Name>_High`, `<object>_High`, never validated, hashed or exported | Pass | `reduce_core/commit.py::_move_to_high` with `hide_viewport` and `hide_render`; validate, hash and export read only `<Name>`/`<Name>_Mobile`. Tested: `_High` flags, contents and names, hash unchanged after a `_High` edit, validate snapshot, and the export pre-report has no `_High` in `test_reduce_finalize.py::_finalize_chain` |
| AC3 | Area-proportional split, at least 12 triangles per part, in-target parts not decimated, per-part report | Pass | `reduce_core/plan.py::split_budget` (area weights, `min_part_tris` 12, source cap, excess redistribution); `decimate.fit_copy` skips decimation when at or below target. Tested in `tests/unit/test_reduce_plan.py`, BDD SCN002, and Blender targets 1500/1038/461 |
| AC4 | Overrides win; `overrides_exceed_budget`, `unknown_part` and `invalid_override` refused before any change | Pass | `plan._check_overrides` and `split_budget`; pydantic `PartOptions` on the host. Tested in unit and BDD SCN003, and `test_reduce.py::test_overrides_are_refused_before_any_change_ac4` |
| AC5 | One `UVMap`, all islands in 0 to 1, no overlap across the asset | Pass | `core._reduce` → `uv.joint_unwrap` + `uv.finalize_unwrap` over all copies. Tested with `polygon_overlap_fraction` across every face of every part |
| AC6 | BC/R/M/N/AO baked per part into `T_<Name>_Body_{BC,N,ORM}` at Desktop px; color spaces | Pass | `reduce_core/transfer.py::bake_channels` (one selected-to-active pass per pair per channel), `bake_core/bake.py::bake_transfer`, `core._pack_textures` (pack BC sRGB, N/ORM Non-Color, ORM = AO/R/M). The suite checks 256 px, packed images and a non-flat BC. A headless probe run outside the repo tree at the previous verification head `d6d4938` passed, and no reduce or bake code has changed since then: the image color spaces are exactly sRGB/Non-Color/Non-Color, and the per-part BC means differ, with the Lid's image texture showing its G = 0.6 R signature. See Remaining Issues M1 |
| AC7 | `cage_extrusion`/`max_ray_distance` asset-wide and per part, defaults 0.03/0.10, reported per part | Pass | `plan.bake_settings` (part, then asset, then `DEFAULTS`); reported in `core._reduced`. Tested in unit, BDD SCN005, and Blender (0.05 asset-wide, 0.5 Lid ray) |
| AC8 | `unbaked_share` per part | Pass | `transfer.measure_coverage` (island mask against hit mask, `plan.unbaked_share`). Tested in Blender (0 ≤ share ≤ 0.01) and unit |
| AC9 | Misses above `miss_threshold` fail with `reduce.bake_misses`; scene unchanged | Pass | `plan.check_misses`, then `_Scope.rollback` (`remove_created`, visibility and render restore) in `core._reduce`. Tested in `test_ray_misses_fail_the_step_and_leave_the_scene_unchanged_ac9` (0.0001 m ray, full `scene_snapshot` equality) |
| AC10 | Reduced asset passes finalize through reimport; `M_<Name>_Body`; tagged `environment_piece` bakes unique | Pass | `bake_core/core.py` (`nmg_reduced`: unique mode), `contract_core/validate.py` (overlap check for reduced). Tested in `test_reduce_finalize.py` for `standard_prop` and `environment_piece`: validate, bake, variants, export and reimport, mode `unique` |
| AC11 | Rerun rebuilds from `<Name>_High` without modifying or duplicating it | Pass | `core._sources` (sources from `_High` via `nmg_source_name`), `commit._retire_previous`. Tested in `test_rerun_rebuilds_from_high_and_never_duplicates_it_ac11` |
| AC12 | Asset in budget with no `_High` left alone, `state` `within_budget` | Pass | `core._reduce` early return before any change (`_within_budget`). Tested in Blender (snapshot equality) and BDD SCN009 |
| AC13 | Armature → `reduce.rigged`; `terrain` → `reduce.class_unsupported`, before any change | Pass | `core._reduce` guards (`ASSET_CLASSES` excludes terrain; `_has_armature` on `<Name>` and `_High`). Tested in Blender and BDD SCN010 |
| AC14 | Panel, `run_for_mcp`, CLI `reduce`, MCP `reduce_asset`; one implementation; job, poll and guarded load-back | Pass | `operators/reduce_to_budget.py`, `reduce_core.run_for_mcp`, `finalize/__main__.py::_run_reduce`, `finalize/mcp_tools.py::reduce_asset` (`clamp_wait` ≤ 150), `pipeline/jobs.py::start_reduce`/`_run_reduce_job`, `pipeline/reduce.py::execute_reduce` (checkpoint, `load_back(suffixes=("", "_High"))`, `reduce.session_changed` with `result_blend`). Tested in BDD SCN011/SCN012, `tests/unit/pipeline/test_reduce_job.py`, `tests/unit/test_reduce_entry_points.py`, and the Blender operator, `run_for_mcp`, envelope and entry-script tests |

## Functional Requirements

| FR | Status | Evidence |
|----|--------|----------|
| FR1 | Pass | `decimate.fit_copy`, total budget guard in `core._reduce` |
| FR2 | Pass | `commit._move_to_high`; exclusion tested for hash, validate and export |
| FR3 | Pass | `plan.split_budget`, `plan._check_overrides`, `PartOptions` |
| FR4 | Pass | `uv.joint_unwrap`/`finalize_unwrap` |
| FR5 | Pass | `transfer.bake_channels`, `bake.bake_transfer` (vertex-color, procedural and image fixtures) |
| FR6 | Pass | `plan.bake_settings`, `DEFAULTS` |
| FR7 | Pass | `transfer.measure_coverage`, `plan.check_misses`, `_Scope.rollback` |
| FR8 | Pass | `rewire.build_material` + `node.image.pack()` + `rewire.collapse`; packed images asserted |
| FR9 | Pass | `_sources` from `_High`, `_within_budget`, rigged/terrain guards |
| FR10 | Pass | Four entry points over `reduce_asset` / `execute_reduce` |
| FR11 | Pass | `core._reduced` / `_within_budget` result shape; host `_result` adds `loaded_back`, `result_blend` |
| FR12 | Pass | `docs/asset-contract.md` (§1 `_High`, §5 Desktop exception, `nmg_reduced`), `docs/mcp/finalize.md` (`reduce_asset`, errors), `docs/skills/reduce-to-budget.md`, `docs/skills/bake-materials.md` (unique mode for tagged `environment_piece`), `skills/finalize-asset/SKILL.md` (`budget.tris` → `reduce_asset`) |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Pure-Python reduce plan | Complete | `plan.py` has no `bpy` import and loads by path in `tests/unit/test_reduce_plan.py` |
| T002 | Reduce core in Blender | Complete | `core.py`, `decimate.py`, `transfer.py`, `commit.py`, `bake_core/bake.py`, `bake_core/state.py` |
| T003 | Finalize integration | Complete | `bake_core/core.py`, `contract_core/validate.py`, `finalize_core/load_back.py` (`suffixes`), `scripts/blender/finalize_session.py` |
| T004 | Background job, CLI, MCP tool | Complete | `pipeline/blender_proc.py` needed no change because its `run_step` is step-generic. The listed `tests/unit/test_finalize_mcp.py`/`test_finalize_cli.py` coverage lives in `tests/unit/test_reduce_entry_points.py` instead. `gate-mcp-schema` passed |
| T005 | Panel operator | Complete | `nmggamedev.reduce_to_budget` registered and in the main panel |
| T006 | Documentation | Complete | All five documents updated |
| T007 | Tests | Complete | Unit, BDD, host fakes and headless Blender suites added. The per-part BC tolerance and color-space assertions are missing (M1), but I confirmed the behavior with a probe |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 4 | Clean split into plan (pure arithmetic), decimate, transfer, commit and core orchestration. `core.py` is 473 lines, mostly result shaping and `_Scope`, and is close to the size that would warrant a split |
| Open/Closed | 4 | Finalize changes are additive: `load_back` gains a defaulted `suffixes`, the session client sends `suffixes` only when given, and validate/bake key off `nmg_reduced` |
| Liskov Substitution | 5 | `BlenderSession` protocol extended compatibly; fakes (`FakeBlenderSession`, `FakeReduceRunner`) substitute cleanly |
| Interface Segregation | 4 | `StepRunner` reused unchanged; the reduce job shares `_create_job` and the lock and status machinery with finalize |
| Dependency Inversion | 4 | `execute_reduce` takes injected `clients`/`runner`; `checkpoint_session` extracted and shared by finalize and reduce |

### Layer Separation

The layers match `steering/snippets/project-structure.md`. The skill only names the MCP tool. The `pipeline/reduce.py` layer composes checkpoint, background step and load-back. The step implementation lives in the add-on (`reduce_core`, `finalize_core/reduce_job.py`). The MCP server wraps `nmg_game_dev.finalize.reduce_asset` and adds no logic. Long Blender work runs in background Blender, not inside an MCP call, which follows the "Long-running Blender work" rule.

### Dependency Flow

`reduce_core` depends on `bake_core`, `variants_core.meshes`, `utils.budgets` and `contract_core` helpers, all inside the add-on. The host package depends only on the step envelope protocol. No cycles were introduced.

---

## Security Assessment

- [x] Authentication: N/A (local tooling, no credentials)
- [x] Authorization: N/A
- [x] Input validation: pydantic `ReduceRequest`/`PartOptions` with PascalCase collection, positive distances, 0 to 1 threshold, and share/tris exclusivity. The add-on revalidates (`plan._check_overrides`, `_threshold`). `tools.json` schema bounds match
- [x] Injection prevention: Blender subprocess argv lists only; `--parts` parsed with `json.loads` and type-checked
- [x] Data protection: no secrets; logs go to the job directory and stderr

## Performance Assessment

- [x] Async patterns: the reduce runs as a detached background job; MCP returns at once or within `wait_seconds` ≤ 150
- [x] Caching: N/A. Reduce is an explicit one-shot step outside the finalize cache, by design
- [x] Resource management: temporary bake images and materials are removed in `finally` blocks; `_Scope` restores render settings; the job lock is released in `finally`
- [x] Query optimization: N/A. Decimation retries are bounded by `DECIMATE_ATTEMPTS`; coverage bakes use 1 sample

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1, AC2 (SCN001) | Yes | Blender headless (`test_reduce.py`) | Yes |
| AC3 (SCN002) | Yes | Yes (`test_reduce_plan_bdd.py`) | Yes |
| AC4 (SCN003) | Yes | Yes | Yes |
| AC5, AC6 (SCN004) | Yes | Blender headless | Yes |
| AC7 (SCN005) | Yes | Yes | Yes |
| AC8, AC9 (SCN006) | Yes | Yes + Blender headless | Yes |
| AC10 (SCN007) | Yes | Blender headless (`test_reduce_finalize.py`) | Yes |
| AC11 (SCN008) | Yes | Blender headless | Yes |
| AC12 (SCN009) | Yes | Yes (`test_reduce_to_budget_bdd.py`) | Yes |
| AC13 (SCN010) | Yes | Yes | Yes |
| AC14 (SCN011, SCN012) | Yes | Yes | Yes |

SCN001, SCN004, SCN007 and SCN008 change the Blender scene. Their docstring maps them to the headless Blender suite, which `gate-blender-headless` runs, instead of pytest-bdd bindings.

### Coverage Summary

- Feature files: 12 scenarios (`tests/bdd/features/reduce_to_budget.feature`), 8 bound in pytest-bdd and 4 covered headless
- Step definitions: Implemented
- Unit tests: `test_reduce_plan.py`, `pipeline/test_reduce_job.py`, `test_reduce_entry_points.py`
- Integration tests: `tests/blender/test_reduce.py`, `tests/blender/test_reduce_finalize.py` (headless Blender 5.2, no live editor)

---

## Exercise Test Results

| Field | Value |
|-------|-------|
| **Reason** | Not applicable. The change does not touch nmg-sdlc `workflows/` or `agents/`. Its consumer-plugin surface (`skills/`, `.claude-plugin/`) is covered by the registered `plugin.validate` and `plugin.session-smoke` validations, which passed |
| **Recommendation** | None |

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` | Pass | `uv run pytest tests/unit tests/bdd -q`: 1381 passed, 10 skipped, in 3 min 32 s |
| `repository.lint` | Pass | `ruff check .`: All checks passed |
| `repository.format` | Pass | `ruff format --check .`: exit 0 |
| `repository.types` | Pass | `mypy src tests`: exit 0 |
| `gate-blender-headless` | Pass | `scripts/run-blender-tests.sh`: 350 passed, 4 skipped, in 4 min 16 s (`test_reduce.py`, `test_reduce_finalize.py` and the merged #148 `test_material_variants.py` ran) |
| `gate-ue-compile` | Pass | DogfoodEditor compiled against `/Users/Shared/Epic Games/UE_5.8`: `Result: Succeeded` (applies via the `.uplugin` version bump) |
| `gate-mcp-schema` | Pass | MCP tools match `tools.json` for every server |
| `gate-shellcheck` | Pass | exit 0 |
| `gate-ship-smoke` | Not applicable | No changed path matches its globs |
| `plugin.validate` | Pass | `claude plugin validate .`: exit 0 |
| `plugin.session-smoke` | Pass | plugin loaded via `--plugin-dir`; `nmg-game-dev:blender` connected |

**Gate Summary**: 10/10 applicable gates passed, 0 failed, 0 incomplete (1 not applicable)

---

## Fixes Applied

| Severity | Category | Location | Original Issue | Fix Applied | Routing |
|----------|----------|----------|----------------|-------------|---------|
| — | — | — | None. The verify publication scope allows only this report, so no code fixes were applied. I reviewed the `34dd816` conflict resolutions and the `2d91c0e` follow-up, and none needs a change | — | — |

## Remaining Issues

### Critical Issues
None.

### High Priority
None.

### Medium Priority

| Field | Value |
|-------|-------|
| **ID** | M1 |
| **Severity** | Medium |
| **Category** | Testing |
| **Location** | `tests/blender/test_reduce.py::test_over_budget_asset_reduces_into_budget_with_names_and_parents` (AC6 block) |
| **Issue** | T007 asks for each part's BC to match its source within tolerance, and for the color spaces to be asserted. The test checks only that the images are 256 px and packed and that the BC is not flat |
| **Impact** | A regression that baked one part's look onto another part's island, or set the wrong color space, would not be caught by the suite |
| **Reason Not Fixed** | The verify publication scope allows only `verification-report.md`. A temporary headless probe at the previous verification head (created and removed, so the tree stayed clean; the reduce and bake code are unchanged since) confirmed the behavior: BC sRGB, N and ORM Non-Color, and distinct per-part BC means with the Lid image's G < R signature. Follow-up: add these assertions to the suite |

### Low Priority

| ID | Category | Location | Issue | Reason Not Fixed |
|----|----------|----------|-------|------------------|
| L1 | Error Handling | `reduce_core/core.py` (`commit.commit` call after the rollback `try`) | `commit` runs outside `_Scope.rollback`. An unexpected exception partway through commit, such as a datablock rename failure, would leave a partly committed scene, reported as `reduce.internal_error` | Commit is a short sequence of link and rename operations after every fallible step has passed, so the risk is low. Out of verify scope |
| L2 | Performance / Correctness risk | `reduce_core/transfer.py::bake_channels` | Parts bake one at a time into a shared image with `bake_margin(size)`. Margin fill from a later part could overwrite neighbouring islands if the atlas island spacing is smaller than the bake margin | The tests show no overlap and correct per-part means. The finalize bake re-bakes from `M_<Name>_Body`. Note for a later review |
| L3 | SOLID | `reduce_core/core.py` (473 lines) | The file is close to the 500-line red flag | Consider moving result shaping (`_within_budget`, `_reduced`) and `_Scope` into their own modules if it grows |
| L4 | Cross-feature consistency | `contract_core/validate.py::_material_variant_checks` (from #148) | #148's prediction of the bake mode uses `"tiling" if asset_class == "environment_piece"` and ignores #139's `nmg_reduced` tag, while `bake_core/core.py` bakes a tagged `environment_piece` in unique mode. The outcome is the same today: a reduced asset holds one `M_<Name>_Body` material, so `merged` is false in both modes and `part_names` returns `["Body"]`. The two mode rules can still drift apart | Not a defect in this change. Follow-up: share one `bake_mode(collection, asset_class)` helper between bake and validate |

---

## Positive Observations

- The pure-Python `plan.py` holds all the arithmetic and override rules, so the budget logic has fast CPython unit and BDD coverage.
- Rollback (`_Scope`, `datablock_pointers`/`remove_created`) is proven by full scene-snapshot equality on failure and refusal paths.
- `checkpoint_session` and `_create_job` were extracted rather than duplicated, so reduce shares the lock, status, polling and guarded load-back with finalize.
- Finalize integration is backward-compatible: `suffixes` defaults to `("", "_Mobile")` and is omitted from the session payload unless given.
- Error codes are stable, and each comes with an actionable remediation on every path (`reduce.*`).

## Recommendations Summary

### Before PR (Must)
- None.

### Short Term (Should)
- [ ] Add per-part BC tolerance and color-space assertions to `test_reduce.py` (M1).

### Long Term (Could)
- [ ] Bring `commit.commit` under the rollback scope, or make it transactional (L1).
- [ ] Keep atlas island spacing at or above the bake margin, or bake the parts with margin 0 and apply one margin pass at the end (L2).
- [ ] Split `core.py` if it grows (L3).
- [ ] Share one bake-mode rule between `bake_core/core.py` and #148's material-variant prediction in `contract_core/validate.py` (L4).

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `plugins/nmg-game-dev-blender-addon/reduce_core/plan.py` | 0 | |
| `plugins/nmg-game-dev-blender-addon/reduce_core/core.py` | 2 | L1, L3 |
| `plugins/nmg-game-dev-blender-addon/reduce_core/decimate.py` | 0 | |
| `plugins/nmg-game-dev-blender-addon/reduce_core/transfer.py` | 1 | L2 |
| `plugins/nmg-game-dev-blender-addon/reduce_core/commit.py` | 0 | |
| `plugins/nmg-game-dev-blender-addon/bake_core/{bake,core,rewire,state,uv}.py` | 0 | |
| `plugins/nmg-game-dev-blender-addon/contract_core/validate.py` | 1 | `reduced` flag and the overlap check are intact after the #148 merge. L4 |
| `plugins/nmg-game-dev-blender-addon/finalize_core/{load_back,reduce_job}.py` | 0 | |
| `plugins/nmg-game-dev-blender-addon/operators/reduce_to_budget.py`, `panels/main_panel.py` | 0 | |
| `scripts/blender/finalize_entry.py`, `scripts/blender/finalize_session.py` | 0 | |
| `src/nmg_game_dev/pipeline/{reduce,jobs,engine}.py`, `clients/blender_session.py` | 0 | |
| `src/nmg_game_dev/finalize/{__main__,mcp_tools,service,__init__}.py` | 0 | #148 conflict resolutions are unions: the `reduce` and `material-variants` subcommands and both exports are kept |
| `mcp-servers/finalize/src/finalize_mcp/server.py`, `mcp-servers/finalize/tools.json` | 0 | |
| `tests/blender/test_reduce.py` | 1 | M1 |
| `docs/*`, `skills/finalize-asset/SKILL.md` | 0 | `quality.contract_failed` keeps both the `budget.tris` → `reduce_asset` line and #148's `material_variant.*` line |
| `CHANGELOG.md`, `VERSION`, plugin manifests | 0 | 0.24.0 on all four version files. The #139 entry and #148's entry from `[Unreleased]` on main are under `[0.24.0]` |

---

## Recommendation

**Ready for PR**

Every acceptance criterion, functional requirement and task has implementation and test evidence. All 10 applicable required validations passed at `2e1acd70c2b9269c2e64439a679e82bb70b7063e` with complete coverage and no ceiling. The open findings are test-hardening and robustness follow-ups that do not block delivery.
