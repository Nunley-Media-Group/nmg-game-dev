# Verification Report: Measure texel density per material slot and exempt trim-atlas and flat-colour slots

**Date**: 2026-11-11
**Issue**: #151
**Reviewer**: Claude (nmg-sdlc architecture-reviewer, verify stage)
**Scope**: Implementation verification against spec

**Verification head**: b43412c5d97f03c99b6478584a6f516b4eba64fc

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 5 |
| Security | 5 |
| Performance | 4 |
| Testability | 5 |
| Error Handling | 4 |
| **Overall** | 4.7 |

### Implementation Status: Pass
**Total Issues**: 0 blocking (2 low-severity observations, no action required)

A new shared module, `contract_core/texel.py`, measures UV area and world area per material slot. It classifies each slot as `trim_atlas`, `flat_colour`, `skipped` or `measured`. Contract validation (`_texel_findings`) and the tiling bake (`check_density`) both use it, so they measure the same faces the same way. Validation reports one `texel.density` finding per failing slot, and the bake raises `texel_density` for the first failing slot. Both name the mesh, the material, the px/m, the minimum and the variant. The validation snapshot (`texel`) and the bake report (`texel_density`) list every slot. When any source material carries `nmg_trim_atlas`, the baked material gets the marker too, and `Material.copy()` keeps it on `_Mobile`. The docs and the `/model-asset` guidance describe the per-slot rule and the marker. All 11 registered validations are recorded at the verification head: 9 applicable ones passed and 2 do not apply to this change.

---

## Issue Scope

