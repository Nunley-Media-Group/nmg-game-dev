# Verification Report: Contract validation, re-import check, and review renders

**Date**: 2026-10-30
**Issue**: #30
**Reviewer**: Claude (nmg-sdlc verify worker)
**Scope**: Implementation verification against spec
**Verification head**: 18a4488f5ce2b24b0be2733fa4c05e2200797d7f

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

**Total Issues**: 4 (all Low or Medium, none blocking)

All seven acceptance criteria are met. The validator, re-import check, review renders, and
texture proof live once in `contract_core`. The operators, the headless entry script, and the
host CLI all call that one implementation. The host-side gate raises the specified
`PipelineError` codes. All five registered validations passed at the verification head, with
complete coverage (5 declared, 5 recorded).

---

## Issue Scope

- Active issue: #30
- Spec: `specs/30-add-contract-validation-re-import-check-and-review-renders`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1–AC7]; FR [FR1–FR6]; tasks [T001–T008]; scenarios [SCN001–SCN007]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":30,"specPath":"specs/30-add-contract-validation-re-import-check-and-review-renders","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6","AC7"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6"],"tasks":["T001","T002","T003","T004","T005","T006","T007","T008"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006","SCN007"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

- Runner: `sdlc-verify-steering.mjs --issue 30 --base main --controller-run-id 85837256-3edd-4589-a50c-08ad4d01aafd`
- Artifact: `.nmg-sdlc/verification/30.json` (head `18a4488f5ce2b24b0be2733fa4c05e2200797d7f`)
- Coverage: declared 5, recorded 5, complete `true`; no missing, duplicate, or unknown ids
- Ceiling: `null` (no cap)

| Validation | Provider | Required | Status | Evidence |
|------------|----------|----------|--------|----------|
| `repository.tests` | builtin.command | yes | passed | `uv run pytest tests/unit tests/bdd -q` exited 0 (298 passed, 1 skipped) |
| `repository.lint` | builtin.command | yes | passed | `uv run ruff check .` exited 0 |
| `repository.types` | builtin.command | yes | passed | `uv run mypy src tests` exited 0 |
| `plugin.validate` | builtin.command | yes | passed | `claude plugin validate .` exited 0 |
| `plugin.session-smoke` | project.plugin-session-smoke | yes | passed | plugin loaded via `--plugin-dir`; `nmg-game-dev:blender` connected |

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Validation reports every checkable contract rule | Pass | `contract_core/validate.py` `validate_asset`. It covers the collection/naming, units, transform, pivot, geometry (`geometry.py`), UV (`uv.py`), material node and coordinate, texture naming and power-of-two, budget/texel, and variant-name rules. Each finding has `rule`/`target`/`message`/`remediation` (`report.py` `finding`). Tests: `test_ac1_compliant_crate_passes_with_snapshots`, `test_ac1_findings_carry_rule_target_message_and_remediation`. |
| AC2 | Each failure class is detected | Pass | `tests/blender/test_contract_validate.py::test_ac2_each_failure_class_fails_with_its_rule` is parametrized over all eight defects in `contract_fixtures.py`. `test_defect_list_matches_the_rule_table` pins the rule ids. `test_ac2_budget_finding_names_the_mobile_lod0` covers the Mobile LOD0 budget. The compliant fixture passes with no findings. |
| AC3 | Re-import check compares exported FBX against the pre-export report | Pass | `contract_core/reimport.py` `reimport_check` checks textures, ORM, UVMap, names, dimensions (0.1%), pivots (0.1 mm), and tris. `run_isolated` spawns `bpy.app.binary_path --background --factory-startup`. Tests: `test_ac3_reimport_passes_after_export` (Desktop + Mobile), `test_ac3_deleted_texture_fails_naming_the_file`. |
| AC4 | Review renders written to a known folder | Pass | `contract_core/render.py` `render_review` uses a temporary `__nmg_review` scene, a 50 mm camera framing the bounds, and a three-sun rig. It writes `<out>/<variant>/<Name>_{front,back,side,three_quarter}.png`, and `_teardown` removes the scene and new datablocks. Tests: `test_ac4_review_renders_write_eight_files_and_keep_the_scene`, `test_ac4_review_renders_skip_mobile_when_it_is_absent`. |
| AC5 | Texture proof sheet compares baked, re-imported, and pre-bake looks | Pass | `render.py` `render_texture_proof`, `_import_reimported` (scratch scene), `_wire_orm` (Separate Color G→Roughness, B→Metallic), and `_compose` (labeled panels). Tests: `test_ac5_proof_sheet_with_pre_bake_has_three_labeled_panels`, `..._without_pre_bake_has_two_panels`, `test_ac5_proof_leaves_no_reimported_datablocks`. |
| AC6 | Gate helper stops finalize on failure | Pass | `src/nmg_game_dev/quality/contract.py` `gate` raises `ContractGateError(PipelineError)` with `quality.contract_failed` / `quality.reimport_mismatch` and stage `quality`. The message lists each rule and target, and `report` is attached. Tests in `tests/unit/quality/test_contract_gate.py` (9 tests). |
| AC7 | One implementation reachable from operators and the CLI | Pass | The operators (`operators/validate_contract.py`, `reimport_check.py`, `render_review.py`) and `scripts/blender/contract_entry.py` all call `contract_core`. The CLI `src/nmg_game_dev/contract/cli.py` exits 0/1/2. Tests: `test_ac7_operator_and_direct_call_write_identical_reports`, `test_ac7_render_operator_writes_the_review_files`, and `tests/unit/test_contract_cli.py` (16 tests, including `test_missing_blender_exits_two_with_remediation`). |

### Functional Requirements

| FR | Status | Evidence |
|----|--------|----------|
| FR1 | Pass | `validate_asset(collection, asset_class, budgets_path=None)`; generic, with no per-asset-type rules |
| FR2 | Pass | `reimport_check` + `run_isolated` spawning `bpy.app.binary_path` |
| FR3 | Pass | `render_review(collection, out_dir, resolution=1024)`, `render_texture_proof(variant_dir, out_dir, pre_bake=None, collection=None)` |
| FR4 | Pass | `contract_core/__init__.py` re-exports; operators, `contract_entry.py`, and CLI share it |
| FR5 | Pass | Pydantic `Finding` / `ContractReport` (alias `class`) and `gate` |
| FR6 | Pass | `tests/blender/contract_fixtures.py` has one fixture per AC2 class, plus the missing-texture re-import case |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Contract validation core | Complete | `report.py`, `validate.py`, `geometry.py`, `uv.py`; checks run on evaluated copies that are removed afterward |
| T002 | Re-import check | Complete | `reimport.py`, `scripts/blender/contract_entry.py` with validate/reimport/render subcommands |
| T003 | Review renders and texture proof | Complete | `render.py` |
| T004 | Operators | Complete | Three operators registered; panel lists them; `last_result` stored via `_common.store_last_result` |
| T005 | Host-side models, gate, and CLI | Complete | `quality/contract.py`, `contract/{__init__,__main__,blender,cli}.py` |
| T006 | Docs and changelog | Complete | `docs/asset-contract.md` §8 names the tools; `CHANGELOG.md` entry ends `(#30)` |
| T007 | Host-side unit tests | Complete | 25 tests pass; covered by `repository.tests`/`lint`/`types` |
| T008 | Blender headless tests | Complete | All `test_contract_*` and `test_addon_registration` tests pass under Blender 5.2.3 LTS |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 4 | Clean module split (report / validate / geometry / uv / reimport / render). `validate.py` (561 lines) carries every rule family; acceptable, but a split is a candidate later. |
| Open/Closed | 4 | Rules are catalogued in `RULES`; adding a rule means a new finding call plus a catalogue entry. |
| Liskov Substitution | 5 | `ContractGateError` is a proper `PipelineError` subtype (`test_gate_error_is_a_pipeline_error`). |
| Interface Segregation | 5 | Four small public functions; operators are thin wrappers. |
| Dependency Inversion | 4 | Host and Blender share only a JSON schema, with no cross-imports. Blender resolution is isolated in `contract/blender.py`. |

### Layer Separation

The design is followed: Blender logic is in the add-on, `quality/contract.py` holds the
deterministic gate only, and the CLI glue lives in `src/nmg_game_dev/contract/`. No skill speaks
MCP directly. Finalize wiring is correctly left to #69.

### Dependency Flow

Host → (subprocess) → Blender entry → `contract_core`. The JSON report is the only contract
between the layers. `extra` keys are ignored by the pydantic model, so the Blender side can
extend reports.

---

## Security Assessment

- [x] Authentication: N/A (local tooling)
- [x] Authorization: N/A
- [x] Input validation: CLI args go through argparse. Subprocesses use list argv (no shell), and report JSON is validated by pydantic.
- [x] Injection prevention: No `shell=True`; paths are passed as separate argv entries.
- [x] Data protection: No credentials handled.

## Performance Assessment

- [x] Async patterns: The re-import runs in a separate headless process, as the design requires. Renders use EEVEE.
- [x] Caching: N/A for this slice (finalize caching belongs to #69).
- [x] Resource management: Evaluated mesh copies are removed in `finally`, and temporary scenes and datablocks are torn down. One exception: `run_isolated` leaves its `mkdtemp` folder behind (see Remaining Issues).
- [x] Query optimization: The UV overlap rasterizes onto a fixed 512×512 grid, which is bounded.

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1 | Yes (SCN001) | Yes (Blender headless test) | Yes |
| AC2 | Yes (SCN002) | Yes | Yes |
| AC3 | Yes (SCN003) | Yes | Yes |
| AC4 | Yes (SCN004) | Yes | Yes |
| AC5 | Yes (SCN005) | Yes | Yes |
| AC6 | Yes (SCN006) | Yes (unit) | Yes |
| AC7 | Yes (SCN007) | Yes (Blender + unit) | Yes |

The `feature.gherkin` header maps the scenarios 1:1 to `tests/blender/test_contract_*.py` and
`tests/unit/quality/test_contract_gate.py`. Blender-dependent ACs are exercised under
`blender --background`, per the steering test table.

### Coverage Summary

- Feature file: 7 scenarios (SCN002 is an 8-row outline)
- Host unit tests: 25 for this issue (`test_contract_gate.py` 9, `test_contract_cli.py` 16); full host suite 298 passed, 1 skipped
- Blender headless: `scripts/run-blender-tests.sh` with `BLENDER_APP=/Volumes/Fast Brick/Applications/Blender.app` (Blender 5.2.3 LTS) gave 47 passed, 2 failed. Both failures are in `tests/blender/test_coexistence.py`, which this issue does not touch (see Remaining Issues). The #30 subset (`test_contract_validate.py`, `test_contract_reimport.py`, `test_contract_render.py`, `test_addon_registration.py`) passed: 17 passed, 0 failed.

## Exercise Test Results

| Field | Value |
|-------|-------|
| **Reason** | Not applicable. The diff touches no nmg-sdlc `workflows/` or `agents/`. Plugin loading was exercised by the registered `plugin.session-smoke` validation (plugin loaded via `--plugin-dir`, Blender MCP connected). |
| **Recommendation** | None |

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` | Pass | exit 0 |
| `repository.lint` | Pass | exit 0 |
| `repository.types` | Pass | exit 0 |
| `plugin.validate` | Pass | exit 0 |
| `plugin.session-smoke` | Pass | plugin loaded; `nmg-game-dev:blender` connected |

**Gate Summary**: 5/5 gates passed, 0 failed, 0 incomplete

---

## Fixes Applied

| Severity | Category | Location | Original Issue | Fix Applied | Routing |
|----------|----------|----------|----------------|-------------|---------|
| — | — | — | No code fixes applied. This step's publication scope is limited to this report. | — | — |

## Remaining Issues

### Critical Issues

None.

### High Priority

None.

### Medium Priority

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Category** | Architecture |
| **Location** | `plugins/nmg-game-dev-blender-addon/contract_core/reimport.py:23`, `src/nmg_game_dev/contract/blender.py:16` |
| **Issue** | `ENTRY_SCRIPT` is found as `<repo>/scripts/blender/contract_entry.py` relative to the source file. This works for the symlinked development add-on and an editable install. A packaged add-on extension or a wheel install has no `scripts/` directory beside it, so `nmggamedev.reimport_check` and the CLI would fail. |
| **Impact** | Re-import from consumer installs fails with `reimport.entry_missing` / `contract.entry_missing`. The failure is actionable, not silent. |
| **Reason Not Fixed** | The design places the entry script in `scripts/blender/`. Moving it into the add-on package is a design change; candidate for #69 or onboarding packaging. |

### Low Priority

- `contract_core/reimport.py` `run_isolated`: the `tempfile.mkdtemp` work folder is never removed. `variant_dir` is not passed through `bpy.path.abspath`, so a `//`-relative path from the operator's DIR_PATH field reaches the subprocess unresolved. Reason not fixed: outside this step's publication scope, and behavior is correct for absolute paths.
- `uv.lock` records the package as `0.7.0` while `pyproject.toml` / `VERSION` are `0.9.0`. This was already stale on `main` (0.7.0 vs 0.8.0). Each `uv run` rewrites it, so the registered command validations leave the tree dirty after the first one. Reason not fixed: outside this step's publication scope. The lockfile should be refreshed in the next version-bump commit. The worker reverted the generated change.
- Environment: `tests/blender/test_coexistence.py` fails two tests because the local Blender user add-on folder holds two copies of blender-mcp (`blender_mcp.py` and `blender-mcp-addon.py`), so enabling `blender_mcp` collides with the already-registered classes. Not caused by #30, not a registered validation. Reason not fixed: host environment. Removing the duplicate add-on file resolves it.

---

## Positive Observations

- One implementation, three entry points, with an operator-vs-direct identical-report test that guards the property.
- All checks run on evaluated copies or scratch scenes, and tests assert that the user scene is unchanged.
- Every rule has a catalogued remediation, so findings are always actionable.
- The CLI removes stale reports before running, so an old report cannot stand in for a new run.

## Recommendations Summary

### Before PR (Must)

- [x] None

### Short Term (Should)

- [ ] Ship `contract_entry.py` inside the add-on package (or resolve it from the add-on dir) so re-import works from packaged installs.
- [ ] Refresh `uv.lock` alongside version bumps.

### Long Term (Could)

- [ ] Clean up the `run_isolated` temp folder and resolve Blender-relative paths.
- [ ] Split `validate.py` by rule family if more rules land.

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `plugins/nmg-game-dev-blender-addon/contract_core/validate.py` | 0 | |
| `plugins/nmg-game-dev-blender-addon/contract_core/reimport.py` | 2 | entry-script location; temp folder and relative path |
| `plugins/nmg-game-dev-blender-addon/contract_core/render.py` | 0 | |
| `plugins/nmg-game-dev-blender-addon/contract_core/report.py` | 0 | |
| `plugins/nmg-game-dev-blender-addon/operators/*.py` | 0 | |
| `scripts/blender/contract_entry.py` | 0 | |
| `src/nmg_game_dev/quality/contract.py` | 0 | |
| `src/nmg_game_dev/contract/*.py` | 1 | entry-script location (shared with reimport.py) |
| `tests/blender/test_contract_*.py`, `tests/unit/**/test_contract_*.py` | 0 | |

---

## Recommendation

**Ready for PR**

Every acceptance criterion, functional requirement, and task is satisfied with passing tests.
All five registered validations passed with complete coverage at
`18a4488f5ce2b24b0be2733fa4c05e2200797d7f`. The remaining items are non-blocking follow-ups.
