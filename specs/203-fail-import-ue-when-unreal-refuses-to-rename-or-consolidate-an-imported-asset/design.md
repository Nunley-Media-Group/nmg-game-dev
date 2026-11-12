# Root Cause Analysis: import_ue reports success when Unreal refuses to rename or consolidate an imported asset

**Issue**: #203
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/145-fix-import-ue-importing-static-meshes-at-1-100-scale-on-ue-5-8/

## Root Cause

`EditorAssetLibrary.rename_asset` and `EditorAssetLibrary.consolidate_assets` report failure by returning `False`, not by raising. The UE Python that `build_import_code` generates from `_IMPORT_TEMPLATE` calls both and drops the result:

- `_rename_to_parts(meshes)`: for each multi-part static mesh whose asset name differs from its part's export name, it consolidates an existing `target` into the new mesh, then renames `object_path` to `target`. Neither result is read. After a refused rename, `_resolve_expected(unreal.StaticMesh)` can still find a stale asset at `target` left by an earlier import. It records that asset's path in `RESULT["static_meshes"]`, and the pivot check and `_bind_materials` then run against it.
- `_ensure_rig_assets(mesh)`: when `create_physics_asset` places the asset outside `dest`, the code renames `created_path` to `SM_<Name>_PhysicsAsset` without reading the result. The next `does_asset_exist(physics)` check catches a refusal, but its message names only the expected path, not the created one.

Because no exception is raised, `_run()` sets `RESULT["ok"] = True`, and `import_variant` accepts the result.

## Affected Code

| File | Symbol / Area | Role |
|------|---------------|------|
| `src/nmg_game_dev/unreal/import_asset.py` | `_IMPORT_TEMPLATE` → `_rename_to_parts` | Discards the `consolidate_assets` and `rename_asset` results for static parts |
| `src/nmg_game_dev/unreal/import_asset.py` | `_IMPORT_TEMPLATE` → `_ensure_rig_assets` | Discards the physics-asset `rename_asset` result |
| `tests/unit/fake_unreal.py` | `FakeWorld`, `EditorAssetLibrary.rename_asset`, `EditorAssetLibrary.consolidate_assets` | Always succeed, so no test can reach the refused path |

## Fix Strategy

Check each result inline in the generated code. Keep the call text as it is, so the existing text assertions still match:

- In `_rename_to_parts`:
  - `if not unreal.EditorAssetLibrary.consolidate_assets(mesh, [_load(target)]):` raises `RuntimeError("consolidate_assets refused to merge " + target + " into " + object_path)`.
  - `if not unreal.EditorAssetLibrary.rename_asset(object_path, target):` raises `RuntimeError("rename_asset refused to rename " + object_path + " to " + target)`.
- In `_ensure_rig_assets`, `if not unreal.EditorAssetLibrary.rename_asset(created_path, physics):` raises `RuntimeError("rename_asset refused to rename " + created_path + " to " + physics)`. It runs before the existing `does_asset_exist(physics)` check, which stays.

The template's `try/except` already records `RESULT["error"] = "RuntimeError: …"` with `ok` false. `import_variant` already raises `PipelineError(code="import_ue.failed", message="UE import of <dest> failed: <error>")`. No change is needed outside the template.

Give the fake per-world failure injection:

- `FakeWorld.refused_renames: set[str]` holds source paths. `rename_asset(source, destination)` with `source` in this set returns `False` and changes nothing.
- `FakeWorld.refused_consolidations: set[str]` holds the paths of assets to be consolidated away. `consolidate_assets(to, [asset])` with `asset.path` in this set returns `False` and changes nothing: no deletion, no save change, no redirect.
- Both default to empty, so every existing test behaves as before. The module docstring lists the two knobs with the existing scenario knobs.

## Changes

| File | Change | Behavioral reason |
|------|--------|-------------------|
| `src/nmg_game_dev/unreal/import_asset.py` | Inline result checks with the exact messages above in `_rename_to_parts` and `_ensure_rig_assets` | AC1, AC2, AC3, FR1 |
| `tests/unit/fake_unreal.py` | `refused_renames` and `refused_consolidations` knobs on `FakeWorld`, honored by `EditorAssetLibrary.rename_asset` / `consolidate_assets` | FR2 |
| `tests/unit/test_unreal_import.py` | Tests for refused rename, refused consolidation, refused physics rename, and the successful paths | AC1–AC4, FR2 |
| `tests/bdd/features/import_ue_refused_rename.feature`, `tests/bdd/steps/test_import_ue_refused_rename.py` | Four scenarios bound with pytest-bdd against the fake | AC1–AC4 |

## Blast Radius

Only the generated import code changes. Callers of `import_variant` see a new `import_ue.failed` where they used to get a false success. The code, remediation, stage, and the `NMG_RESULT` schema are unchanged. On the success path every call still returns `True`, so the result, the saves, and the redirects are the same as before. Rigged Mobile imports never rename, so they are unaffected.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Inline `if not …: raise RuntimeError(…)` at each call | Selected | Keeps the call text the existing tests assert, and reuses the template's error path |
| A shared `_rename(source, target)` helper in the template | Rejected | Changes the asserted call text for no behavioral gain across three call sites |
| Verify with `does_asset_exist(target)` after each call | Rejected | A stale asset at `target` from an earlier import passes that check, which is the defect |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #203 | 2026-11-11 | Initial defect design |
