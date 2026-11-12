# Verification Report: Material variants for finalized assets

**Date**: 2026-11-11
**Issue**: #148
**Reviewer**: Claude (nmg-sdlc architecture-reviewer, verify worker)
**Scope**: Implementation verification against spec

**Verification head**: 10d3520de9888dced98fd332fd6a7241d211bec2

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
**Total Issues**: 5 (0 Critical, 0 High, 2 Medium, 3 Low), none blocking

All ten acceptance criteria and all nine tasks are met at `10d3520`. Since the last verified head (`4bab2fb`), the branch has merged `origin/main` three times (`35a0337`, `0f0d760`, `10d3520`). Those merges bring in #192, #201, #183, #198 and #199, so the branch now contains the current `origin/main` at `9337c95`. This run verified the merged head again from scratch. The feature:

- Finds `<Name>.material-variants.json` beside the `.blend`, or takes an explicit path.
- Checks the declaration against eight `material_variant.*` contract rules.
- Writes the Desktop and Mobile variant textures and records them in the sidecar.
- Imports the variants into Unreal with metadata tags, reuses existing variant assets, and deletes stale ones.
- Lists variants through an MCP tool and a CLI command.
- Adds the `Tint` parameter to the master-material builder.
- Adds the declaration to the validate and export cache keys.
- Documents all of the above.

The newly merged changes overlap #148 in five places. Each one was checked:

