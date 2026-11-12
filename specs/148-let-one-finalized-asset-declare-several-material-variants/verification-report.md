# Verification Report: Material variants for finalized assets

**Date**: 2026-11-11
**Issue**: #148
**Reviewer**: Claude (nmg-sdlc architecture-reviewer, verify worker)
**Scope**: Implementation verification against spec

**Verification head**: 7a43238eb09062b00b68ca2d4c147ab990092a13

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
**Total Issues**: 4 (0 Critical, 0 High, 1 Medium, 3 Low), none blocking

All ten acceptance criteria and all nine tasks are met at `7a43238`, the merge of `origin/main` (#173, #182, #184, #185, #187) into the #148 branch. This run re-verified the merged head. Here is what the feature delivers:

- Finds `<Name>.material-variants.json` beside the `.blend`, or takes an explicit path.
- Checks the declaration with eight `material_variant.*` contract rules.
- Writes Desktop and Mobile variant textures and records them in the sidecar.
- Imports into Unreal with metadata tags, reuses existing variant assets, and deletes stale ones.
- Lists variants through the MCP tool and the CLI.
- Adds the `Tint` parameter to the master-material builder.
- Adds the declaration to the validate and export cache keys, and documents the feature.

The AC7 failure in the earlier `c868ff5` run is fixed. Commit `03dfcab` changes the `import_ue` result's `material_variants` to a list with one entry per imported instance (`name`, `material`, `instance`, `texture`). A variant name used on two materials therefore no longer overwrites the first entry.

The merge kept both sides. `import_asset.py` runs main's multi-part build scale, rename, and LOD-group logic first, then #148's `_bind_material_variants` and `_delete_stale_variants`. `validate.py` takes main's per-variant `resolve_budget` (#182), and `_material_variant_checks` still reads `budgets["desktop"]["max_texture_px"]`, which the resolved Desktop budget provides. The #148 host tests were ported onto main's `tests/unit/fake_unreal.py`, which gained tags, listing, deletion, and vector parameters.

All 11 registered validations are recorded at this exact head and spec identity, and coverage is complete. Ten passed, including `gate-blender-headless`, `gate-ue-compile`, `gate-shellcheck`, and `plugin.session-smoke`. `gate-ship-smoke` does not apply.

---

## Issue Scope

- Active issue: #148
- Spec: `specs/148-let-one-finalized-asset-declare-several-material-variants`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1-AC10]; FR [FR1-FR9]; tasks [T001-T009]; scenarios [SCN001-SCN010]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":148,"specPath":"specs/148-let-one-finalized-asset-declare-several-material-variants","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6","AC7","AC8","AC9","AC10"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6","FR7","FR8","FR9"],"tasks":["T001","T002","T003","T004","T005","T006","T007","T008","T009"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006","SCN007","SCN008","SCN009","SCN010"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

- Artifact: `.nmg-sdlc/verification/148.json` (generatedAt `2026-11-12T00:06:35.742Z`, base ref `main`)
- Identity: head `7a43238eb09062b00b68ca2d4c147ab990092a13`, clean tree, specHash `sha256:e63bc77a…7164f`, steeringHash `sha256:119992c8…096a9`, run id `fef03425-c990-4686-b9f1-8b3d69cb6efb`
- Coverage: declared 11, recorded 11, complete `true`; missing, duplicate, and unknown are empty
- Ceiling: `null`, so the steering evidence does not cap the status
- This worker ran `sdlc-verify-steering.mjs` fresh at the merged head under this controller run. `sdlc-finalize-verification.mjs` checks the artifact's identity again at publication.

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | An asset declares its material variants | Pass | `src/nmg_game_dev/finalize/service.py` `resolve_material_variants` (explicit path wins, else `<collection>.material-variants.json` beside `blend`); `contract_core/validate.py` adds report key `material_variants`; tests `test_the_declaration_beside_the_blend_is_found_and_absolute`, `test_an_explicit_declaration_wins_over_the_one_beside_the_blend`, `test_scn001_the_declaration_is_read_and_each_variant_is_listed` |
| AC2 | Texture variants are imported for Desktop and Mobile | Pass | `variants_core/material_variants.py` (Desktop copy; Mobile scaled to the Mobile `T_<Name>_<Part>_BC` size with `mobile_image_copy`); `unreal/import_asset.py` `_import_textures` (`_BC_<Variant>` is sRGB) and `_bind_material_variants` (BaseColor = variant, Normal and ORM = main set); tests `test_scn002_…`, `test_the_mobile_variant_is_scaled_to_the_mobile_base_colour`, `test_a_texture_variant_is_created_beside_the_main_set_with_its_textures` |
| AC3 | Parameter variants use Tint | Pass | Parameter-only entries write no texture (`test_scn003_…`); the import sets `Tint` on the MI (`test_a_parameter_variant_sets_tint_and_keeps_the_main_textures`); `scripts/unreal/build_master_material.py` `_tint` plus a Multiply node, proven against a fake `unreal` module (`test_tint_is_the_vector_parameter_with_a_white_default`, `test_base_color_is_the_base_color_sampler_times_tint`); the main MI never sets `Tint`. The shipped `M_NmgORM.uasset` still needs a rebuild in a live editor (see Remaining Issues) |
| AC4 | The main asset is unchanged | Pass | Variant MIs are never assigned to slots (`test_variant_instances_are_tagged_and_never_bound_to_the_mesh_slot`); without a declaration the sidecar has no `material_variants` key and exports are unchanged (`test_scn004_…`, `test_without_material_variants_the_bindings_are_unchanged`, `test_a_sidecar_without_material_variants_imports_with_none`) |
| AC5 | The contract checks material variants | Pass | `contract_core/material_variants.py` `check_declaration` (rules name, duplicate, material_missing, texture_missing, texture_size, parameter, empty) and `load_declaration` (`declaration_invalid`); findings survive `authored=True`; parametrized `test_scn005_each_rule_yields_a_finding_naming_the_asset_and_variant`, `test_a_malformed_declaration_raises_declaration_invalid` |
| AC6 | Material merging is handled | Pass | `validate.py` `_material_variant_checks` reuses `bake_core.rewire.part_names` and the bake's merge condition; `material_merged` names `M_<Name>_Body`; tests `test_scn006_…`, `test_a_variant_on_the_merged_body_material_is_accepted` |
| AC7 | The sidecar and import result record material variants | Pass | Sidecar: `finalize_core/steps.py` `_sidecar_payload` adds `material_variants` `{desktop, mobile}` in the design entry shape (`test_scn007_…`). Import result: `material_variants` is a list of `{name, material, instance, texture}` entries, `textures` includes the variant textures, and `removed` and `warnings` are added (commit `03dfcab`, kept by the merge; `test_one_variant_name_on_two_materials_lists_both_instances`). The design's dict shape is judged below |
| AC8 | Material variants can be listed from Unreal | Pass | `src/nmg_game_dev/unreal/material_variants.py` reads the `nmg.*` tags and returns rows sorted by material, then name, or `[]` when nothing is found; the MCP tool `list_material_variants` and the CLI `material-variants` share it; tests `test_listing_returns_…`, `test_the_mcp_tool_returns_the_same_rows_as_the_listing`, `test_the_cli_lists_the_rows_as_json`, `test_the_mcp_tool_returns_the_unreachable_error_structured` |
| AC9 | Re-runs are idempotent and remove stale variants | Pass | Export clears `T_<Name>_*_BC_*.png` before writing (`test_scn009_…`); the import reuses existing assets through `_instance` and `replace_existing` (`test_reimporting_the_same_declaration_reuses_every_variant_asset`) and deletes only tagged pairs that are no longer declared, instances before textures, listing each in `removed` (`test_removing_a_variant_deletes_its_tagged_assets_and_reports_them`) |
| AC10 | The contract and skills document material variants | Pass | `docs/asset-contract.md` §4 "Material variants", `skills/finalize-asset/SKILL.md` "Material variants", `docs/mcp/finalize.md`; test `test_the_documents_name_the_declaration_naming_rules_and_listing` |

### Judgment: AC7/FR7 against the design.md `import_variant` row

`design.md` still shows the `import_variant` result as `"material_variants": {"<Variant>": {...}}`, a dict keyed by variant name. The implement stage cannot edit spec files, so the row was left unchanged when `03dfcab` moved to a list. Requirements take precedence over design. AC7 says "the `import_ue` result for each variant lists the imported variant textures and material instance paths", and FR7 says the result "records material variants". A dict keyed by variant name cannot meet AC7 for a valid declaration that uses one variant name on two materials (for example, `Red` on both `M_<Name>_Body` and `M_<Name>_Trim`), because the second entry would overwrite the first. The list shape lists every imported instance. `docs/asset-contract.md` documents it, and `test_one_variant_name_on_two_materials_lists_both_instances` proves it.

**Verdict:** AC7 and FR7 pass. The design.md row is stale documentation, recorded as a Low remaining issue so the design can be updated in a spec amendment.

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Parse and validate the declaration | Complete | `contract_core/material_variants.py`, `validate.py`, `report.py` RULES, `utils/master_material.py` |
| T002 | Export variant textures and sidecar | Complete | `variants_core/material_variants.py`, `finalize_core/steps.py`; the sidecar payload is built in `steps.py`, not `sidecars.py`, which does not change behaviour |
| T003 | Host request and cache keys | Complete | `request.py`, `service.py`, `steps.py` (`material_variants_fingerprint`, `_STEP_VERSION = "4"`), CLI, MCP, `tools.json` |
| T004 | Tint on M_NmgORM | Complete | Builder updated and proven with a fake `unreal` module; no live editor was used |
| T005 | Import and stale deletion | Complete | `import_asset.py` `_bind_material_variants`, `_delete_stale_variants`; `engine.py` `_sidecar_material_variants` |
| T006 | List from Unreal | Complete | `unreal/material_variants.py`, MCP tool, CLI command |
| T007 | Documentation | Complete | Asset contract §4, SKILL.md, `docs/mcp/finalize.md`; §6 budget table unchanged |
| T008 | Blender tests | Complete | `tests/blender/test_material_variants.py`, `contract_fixtures.py`; run by `gate-blender-headless` |
| T009 | Host unit tests | Complete | Combined in `tests/unit/test_material_variants_host.py` and `tests/unit/test_build_master_material.py` instead of the listed `test_unreal_import.py`, `pipeline/test_steps.py`, and `pipeline/test_engine.py`; every listed acceptance bullet has a test |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 4 | Declaration parsing and rules (`contract_core/material_variants.py`, no bpy), export (`variants_core/material_variants.py`), import, and listing are separate modules. `import_asset.py`'s UE template grows by two focused functions |
| Open/Closed | 4 | Parameters are table-driven (`MASTER_PARAMETERS`), so a new master parameter is a table change plus a builder change, kept in sync by a unit test |
| Liskov Substitution | 5 | `list_material_variants` and `import_variant` take any `UnrealPythonClient`; fakes stand in for the real client |
| Interface Segregation | 4 | New keyword-only optional arguments; existing callers are unaffected |
| Dependency Inversion | 4 | The MCP layer injects the client; the contract core receives predicted parts, merged sources, and sizes from `validate.py` instead of reading bpy itself |

### Layer Separation

The layers follow `steering/snippets/project-structure.md`. The skill calls the finalize MCP and CLI. The MCP server only adds a thin wrapper (`server.py` calls `mcp_tools.list_material_variants`). The pipeline composes the steps, the step implementations live in `finalize_core` and `src/nmg_game_dev/unreal/`, and the contract stays deterministic.

### Dependency Flow

Host code never imports the add-on. The add-on's `utils/master_material.py` is pure Python, so the unit suite can read it without Blender. Host and Blender share data through `request.json` and the sidecar.

---

## Security Assessment

- [x] Authentication: not applicable (local tooling)
- [x] Authorization: stale deletion is limited to assets in `dest` whose `nmg.asset` tag matches and whose slot and variant pair is undeclared, so assets finalize did not create are never deleted
- [x] Input validation: the declaration's schema is checked strictly (unknown keys rejected, typed fields); the MCP listing refuses category and collection names that are not PascalCase; `FinalizeRequest` checks the same pattern
- [x] Injection prevention: parameters reach the UE Python templates JSON-encoded twice (`json.dumps(json.dumps(params))`), never interpolated as code
- [x] Data protection: no secrets involved. `base_color` may be absolute, but the declaration is the author's own project file, so this is acceptable

---

## Performance Assessment

- [x] Async patterns: long Blender work stays in the background job runner; the listing is one UE Python round trip
- [x] Caching: the validate and export cache keys include the declaration bytes and every referenced texture's bytes; the bake and variants keys are unchanged, so a declaration edit does not re-bake
- [x] Resource management: Blender images loaded for Mobile scaling are removed in `finally` blocks
- [x] Query optimization: stale deletion and listing load every asset in one or two non-recursive folders. That is bounded by the asset's own folder, and acceptable

---

## Error Handling Assessment

- Structured codes: `finalize.material_variants_not_found`, `material_variant.declaration_invalid` (`ContractError`), `finalize.material_variants_failed`, and `mcp.unreal.unreachable`, each with a remediation.
- The MCP `_request` path now converts `PipelineError` into the structured `{"error": …}` payload.
- A master material without `Tint` does not fail the import. The import reports the missing parameter in `warnings` with a rebuild hint, so the problem is reported rather than hidden.
- Minor: `engine._sidecar_material_variants` does not catch `JSONDecodeError` on a corrupt sidecar. The export step writes the sidecar itself, so this is Low (see Remaining Issues).

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1 | Yes (SCN001) | Yes (unit + Blender) | Yes |
| AC2 | Yes (SCN002) | Yes | Yes |
| AC3 | Yes (SCN003) | Yes | Yes |
| AC4 | Yes (SCN004) | Yes | Yes |
| AC5 | Yes (SCN005) | Yes (parametrized per rule) | Yes |
| AC6 | Yes (SCN006) | Yes | Yes |
| AC7 | Yes (SCN007) | Yes | Yes |
| AC8 | Yes (SCN008) | Yes | Yes |
| AC9 | Yes (SCN009) | Yes | Yes |
| AC10 | Yes (SCN010) | Yes | Yes |

### Coverage Summary

- Feature file: 10 scenarios (`specs/148-…/feature.gherkin`), mapped to pytest tests named for each scenario
- Unit and BDD suite (`repository.tests`): 1091 passed, 9 skipped; the #148 host files alone (`test_material_variants_host.py`, `test_build_master_material.py`): 43 passed
- Headless Blender suite (`gate-blender-headless`): 236 passed, including the 12 tests in `tests/blender/test_material_variants.py`
- UE master-material builder: proven against an in-memory fake `unreal` module; no live editor

---

## Exercise Test Results

| Field | Value |
|-------|-------|
| **Reason** | Not applicable. This change does not touch nmg-sdlc `workflows/` or `agents/`. The nmg-game-dev plugin surfaces it does change (`skills/finalize-asset/SKILL.md` and the finalize MCP server) are covered by `plugin.validate` and `plugin.session-smoke` |
| **Recommendation** | None |

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` | Pass | `uv run pytest tests/unit tests/bdd -q`: 1091 passed, 9 skipped |
| `repository.lint` | Pass | `ruff check .`: All checks passed! |
| `repository.format` | Pass | `ruff format --check .`: 325 files already formatted |
| `repository.types` | Pass | `mypy src tests`: no issues in 206 source files |
| `gate-blender-headless` | Pass | `scripts/run-blender-tests.sh`: 236 passed |
| `gate-ue-compile` | Pass | DogfoodEditor compiled against `/Users/Shared/Epic Games/UE_5.8` |
| `gate-mcp-schema` | Pass | MCP tools match `tools.json` for every server under `mcp-servers/` |
| `gate-shellcheck` | Pass | `shellcheck -S style` clean on every `scripts/**.sh`. It applies because the diff against base ref `main` includes main's #184 script change |
| `gate-ship-smoke` | Not applicable | No ship paths changed |
| `plugin.validate` | Pass | `claude plugin validate .`: validation passed (with warnings) |
| `plugin.session-smoke` | Pass | Plugin loaded with `--plugin-dir`; `nmg-game-dev:blender` connected |

**Gate Summary**: 10/10 applicable gates passed, 0 failed, 0 incomplete (1 not applicable)

---

## Fixes Applied

| Severity | Category | Location | Original Issue | Fix Applied | Routing |
|----------|----------|----------|----------------|-------------|---------|
| — | — | — | None in this verification run. The AC7 fix (`03dfcab`) was made in the implement stage, and the merge (`7a43238`) was resolved before this run | — | — |

## Remaining Issues

### Critical Issues
None.

### High Priority
None.

### Medium Priority

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Category** | Architecture (shipped content) |
| **Location** | `plugins/nmg-game-dev-ue-plugin/Content/Materials/M_NmgORM.uasset` |
| **Issue** | The shipped master material was last rebuilt in #115 and has no `Tint` parameter. `scripts/unreal/build_master_material.py` now builds it, but the binary asset needs a rebuild in a live UE 5.8 editor |
| **Impact** | Until the rebuild, consumers who import a parameter-only material variant get an instance that looks like the main one. The import still succeeds and its `warnings` list names the instance and the missing parameter. Texture variants are not affected |
| **Reason Not Fixed** | SDLC stages never touch the live editor (project rule, and T004). The spec chooses fake-module proof for the builder |
| **Recommendation** | Open a follow-up issue to run `build_master_material.py` in a live UE 5.8 editor and commit the rebuilt `M_NmgORM.uasset` |

### Low Priority

| Severity | Category | Location | Issue | Reason Not Fixed |
|----------|----------|----------|-------|------------------|
| Low | Documentation | `specs/148-…/design.md` (API table, `import_variant` row) | Still shows `material_variants` as a dict keyed by variant name; the code and the asset contract use a list of `{name, material, instance, texture}`, and the row does not mention `warnings` | Spec files are read-only in verify. Requirements AC7/FR7 take precedence (see Judgment). Update the row in a spec amendment |
| Low | Error Handling | `src/nmg_game_dev/pipeline/engine.py` `_sidecar_material_variants` | A corrupt sidecar raises an unstructured `JSONDecodeError` | The export step writes the sidecar in the same job, so corruption is unlikely; not worth widening scope |
| Low | Delivery | Branch vs `origin/main` | `origin/main` gained `0e2fa86` and `38d164c` (#188, #190) after the `7a43238` merge. `git merge-tree` against `origin/main` reports a conflict in `CHANGELOG.md` only (main's new #188 entry beside this issue's `[Unreleased]` entry). No #148 source file is touched by those commits | A version-file merge is orchestrator-owned at deliver; merging here would move the verified head |
| Low | Testing | `tasks.md` T009 file list | Tests are combined in `tests/unit/test_material_variants_host.py` instead of the listed per-module test files | Every acceptance bullet still has a test; only the file placement differs |

---

## Positive Observations

- The predicted parts and the merge decision reuse the bake's own `part_names` and merge condition, so validation cannot drift from what the bake produces.
- Metadata tags (`nmg.asset`, `nmg.material_variant`, `nmg.material_slot`) make listing and stale deletion unambiguous and limit deletion to assets finalize created.
- A unit test keeps `MASTER_PARAMETERS` in sync with the parameters the builder creates.
- The cache-key design leaves the expensive bake and variants steps unaffected by declaration edits.

---

## Recommendations Summary

### Before PR (Must)
- None.

### Short Term (Should)
- [ ] Follow-up issue: rebuild and commit `M_NmgORM.uasset` with `Tint` in a live UE 5.8 editor.
- [ ] Amend `design.md` so the `import_variant` row shows the list shape and `warnings`.

### Long Term (Could)
- [ ] Make `_sidecar_material_variants` return a structured error for a corrupt sidecar.

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `plugins/nmg-game-dev-blender-addon/contract_core/material_variants.py` | 0 | Rules and declaration parsing |
| `plugins/nmg-game-dev-blender-addon/contract_core/validate.py` | 0 | Part prediction and merge reuse |
| `plugins/nmg-game-dev-blender-addon/contract_core/report.py` | 0 | Rule remediations |
| `plugins/nmg-game-dev-blender-addon/finalize_core/steps.py` | 0 | Request pass-through and sidecar |
| `plugins/nmg-game-dev-blender-addon/variants_core/material_variants.py` | 0 | Texture export and stale clearing |
| `plugins/nmg-game-dev-blender-addon/utils/master_material.py` | 0 | Parameter table |
| `src/nmg_game_dev/finalize/service.py`, `mcp_tools.py`, `__main__.py` | 0 | Discovery, MCP, CLI |
| `src/nmg_game_dev/pipeline/request.py`, `steps.py`, `engine.py` | 1 | Low: unstructured sidecar decode error |
| `src/nmg_game_dev/unreal/import_asset.py` | 0 | Variant MIs, tags, stale deletion, list result; merge order after main's LOD-group and rename logic checked |
| `src/nmg_game_dev/unreal/material_variants.py` | 0 | Tag-based listing |
| `mcp-servers/finalize/src/finalize_mcp/server.py`, `tools.json` | 0 | New tool and argument |
| `scripts/unreal/build_master_material.py` | 1 | Medium: shipped asset not rebuilt |
| `docs/asset-contract.md`, `docs/mcp/finalize.md`, `skills/finalize-asset/SKILL.md` | 0 | Documentation |

---

## Recommendation

**Ready for PR**

Every acceptance criterion, functional requirement, and task passes. All registered gates are recorded green at the exact merged head `7a43238`. The remaining items are a live-editor content rebuild, which belongs in a follow-up issue, and documentation and robustness polish. None of them blocks delivery.
