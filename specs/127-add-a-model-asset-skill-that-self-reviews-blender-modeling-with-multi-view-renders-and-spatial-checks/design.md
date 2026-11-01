# Design: Add a /model-asset skill that self-reviews Blender modeling with multi-view renders and spatial checks

**Issue**: #127
**Date**: 2026-11-01
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/69-reshape-the-pipeline-to-finalize-an-authored-asset-instead-of-generating-from-a-prompt/

## Overview

Three pieces ship together: an add-on inspection core (`inspect_core/`) beside `contract_core/` that reports part relationships, manifoldness, and triangle budget for one collection; an operator `nmggamedev.inspect_spatial` over it; and the `/model-asset` skill (SKILL.md plus a Blender API reference) whose Flow drives the agent through plan → blockout → inspect + render → fix → detail → present, with no approval waits. The skill calls the inspection and `contract_core.render_review` through `execute_blender_code`, following the `from nmg_game_dev_blender_addon.<core> import ...` pattern already documented in `docs/skills/bake-materials.md` and `docs/rigging-and-animation.md`.

## Architecture

```
skills/model-asset/SKILL.md ──execute_blender_code──▶ nmg_game_dev_blender_addon.inspect_core.inspect_asset
                            ──execute_blender_code──▶ nmg_game_dev_blender_addon.contract_core.render_review
                            ──look────────────────▶ the review PNGs
operators/inspect_spatial.py ─────────────────────▶ inspect_core.inspect_asset → scene.nmg_game_dev.last_result
inspect_core/spatial.py reuses:
  contract_core.geometry.geometry_findings
  contract_core.validate.triangle_count
  contract_core.report.ContractError
  utils.budgets.CONTRACT_BUDGETS / resolve_budget(asset_class, budgets_path, variant="desktop")
```

New files:

- `plugins/nmg-game-dev-blender-addon/inspect_core/__init__.py` — exports `inspect_asset`, `INSPECT_RULES`, `DEFAULT_GAP_TOLERANCE`.
- `plugins/nmg-game-dev-blender-addon/inspect_core/spatial.py` — the implementation.
- `plugins/nmg-game-dev-blender-addon/operators/inspect_spatial.py` — `NMGGAMEDEV_OT_inspect_spatial`, added to `operators/__init__.py`, `REGISTER_CLASSES` in the add-on `__init__.py`, and `panels/main_panel.py` beside `render_review`.
- `skills/model-asset/SKILL.md`, `skills/model-asset/references/blender-api.md`, `docs/skills/model-asset.md`.

## API / Interface Changes

| Interface | Input | Output / Error | Behavior |
|-----------|-------|----------------|----------|
| `inspect_core.inspect_asset(collection, asset_class, budgets_path=None, *, gap_tolerance=0.001)` | collection name; one of `utils.budgets.ASSET_CLASSES`; optional `nmg-budgets.json` path; gap tolerance in metres | report dict (below) | Read-only inspection of the mesh objects in `collection.all_objects` |
| same | collection not in `bpy.data.collections` | raises `ContractError("inspect.collection_missing", message, remediation)` | Raised before any evaluated copy is made |
| same | `asset_class` not in `CONTRACT_BUDGETS` | raises `ContractError("inspect.unknown_asset_class", message naming the class, remediation listing `ASSET_CLASSES`)` | Checked before `resolve_budget`; an invalid overrides file still raises `variants.budget_override_invalid` as `ContractError` |
| `bpy.ops.nmggamedev.inspect_spatial(collection_name, asset_class, budgets_path, gap_tolerance)` | `StringProperty`, `EnumProperty(items=ASSET_CLASS_ITEMS)` default `standard_prop`, `StringProperty(subtype="FILE_PATH")`, `FloatProperty` default 0.001 min 0 | `{"FINISHED"}` and `scene.nmg_game_dev.last_result` = the report as JSON via `store_last_result`; `{"CANCELLED"}` with an ERROR report on `ContractError` | Same pattern as `operators/render_review.py`; `bl_options = {"REGISTER"}` (no UNDO — nothing changes); logs through `log_operator_result` |

Report shape (plain JSON types only):

```json
{
  "kind": "inspect",
  "asset": "<Name>",
  "class": "<asset_class>",
  "gap_tolerance": 0.001,
  "passed": true,
  "parts": [
    {"name": "...", "bounds": {"min": [x, y, z], "max": [x, y, z]}, "tris": 12,
     "non_manifold_edges": 0, "geometry": [<geometry_findings dicts>]}
  ],
  "findings": [
    {"rule": "floating", "blocking": true, "parts": ["P"], "gap": 0.05, "message": "...", "remediation": "..."},
    {"rule": "interpenetration", "blocking": false, "parts": ["A", "B"], "message": "...", "remediation": "..."},
    {"rule": "non_manifold", "blocking": true, "parts": ["P"], "edges": 4, "message": "...", "remediation": "..."},
    {"rule": "over_budget", "blocking": true, "parts": [], "triangles": 2400, "budget": 2000, "message": "...", "remediation": "..."}
  ],
  "triangles": {"total": 2400, "budget": 2000, "headroom": -400}
}
```

- `passed` is true exactly when no finding has `blocking: true`. Per-part `geometry` entries are reported but are not blocking (the contract validate step owns them).
- Bounds and gaps are rounded to 6 decimals; parts are sorted by name; findings are sorted by rule then parts.
- `headroom` = `budget - total` (negative when over budget). `budget` is the Desktop `tris` from `resolve_budget(asset_class, budgets_path, variant="desktop")`.
- `INSPECT_RULES` maps each rule to its remediation text (e.g. floating → "Move or extend the part until it touches the body, or join it to its neighbour").

