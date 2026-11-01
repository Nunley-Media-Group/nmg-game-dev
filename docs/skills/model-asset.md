# Model asset

`/model-asset` models an asset freeform in the open Blender session, through the Blender MCP, and
checks its own work before `/finalize-asset` bakes and imports it. The agent plans the asset in
metres, blocks it out, inspects it numerically and from rendered views, and fixes each blocking
finding with a small edit. It repeats until the inspection passes. Nothing waits for approval along
the way.

The skill is asset-type agnostic. It has no per-asset recipe, and the rules that apply to every asset
live in `docs/asset-contract.md`.

## The loop

1. Inspect the scene: `get_addon_status`, then `get_scene_info`.
2. Plan: real-world dimensions in metres, the collection `<Name>`, the `asset_class`, and the parts.
3. Write one generating script for the asset and change it with localized edits.
4. Block out the parts inside collection `<Name>`.
5. Inspect with `inspect_asset`, and render the review views with `render_review`. Read the renders
   with `look`.
6. Fix every blocking finding, then repeat step 5 until `passed` is true.
7. Add detail and materials, and re-run the inspection after each pass.
8. Present the final renders and the inspection summary, then run `/finalize-asset`.

Skill definition: `skills/model-asset/SKILL.md`. Blender API reference for the loop's calls:
`skills/model-asset/references/blender-api.md`.

## Entry points

All of them call one implementation, `inspect_core.inspect_asset`.

| Entry point | Use it when |
|-------------|-------------|
| `inspect_core.inspect_asset(...)` from `execute_blender_code` | The agent is authoring. This is what the skill's Flow uses. |
| Panel operator `nmggamedev.inspect_spatial` | You are working in the Blender UI and want a dialog. |

```python
from nmg_game_dev_blender_addon.inspect_core import inspect_asset

report = inspect_asset("<Name>", "standard_prop")
print(report["passed"], report["findings"])
```

## Inputs

| Input | Meaning |
|-------|---------|
| `collection` | The asset collection `<Name>`. Its mesh parts are inspected, including parts in nested collections. |
| `asset_class` | One of `small_prop`, `standard_prop`, `hero_prop`, `character`, `environment_piece`. Sets the Desktop triangle budget (contract section 6). |
| `budgets_path` | Optional `nmg-budgets.json`. A `desktop` object in a class's overrides changes the budget this inspection uses. |
| `gap_tolerance` | Metres within which two parts count as touching. Default `0.001` (1 mm). |

The operator takes the same inputs as `collection_name`, `asset_class`, `budgets_path`, and
`gap_tolerance`. It stores the report as JSON in `bpy.context.scene.nmg_game_dev.last_result`.

## Report fields

The report is plain JSON. `json.dumps(report)` always succeeds.

| Field | Meaning |
|-------|---------|
| `kind` | `"inspect"` |
| `asset` | The collection name |
| `class` | The `asset_class` used |
| `gap_tolerance` | The tolerance used, in metres |
| `passed` | `true` exactly when no finding has `"blocking": true` |
| `parts` | One entry per mesh part, sorted by name (see below) |
| `findings` | Every finding, sorted by rule and then by part names |
| `triangles` | `total` triangles across the parts, the Desktop `budget`, and `headroom` (`budget - total`, negative when over) |

Each entry in `parts` carries:

| Field | Meaning |
|-------|---------|
| `name` | The object name |
| `bounds` | `min` and `max` corners of the part's world-space bounds, in metres, rounded to 6 decimals |
| `tris` | Triangles in the evaluated mesh (modifiers applied) |
| `non_manifold_edges` | Edges that do not have exactly two faces, including boundary and wire edges |
| `geometry` | The contract geometry findings for the part (see below) |

Each entry in `findings` carries `rule`, `blocking`, `parts`, `message`, and `remediation`. Some
rules add fields:

- `floating` adds `gap`, the distance in metres to the main body. It is `null` when the part has no
  surface to measure from.
- `non_manifold` adds `edges`, the count of offending edges.
- `over_budget` adds `triangles` and `budget`. Its `parts` list is empty, because the budget is for
  the whole asset.
- `interpenetration` names the two parts in `parts`.

The per-part `geometry` entries are the contract checks: `geometry.loose` (loose vertices),
`geometry.zero_area` (zero-area faces), `geometry.duplicates` (duplicate vertices), and
`geometry.normals` (faces whose normals are inconsistent or inward). They are reported for reference
and never block here. `docs/asset-contract.md` and `/finalize-asset` own them.

## Blocking rules

| Rule | Blocking | Triggers when | Fix |
|------|----------|---------------|-----|
| `floating` | Yes | A part's surface is farther than `gap_tolerance` from every part of the main body | Move or extend the part until it touches the body, or join it to its neighbour |
| `non_manifold` | Yes | A part has edges that do not have exactly two faces | Close the open edges |
| `over_budget` | Yes | The total triangles exceed the Desktop `tris` for the `asset_class` | Remove triangles, or raise the class's Desktop `tris` in `nmg-budgets.json` |
| `interpenetration` | No | Two parts' surfaces cross, or a vertex of one part lies deeper than `gap_tolerance` inside the other | Separate the parts so they only touch, unless the overlap is intentional |

The main body is the connected group of parts with the largest summed bounds volume. Ties go to the
group with more parts, then to the group whose first part name sorts first. Every part outside that
group is floating.

## How the measurements work

- The inspection reads evaluated meshes, so a part that reaches the body only through an Array or a
  Mirror modifier is connected through its evaluated geometry.
- Two parts are connected when their surfaces are within `gap_tolerance` of each other, or when they
  interpenetrate.
- A gap is the smallest distance from a vertex of one part to the surface of the other, in either
  direction. Where the closest points lie in the middle of two edges, the gap can be slightly larger
  than the true minimum.
- Interpenetration counts only when a triangle of one part crosses a triangle of the other. Faces
  that only touch, such as a cap resting flush on the body, are not interpenetration. Coplanar faces
  that overlap on the same plane are not reported.
- Mesh objects with no vertices are skipped. Non-mesh objects, such as empties, lights, and cameras,
  are not parts.
- The inspection is read-only. Each evaluated copy is removed before the call returns, so objects,
  transforms, and datablocks do not change.

## Failure codes

Each failure raises `ContractError` with a `code`, a `message`, and a `remediation`. The operator
reports it as an ERROR, so under `bpy.ops` it raises `RuntimeError` with the code at the start of the
message.

| Code | Meaning | Remediation |
|------|---------|-------------|
| `inspect.collection_missing` | The open file has no collection with the given name | Pass the exact name of `<Name>`, or create the collection |
| `inspect.unknown_asset_class` | The `asset_class` is not in the contract budgets | Use one of the five classes listed above |
| `variants.budget_override_invalid` | `nmg-budgets.json` is unreadable or has an invalid value | Fix the file named in the message, or pass no budget path |

## Related

- `docs/asset-contract.md`: what "done" means for a generated asset, including the budgets in
  section 6.
- `docs/skills/bake-materials.md`: the bake step that `/finalize-asset` runs after the authoring loop.
