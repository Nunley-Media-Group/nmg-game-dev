# Verification Report: Material variants for finalized assets

**Date**: 2026-11-11
**Issue**: #148
**Reviewer**: Claude (nmg-sdlc architecture-reviewer, verify worker)
**Scope**: Implementation verification against spec

**Verification head**: c868ff578d46a8c47cdc08eab67ab859de4b8f32

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 4 |
| Architecture (SOLID) | 4 |
| Security | 5 |
| Performance | 4 |
| Testability | 5 |
| Error Handling | 4 |
| **Overall** | 4.3 |

### Implementation Status: Fail
**Total Issues**: 5 (1 High, 1 Medium, 3 Low)

The feature is implemented end to end: declaration discovery, `material_variant.*` contract rules, Desktop/Mobile variant textures, sidecar records, UE import with tags and stale deletion, listing through the MCP tool and the CLI, the `Tint` builder change, cache keys, and docs.

Status is **Fail** for two reasons.

1. **Registered gate (caps status at Fail).** This verify step's mandatory run of the registered gate at this head recorded `repository.tests` as failed: 1 failed, 1003 passed, 9 skipped. The only failure was `tests/bdd/steps/test_scaffold.py::test_unreal_launcher_detaches`, which asserts that `scripts/start-unreal-mcp.sh` returns in under 2 s. It took 3.76 s while other lanes were compiling Unreal on the same host. #148 changes neither the script nor the test. Rerun alone at this head, it passed twice and failed once. The earlier gate run at this head passed. Diagnosis: a timing-sensitive test failing under host load, not a #148 regression. Because of that failure, `gate-ue-compile` and `plugin.session-smoke` were recorded as incomplete (`deferred until required local validations pass`). The other required gates passed.
2. **One AC7 defect (Partial on its own).**

The `import_ue` result keys `material_variants` by the variant name alone. A declaration that is valid under the contract, such as `Red` on both `M_<Name>_Body` and `M_<Name>_Lid`, creates both material instances in Unreal, but the result lists only the last one. AC7 requires the result to list the material instance paths that were imported. The approved design.md interface row fixes that variant-keyed shape, so the fix needs a design amendment (see Remaining Issues).

---

## Issue Scope

