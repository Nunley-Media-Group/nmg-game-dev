---
name: finalize-asset
description: Finalize a collection you authored in Blender into Desktop and Mobile variants imported into Unreal
required_mcp: [blender, unreal, finalize]
required_env: [BLENDER_BIN?, BLENDER_APP?, UE_MCP_PORT?, NMG_GAME_DEV_CACHE_DIR?]
unattended_safe: true
---

# Finalize Asset

Makes an asset the agent authored in the open Blender session shippable. It validates the collection
against `docs/asset-contract.md`, bakes its materials to contract texture sets, builds Desktop and
Mobile variants, exports them, re-verifies each export with a headless re-import, loads the baked
result back into the session, and imports both variants into Unreal. For a rigged character it also
exports every animation clip on `SK_<Name>` and imports each clip into Unreal. Use it when the
developer says an asset is done and wants it in Unreal. The Blender steps run in background Blender,
so this skill never sends a bake, variant, or export through a Blender MCP call.

## Flow

1. Confirm that the collection `<Name>` exists in the open Blender session, or that a saved `.blend`
   is available. Confirm `category` (PascalCase) and `asset_class` (`small_prop`, `standard_prop`,
   `hero_prop`, `character`, or `environment_piece`). When either is omitted, both come from the design
   backlog (`docs/design/backlog.json`): the asset entry whose `asset_name` is `<Name>` supplies them,
   and explicit values win. A successful `finalize_asset` marks that entry `finalized`. If one is
   missing and no backlog entry supplies it, stop with an error that names it. Do not guess a category
   or class.
2. Call `finalize_asset` with `collection`, `category`, `asset_class`, and `export_root`. Add `blend`,
   `budgets_path`, or `material_variants_path` when they apply. Pass `force: true` only when the developer asks to rerun every
   step. Pass `wait_seconds: 150` so a small asset returns its result in the same call.
3. If the reply has no `result`, poll `get_finalize_job` with the returned `job_id` until `state` is
   `succeeded` or `failed`. Report `step` and `progress` as they change.
4. On `succeeded`, report each step's `cache_hit`, the Unreal content paths
   `/Game/<Category>/<Name>/Desktop/` and `/Game/<Category>/<Name>/Mobile/`, and `loaded_back`. If
   `loaded_back` is false, say that the session was not updated and name the result `.blend` path.
   When the result has an `animations` entry, also report its `content_path`, how many clips were
   served from cache for export and for import, every name under `stale`, and every skeleton under
   `compatible`.
5. On `failed`, report `error.code`, `error.message`, `error.stage`, and `error.remediation`, then stop.
   A failed step stops the run before UE import. The one exception is `finalize.session_changed`, where
   the UE import still runs.

To run one step, call `run_finalize_step` with `step` set to `validate`, `bake`, `variants`, `export`,
`export_anims`, `reimport`, `import_ue`, or `import_anims`. It takes the same inputs and returns a
result with `step`, `cache_hit`, `outputs`, and `summary`. Each step runs the earlier steps it depends
on first, from the cache when they are already there.

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

- `export_anims` (Blender) writes one armature-only FBX per clip to
  `<export_root>/<Category>/<Name>/Animations/A_<Name>_<Clip>.fbx`, plus `nmg-animations.json` beside
  them. The clips are the rig's provenance clips and every action the rig holds in its slot or NLA
  tracks. Unrelated actions in the file are not exported. Each sidecar clip entry has `name`, `file`,
  `asset_path`, `frame_start`, `frame_end`, `frame_count`, `fps`, and `source`. The `source` is the
  recorded library, file, SHA-256, and source skeleton for a provenance clip, or `"authored"`.
- `import_anims` (Unreal) imports each clip as the AnimSequence
  `/Game/<Category>/<Name>/Animations/A_<Name>_<Clip>` on the Desktop skeleton
  `/Game/<Category>/<Name>/Desktop/SM_<Name>_Skeleton`. It creates no other skeleton, skeleton mesh,
  or physics asset. It checks each clip's skeleton and frame count against the sidecar, and a
  difference fails the step.

Each clip is cached on its own, so a change to `Walk` re-exports and re-imports only `Walk`, and the
mesh steps stay cache hits. `force` reruns every clip. An unrigged asset, or a rig with no clips,
passes through: both steps report zero clips, write nothing under `Animations/`, and make no Unreal
call.

`import_anims` reports AnimSequences named `A_<Name>_*` that are no longer clips under `stale`. It
never deletes them. Remove a stale sequence by hand in Unreal if it is no longer wanted.

To let one character's clips play on another character's skeleton, set `compatible_with` to a list of
`<Category>/<Name>` values, for example `["Characters/Guard"]`. The CLI takes `--compatible-with` once
per value. `import_anims` then lists each skeleton as compatible with the other, in both directions,
without duplicates. Both characters keep their own skeleton assets. Every target must already be
finalized, and its bone names must match this character's, or nothing is registered. Only register
characters rigged with the same bone names.