- `bake_core/rewire.py` (#198): the merge adds `_free_contract_name`, which renames an image that already holds a contract name to `<name>_Src` before the baked image takes that name. It does not change `part_names` or the merge condition that #148's `_material_variant_checks` reuses, so the predicted parts still match the bake.
- `contract_core/validate.py` (#198, #199): the merge adds the `naming.mesh_data` check and a keyword-only `progress` callback. `material_variants_path` and `_material_variant_checks` are unchanged, and the declaration findings still survive `authored=True`.
- `finalize_core/steps.py` (#199): `_validate` now passes `progress=report_progress` next to `material_variants_path`. `_export` and `_sidecar_payload` are unchanged.
- `contract_core/report.py`: the merge adds the `naming.mesh_data` rule and rewords `geometry.normals`. The `material_variant.*` remediations are intact.
- Finalize MCP (#183): `import_audio` is added beside `list_material_variants` in `mcp_tools.py`, `server.py` and `tools.json`. `gate-mcp-schema` confirms that the tools match `tools.json`, and `plugin.session-smoke` lists the finalize server with 5 tools.

All 11 registered validations are recorded at this exact head and spec identity, and coverage is complete. Ten passed and one does not apply (`gate-ship-smoke`).

This review found no new issues. The Medium and Low items from the previous verification still apply and are carried forward under Remaining Issues. This verify publication may write only this report, so none of them is fixed here.

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

- Artifact: `.nmg-sdlc/verification/148.json` (generatedAt `2026-11-12T05:08:44.158Z`, base ref `main`)
- Identity: head `10d3520de9888dced98fd332fd6a7241d211bec2`, clean tree, specHash `sha256:e63bc77a…7164f`, steeringHash `sha256:754f3665…0a584`, controller run id `ae3e6bba-0370-442c-b466-f833e34daa1c`
- Coverage: declared 11, recorded 11, complete `true`; nothing missing, duplicated, or unknown
- Ceiling: `null`, so the steering evidence does not cap the status
- This worker ran `sdlc-verify-steering.mjs` fresh at the merged head under this controller run. `sdlc-finalize-verification.mjs` checks the artifact's identity again at publication.

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | An asset declares its material variants | Pass | `src/nmg_game_dev/finalize/service.py` `resolve_material_variants`: an explicit path wins; otherwise `<collection>.material-variants.json` beside `blend` is used. `contract_core/validate.py` adds the report key `material_variants`. Tests: `test_the_declaration_beside_the_blend_is_found_and_absolute`, `test_an_explicit_declaration_wins_over_the_one_beside_the_blend`, `test_scn001_the_declaration_is_read_and_each_variant_is_listed` |
| AC2 | Texture variants are imported for Desktop and Mobile | Pass | `variants_core/material_variants.py` copies the texture for Desktop and scales it to the Mobile `T_<Name>_<Part>_BC` size with `mobile_image_copy`. In `unreal/import_asset.py`, `_import_textures` treats `_BC_<Variant>` as sRGB, and `_bind_material_variants` sets BaseColor to the variant texture and Normal and ORM to the main set. Tests: `test_scn002_…`, `test_the_mobile_variant_is_scaled_to_the_mobile_base_colour`, `test_a_texture_variant_is_created_beside_the_main_set_with_its_textures` |
| AC3 | Parameter variants use Tint | Pass | Parameter-only entries write no texture (`test_scn003_…`), and the import sets `Tint` on the MI (`test_a_parameter_variant_sets_tint_and_keeps_the_main_textures`). `scripts/unreal/build_master_material.py` adds `_tint` and a Multiply node, proven against a fake `unreal` module (`test_tint_is_the_vector_parameter_with_a_white_default`, `test_base_color_is_the_base_color_sampler_times_tint`). The main MI never sets `Tint`. The shipped `M_NmgORM.uasset` still needs a rebuild in a live editor (see Remaining Issues) |
| AC4 | The main asset is unchanged | Pass | Variant MIs are never assigned to mesh slots (`test_variant_instances_are_tagged_and_never_bound_to_the_mesh_slot`). Without a declaration, the sidecar has no `material_variants` key and the exports are unchanged (`test_scn004_…`, `test_without_material_variants_the_bindings_are_unchanged`, `test_a_sidecar_without_material_variants_imports_with_none`) |
| AC5 | The contract checks material variants | Pass | In `contract_core/material_variants.py`, `check_declaration` applies the name, duplicate, material_missing, texture_missing, texture_size, parameter, and empty rules, and `load_declaration` raises `declaration_invalid`. These findings survive `authored=True`. Tests: parametrized `test_scn005_each_rule_yields_a_finding_naming_the_asset_and_variant`, `test_a_malformed_declaration_raises_declaration_invalid` |
| AC6 | Material merging is handled | Pass | `validate.py` `_material_variant_checks` reuses `bake_core.rewire.part_names` and the bake's merge condition, and `material_merged` names `M_<Name>_Body`. Tests: `test_scn006_…`, `test_a_variant_on_the_merged_body_material_is_accepted` |
| AC7 | The sidecar and import result record material variants | Pass | `finalize_core/steps.py` `_sidecar_payload` adds `material_variants` with `desktop` and `mobile` lists in the design entry shape (`test_scn007_…`). In the import result, `material_variants` is a list of `{name, material, instance, texture}` entries, `textures` includes the variant textures, and `removed` and `warnings` are added (`test_one_variant_name_on_two_materials_lists_both_instances`). The design's dict shape is judged below |
| AC8 | Material variants can be listed from Unreal | Pass | `src/nmg_game_dev/unreal/material_variants.py` reads the `nmg.*` tags and returns rows sorted by material, then name, or `[]` when nothing is found. The MCP tool `list_material_variants` and the CLI command `material-variants` share this code. Tests: `test_listing_returns_…`, `test_the_mcp_tool_returns_the_same_rows_as_the_listing`, `test_the_cli_lists_the_rows_as_json`, `test_the_mcp_tool_returns_the_unreachable_error_structured` |
| AC9 | Re-runs are idempotent and remove stale variants | Pass | Export clears `T_<Name>_*_BC_*.png` before it writes (`test_scn009_…`). The import reuses existing assets through `_instance` and `replace_existing` (`test_reimporting_the_same_declaration_reuses_every_variant_asset`). It deletes only tagged slot and variant pairs that are no longer declared, instances before textures, and lists each one in `removed` (`test_removing_a_variant_deletes_its_tagged_assets_and_reports_them`). Deleting the whole file is a separate case, outside AC9 (Medium, see Remaining Issues) |
| AC10 | The contract and skills document material variants | Pass | `docs/asset-contract.md` §4 "Material variants", `skills/finalize-asset/SKILL.md` "Material variants", and `docs/mcp/finalize.md`. Test: `test_the_documents_name_the_declaration_naming_rules_and_listing` |

### Judgment: AC7/FR7 against the design.md `import_variant` row

`design.md` still shows the `import_variant` result as `"material_variants": {"<Variant>": {...}}`, a dict keyed by variant name. Requirements take precedence over the design. AC7 requires the result to list the imported variant textures and material instance paths. A dict keyed by variant name cannot do that when a valid declaration uses one variant name on two materials, because the second entry overwrites the first. The implemented list has one entry per instance. `docs/asset-contract.md` documents it, and `test_one_variant_name_on_two_materials_lists_both_instances` proves it.

**Verdict:** AC7 and FR7 pass. The design.md row is stale and is recorded as a Low remaining issue.

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Parse and validate the declaration | Complete | `contract_core/material_variants.py`, `validate.py`, `report.py` RULES, `utils/master_material.py` |
| T002 | Export variant textures and sidecar | Complete | `variants_core/material_variants.py` and `finalize_core/steps.py`. The sidecar payload is built in `steps.py` rather than `sidecars.py`; the behaviour is the same |
| T003 | Host request and cache keys | Complete | `request.py`, `service.py`, `steps.py` (`material_variants_fingerprint`, `_STEP_VERSION = "4"`), the CLI, the MCP server, and `tools.json` |
| T004 | Tint on M_NmgORM | Complete | The builder is updated and proven with a fake `unreal` module. No live editor was used |
| T005 | Import and stale deletion | Complete | `import_asset.py` `_bind_material_variants` and `_delete_stale_variants`; `engine.py` `_sidecar_material_variants`. Both still run after #196's mesh resolution, and the later merges do not touch `import_asset.py` |
| T006 | List from Unreal | Complete | `unreal/material_variants.py`, the MCP tool, and the CLI command |
| T007 | Documentation | Complete | Asset contract §4, SKILL.md, and `docs/mcp/finalize.md`. The §6 budget table is unchanged |
| T008 | Blender tests | Complete | `tests/blender/test_material_variants.py` and `contract_fixtures.py`, run by `gate-blender-headless` |
| T009 | Host unit tests | Complete | Combined in `tests/unit/test_material_variants_host.py` and `tests/unit/test_build_master_material.py`. Every listed acceptance bullet has a test |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 4 | Declaration parsing and rules (`contract_core/material_variants.py`, which imports no bpy), export, import, and listing are separate modules. The UE template in `import_asset.py` gains two focused functions |
| Open/Closed | 4 | Parameters are table-driven (`MASTER_PARAMETERS`), and a unit test keeps the table in sync with the builder |
| Liskov Substitution | 5 | `list_material_variants` and `import_variant` accept any `UnrealPythonClient`, and fakes substitute cleanly |
| Interface Segregation | 4 | The new arguments are optional keywords, so existing callers are unaffected |
| Dependency Inversion | 4 | The MCP layer injects the client. The contract core receives the predicted parts, the merged sources, and the sizes from `validate.py` |

### Layer Separation

The layers follow `steering/snippets/project-structure.md`. The skill calls the finalize MCP tools and the CLI. The MCP server is a thin wrapper over `mcp_tools`. The pipeline composes the steps, the step implementations live in `finalize_core` and `src/nmg_game_dev/unreal/`, and the contract checks stay deterministic.

### Dependency Flow

Host code never imports the add-on. The add-on's `utils/master_material.py` is pure Python, so the unit suite can read it. Host and Blender exchange data only through `request.json` and the sidecar.

---

## Security Assessment

- [x] Authentication: not applicable (local tooling)
- [x] Authorization: stale deletion touches only assets in `dest` whose `nmg.asset` tag matches and whose slot and variant pair is no longer declared
- [x] Input validation: the declaration schema is strict (unknown keys are rejected and fields are typed). The MCP listing rejects category and collection names that are not PascalCase
- [x] Injection prevention: parameters reach the UE Python templates double-JSON-encoded and are never interpolated as code
- [x] Data protection: no secrets are involved. `base_color` may be an absolute path, but it points into the author's own project files

---

## Performance Assessment

- [x] Async patterns: long Blender work stays in the background job runner, and listing takes one UE Python round trip
- [x] Caching: the validate and export cache keys include the declaration bytes and each referenced texture's bytes. The bake and variants keys are unchanged, so editing the declaration never re-bakes
- [x] Resource management: Blender images loaded for Mobile scaling are freed in `finally` blocks
- [x] Query optimization: listing and stale deletion read only one or two non-recursive asset folders

---

## Error Handling Assessment

- Each structured code carries a remediation: `finalize.material_variants_not_found`, `material_variant.declaration_invalid` (`ContractError`), `finalize.material_variants_failed`, and `mcp.unreal.unreachable`.
- The MCP and CLI request paths convert `PipelineError` into structured errors.
- If the master material lacks `Tint`, the import still succeeds and its `warnings` list carries a rebuild hint.
- Minor: `engine._sidecar_material_variants` does not catch `JSONDecodeError` from a corrupt sidecar (Low).

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

- Feature file: 10 scenarios, each mapped to pytest tests named for the scenario
- Unit and BDD suite (`repository.tests`): 1263 passed, 10 skipped
- Headless Blender suite (`gate-blender-headless`): 307 passed, 4 skipped, including `tests/blender/test_material_variants.py`
- UE master-material builder: proven against an in-memory fake `unreal` module, with no live editor

---

## Exercise Test Results

| Field | Value |
|-------|-------|
| **Reason** | Not applicable: the change does not touch nmg-sdlc `workflows/` or `agents/`. The nmg-game-dev plugin surfaces it does touch (`skills/finalize-asset/SKILL.md` and the finalize MCP server) are covered by `plugin.validate` and `plugin.session-smoke` |
| **Recommendation** | None |

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` | Pass | `uv run pytest tests/unit tests/bdd -q`: 1263 passed, 10 skipped |
| `repository.lint` | Pass | `ruff check .`: All checks passed! |
| `repository.format` | Pass | `ruff format --check .`: 359 files already formatted |
| `repository.types` | Pass | `mypy src tests`: no issues found in 231 source files |
| `gate-blender-headless` | Pass | `scripts/run-blender-tests.sh`: 307 passed, 4 skipped |
| `gate-ue-compile` | Pass | DogfoodEditor compiled against `/Users/Shared/Epic Games/UE_5.8` (Result: Succeeded) |
| `gate-mcp-schema` | Pass | `scripts/validate-mcp-tools.py`: MCP tools match tools.json for every server |
| `gate-shellcheck` | Pass | `shellcheck -S style` is clean on every `scripts/**.sh` |
| `gate-ship-smoke` | Not applicable | No ship paths changed |
| `plugin.validate` | Pass | `claude plugin validate .`: Validation passed with warnings (directory-profile notes only) |
| `plugin.session-smoke` | Pass | Plugin loaded with `--plugin-dir`. The required `nmg-game-dev:blender` server connected, and so did finalize (5 tools), meshy and texture-gen. Unreal is not in `expectConnected` |

**Gate Summary**: 10/10 applicable gates passed, 0 failed, 0 incomplete (1 not applicable)

---

## Fixes Applied

| Severity | Category | Location | Issue | Fix | Routing |
|----------|----------|----------|-------|-----|---------|
| — | — | — | None in this run. The verify publication scope allows writing only this report | — | — |

## Remaining Issues

### Critical Issues
None.

### High Priority
None.

### Medium Priority

| Severity | Category | Location | Issue | Reason Not Fixed |
|----------|----------|----------|-------|------------------|
| Medium | Architecture (shipped content) | `plugins/nmg-game-dev-ue-plugin/Content/Materials/M_NmgORM.uasset` | The shipped master material has no `Tint` parameter until someone rebuilds it with `build_master_material.py` in a live UE 5.8 editor. Until then, a parameter-only variant looks like the main material. The import still succeeds and names the missing parameter in `warnings` | SDLC stages never touch the live editor (project rule and T004), and the spec chose fake-module proof for the builder. Tracked by #204, whose approved spec rebuilds the asset headlessly |
| Medium | Correctness (stale cleanup) | `plugins/nmg-game-dev-blender-addon/finalize_core/steps.py` `_export`; `variants_core/material_variants.py` | `T_<Name>_*_BC_*.png` is cleared only inside `export_material_variants`, which runs only when the report has `material_variants`. If an author deletes the whole `<Name>.material-variants.json` (instead of removing entries), the old variant PNGs stay in the Desktop and Mobile export folders, and `_import_textures` imports them again. This contradicts the asset contract's stale-deletion wording for that path. AC9's scenario (removing one entry) works | Outside the AC scope. This verify publication may write only this report. Fix: call the clearing step on every export, and add a Blender test for deleting the whole file |

### Low Priority

| Severity | Category | Location | Issue | Reason Not Fixed |
|----------|----------|----------|-------|------------------|
| Low | Documentation | `specs/148-…/design.md` (API table, `import_variant` row) | Still shows `material_variants` as a dict keyed by variant name and omits `warnings` | Spec files are read-only in verify. Requirements AC7/FR7 take precedence |
| Low | Error Handling | `src/nmg_game_dev/pipeline/engine.py` `_sidecar_material_variants` | A corrupt sidecar raises an unstructured `JSONDecodeError` | The same job's export step writes the sidecar, so corruption is unlikely |
| Low | Testing | `tasks.md` T009 file list | The tests are combined in `tests/unit/test_material_variants_host.py` instead of the per-module test files listed in T009 | Every acceptance bullet still has a test |

---

## Positive Observations

- The predicted parts and the merge decision reuse the bake's own `part_names` and merge condition, so validation cannot drift from what the bake produces.
- The metadata tags make listing and stale deletion unambiguous and limit deletion to assets that finalize created.
- A unit test keeps `MASTER_PARAMETERS` in sync with the builder.
- Editing the declaration never invalidates the bake or variants cache.

---

## Recommendations Summary

### Before PR (Must)
- None.

### Short Term (Should)
- [ ] Rebuild `M_NmgORM.uasset` with `Tint` and commit it. Spec #204 (approved on main) covers this with a headless rebuild.
- [ ] Follow-up issue: clear stale `T_<Name>_*_BC_*.png` on every export, so deleting the declaration file removes variant textures.
- [ ] Amend the `import_variant` row in `design.md` to show the list shape and `warnings`.

### Long Term (Could)
- [ ] Make `_sidecar_material_variants` return a structured error for a corrupt sidecar.

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `plugins/nmg-game-dev-blender-addon/contract_core/material_variants.py` | 0 | Rules and declaration parsing |
| `plugins/nmg-game-dev-blender-addon/contract_core/validate.py` | 0 | Part prediction and merge reuse; checked again after the merged #198 and #199 changes |
| `plugins/nmg-game-dev-blender-addon/contract_core/report.py` | 0 | Rule remediations |
| `plugins/nmg-game-dev-blender-addon/finalize_core/steps.py` | 1 | Medium: stale PNGs stay when the declaration file is deleted |
| `plugins/nmg-game-dev-blender-addon/variants_core/material_variants.py` | 0 | Texture export and stale clearing |
| `plugins/nmg-game-dev-blender-addon/utils/master_material.py` | 0 | Parameter table |
| `src/nmg_game_dev/finalize/service.py`, `mcp_tools.py`, `__main__.py` | 0 | Discovery, MCP, CLI |
| `src/nmg_game_dev/pipeline/request.py`, `steps.py`, `engine.py` | 1 | Low: unstructured sidecar decode error |
| `src/nmg_game_dev/unreal/import_asset.py` | 0 | Variant MIs, tags, stale deletion, and the result list; ordering checked after #196's mesh resolution |
| `plugins/nmg-game-dev-blender-addon/bake_core/rewire.py` | 0 | Merged #198 `_free_contract_name`; `part_names` and the merge condition are unchanged |
| `src/nmg_game_dev/unreal/material_variants.py` | 0 | Tag-based listing |
| `mcp-servers/finalize/src/finalize_mcp/server.py`, `tools.json` | 0 | New tool and argument |
| `scripts/unreal/build_master_material.py` | 1 | Medium: the shipped asset is not rebuilt |
| `docs/asset-contract.md`, `docs/mcp/finalize.md`, `skills/finalize-asset/SKILL.md` | 0 | Documentation |

---

## Recommendation

**Ready for PR**

Every acceptance criterion, functional requirement, and task passes, and all registered gates are recorded green at the exact merged head `10d3520`. The branch contains the current `origin/main` (`9337c95`), and the merged #192, #201, #183, #198 and #199 changes do not regress any #148 behaviour. The two Medium items are a content rebuild (#204) and a stale-cleanup edge case outside the ACs. Neither blocks delivery.
