---
name: finalize-asset
description: Finalize a collection you authored in Blender into Desktop and Mobile variants imported into Godot
required_mcp: [blender, finalize]
required_env: [BLENDER_BIN?, BLENDER_APP?, GODOT_BIN?, NMG_GAME_DEV_CACHE_DIR?]
unattended_safe: true
---

# Finalize Asset

Makes an asset the agent authored in the open Blender session shippable. It validates the collection
against `docs/asset-contract.md`, bakes its materials to contract texture sets, builds Desktop and
Mobile variants, exports them, re-verifies each export with a headless re-import, loads the baked
result back into the session, and imports both variants into the project's Godot project
(`game/project.godot`) with `godot --headless`. For a rigged character it also exports every animation
clip on `SK_<Name>` and imports each clip into Godot as an animation library. Use it when the developer
says an asset is done and wants it in the game. The Blender steps run in background Blender, so this
skill never sends a bake, variant, or export through a Blender MCP call. Godot runs headless only:
there is no editor to open and no live-editor bridge.

## Flow

1. Confirm that the collection `<Name>` exists in the open Blender session, or that a saved `.blend`
   is available. Confirm `category` (PascalCase) and `asset_class` (`small_prop`, `standard_prop`,
   `hero_prop`, `character`, `environment_piece`, or `terrain`). When either is omitted, both come from the design
   backlog (`docs/design/backlog.json`): the asset entry whose `asset_name` is `<Name>` supplies them
   (for each collection in a batch), and explicit values win. A successful `finalize_asset` marks that
   entry `finalized`. If one is missing and no backlog entry supplies it, stop with an error that names
   it. Do not guess a category or class.
2. Call `finalize_asset` with `collection`, `category`, `asset_class`, and `export_root`. In a
   consumer project `export_root` is `game/assets`, inside the Godot project. Add `blend`,
   `budgets_path`, or `material_variants_path` when they apply. Pass `force: true` only when the
   developer asks to rerun every step. Pass `wait_seconds: 150` so a small asset returns its result in
   the same call.
   To finalize several collections, call `finalize_asset` once with `requests`: a list with one object
   per collection, each taking the same keys (an entry sets its own `material_variants_path` and `compatible_with`).
   Top-level `category`, `asset_class`, and `export_root` fill in any key an entry leaves out. The collections run one at a time, in the order
   given, under one job lock, so a batch never interleaves with another finalize job. Pass
   `fail_fast: true` only when one failure should skip the rest. By default the other collections still
   run, because one asset's bake failure should not hold up unrelated assets.
   When another finalize job may be running, pass `wait_for_lock: true`. Without it, the call fails at
   once with `finalize.job_running`. Add `lock_wait_seconds` to cap how long the job waits.
3. If the reply has no `result`, poll `get_finalize_job` with the returned `job_id` until `state` is
   `succeeded` or `failed`. Report `step` and `progress` as they change. A job that is waiting for the
   lock reports `state: waiting`. For a batch, `batch` names the collection that is running, and
   `batch.completed` out of `batch.total`, so say which collection is in progress.
4. On `succeeded`, report each step's `cache_hit`, the Godot resource paths `desktop_resource_path`
   and `mobile_resource_path` (`res://assets/<Category>/<Name>/<Variant>/<Name>.glb`), and
   `loaded_back`. For `terrain`, each variant folder holds the scene `<Name>.tscn` with its chunks and
   heightmap collision. If `loaded_back` is false, say that the session was not updated and name the
   result `.blend` path. Game code loads an asset through `NmgAssets.resolve_variant_path`, which picks
   the variant for the running platform (`docs/asset-contract.md` section 7).
   For a batch, `result.batch` gives each collection's `state` and the `succeeded`, `failed`, and
   `skipped` counts. Each collection's step detail stays in its job directory under
   `items/<index>-<collection>/`, so point the developer there if they need it.
   When the result has an `animations` entry, also report how many clips were served from cache for
   export and for import, and every character under `compatible`.
5. On `failed`, report `error.code`, `error.message`, `error.stage`, and `error.remediation`, then stop.
   A failed step stops the run before the Godot import. The one exception is
   `finalize.session_changed`, where the Godot import still runs. For a batch, `finalize.batch_failed` is the summary: report each failed
   collection from `result.batch.items` with its own code, message, stage, and remediation, and name the
   collections that were skipped. Collections that already succeeded stay imported.

