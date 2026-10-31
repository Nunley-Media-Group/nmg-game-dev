# Design: Normalize Meshy GLB imports to a welded mesh with the origin at the bottom center

**Issue**: #105
**Date**: 2026-10-31
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/98-add-optional-meshy-model-generation-and-retexturing-through-the-meshy-api/

## Overview

`_import_glb` in `scripts/blender/meshy_session.py` gains a `_normalize(obj)` step after the existing join, rename, and material handling. `_normalize` welds, recenters, and fixes normals on `SM_<Name>`, and returns the numbers the result reports. The Meshy job copies those numbers into its result. No other op changes.

## Architecture

`_normalize(obj) -> dict` runs in object mode on the joined `SM_<Name>`:

1. **Bake transforms.** `mesh.transform(obj.matrix_world)`, then `obj.matrix_world = Matrix.Identity(4)`. `mathutils` is imported at the top of the script.
2. **Weld.** In a `bmesh` from the mesh, record the vertex count, run `bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=WELD_DISTANCE)` with `WELD_DISTANCE = 1e-5`, then `bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])`, write back, and free. `merged_vertices` is the count before minus the count after. UV and material indices live on face corners and faces, so the merge keeps them.
3. **Recenter.** From the mesh vertices, compute `min_x/max_x/min_y/max_y/min_z`. `offset = (-(min_x+max_x)/2, -(min_y+max_y)/2, -min_z)`. Apply `mesh.transform(Matrix.Translation(offset))`. An empty mesh is already rejected before this step.
4. **Normals.** Clear custom split normals: when `mesh.has_custom_normals`, run `bpy.ops.mesh.customdata_custom_splitnormals_clear()` under `bpy.context.temp_override(object=obj, active_object=obj)`. Then run `bpy.ops.object.shade_smooth_by_angle(angle=math.radians(SMOOTH_ANGLE_DEG), keep_sharp_edges=True)` under `temp_override(selected_editable_objects=[obj], active_object=obj, object=obj)`, with `SMOOTH_ANGLE_DEG = 30`.
5. Return `{"merged_vertices": int, "origin_offset": [round(v, 6) for v in offset]}`.

If an operator in step 4 raises, `_import_glb` returns `_fail(SESSION_FAILED, …)` naming the step. It does not leave a half-normalized mesh in place silently. The collection stays, so the user can retry after deleting it, as with today's import failures.

`_import_glb` merges the `_normalize` dict into its success result. `src/nmg_game_dev/meshy/jobs.py` copies `merged_vertices` and `origin_offset` from `imported` into the job `result` when `loaded_into_session` is true. The module docstring's `import_glb` line lists the two new keys.

## API / Interface Changes

| Interface | Input | Output / Error | Behavior |
|-----------|-------|----------------|----------|
| `meshy_session.py` op `import_glb` | `{"name", "path"}` | `{"ok", "collection", "mesh", "material", "merged_vertices", "origin_offset"}` or the existing error shape | Welds, recenters, and fixes normals before returning |
| Meshy generate job `result` | — | adds `merged_vertices`, `origin_offset` when loaded into the session | Surfaces the normalization to the agent |

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| `bmesh` weld + mesh-level translate | Selected | Deterministic, headless-safe, same approach as `variants_core/cleanup.py` |
| `bpy.ops.mesh.remove_doubles` in edit mode | Rejected | Needs mode switching and context; bmesh is simpler and testable |
| Set origin with `origin_set` + move object | Rejected | Leaves a non-identity location; the contract wants geometry moved and transforms at identity |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #105 | 2026-10-31 | Initial feature design |