- Active issue: #151
- Spec: `specs/151-measure-texel-density-per-material-slot-and-exempt-trim-atlas-and-flat-colour-slots`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1–AC9]; FR [FR1–FR13]; tasks [T001–T005]; scenarios [SCN001–SCN009]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":151,"specPath":"specs/151-measure-texel-density-per-material-slot-and-exempt-trim-atlas-and-flat-colour-slots","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6","AC7","AC8","AC9"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6","FR7","FR8","FR9","FR10","FR11","FR12","FR13"],"tasks":["T001","T002","T003","T004","T005"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006","SCN007","SCN008","SCN009"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

- Artifact: `.nmg-sdlc/verification/151.json` (run id `a10c9007-0d1e-4e0a-acce-90cf7936cefd`)
- Identity: head `b43412c5d97f03c99b6478584a6f516b4eba64fc`, tree clean, spec hash `sha256:02f5a85a…`, steering hash `sha256:119992c8…`
- Coverage: declared 11, recorded 11, complete `true`, with no missing, duplicate or unknown ids
- Ceiling: `null` (no cap)

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Density measured per material slot | Pass | `contract_core/texel.py` `slot_areas` groups polygons by `material_index`; `validate._texel_findings` and `tiling.check_density` compare each slot on its own. Test `test_scn001_each_slot_is_measured_from_its_own_faces` |
| AC2 | Atlas/flat-dominated mesh passes when tiling slots are dense | Pass | `classify` exempts marked and collapsed slots. Tests `test_scn002_dense_tiling_slot_passes_beside_atlas_and_flat_faces` (validation) and `test_scn002_bake_density_passes_a_dense_slot_beside_exempt_slots` (bake) |
| AC3 | Failing slot is named | Pass | Finding message `"<obj> slot '<material>' reaches <d> px/m … <min> px/m on <variant>"` (`validate.py`); `BakeError("texel_density", "Mesh '<obj>' slot '<material>' has <d> px/m at <variant> size; the minimum is <min>.")` (`tiling.py`). Tests `test_scn003_*` in both suites |
| AC4 | Flat-colour slot exempt without a marker | Pass | `classify`: `uv_area <= FLAT_COLOUR_UV_AREA (1e-8)` → `flat_colour`. Unit test of the inclusive cut-off; tests `test_scn004_*` |
| AC5 | Declared trim-atlas slot exempt | Pass | `is_trim_atlas` reads `material.get("nmg_trim_atlas")`, and `classify` checks it first. Tests `test_classify_checks_the_marker_first` and `test_scn005_*` |
| AC6 | Undeclared low-density slot fails; remediation names both remedies | Pass | `report.RULES["texel.density"]` and `errors.REASONS["texel_density"]` name raising the density and setting `nmg_trim_atlas`. Test `test_scn006_undeclared_low_density_slot_fails_with_both_remedies` |
| AC7 | Reports list measured and exempt slots | Pass | `texel.slot_entry`; validation `snapshot[<obj>]["texel"]`; bake result `texel_density` (`core._result`). Tests `test_scn007_*` (validation and bake) and unit `slot_entry` tests |
| AC8 | Declaration holds through finalize and Mobile | Pass | `rewire.build_material(trim_atlas=…)` with `core.py` `any(is_trim_atlas(source) …)`; `Material.copy()` keeps the ID property. Tests `test_mobile_material_copy_keeps_the_trim_marker` and `test_scn008_marker_holds_on_the_baked_and_mobile_materials` (bake → `build_mobile` → validate) |
| AC9 | Single-slot tiling meshes behave as before | Pass | Same `texel.density` code and `texel_density` reason, and the 256/128 constants re-exported (`validate.TEXEL_DENSITY_MIN`, `tiling.*_DENSITY_MIN`). Existing `test_ac2_low_texel_density_fails` still passes; new test `test_scn009_single_undeclared_slot_keeps_its_code_and_reason` |

### Functional Requirements

| FR | Status | Evidence |
|----|--------|----------|
| FR1 | Pass | `validate._texel_findings` measures per slot (`environment_piece` only, via `texel_check`) |
| FR2 | Pass | `tiling.check_density` uses `texel.slot_areas` on an evaluated copy |
| FR3 | Pass | `FLAT_COLOUR_UV_AREA = 1e-8`, a named constant |
| FR4 | Pass | `TRIM_ATLAS_PROPERTY = "nmg_trim_atlas"`; docs explain how to set it in the UI and from a script |
| FR5 | Pass | `rewire.build_material` sets the marker; Mobile copy keeps it (tested) |
| FR6 | Pass | One finding per failing slot; messages name the mesh, the material, px/m, the minimum and the variant |
| FR7 | Pass | Snapshot `texel` and bake `texel_density` |
| FR8 | Pass | Validation and bake share `evaluated_copy`, `slot_areas`, `classify` and `density`; only the px source differs, as designed |
| FR9 | Pass | `report.py` and `errors.py` remediation updated |
| FR10 | Pass | `docs/asset-contract.md` §4 and §6, `docs/skills/bake-materials.md` |
| FR11 | Pass | `skills/model-asset/SKILL.md` step 7 and `docs/skills/model-asset.md` step 7 |
| FR12 | Pass | Unit plus headless Blender tests cover SCN001–SCN009, including the case where the aggregate is below 256 but the tiling slot passes |
| FR13 | Pass | Code, reason and minimums unchanged (`test_constants_match_the_contract`) |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Shared per-slot measurement | Complete | `contract_core/texel.py` created; its pure helpers load under CPython |
| T002 | Contract validation per slot | Complete | `validate.py` and `report.py`; the old `_areas` and `_evaluated_copy` were removed in favour of `texel` |
| T003 | Tiling bake per slot and marker carry-over | Complete | `tiling.py`, `core.py`, `rewire.py` and `errors.py`. `variants_core/textures.py` needed no change because `Material.copy()` already keeps ID properties, as the design expected; a test asserts it. `uv.world_area` removed and no callers remain |
| T004 | Documentation and skill guidance | Complete | 4 files updated; `plugin.validate` passes |
| T005 | Tests | Complete | `tests/unit/test_texel_classify.py` (new); `tests/blender/test_contract_validate.py`, `test_bake_tiling.py` and `test_variants_mobile.py` extended; fixtures in `tests/blender/texel_fixtures.py`. No live editor is used |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 5 | `texel.py` owns measurement and classification; validation and bake own only their reporting and raising |
| Open/Closed | 5 | Exemption kinds live in one `classify` function, so a new kind is a local change |
| Liskov Substitution | 5 | N/A beyond duck-typed `SlotArea` and material inputs, which are used consistently |
| Interface Segregation | 5 | Pure helpers (`classify`, `density`, `slot_entry`) are separate from the bpy readers (`slot_areas`, `evaluated_copy`) |
| Dependency Inversion | 4 | `bake_core` now imports `contract_core.texel`, a sideways dependency inside the add-on, chosen deliberately for FR8. `bpy` is imported lazily in `evaluated_copy` |

### Layer Separation

Changes stay within the step-implementation layer (`contract_core`, `bake_core`) of the Blender add-on. They add no MCP, pipeline or skill-layer coupling. The skill change is guidance text only.

### Dependency Flow

`validate.py` → `texel`, and `tiling.py`, `core.py`, `rewire.py` → `contract_core.texel`. The dependencies have no cycles, and `texel.py` imports nothing from the add-on.

---

## Security Assessment

- [x] Authentication: N/A (no external services)
- [x] Authorization: N/A
- [x] Input validation: the marker is read with `bool(material.get(...))`, so a non-bool value cannot raise; division by zero is guarded because `classify` returns `skipped` before `density` is called
- [x] Injection prevention: N/A (no shell, SQL or eval)
- [x] Data protection: no credentials or PII touched

---

## Performance Assessment

- [x] Async patterns: N/A (synchronous Blender work, as before)
- [x] Caching: N/A
- [x] Resource management: each evaluated mesh copy is removed in a `finally` block in both validation and bake
- [x] Query optimization: one pass over polygons per mesh, using pure-Python fan triangulation like the previous code. The bake now also builds an evaluated copy per mesh, a small fixed cost relative to the bake itself

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1 | Yes (SCN001) | Yes (headless Blender test) | Yes |
| AC2 | Yes (SCN002) | Yes | Yes |
| AC3 | Yes (SCN003) | Yes | Yes |
| AC4 | Yes (SCN004) | Yes | Yes |
| AC5 | Yes (SCN005) | Yes | Yes |
| AC6 | Yes (SCN006) | Yes | Yes |
| AC7 | Yes (SCN007) | Yes | Yes |
| AC8 | Yes (SCN008) | Yes | Yes |
| AC9 | Yes (SCN009) | Yes | Yes |

### Coverage Summary

- Feature file: 9 scenarios (`feature.gherkin`). Each is implemented as a headless Blender test tagged with its scenario id, matching how this repository implements Blender-dependent ACs (`tests/blender/` through `gate-blender-headless`)
- Unit tests: `tests/unit/test_texel_classify.py` (classification order, cut-off boundary, density arithmetic, report entries, marker parsing, no `bpy` import)
- Suites: `repository.tests` 1023 passed, 9 skipped; `gate-blender-headless` 227 passed

---

## Exercise Test Results

| Field | Value |
|-------|-------|
| **Reason** | Not required. The change touches no nmg-sdlc `workflows/` or `agents/`. The only skill change is one guidance sentence in `skills/model-asset/SKILL.md`, which `plugin.validate` and `plugin.session-smoke` cover (the plugin loaded with `--plugin-dir` and its MCP servers checked) |
| **Recommendation** | None |

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| repository.tests | Pass | `uv run pytest tests/unit tests/bdd -q`: 1023 passed, 9 skipped |
| repository.lint | Pass | `uv run ruff check .`: All checks passed |
| repository.format | Pass | `uv run ruff format --check .`: 318 files already formatted |
| repository.types | Pass | `uv run mypy src tests`: no issues in 201 source files |
| gate-blender-headless | Pass | `scripts/run-blender-tests.sh`: 227 passed in 173 s |
| gate-ue-compile | Pass | `Build.sh DogfoodEditor Mac Development`: Result: Succeeded (applicable because version files changed) |
| gate-mcp-schema | Pass | MCP tools match tools.json for every server |
| gate-shellcheck | Not applicable | No `scripts/**.sh` changed |
| gate-ship-smoke | Not applicable | No ship paths changed |
| plugin.validate | Pass | `claude plugin validate .`: Validation passed with warnings (the existing `PRIVACY_URL_MISSING` notice, unrelated to this change) |
| plugin.session-smoke | Pass | Herdr session loaded this checkout with `--plugin-dir` and checked `/mcp` in an ephemeral project |

**Gate Summary**: 9/9 applicable gates passed, 0 failed, 0 incomplete (2 not applicable)

---

## Fixes Applied

| Severity | Category | Location | Original Issue | Fix Applied | Routing |
|----------|----------|----------|----------------|-------------|---------|
| — | — | — | No fixes needed | — | — |

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
| **Category** | Architecture |
| **Location** | `plugins/nmg-game-dev-blender-addon/bake_core/core.py` (`trim_atlas=any(is_trim_atlas(source) for source in item.sources)`) |
| **Issue** | If several source materials were ever merged into one baked material, one marked source would make the whole merged material exempt |
| **Impact** | None today. Tiling mode raises `material_limit` instead of merging, and unique mode never measures density |
| **Reason Not Fixed** | Out of scope, not reachable, and matches the approved design ("true when any of `item.sources` carries the marker") |

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Testing |
| **Location** | `plugins/nmg-game-dev-blender-addon/contract_core/validate.py` `_texel_findings` |
| **Issue** | A validation snapshot entry holds the px/m only for its own variant. Desktop objects carry `desktop` and `_Mobile` objects carry `mobile`; the bake report carries both |
| **Impact** | None. This matches the per-variant snapshot structure and the docs ("each measured slot's Desktop or Mobile px/m") |
| **Reason Not Fixed** | Consistent with the design; not a defect |

---

## Positive Observations

- Validation and bake now share one measure and one classification, which closes the drift risk FR8 targets.
- Old helpers (`validate._areas`, `validate._evaluated_copy`, `uv.world_area`) were removed rather than left duplicated.
- The pure helpers are unit-tested under plain CPython by loading the file by path. A test also asserts that the module does not import `bpy` at load time.
- SCN008 runs bake → `build_mobile` → validate end to end in headless Blender, with no live editor.

---

## Recommendations Summary

### Before PR (Must)
- None

### Short Term (Should)
- None

### Long Term (Could)
- If tiling mode ever merges materials, decide whether the trim-atlas marker should require all sources to be marked.

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `plugins/nmg-game-dev-blender-addon/contract_core/texel.py` | 0 | New shared module |
| `plugins/nmg-game-dev-blender-addon/contract_core/validate.py` | 0 | Per-slot findings and snapshot |
| `plugins/nmg-game-dev-blender-addon/contract_core/report.py` | 0 | Remediation |
| `plugins/nmg-game-dev-blender-addon/bake_core/tiling.py` | 0 | Per-slot bake check |
| `plugins/nmg-game-dev-blender-addon/bake_core/core.py` | 1 (low) | Report field and marker flag |
| `plugins/nmg-game-dev-blender-addon/bake_core/rewire.py` | 0 | Marker on baked material |
| `plugins/nmg-game-dev-blender-addon/bake_core/errors.py` | 0 | Remediation |
| `plugins/nmg-game-dev-blender-addon/bake_core/uv.py` | 0 | Dead helper removed |
| `docs/asset-contract.md`, `docs/skills/bake-materials.md`, `docs/skills/model-asset.md`, `skills/model-asset/SKILL.md` | 0 | Docs and guidance |
| `tests/unit/test_texel_classify.py`, `tests/blender/test_contract_validate.py`, `tests/blender/test_bake_tiling.py`, `tests/blender/test_variants_mobile.py`, `tests/blender/texel_fixtures.py` | 0 | Coverage for SCN001–SCN009 |

---

## Recommendation

**Ready for PR**

All nine acceptance criteria and thirteen functional requirements are implemented and tested. Every registered validation that applies passed at head `b43412c5d97f03c99b6478584a6f516b4eba64fc`, with complete coverage and no ceiling. The two remaining observations are low-severity, need no action, and match the approved design.