To run one step, call `run_finalize_step` with `step` set to `validate`, `bake`, `variants`, `export`,
`export_anims`, `reimport`, `import_godot`, or `import_anims`. It takes the same inputs, including
`wait_for_lock`, and returns a result with `step`, `cache_hit`, `outputs`, and
`summary`. Each step runs the earlier steps it depends on first, from the cache when they are
already there.

`import_godot` resolves Godot from `GODOT_BIN`, then `godot` on `PATH`, then `/Applications/Godot.app`.
It runs `godot --headless --path game --import`, then a probe that checks each variant's mesh names,
triangles, material slots, and bounds against the exported `nmg-asset.json`. Godot 4 tracks its latest
stable release and is never pinned. A Godot failure is reported at once; there is nothing to wait for
or retry.

When `validate` reports `budget.tris` on a generated asset (a Meshy or similar model whose Desktop
triangle count is over its class budget), run `reduce_asset` on the collection with its
`asset_class` before finalizing again. It decimates the parts to the Desktop budget, keeps the
originals in the hidden `<Name>_High` collection that finalize never reads, and bakes the look onto
the reduced mesh. Then call `finalize_asset` again. Its result is a job like any other. Details are in
`docs/skills/reduce-to-budget.md`.

Never call the Blender MCP for a bake, a variant, or an export. Reruns are cheap: unchanged steps are
cache hits, so rerun after a fix without `force`.

## Animation clips

A rigged character (`SK_<Name>` in collection `<Name>`) can hold animation clips. Finalize runs two
steps for them, after the mesh steps they depend on:

- `export_anims` (Blender) writes one armature-only `.glb` per clip to
  `<export_root>/<Category>/<Name>/Animations/A_<Name>_<Clip>.glb`, plus `nmg-animations.json` beside
  them. The clips are the rig's provenance clips and every action the rig holds in its slot or NLA
  tracks. Unrelated actions in the file are not exported. Each sidecar clip entry has `name`, `file`,
  `asset_path`, `frame_start`, `frame_end`, `frame_count`, `fps`, and `source`. The `source` is the
  recorded library, file, SHA-256, and source skeleton for a provenance clip, or `"authored"`.
- `import_anims` (Godot, headless) writes each changed clip's `.import` file with
  `importer="animation_library"`, imports it, and probes it as an `AnimationLibrary` beside the
  Desktop and Mobile variants. It checks each clip's animation and frame count against the sidecar,
  and a difference fails the step.

Each clip is cached on its own, so a change to `Walk` re-exports and re-imports only `Walk`, and the
mesh steps stay cache hits. `force` reruns every clip. An unrigged asset, or a rig with no clips,
passes through: both steps report zero clips, write nothing under `Animations/`, and start no Godot
process.

To let one character's clips play on another character's skeleton, set `compatible_with` to a list of
`<Category>/<Name>` values, for example `["Characters/Guard"]`. The CLI takes `--compatible-with` once
per value. `import_anims` then checks that every bone track in each clip exists in each target's
Desktop `Skeleton3D`. Every target must already be finalized. Only list characters rigged with the
same bone names.

## Material variants

When the asset ships in several looks, declare them in `<Name>.material-variants.json` beside its
`.blend`. The format is in `docs/asset-contract.md` section 4. Each entry names a material and either a
replacement base-colour PNG, `Tint` values, or both. `validate` checks the declaration before anything is
baked, and `import_godot` writes each variant as a `StandardMaterial3D` resource,
`M_<Name>_<Part>_<Variant>.tres`, in both variant folders. A `--blend` run finds the file beside the blend. A session run has no blend, so it
needs `material_variants_path` set to the declaration's path.

To list an asset's variants, call `list_material_variants` with `category` and `collection` (and
`export_root` when it is not `game/assets`), or run
`python -m nmg_game_dev.finalize material-variants --category <C> --collection <N> [--json]`. It reads
`nmg-variants.json` and never starts Godot. Each row gives the variant's material and the `res://` path
of its Desktop and Mobile `.tres`. An asset with no variants
returns an empty list.

## Failure modes and remediation

