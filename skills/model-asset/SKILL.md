---
name: model-asset
description: Model an asset freeform in Blender through the Blender MCP with a plan, blockout, spatial inspection, multi-view review, and fix loop
required_mcp: [blender]
required_env: []
unattended_safe: true
---

# Model Asset

Models one asset freeform in the open Blender session, through `execute_blender_code` and `look`.
It runs an autonomous loop: plan, block out, inspect the geometry numerically and from rendered
views, fix each blocking finding with a small edit, and repeat until the checks pass. Use it when a
developer asks Claude to model an asset in Blender, before `/finalize-asset` bakes and imports it.

This skill is asset-type agnostic. The plan comes from the developer's description and the asset's
real-world size; no per-asset recipe applies. Rules that hold for every asset live in
`docs/asset-contract.md`.

## Flow

Run these steps in order. No step waits for approval: when a check fails, fix it and continue on
your own judgment. Stop only when the final presentation is written.

1. Inspect the scene. Call `get_addon_status` for the Blender version and the loaded add-ons, then
   `get_scene_info` for the existing objects and collections. Note any collection that already uses
   the name you plan to use.
2. Plan the asset. Write the real-world dimensions of every part in metres, the target collection
   `<Name>`, the `asset_class` (`small_prop`, `standard_prop`, `hero_prop`, `character`, or
   `environment_piece`), and the list of parts with their placement.
3. Write one generating script for the asset with `execute_blender_code`. Keep that one script for
   the whole session. Change it with localized edits to a single part or value; never regenerate the
   whole script from the start.
4. Block out. Build every part at its planned dimensions as a mesh object inside collection `<Name>`,
   using the plan's metres as the scale.
5. Inspect and review. Run `inspect_asset` through `execute_blender_code` with the snippet below, and
   then run `render_review("<Name>", "<out_dir>", 512)` through `execute_blender_code`. It writes the front,
   back, side, and three-quarter renders. Read each PNG it returns with `look`, and read the report's
   `findings` and `triangles` fields.
6. Fix the blocking findings. Every finding with `"blocking": true` (`floating`, `non_manifold`, and
   `over_budget`) must be fixed with localized edits to the generating script. Look at the renders for
   each `interpenetration` finding and separate the parts when the overlap is not intended. Repeat
   step 5 until `passed` is true.
7. Add detail and materials. Look up shader nodes by type, never by name:
   `next(n for n in material.node_tree.nodes if n.type == "BSDF_PRINCIPLED")`. Set Principled inputs by their
   current names, and read enum identifiers at runtime rather than hardcoding them. After each detail
   or material pass, run the inspection again and fix any new blocking finding.
8. Present the result. Show the final multi-view renders with `look`, and summarize the inspection:
   `passed`, the count of blocking and non-blocking findings, `triangles.total` against
   `triangles.budget`, and the `headroom`. Then point the developer to `/finalize-asset` to bake and
   import the asset.

The inspection snippet for step 5 runs in the live session. Replace `<Name>` and `<asset_class>`
before running it:

```python
import json
from nmg_game_dev_blender_addon.inspect_core import inspect_asset

report = inspect_asset("<Name>", "<asset_class>")
print(json.dumps(report, indent=2))
```

Its report has `kind`, `asset`, `class`, `gap_tolerance`, `passed`, `parts` (each with `name`,
`bounds`, `tris`, `non_manifold_edges`, and `geometry`), `findings`, and `triangles`
(`total`, `budget`, `headroom`). `docs/skills/model-asset.md` describes every field and blocking rule.

### Operator alternative

When the add-on's panel is the only path available, run the same inspection from the operator:
`bpy.ops.nmggamedev.inspect_spatial(collection_name="<Name>", asset_class="<asset_class>")`. It stores
the report in `bpy.context.scene.nmg_game_dev.last_result` as JSON. A failure raises `RuntimeError`
that starts with the `inspect.*` code.

### Blender API reference

For the bmesh, modifier, Geometry Nodes, and shader-node calls the loop needs, and for the changes
since Blender 4.x that affect them, read `references/blender-api.md`. Each snippet there runs as
written in headless Blender.

## Failure modes and remediation

- `inspect.collection_missing` → No collection `<Name>` exists in the open file. Create it, or fix the
  name in the inspection call, then rerun step 5.
- `inspect.unknown_asset_class` → The `asset_class` is not one of `small_prop`, `standard_prop`,
  `hero_prop`, `character`, or `environment_piece`. Use one of them, then rerun step 5.
- `variants.budget_override_invalid` → `nmg-budgets.json` cannot be read or has an invalid value. Fix
  the file named in the message, or pass no budget path to use the contract defaults.
- `render.asset_missing` → The collection `<Name>` is not in the open file. Create it, then rerun
  `render_review`.
- `render.empty_asset` → Collection `<Name>` has no geometry to render. Block out the parts, then rerun
  `render_review`.
- `mcp.blender.unreachable` → The Blender MCP cannot be reached. Run `scripts/start-blender-mcp.sh`,
  then rerun the step that failed.
