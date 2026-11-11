# Tasks: Material variants for finalized assets

**Issue**: #148
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley

## Implementation Tasks

### T001: Parse and validate the material-variant declaration

**File(s)**: `plugins/nmg-game-dev-blender-addon/contract_core/material_variants.py`, `plugins/nmg-game-dev-blender-addon/contract_core/validate.py`, `plugins/nmg-game-dev-blender-addon/contract_core/report.py`, `plugins/nmg-game-dev-blender-addon/utils/master_material.py`
**Type**: Create, Modify
**Depends**: none
**Acceptance**:
- `validate_asset` accepts `material_variants_path` and, when it is set, adds the report key `material_variants` with each entry's name, material, resolved texture file, and parameters (AC1).
- Each rule in design.md's rule table produces a finding with its `material_variant.*` id, a target, and a message naming the asset, the material variant, and the rule, plus a remediation (AC5, AC6). These findings survive `authored=True`.
- `material_variant.material_merged` names `M_<Name>_Body`. Predicted parts reuse `bake_core/rewire.part_names` and the bake's merge condition (AC6).
- A malformed declaration raises `ContractError` `material_variant.declaration_invalid`.
- Without `material_variants_path`, reports are unchanged (AC4).
- `utils/master_material.py` defines `MASTER_PARAMETERS = {"Tint": "vector"}` without importing bpy.

### T002: Export variant textures and record them in the sidecar

**File(s)**: `plugins/nmg-game-dev-blender-addon/variants_core/material_variants.py`, `plugins/nmg-game-dev-blender-addon/finalize_core/steps.py`, `plugins/nmg-game-dev-blender-addon/variants_core/sidecars.py`
**Type**: Create, Modify
**Depends**: T001
**Acceptance**:
- `_validate` and `_export` pass `request["material_variants_path"]` (when present) to `validate_asset` (AC1, AC5).
- After a passing pre-check, export removes `T_<Name>_*_BC_*.png` from both variant folders. It then writes `T_<Name>_<Part>_BC_<Variant>.png` for each texture-based material variant, at the size of that folder's `T_<Name>_<Part>_BC` (AC2, AC9).
- Parameter-only material variants write no texture (AC3).
- `nmg-variants.json` gains `material_variants` with `desktop` and `mobile` lists in the design.md entry shape, only when a declaration exists (AC4, AC7).

### T003: Carry the declaration through the host request and cache keys

**File(s)**: `src/nmg_game_dev/pipeline/request.py`, `src/nmg_game_dev/pipeline/steps.py`, `src/nmg_game_dev/finalize/service.py`, `src/nmg_game_dev/finalize/__main__.py`, `src/nmg_game_dev/finalize/mcp_tools.py`, `mcp-servers/finalize/src/finalize_mcp/server.py`, `mcp-servers/finalize/tools.json`
**Type**: Modify
**Depends**: none
**Acceptance**:
- `FinalizeRequest.material_variants_path` is written to `request.json` as an absolute path.
- `build_request` uses an explicit path, or discovers `<collection>.material-variants.json` beside `blend`. A missing explicit path raises `finalize.material_variants_not_found` (AC1).
- The CLI `--material-variants` option and the MCP `material_variants_path` argument of `finalize_asset` and `run_finalize_step` pass the explicit path. `tools.json` documents it, and `gate-mcp-schema` passes.
- `settings_hash` includes `material_variants_fingerprint` for `validate` and `export` only, so a changed declaration or texture byte changes those keys and leaves the `bake` and `variants` keys unchanged (FR9).
- `_STEP_VERSION` is `"4"`.

### T004: Add the Tint parameter to M_NmgORM