## Material variants

When the asset ships in several looks, declare them in `<Name>.material-variants.json` beside its
`.blend`. The format is in `docs/asset-contract.md` section 4. Each entry names a material and either a
replacement base-colour PNG, `Tint` values, or both. `validate` checks the declaration before anything is
baked, and the import creates each variant as `MI_<Name>_<Part>_<Variant>` beside the main instances in
both Content folders. A `--blend` run finds the file beside the blend. A session run has no blend, so it
needs `material_variants_path` set to the declaration's path.

To list an asset's variants from Unreal, call `list_material_variants` with `category` and `collection`,
or run `python -m nmg_game_dev.finalize material-variants --category <C> --collection <N> [--json]`. Each
row gives the variant's material and its Desktop and Mobile instance paths. An asset with no variants
returns an empty list.

## Failure modes and remediation

- `finalize.session_changed` → The session's `<Name>` changed during the job, so nothing was loaded back. Read the result `.blend` named in the message. Revert or re-author the session changes, then rerun.
- `finalize.job_crashed` → A background Blender process exited before its step finished. Read `blender-<step>.log` in the job directory, fix the cause, and rerun. The open session is unchanged.
- `finalize.job_running` → Another job holds the lock for this cache root. Wait for it with `get_finalize_job`, or stop it, then rerun.
- `finalize.job_not_found` → The `job_id` is not in this cache root. Use the id that `finalize_asset` or `run_finalize_step` returned.
- `finalize.blender_not_found` → Set `BLENDER_BIN` to the Blender executable, or `BLENDER_APP` to the app bundle, then rerun.
- `finalize.collection_not_found` → The session or `--blend` has no collection named `<Name>`. Check the name is PascalCase and matches the collection.
- `quality.contract_failed` → Read the findings in the contract report. Fix each one in Blender using `docs/asset-contract.md`, then rerun. A `budget.tris` finding on a generated asset is fixed with `reduce_asset` instead (see above). A `material_variant.*` finding names the variant and the rule: fix that entry in `<Name>.material-variants.json`, or the material it names.
- `validate.material_variant.declaration_invalid` → The material-variants file is not valid JSON or not the format in `docs/asset-contract.md` section 4. Fix the file, then rerun.
- `finalize.material_variants_not_found` → The `material_variants_path` does not exist. Pass the path of an existing declaration, or omit it to use the one beside the `.blend`.
- `finalize.material_variants_failed` → Unreal could not list the material variants. Read the UE error in the message, confirm the editor is idle, then rerun `list_material_variants`.
- `quality.reimport_mismatch` → The exported FBX re-imported differently from its pre-export report. Read the re-import report, fix the export cause, then rerun.
- `bake.texture.bake_failed` → Read `blender-bake.log`, fix the material it names, then rerun.
- `variants.<code>` → Read the message, fix the mesh or material it names, then rerun.
- `import_ue.failed` → Check the editor Output Log for the import, then rerun `import_ue`.
- `import_ue.pivot_mismatch` → A child part's pivot moved. Fix it in Blender, then rerun with `force: true` so the UE content is reimported.
- `finalize.clip_name_invalid` → An action the rig holds has a name that breaks `^[A-Za-z][A-Za-z0-9_]*$`. Nothing was exported. Rename the action to start with a letter and use only letters, digits, and underscores, then rerun.
- `finalize.skeleton_not_found` → `import_anims` found no Desktop skeleton for the character, or a `compatible_with` target has none. For the character itself, run `import_ue` first, then rerun `import_anims`. For a target, finalize that character first, or remove it from `compatible_with`.
- `finalize.skeleton_mismatch` → A `compatible_with` target's bone names differ from this character's. The message lists the differing bones. Only register characters rigged with the same bone names, then rerun.
- `import_anims.clip_mismatch` → A clip's AnimSequence has another skeleton or frame count than the sidecar records. The message names the clip, the expected value, and the measured value. Re-export the clip, then rerun `import_anims` with `force: true`.
- `import_anims.failed` → The Unreal import call for the clips failed. Check the editor Output Log, confirm the clip FBX files exist in `Animations/`, then rerun `import_anims`.
- `mcp.blender.unreachable` → Run `scripts/start-blender-mcp.sh`, then rerun.
- `mcp.unreal.unreachable` → Run `scripts/start-unreal-mcp.sh`, then rerun `import_ue`.

Full reference: `docs/mcp/finalize.md`. The animation layout and sidecar are described in
`docs/rigging-and-animation.md`.

## Test fixtures

- `tests/bdd/features/finalize.feature`: the scenarios this skill follows.
- `tests/bdd/features/rigged_animations.feature`: the animation clip scenarios (SCN001-SCN016 of #138).
- `tests/e2e/test_finalize_e2e.py` (`--runslow`): a fixture crate finalized through Blender and UE 5.8.
