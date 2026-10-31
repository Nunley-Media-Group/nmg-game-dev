# Root Cause Analysis: M_NmgORM sampler defaults and skeletal-mesh usage

**Issue**: #101
**Date**: 2026-10-31
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/69-reshape-the-pipeline-to-finalize-an-authored-asset-instead-of-generating-from-a-prompt/

## Root Cause

`_sampler()` in the `_MATERIAL_CODE` that `scripts/unreal/build_master_material.py` sends through `UnrealMcpClient.execute_python_code` sets `parameter_name` and `sampler_type` on each `MaterialExpressionTextureSampleParameter2D` but never sets `texture`. Every parameter keeps the expression default `/Engine/EngineResources/DefaultTexture`, a Color texture. UE validates the sampler type against the default texture's compression, so the `Normal` (SAMPLERTYPE_NORMAL) and `ORM` (SAMPLERTYPE_MASKS) expressions fail. The base material fails to compile, and every instance falls back to the Default Material, even when it overrides the parameters with correctly typed textures. `_build()` also never sets `used_with_skeletal_mesh`, so instances on skeletal meshes have no compiled shader permutation.

## Affected Code

| File | Symbol / Area | Role |
|------|---------------|------|
| `scripts/unreal/build_master_material.py` | `_MATERIAL_CODE` `_sampler()` | Leaves the default texture unset |
| `scripts/unreal/build_master_material.py` | `_MATERIAL_CODE` `_build()` | Never enables skeletal-mesh usage |
| `plugins/nmg-game-dev-ue-plugin/Content/Materials/M_NmgORM.uasset` | Committed asset | Built with the defect |

## Fix Strategy

Give `_sampler()` a `default_texture` path argument. It loads the texture with `unreal.EditorAssetLibrary.load_asset`, raises `RuntimeError("could not load default texture " + path)` when the result is not an `unreal.Texture`, and sets `node.set_editor_property("texture", texture)` after setting `sampler_type`. `_build()` passes `/Engine/EngineResources/DefaultTexture` for `BaseColor`, `/Engine/EngineMaterials/DefaultNormal` for `Normal`, and `/Engine/EngineMaterials/DefaultDiffuse_TC_Masks` for `ORM`. Before `recompile_material`, `_build()` calls `material.set_editor_property("used_with_skeletal_mesh", True)`. Parameter names, node positions, connections, the `_clear()` in-place rebuild path, the `NMG_RESULT` line, and exit codes stay as they are. Then rebuild and commit the `.uasset` by running the script against a UE 5.8 editor launched with `scripts/start-unreal-mcp.sh` on `fixtures/dogfood.uproject`. The dogfood project mounts the plugin at `/nmg-game-dev/`.

## Changes

| File | Change | Behavioral reason |
|------|--------|-------------------|
| `scripts/unreal/build_master_material.py` | Typed default textures on all three samplers; `used_with_skeletal_mesh = True`; docstring names the defaults | AC1, AC2, FR1, FR2 |
| `plugins/nmg-game-dev-ue-plugin/Content/Materials/M_NmgORM.uasset` | Rebuilt by the fixed script | AC1, AC2, FR3 |
| `tests/unit/test_build_master_material.py` | New unit tests over `_MATERIAL_CODE` and the committed asset | AC1–AC3 |
| `tests/bdd/features/master_material.feature`, `tests/bdd/test_master_material_bdd.py` | BDD scenarios SCN001–SCN003 | AC1–AC3 |
| `CHANGELOG.md` | `[Unreleased]` Fixed entry ending `(#101)` | FR3 |

## Blast Radius

Only the plugin-owned master material changes. `import_asset.py` keeps parenting `MI_<Name>_<Part>` to the same path and setting the same parameter names, so existing instances keep their parent and their overrides. The added skeletal-mesh usage adds one shader permutation at cook.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Engine `DefaultNormal` and `DefaultDiffuse_TC_Masks` as defaults | Selected | Both ship with UE 5.8 and already have Normal and Masks compression; no new plugin content |
| Plugin-owned `T_NmgDefault_N` / `T_NmgDefault_ORM` textures created by the builder | Rejected | Adds assets and import code for the same result |
| Set the sampler type to `SAMPLERTYPE_COLOR` everywhere | Rejected | Breaks normal unpacking and linear sampling of ORM |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #101 | 2026-10-31 | Initial defect report |