## Algorithm

1. Validate `asset_class`, then the collection (errors above). Call `bpy.context.view_layer.update()`.
2. For each `MESH` object in `collection.all_objects`: make an evaluated copy with `bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph), depsgraph=depsgraph)` (modifiers evaluated), and inside `try/finally` (always `bpy.data.meshes.remove(copy)`): record `triangle_count(copy)`, `geometry_findings(obj.name, copy)`, world-space vertex coordinates (`obj.matrix_world @ v.co`) and polygon index lists, and the non-manifold edge count from a bmesh of the copy (`sum(1 for e in bm.edges if not e.is_manifold)`, which counts boundary and wire edges).
3. Build a `mathutils.bvhtree.BVHTree.FromPolygons(world_verts, polygons)` per part (pure math, not a datablock).
4. For each pair (A, B): `interpenetrating` when `bvh_a.overlap(bvh_b)` is non-empty, or when A lies inside B (or B inside A): the nearest point on B to A's first vertex has a face normal pointing away from that vertex (`(nearest - v).dot(normal) > 0`). Otherwise the gap is the minimum of `bvh_b.find_nearest(v)` distances over A's vertices and of `bvh_a.find_nearest(v)` over B's vertices. A pair is connected when interpenetrating or gap ≤ `gap_tolerance`.
5. Connected components over that graph. The main component is the one with the largest summed world-bounds volume (ties: more parts, then first part name). Every part outside the main component gets one `floating` finding whose `gap` is its minimum gap to any main-component part. A collection with one part has no floating findings.
6. One `interpenetration` finding per interpenetrating pair; one `non_manifold` finding per part with a non-zero count; one `over_budget` finding when the total exceeds the budget.
7. Nothing in `bpy.data` is created that survives the call; no object, collection, transform, or selection changes.

## SKILL.md content

Frontmatter: `name: model-asset`; `description: Model an asset freeform in Blender through the Blender MCP with a plan, blockout, spatial inspection, multi-view review, and fix loop` (one line); `required_mcp: [blender]`; `required_env: []`; `unattended_safe: true`.

Flow (numbered, in this order, with no approval wait; the skill states the agent never stops to ask before continuing):
1. Inspect the scene: `get_addon_status`, `get_scene_info`.
2. Plan: write the real-world dimensions in metres, the target collection `<Name>`, the `asset_class`, and the parts.
3. Keep one generating script per asset; change it with localized edits, never regenerate it.
4. Block out the parts at planned dimensions inside collection `<Name>`.
5. Inspect: run `inspect_asset` through `execute_blender_code` (snippet printing `json.dumps(report)`), and `render_review("<Name>", out_dir, 512)`; read each PNG with `look`.
6. Fix every blocking finding (`floating`, `non_manifold`, `over_budget`) with localized edits; repeat step 5 until `passed` is true.
7. Detail and add materials (shader nodes looked up by type); re-run the inspection after each pass.
8. Finish by presenting the final multi-view renders and the inspection summary, and point to `/finalize-asset`.

Also: the operator alternative (`bpy.ops.nmggamedev.inspect_spatial(...)` then `scene.nmg_game_dev.last_result`), a pointer to `references/blender-api.md`, and Failure modes and remediation for `inspect.collection_missing`, `inspect.unknown_asset_class`, `variants.budget_override_invalid`, `render.asset_missing`, and `mcp.blender.unreachable` (run `scripts/start-blender-mcp.sh`). No asset-type examples; placeholders are `<Name>` and `<Part>`.

## Blender API reference content

`skills/model-asset/references/blender-api.md` has one heading per topic, each with at least one self-contained fenced `python` block (imports its own modules, builds what it needs, no add-on dependency): bmesh construction (`bmesh.new`, `bmesh.ops.create_cube`, `bm.to_mesh`); modifier stacks (`obj.modifiers.new`, ordering, applying via `bpy.ops.object.modifier_apply` under `bpy.context.temp_override(object=obj, active_object=obj)` and the ops-free `new_from_object` route); Geometry Nodes (`bpy.data.node_groups.new(type="GeometryNodeTree")`, `tree.interface.new_socket`, a `NODES` modifier using the group); shader nodes by type (`next(n for n in tree.nodes if n.type == "BSDF_PRINCIPLED")`, inputs by identifier); and a "Changes since Blender 4.x" section (node-group `interface` sockets, auto-smooth replaced by Smooth by Angle / `set_sharp_from_angle`, Principled BSDF input renames, render engine enum read at runtime, `temp_override` replacing context dicts). Snippets must pass on the Blender 5.2 that `gate-blender-headless` runs.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Extend `validate_asset` with the spatial rules | Rejected | The contract validate report feeds the finalize gate; authoring-time rules (interpenetration, headroom) would change gate behavior, which is out of scope |
| Bounding-box distances between parts | Rejected | Boxes overlap for parts that do not touch (an L-shaped part), so a floating handle can pass |
| BVH surface distance and overlap per pair | Selected | `mathutils.bvhtree` ships with Blender, needs no datablocks, and measures surface-to-surface gaps |
| New `InspectError` class | Rejected | `ContractError` already carries `code`, `message`, `remediation` and is what operators catch |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #127 | 2026-11-01 | Initial feature design |