**File(s)**: `scripts/unreal/build_master_material.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- The builder adds a `MaterialExpressionVectorParameter` named `Tint` with default (1, 1, 1, 1) and a Multiply between `BaseColor` RGB and Base Color. Normal and ORM wiring, sampler defaults, and skeletal usage are unchanged (AC3).
- Implementation and verification never launch, restart, or connect to a live Blender GUI session or Unreal editor.

### T005: Import material variants into Unreal and delete stale ones

**File(s)**: `src/nmg_game_dev/unreal/import_asset.py`, `src/nmg_game_dev/pipeline/engine.py`
**Type**: Modify
**Depends**: T002, T004
**Acceptance**:
- `_run_import` passes each variant's `material_variants` sidecar list to `import_variant`, which passes it into the template params.
- `_import_textures` treats `_BC_<Variant>` stems as sRGB base colour (AC2).
- For each entry, the template creates or reuses `MI_<Name>_<Part>_<Variant>` in `dest`, parented to `M_NmgORM`. It sets `BaseColor` to the variant texture (or the main `_BC`), sets `Normal` and `ORM` to the main textures, and sets each declared vector parameter. It sets the `nmg.asset`, `nmg.material_variant`, and `nmg.material_slot` metadata tags on the MI and its texture, saves both, and never assigns the MI to a mesh slot (AC2, AC3, AC4).
- The template deletes tagged assets in `dest` whose `nmg.asset` is `<Name>` and whose slot/variant pair is no longer declared, and records their paths in `removed` (AC9).
- The result gains `material_variants` and `removed` as specified in design.md (AC7).
- With no material variants, the template's bindings and result keys for meshes, textures, and materials are unchanged (AC4).

### T006: List material variants from Unreal

**File(s)**: `src/nmg_game_dev/unreal/material_variants.py`, `src/nmg_game_dev/unreal/__init__.py`, `src/nmg_game_dev/finalize/__main__.py`, `src/nmg_game_dev/finalize/mcp_tools.py`, `mcp-servers/finalize/src/finalize_mcp/server.py`, `mcp-servers/finalize/tools.json`
**Type**: Create, Modify
**Depends**: T005
**Acceptance**:
- `list_material_variants(client, category, name)` runs UE Python through the Unreal MCP client and returns the design.md list, built from the metadata tags in the Desktop and Mobile folders (AC8).
- It returns `[]` when no tagged assets exist or the folders are missing (AC8).
- The finalize MCP tool `list_material_variants(category, collection)` and the CLI `material-variants --category --collection [--json]` share that implementation. An unreachable Unreal MCP returns the structured `mcp.unreal.unreachable` error. `gate-mcp-schema` passes.

### T007: Document material variants

**File(s)**: `docs/asset-contract.md`, `skills/finalize-asset/SKILL.md`, `docs/mcp/finalize.md`
**Type**: Modify
**Depends**: T001, T005, T006
**Acceptance**:
- `docs/asset-contract.md` §4 documents material variants: the declaration file name, location, and JSON format; `T_<Name>_<Part>_BC_<Variant>` and `MI_<Name>_<Part>_<Variant>` naming; every `material_variant.*` rule; the merged-material rule; the `Tint` parameter; and stale deletion (AC10).
- `skills/finalize-asset/SKILL.md` explains how to declare and pass material variants and how to list them (AC10).
- `docs/mcp/finalize.md` documents `list_material_variants` and the `material_variants_path` argument (AC10).
- The §6 budget table is unchanged.
- `plugin.validate` passes.

### T008: Blender regression tests for declaration, validation, and export

**File(s)**: `tests/blender/test_material_variants.py`, `tests/blender/contract_fixtures.py`
**Type**: Create, Modify
**Depends**: T001, T002
**Acceptance**:
- SCN001 (AC1): the compliant Crate with a declaration of `Red` (512 px PNG) and `Blue` (`Tint`) passes `validate_asset(..., authored=True, material_variants_path=...)`, and the report's `material_variants` lists both.
- SCN005 (AC5): one parametrized case per rule in the rule table yields a finding with that rule id, naming `Crate` and the variant. A malformed JSON file raises `material_variant.declaration_invalid`.
- SCN006 (AC6): an asset with more authored materials than the Mobile limit, declaring on one of them, fails with `material_variant.material_merged` naming `M_<Name>_Body`.
- SCN002/SCN003/SCN007 (AC2, AC3, AC7): finalize_core `_export` on the Crate writes `T_Crate_Body_BC_Red.png` in Desktop at 512 px and in Mobile at the Mobile `T_Crate_Body_BC` size, writes no `Blue` texture, and records `material_variants` in `nmg-variants.json`.
- SCN004 (AC4): without a declaration, the exported file list and `nmg-variants.json` match a run without the feature (no `material_variants` key).
- SCN009 (AC9): re-exporting without `Blue`'s texture entry removes that texture from both folders.
- All tests pass through `scripts/run-blender-tests.sh` (`gate-blender-headless`).

### T009: Host unit tests for request, caching, import, listing, and master material

**File(s)**: `tests/unit/test_material_variants_host.py`, `tests/unit/test_unreal_import.py`, `tests/unit/test_build_master_material.py`, `tests/unit/pipeline/test_steps.py`, `tests/unit/pipeline/test_engine.py`
**Type**: Create, Modify
**Depends**: T003, T004, T005, T006
**Acceptance**:
- SCN001 (AC1): `build_request` discovers the file beside `blend`, prefers an explicit path, and raises `finalize.material_variants_not_found` for a missing explicit path.
- FR9: changing the declaration or a referenced texture's bytes changes the `validate` and `export` settings hashes but not the `bake` or `variants` hashes.
- SCN002/SCN003 (AC2, AC3): `build_import_code` with material-variant entries emits params whose template creates `MI_<Name>_<Part>_<Variant>` with `BaseColor`, `Normal`, `ORM`, and `Tint`, and treats `_BC_<Variant>` as sRGB. `tests/unit/test_build_master_material.py` executes the builder's UE code against an in-memory fake `unreal` module. It asserts a `Tint` vector parameter with default (1, 1, 1, 1), a Multiply fed by `BaseColor` RGB and `Tint` whose output connects to Base Color, and unchanged Normal/ORM wiring. `MASTER_PARAMETERS` matches the parameters the fake recorded.
- SCN004 (AC4): with no material variants, `build_import_code` produces the same params as before plus an empty `material_variants` list, and the template never assigns a variant MI to a slot.
- SCN007 (AC7): `import_variant` with a fake client returns the `material_variants` and `removed` keys. `pipeline/test_engine.py` shows `_run_import` passing the sidecar's per-variant lists.
- SCN008 (AC8): `list_material_variants` with a fake client parses tagged results into the documented list and returns `[]` for an empty answer. The MCP tool and the CLI return the same list.
- SCN009 (AC9): the import template deletes only tagged `nmg.asset` matches that are no longer declared and lists them in `removed`.
- SCN010 (AC10): a unit test asserts that `docs/asset-contract.md` names `.material-variants.json`, `T_<Name>_<Part>_BC_<Variant>`, `MI_<Name>_<Part>_<Variant>`, and `material_variant.material_merged`, and that `docs/mcp/finalize.md` names `list_material_variants`.
- `uv run pytest tests/unit tests/bdd -q` (`repository.tests`), `repository.lint`, `repository.format`, and `repository.types` pass.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #148 | 2026-11-11 | Initial feature tasks |
