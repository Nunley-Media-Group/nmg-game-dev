# Root Cause Analysis: A millimetre-scale pivot offset on a rigged mesh blocks finalize

**Issue**: #244
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/140-fix-finalize-export-failing-the-contract-on-mobile-lods-the-variants-step-decimated/

## Root Cause

`contract_core/validate.py` `_pivot_findings()` holds the root origin and the world bounding-box bottom center to `PIVOT_TOLERANCE = 1e-3` for every asset. It builds the box from `obj.bound_box` and `matrix_world` over the root and its non-LOD parts. A skinned character's box comes from soft extremities, so it easily lands just over 1 mm off. The only code that moves mesh data onto the origin is `variants_core/mobile.py` `_reseat()`, which runs for Mobile only. The Desktop mesh is never re-seated, and `finalize_core/steps.py` has no step that could do it before validate. A validate-time fix would also be lost, because validate saves no .blend and later steps start from the checkpoint or the previous step's .blend.

## Affected Code

| File | Symbol / Area | Role |
|------|---------------|------|
| `plugins/nmg-game-dev-blender-addon/contract_core/validate.py` | `_pivot_findings`, `PIVOT_TOLERANCE`, `validate_asset` | One tolerance for every asset |
| `plugins/nmg-game-dev-blender-addon/contract_core/report.py` | `RULES["pivot.bottom_center"]` | Remediation text |
| `plugins/nmg-game-dev-blender-addon/variants_core/cleanup.py` | `cleanup_desktop` | Desktop step that never re-seats |
| `plugins/nmg-game-dev-blender-addon/finalize_core/steps.py` | `_variants` | Variants step outputs |
| `plugins/nmg-game-dev-blender-addon/variants_core/mobile.py` | `_reseat` | Prior art for Mobile |

## Fix Strategy

1. **Shared measure.** In `contract_core/validate.py`, pull the box arithmetic out of `_pivot_findings` into the public `bottom_center(meshes) -> Vector`. It returns the x and y centers and the minimum z of the world corners of each mesh's `bound_box`. `_pivot_findings` calls it. The re-seat calls it too, so both measure the same box, and #236's rest-pose change applies to both.
2. **Rigged allowance.**
   - Add `RIGGED_PIVOT_TOLERANCE = 5e-3`.
   - `validate_asset` passes `rigged_authored=True` to `_pivot_findings` for the desktop variant when `authored` is true and the collection holds an ARMATURE named `SK_<Name>`, the same test `variants_core.assets.asset_armature` uses.
   - With `rigged_authored`, the three bottom-center values are held to `RIGGED_PIVOT_TOLERANCE`. The three origin values stay at `PIVOT_TOLERANCE`.
   - Export-time validation (`authored=False`), the Mobile variant, and static assets keep `PIVOT_TOLERANCE` everywhere.
   - When the rigged allowance is in force and the check fails, the message ends with "finalize re-seats a rigged mesh only within 5 mm of the origin; move the mesh data closer."
3. **Desktop re-seat.** Add `reseat_desktop(collection_name) -> dict` to `variants_core/cleanup.py`:
   - Return `{"reseated": False, "offset": [0.0, 0.0, 0.0]}` when `asset_armature(collection_name)` is None.
   - Otherwise call `bpy.context.view_layer.update()` and measure `bottom_center` over the Desktop root and its non-LOD mesh parts.
   - If the offset is exactly zero, return `reseated: False` with that offset.
   - Otherwise, for each of those meshes, transform its data by `Matrix.Translation(obj.matrix_world.inverted().to_3x3() @ -offset)` and call `data.update()`, then `view_layer.update()`.
   - Return `{"reseated": True, "offset": [round(c, 6) for c in offset]}`.

   `cleanup_desktop` calls it after cleaning and adds the result to its report as `pivot`. Origins, transforms, modifiers, vertex groups, and bones are untouched.
4. **Report.** `finalize_core/steps.py` `_variants` adds `"pivot": cleanup["pivot"]` to its outputs.
5. **Remediation and docs.** Extend `RULES["pivot.bottom_center"]` with: "A rigged asset may sit up to 5 mm off at authoring time; finalize's variants step moves its mesh data onto the origin. Larger offsets: move the mesh data." Add the same rule to `docs/asset-contract.md` section 2, after the root-origin bullet.

## Changes

| File | Change | Behavioral reason |
|------|--------|-------------------|
| `plugins/nmg-game-dev-blender-addon/contract_core/validate.py` | `bottom_center`, `RIGGED_PIVOT_TOLERANCE`, rigged authored allowance, message suffix | AC1, AC4, AC5, FR1 |
| `plugins/nmg-game-dev-blender-addon/contract_core/report.py` | Remediation text | AC4, FR4 |
| `plugins/nmg-game-dev-blender-addon/variants_core/cleanup.py` | `reseat_desktop`, `pivot` in the report | AC1–AC3, AC6, FR2, FR3 |
| `plugins/nmg-game-dev-blender-addon/finalize_core/steps.py` | `pivot` in the variants outputs | FR3 |
| `docs/asset-contract.md` | Rigged allowance and re-seat | FR4 |
| `tests/blender/test_pivot_reseat.py` | SCN001–SCN006 | FR5 |

## Blast Radius

- Only rigged assets change. Authored validate accepts bottom-center offsets of 1–5 mm on them, and their Desktop mesh data moves by that offset in the variants step.
- Mobile is built from the cleaned Desktop and still runs its own `_reseat`.
- Static assets, export-time validation, and the origin check keep the 1 mm tolerance.
- The skin binding shifts by the same sub-5 mm offset relative to the bones, which is what moving the mesh data by hand does today.
- Callers of `cleanup_desktop` gain a `pivot` key and lose nothing.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Raise the rigged tolerance only | Rejected | Interview: exported variants should sit on the origin |
| Add a `fix_pivot` finalize step | Rejected | Interview: needs a new pipeline step, MCP schema entries, and caching for the same outcome |
| Allow 5 mm in authored validate, then re-seat in the variants step | Selected | Interview choice; reuses the Mobile re-seat approach |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #244 | 2026-11-18 | Initial defect design |