- Active issue: #148
- Spec: `specs/148-let-one-finalized-asset-declare-several-material-variants`
- Manifest: `implicit single issue`
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1–AC10]; FR [FR1–FR9]; tasks [T001–T009]; scenarios [SCN001–SCN010]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":148,"specPath":"specs/148-let-one-finalized-asset-declare-several-material-variants","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6","AC7","AC8","AC9","AC10"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6","FR7","FR8","FR9"],"tasks":["T001","T002","T003","T004","T005","T006","T007","T008","T009"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006","SCN007","SCN008","SCN009","SCN010"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Not complete (AC7 Partial; `repository.tests` failed, with 2 gates deferred)
- PR evidence: Not required

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Declaration beside the `.blend` or explicit; validate report lists each variant | Pass | `src/nmg_game_dev/finalize/service.py:81` (`resolve_material_variants`); `contract_core/validate.py:125`; `contract_core/material_variants.py:44,89`; `finalize_core/steps.py` passes `material_variants_path` to validate and the export pre-check. Tests: `test_the_declaration_beside_the_blend_is_found_and_absolute`, `test_an_explicit_declaration_wins_over_the_one_beside_the_blend`, `test_scn001_the_declaration_is_read_and_each_variant_is_listed` |
| AC2 | Texture variant exported for Desktop and Mobile at each folder's BC size; imported; `MI_<Name>_<Part>_<Variant>` parented to `M_NmgORM` with BaseColor/Normal/ORM | Pass | `variants_core/material_variants.py:21` (copy for Desktop, `mobile_image_copy` scaled to the Mobile `T_<Name>_<Part>_BC`); `unreal/import_asset.py:144` (sRGB for `_BC_<Variant>`), `:360` (`_bind_material_variants`). Tests: `test_scn002_…`, `test_the_mobile_variant_is_scaled_to_the_mobile_base_colour`, `test_a_texture_variant_is_created_beside_the_main_set_with_its_textures`, `test_the_variant_texture_is_imported_in_both_folders_with_the_same_names` |
| AC3 | Parameter variant sets `Tint` on the main set; no extra texture; `M_NmgORM` gains `Tint` (default white) multiplying base colour; main MI does not set `Tint` | Pass (see Remaining Issue 2) | `scripts/unreal/build_master_material.py:71` (`_tint`) and the Multiply into Base Color; `utils/master_material.py:13`. Tests: `test_scn003_a_parameter_variant_writes_no_texture_and_lists_its_tint`, `test_a_parameter_variant_sets_tint_and_keeps_the_main_textures`, `test_tint_is_the_vector_parameter_with_a_white_default`, `test_base_color_is_the_base_color_sampler_times_tint`, `test_master_parameter_table_matches_the_vector_parameters_the_builder_creates`. The builder is proven against the fake `unreal` module, as design.md §7 specifies. The committed `M_NmgORM.uasset` is not rebuilt (no live editor in SDLC work). |
| AC4 | Main asset unchanged; no declaration means no `material_variants` key and unchanged bindings | Pass | `finalize_core/steps.py` `_sidecar_payload` adds the key only when declared; the import template never assigns a variant MI to a slot. Tests: `test_scn004_without_a_declaration_the_export_matches_the_unfeatured_export`, `test_without_a_declaration_the_report_has_no_material_variants`, `test_without_material_variants_the_bindings_are_unchanged`, `test_variant_instances_are_tagged_and_never_bound_to_the_mesh_slot`, `test_a_sidecar_without_material_variants_imports_with_none` |
| AC5 | Each `material_variant.*` rule fails validate with asset, variant, and rule named; nothing baked | Pass | `contract_core/material_variants.py:89` (`check_declaration`; `_fail` message names collection, variant, material, rule); `contract_core/report.py` remediation for every rule; findings survive `authored=True`. Tests: `test_scn005_each_rule_yields_a_finding_naming_the_asset_and_variant` (parametrized per rule), `test_a_malformed_declaration_raises_declaration_invalid` |
| AC6 | Variant on a merged authored material fails `material_merged` naming `M_<Name>_Body`; a variant on Body works for both variants | Pass | `contract_core/validate.py:125` reuses `bake_core.rewire.part_names` and the bake's merge condition. Tests: `test_scn006_a_variant_on_a_merged_authored_material_is_rejected`, `test_a_variant_on_the_merged_body_material_is_accepted` |
| AC7 | Sidecar `material_variants` lists Desktop and Mobile entries; `import_ue` result lists imported variant textures and MI paths | **Partial** | Sidecar: Pass (`variants_core/material_variants.py:21`, `test_scn007_the_sidecar_lists_each_texture_variant_for_both_folders`). Import result: `unreal/import_asset.py:392` writes `RESULT["material_variants"][variant]`. Two materials that share a variant name overwrite each other. Reproduced with the unit harness's fake `unreal`: `Red` on `M_Crate_Body` and `M_Crate_Lid` created both `MI_Crate_Body_Red` and `MI_Crate_Lid_Red`, but the result held only `{"Red": {"material": "M_Crate_Lid", "instance": ".../MI_Crate_Lid_Red"}}`. |
| AC8 | `list_material_variants` MCP tool and `material-variants` CLI list name, slot, and Desktop/Mobile MI paths; `[]` when none or missing | Pass | `unreal/material_variants.py:70` (reads `nmg.*` tags and keys rows by (material, variant), so shared names list correctly); `finalize/mcp_tools.py:111`; `finalize/__main__.py:182`; `mcp-servers/finalize/tools.json`. Tests: `test_listing_returns_each_variant_with_its_instance_in_both_folders`, `test_listing_returns_an_empty_list_when_nothing_is_tagged_or_the_folders_are_missing`, `test_the_mcp_tool_returns_the_same_rows_as_the_listing`, `test_the_mcp_tool_returns_the_unreachable_error_structured`, `test_the_cli_lists_the_rows_as_json` |
| AC9 | Re-run reuses kept variants, deletes removed variant's MI and texture from both Content folders and lists them; export folder drops the PNG | Pass | `unreal/import_asset.py:399` (`_delete_stale_variants`: only `nmg.asset`-tagged assets whose (slot, variant) pair is no longer declared; MIs before textures); `variants_core/material_variants.py` clears `T_<Name>_*_BC_*.png` before writing. Tests: `test_removing_a_variant_deletes_its_tagged_assets_and_reports_them`, `test_reimporting_the_same_declaration_reuses_every_variant_asset`, `test_scn009_removing_a_variant_deletes_its_texture_from_both_folders` |
| AC10 | Docs cover file name, location, format, naming, rules, stale deletion, and listing | Pass | `docs/asset-contract.md:67` (§4 "Material variants"); `skills/finalize-asset/SKILL.md` "Material variants"; `docs/mcp/finalize.md` (tool table, CLI, error codes, cache keys). Test: `test_the_documents_name_the_declaration_naming_rules_and_listing` |

### Functional requirements

| FR | Status | Notes |
|----|--------|-------|
| FR1 | Pass | Discovery beside `.blend`, explicit path wins, missing explicit path raises `finalize.material_variants_not_found` |
| FR2 | Pass | `docs/asset-contract.md` §4 |
| FR3 | Pass | Validate step and export pre-check both pass the declaration |
| FR4 | Pass | Desktop copy and Mobile scaled copy; stale PNGs cleared first |
| FR5 | Pass | Create or reuse, tag, stale deletion |
| FR6 | Pass | Builder change. Committed `.uasset` not rebuilt (Remaining Issue 2) |
| FR7 | **Partial** | Sidecar Pass; import result loses entries on shared variant names (Remaining Issue 1) |
| FR8 | Pass | MCP tool and CLI share `list_material_variants` |
| FR9 | Pass | `pipeline/steps.py:108` fingerprint in validate and export only; `_STEP_VERSION` "4" |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Parse and validate the declaration | Complete | |
| T002 | Export variant textures and sidecar | Complete | `variants_core/sidecars.py` needed no change; the payload is built in `finalize_core/steps.py` |
| T003 | Host request and cache keys | Complete | |
| T004 | `Tint` on `M_NmgORM` | Complete | Builder only. The committed asset needs a rebuild in a live editor, which SDLC work does not do |
| T005 | Import variants and delete stale ones | Complete with defect | Result keyed by variant name (AC7) |
| T006 | List from Unreal | Complete | |
| T007 | Documentation | Complete | §6 budget table unchanged |
| T008 | Blender regression tests | Complete | `tests/blender/test_material_variants.py`, through `gate-blender-headless` |
| T009 | Host unit tests | Complete | `tests/unit/test_material_variants_host.py`, `tests/unit/test_build_master_material.py`. No test covers one variant name on two materials |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 4 | Declaration parsing and rules (`contract_core/material_variants.py`, no bpy), export (`variants_core/material_variants.py`), import template, and listing are separate. `check_declaration` is long but linear |
| Open/Closed | 4 | `MASTER_PARAMETERS` is a table, so a new master parameter is a data change. Only `vector` kinds are validated today |
| Liskov Substitution | 5 | No new hierarchies |
| Interface Segregation | 4 | `list_material_variants` takes only a client, category, and name. The CLI and MCP layers wrap it without logic |
| Dependency Inversion | 4 | UE access goes through `UnrealPythonClient`; the CLI and MCP tool take an injectable client for tests |

### Layer Separation

Layers follow `steering/snippets/project-structure.md`. The skill calls finalize MCP tools, not sockets. The pipeline engine reads the sidecar and hands per-variant lists to the UE step. The finalize MCP server adds no logic. Blender-side code stays in `contract_core`/`variants_core`/`finalize_core`.

### Dependency Flow

`contract_core.material_variants` depends only on `utils.master_material` and `report`. `validate.py` reuses `bake_core.rewire.part_names` so predicted parts cannot drift from the bake. `variants_core.material_variants` reuses `png_size` and `mobile_image_copy`. No cycles were introduced.

---

## Security Assessment

- [x] Authentication: no change. The Unreal MCP client is reused
- [x] Authorization: stale deletion only removes assets tagged `nmg.asset == <Name>` inside the asset's own destination folder
- [x] Input validation: the declaration is schema-checked (unknown keys rejected), names are anchored PascalCase, `Tint` components are finite and non-negative, and the MCP listing rejects non-PascalCase category and collection
- [x] Injection prevention: UE code receives parameters through a double-JSON-encoded `PARAMS` literal, never string interpolation
- [x] Data protection: no credentials or secrets touched

`base_color` may be an absolute path or contain `..`. The asset author controls the file, so this is acceptable.

---

## Performance Assessment

- [x] Async patterns: no new MCP-call bake work. Variant texture writes happen inside the existing background export step
- [x] Caching: validate and export keys include declaration and texture bytes; bake and variants stay cached when only variants change
- [x] Resource management: images loaded for Mobile scaling are removed in `finally` blocks
- [x] Query optimization: stale deletion and listing load each asset in one folder (non-recursive). That is acceptable for per-asset folders

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1 | Yes (SCN001) | Yes (unit + Blender) | Yes |
| AC2 | Yes (SCN002) | Yes | Yes |
| AC3 | Yes (SCN003) | Yes | Yes |
| AC4 | Yes (SCN004) | Yes | Yes |
| AC5 | Yes (SCN005) | Yes | Yes |
| AC6 | Yes (SCN006) | Yes | Yes |
| AC7 | Yes (SCN007) | Yes | Yes, but no case with a shared variant name |
| AC8 | Yes (SCN008) | Yes | Yes |
| AC9 | Yes (SCN009) | Yes | Yes |
| AC10 | Yes (SCN010) | Yes | Yes |

### Coverage Summary

- Feature file: 10 scenarios (`specs/148-…/feature.gherkin`), mapped to named pytest and headless-Blender tests as tasks.md specifies
- Unit tests: 41 feature tests in `tests/unit/test_material_variants_host.py` and `tests/unit/test_build_master_material.py`. Rerun locally at this head: 41 passed
- Blender headless tests: `tests/blender/test_material_variants.py`, run by `gate-blender-headless`
- UE-side code is exercised against an in-memory fake `unreal` module. No live editor was used, per project policy

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` | **Fail** | `uv run pytest tests/unit tests/bdd -q`: 1 failed, 1003 passed, 9 skipped. The failure is `test_scaffold.py::test_unreal_launcher_detaches` ("Script took 3.76s (> 2s)"), a timing test outside #148's diff that failed under concurrent host load. Isolated reruns: 2 of 3 passed. The 41 feature unit tests passed |
| `repository.lint` | Pass | `ruff check .`: All checks passed |
| `repository.format` | Pass | `ruff format --check .` exited 0 |
| `repository.types` | Pass | `mypy src tests` exited 0 |
| `gate-blender-headless` | Pass | `scripts/run-blender-tests.sh` exited 0 (includes `tests/blender/test_material_variants.py`) |
| `gate-ue-compile` | Incomplete | Deferred until required local validations pass. An earlier run at this head passed |
| `gate-mcp-schema` | Pass | `validate-mcp-tools.py` exited 0 (`list_material_variants`, `material_variants_path`) |
| `gate-shellcheck` | Not applicable | No `scripts/**.sh` in the change |
| `gate-ship-smoke` | Not applicable | No ship paths in the change |
| `plugin.validate` | Pass | `claude plugin validate .` exited 0 |
| `plugin.session-smoke` | Incomplete | Deferred until required local validations pass. An earlier run at this head passed |

Artifact: `.nmg-sdlc/verification/148.json`, generated 2026-11-11T21:41:45Z at head `c868ff578d46a8c47cdc08eab67ab859de4b8f32`, clean tree. Coverage is complete (11 declared, 11 recorded), with ceiling `Incomplete` and a required failure.

**Gate Summary**: 6/9 applicable gates passed, 1 failed, 2 incomplete (2 not applicable)

---

## Fixes Applied

None. This verify step may only write `verification-report.md`. The publication scope bound for this step does not allow source edits.

## Remaining Issues

### High Priority

| Field | Value |
|-------|-------|
| **Severity** | High (AC7 not met for a valid declaration) |
| **Category** | Architecture / Spec compliance |
| **Location** | `src/nmg_game_dev/unreal/import_asset.py:392`; design.md "API / Interface Changes" row for `import_variant` |
| **Issue** | The `import_ue` result's `material_variants` is a dict keyed by variant name. The contract allows one variant name on several materials, because `material_variant.duplicate` is per material. A shared name, such as a `Red` look across `Body` and `Lid`, keeps only the last entry. |
| **Impact** | Unreal state is correct: both instances are created and tagged, and `list_material_variants` lists both. The finalize result returned to the agent and developer omits created instances, so AC7 and FR7 are only partly met. Applying one look to every part of an asset is a common use, so this case is likely. |
| **Reason Not Fixed** | The verify scope may only write the report. The variant-keyed shape is also fixed by the approved design.md, so any fix needs a design amendment. |
| **Suggested fix** | Key the result by material instance name (`MI_<Name>_<Part>_<Variant>`), or make it a list of `{name, material, instance, texture}` entries. Amend design.md's `import_variant` interface row to match. Add a unit test with one variant name on two materials. |

### Medium Priority

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Category** | Error Handling / Delivery |
| **Location** | `plugins/nmg-game-dev-ue-plugin/Content/Materials/M_NmgORM.uasset`; `unreal/import_asset.py` `_bind_material_variants` |
| **Issue** | The committed `M_NmgORM.uasset` was built before #148 and has no `Tint` parameter. Only the builder script changed. The import calls `set_material_instance_vector_parameter_value` without checking its return value. On a pre-#148 master, a parameter-only variant imports without error and renders exactly like the main material. |
| **Impact** | Parameter (`Tint`) variants have no visible effect in consumer projects until a maintainer rebuilds the master with `scripts/unreal/build_master_material.py` in a live UE 5.8 editor and commits the asset. `docs/asset-contract.md` §4 documents the rebuild. |
| **Judgment against the spec** | Within scope. Design.md §7 and T004 define the deliverable as the builder change, proven against a fake `unreal` module, and forbid a live editor. AC3's master-material clause holds at the source level. The asset rebuild is a maintainer step outside the SDLC run. |
| **Reason Not Fixed** | Needs a live editor, which SDLC work must not use. |
| **Recommendation** | Track the rebuild and commit of `M_NmgORM.uasset` as a follow-up issue before release. Consider making the import fail or warn when a declared parameter is missing on the parent. |

### Low Priority

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Error Handling |
| **Location** | `src/nmg_game_dev/unreal/import_asset.py:399` |
| **Issue** | If a variant keeps its name and material but drops its `base_color` (texture to parameter-only), its tagged `T_..._BC_<Variant>` texture stays in Content, because the (slot, variant) pair is still declared. The export folder PNG is removed. |
| **Reason Not Fixed** | Outside AC9, which covers removed variants. Verify scope only. |

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Testing |
| **Location** | `tests/bdd/steps/test_scaffold.py:271` (`script_returns_quickly`) |
| **Issue** | A hard 2 s wall-clock limit on `start-unreal-mcp.sh` fails when the host is loaded (3.76 s here, with parallel lanes compiling UE). It is outside #148's diff, but it blocks this gate. |
| **Reason Not Fixed** | Outside #148's scope, and verify may only write the report. Re-run the gate on a quieter host, or harden the test in a separate issue. |

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Process |
| **Location** | `.nmg-sdlc/verification/148.json` `changedPaths` |
| **Issue** | The local `main` ref is behind `origin/main`, so the gate's `--base main` diff also lists other issues' spec files. Applicability only grows, so the gate result is conservative and still valid. The branch is also behind `origin/main` by seven spec-approval commits (docs only). Delivery handles mergeability. |
| **Reason Not Fixed** | Not a code defect. |

---

## Positive Observations

- The predicted parts and merge decision reuse the bake's own `part_names` and merge condition, so validation cannot disagree with the bake.
- Tags drive both listing and stale deletion, so part names containing underscores are never parsed, and deletion is limited to assets finalize created.
- Cache keys move only for validate and export, and the fingerprint covers texture bytes. `_STEP_VERSION` was bumped.
- Without a declaration, outputs are unchanged and tests prove it.
- The UE builder and import templates are exercised against in-memory fakes instead of a live editor.

---

## Recommendations Summary

### Before PR (Must)
- [ ] Re-run the full registered gate to green after the fix below. `repository.tests` failed on a load-sensitive scaffold timing test, so run it when no other lane is compiling Unreal.
- [ ] Fix the `import_ue` result shape so one variant name on several materials is listed in full. Amend design.md's interface row and add a test (Remaining Issue 1).

### Short Term (Should)
- [ ] Rebuild and commit `M_NmgORM.uasset` with `Tint` in a maintainer session, and/or make the import flag a declared parameter the parent lacks (Remaining Issue 2).

### Long Term (Could)
- [ ] Delete a variant's stale texture when it becomes parameter-only.

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `plugins/nmg-game-dev-blender-addon/contract_core/material_variants.py` | 0 | |
| `plugins/nmg-game-dev-blender-addon/contract_core/validate.py` | 0 | |
| `plugins/nmg-game-dev-blender-addon/contract_core/report.py` | 0 | |
| `plugins/nmg-game-dev-blender-addon/variants_core/material_variants.py` | 0 | |
| `plugins/nmg-game-dev-blender-addon/finalize_core/steps.py` | 0 | |
| `plugins/nmg-game-dev-blender-addon/utils/master_material.py` | 0 | |
| `scripts/unreal/build_master_material.py` | 1 | Committed asset not rebuilt (Medium) |
| `src/nmg_game_dev/unreal/import_asset.py` | 2 | Result collision (High); stale texture on texture-to-parameter change (Low) |
| `src/nmg_game_dev/unreal/material_variants.py` | 0 | |
| `src/nmg_game_dev/pipeline/{engine,request,steps}.py` | 0 | |
| `src/nmg_game_dev/finalize/{service,mcp_tools,__main__,__init__}.py` | 0 | |
| `mcp-servers/finalize/src/finalize_mcp/server.py`, `mcp-servers/finalize/tools.json` | 0 | |
| `docs/asset-contract.md`, `docs/mcp/finalize.md`, `skills/finalize-asset/SKILL.md` | 0 | |
| `tests/unit/test_material_variants_host.py`, `tests/unit/test_build_master_material.py`, `tests/blender/test_material_variants.py`, `tests/blender/contract_fixtures.py` | 1 | No shared-variant-name case |

---

## Recommendation

**Needs fixes**

Nine of ten ACs are met. The registered gate at this head recorded a `repository.tests` failure, a load-sensitive timing test unrelated to #148, and deferred `gate-ue-compile` and `plugin.session-smoke`, so status is capped at Fail. AC7 is Partial: the `import_ue` result drops material instances when two materials share a variant name, which the contract allows. Route back to implementation to change the result shape (with a design.md amendment) and add a covering test, then re-run the full gate and re-verify. The `M_NmgORM.uasset` rebuild is within spec scope as delivered, but it should be tracked as a follow-up before parameter variants are relied on.