- `finalize.session_changed` → The session's `<Name>` changed during the job, so nothing was loaded back. Read the result `.blend` named in the message. Revert or re-author the session changes, then rerun.
- `finalize.job_crashed` → A background Blender process exited before its step finished. Read `blender-<step>.log` in the job directory, fix the cause, and rerun. The open session is unchanged.
- `finalize.job_running` → Another job holds the lock for this cache root. Rerun with `wait_for_lock: true` so finalize waits for the lock itself. If `lock_wait_seconds` runs out first, the error names the job that still holds the lock. Check that job with `get_finalize_job`, and stop its process only when it is stuck.
- `finalize.invalid_batch` → Nothing was started. Each listed entry names its zero-based index and the reason, such as a missing `export_root` or an unknown key. Fix those entries, then rerun the batch.
- `finalize.batch_failed` → One or more collections failed. The message gives the failed and skipped counts. Read each failed collection's error in `result.batch`, fix it, then rerun the whole batch without `force`. Collections that already passed are cache hits.
- `finalize.job_not_found` → The `job_id` is not in this cache root. Use the id that `finalize_asset` or `run_finalize_step` returned.
- `finalize.blender_not_found` → Set `BLENDER_BIN` to the Blender executable, or `BLENDER_APP` to the app bundle, then rerun.
- `finalize.collection_not_found` → The session or `--blend` has no collection named `<Name>`. Check the name is PascalCase and matches the collection.
- `quality.contract_failed` → Read the findings in the contract report. Fix each one in Blender using `docs/asset-contract.md`, then rerun. A `budget.tris` finding on a generated asset is fixed with `reduce_asset` instead (see above). A `material_variant.*` finding names the variant and the rule: fix that entry in `<Name>.material-variants.json`, or the material it names.
- `validate.material_variant.declaration_invalid` → The material-variants file is not valid JSON or not the format in `docs/asset-contract.md` section 4. Fix the file, then rerun.
- `finalize.material_variants_not_found` → The `material_variants_path` does not exist. Pass the path of an existing declaration, or omit it to use the one beside the `.blend`.
- `finalize.material_variants_failed` → The asset's `nmg-variants.json` is missing or invalid. Finalize the asset into that export root first, or pass the `export_root` it was finalized into.
- `quality.reimport_mismatch` → The exported `.glb` re-imported differently from its pre-export report. Read the re-import report, fix the export cause, then rerun.
- `bake.texture.bake_failed` → Read `blender-bake.log`, fix the material it names, then rerun.
- `variants.<code>` → Read the message, fix the mesh or material it names, then rerun.
- `godot.not_found` → Install Godot 4 (latest stable) or set `GODOT_BIN` to its executable, then rerun `import_godot`.
- `import_godot.project_missing` → No `project.godot` at or above `export_root`. Run `/onboard-consumer` to create `game/project.godot`, or pass `export_root` `game/assets`.
- `import_godot.import_failed` → The headless import printed an `ERROR:` line or exited non-zero; the message holds the first error. Fix the file it names, then rerun `import_godot`.
- `import_godot.mismatch` → A variant's probed mesh names, triangles, material slots, or bounds differ from its `nmg-asset.json`, or a terrain chunk is missing. Rerun with `force: true` so the variant is re-exported and re-imported.
- `import_godot.terrain_height_mismatch` → A terrain scene's collision or chunk height range differs from the heightfield by more than 5 cm. Rerun with `force: true`. If the mismatch persists, report it; it is not a grid fault.
- `finalize.clip_name_invalid` → An action the rig holds has a name that breaks `^[A-Za-z][A-Za-z0-9_]*$`. Nothing was exported. Rename the action to start with a letter and use only letters, digits, and underscores, then rerun.
- `finalize.skeleton_not_found` → `import_anims` found no Desktop skeleton for the character, or a `compatible_with` target has none. For the character itself, run `import_godot` first, then rerun `import_anims`. For a target, finalize that character first, or remove it from `compatible_with`.
- `finalize.skeleton_mismatch` → A clip has a bone track that a `compatible_with` target's skeleton lacks. The message lists the bones. Only list characters rigged with the same bone names, then rerun.
- `import_anims.clip_mismatch` → A clip is missing from its `AnimationLibrary`, or its frame count differs from the sidecar. The message names the clip, the expected value, and the measured value. Re-export the clip, then rerun `import_anims` with `force: true`.
- `import_anims.failed` → The clip import or its probe failed. Run `godot --headless --path game --import` to read the errors, confirm the clip `.glb` files exist in `Animations/`, then rerun `import_anims`.
- `mcp.blender.unreachable` → Run `scripts/start-blender-mcp.sh`, then rerun.

Full reference: `docs/mcp/finalize.md`. The animation layout and sidecar are described in
`docs/rigging-and-animation.md`.

## Test fixtures

- `tests/bdd/features/finalize.feature`: the scenarios this skill follows.
- `tests/bdd/features/rigged_animations.feature`: the animation clip scenarios (SCN001-SCN016 of #138).
- `tests/e2e/test_finalize_e2e.py` (`--runslow`): a fixture crate finalized through Blender and headless Godot.
