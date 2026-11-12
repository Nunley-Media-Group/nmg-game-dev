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
result back into the session, and imports both variants into Unreal. Use it when the developer says
an asset is done and wants it in Unreal. The Blender steps run in background Blender, so this skill
never sends a bake, variant, or export through a Blender MCP call.

## Flow

1. Confirm that the collection `<Name>` exists in the open Blender session, or that a saved `.blend`
   is available. Confirm `category` (PascalCase) and `asset_class` (`small_prop`, `standard_prop`,
   `hero_prop`, `character`, or `environment_piece`). When either is omitted, both come from the design
   backlog (`docs/design/backlog.json`): the asset entry whose `asset_name` is `<Name>` supplies them
   (for each collection in a batch), and explicit values win. A successful `finalize_asset` marks that
   entry `finalized`. If one is missing and no backlog entry supplies it, stop with an error that names
   it. Do not guess a category or class.
2. Call `finalize_asset` with `collection`, `category`, `asset_class`, and `export_root`. Add `blend`,
   `budgets_path`, or `material_variants_path` when they apply. Pass `force: true` only when the
   developer asks to rerun every step. Pass `wait_seconds: 150` so a small asset returns its result in
   the same call.
   To finalize several collections, call `finalize_asset` once with `requests`: a list with one object
   per collection, each taking the same keys (an entry sets its own `material_variants_path`).
   Top-level `category`, `asset_class`, `export_root`, and the PIE options fill in any key an entry
   leaves out. The collections run one at a time, in the order
   given, under one job lock, so a batch never interleaves with another finalize job. Pass
   `fail_fast: true` only when one failure should skip the rest. By default the other collections still
   run, because one asset's bake failure should not hold up unrelated assets.
   When another finalize job may be running, pass `wait_for_lock: true`. Without it, the call fails at
   once with `finalize.job_running`. Add `lock_wait_seconds` to cap how long the job waits.
3. If the reply has no `result`, poll `get_finalize_job` with the returned `job_id` until `state` is
   `succeeded` or `failed`. Report `step` and `progress` as they change. A job that is waiting for the
   lock reports `state: waiting`. For a batch, `batch` names the collection that is running, and
   `batch.completed` out of `batch.total`, so say which collection is in progress.
4. On `succeeded`, report each step's `cache_hit`, the Unreal content paths
   `/Game/<Category>/<Name>/Desktop/` and `/Game/<Category>/<Name>/Mobile/`, and `loaded_back`. If
   `loaded_back` is false, say that the session was not updated and name the result `.blend` path.
   For a batch, `result.batch` gives each collection's `state` and the `succeeded`, `failed`, and
   `skipped` counts. Each collection's step detail stays in its job directory under
   `items/<index>-<collection>/`, so point the developer there if they need it.
5. On `failed`, report `error.code`, `error.message`, `error.stage`, and `error.remediation`, then stop.
   A failed step stops the run before UE import. The one exception is `finalize.session_changed`, where
   the UE import still runs. For a batch, `finalize.batch_failed` is the summary: report each failed
   collection from `result.batch.items` with its own code, message, stage, and remediation, and name the
   collections that were skipped. Collections that already succeeded stay imported.

To run one step, call `run_finalize_step` with `step` set to `validate`, `bake`, `variants`, `export`,
`reimport`, or `import_ue`. It takes the same inputs, including `wait_for_lock` and the PIE options,
and returns a result with `step`, `cache_hit`, `outputs`, and `summary`.

Two settings govern the Unreal import. `pie_mode` decides what happens when the editor is in Play In
Editor (PIE) before an import: `wait`, the default, polls until PIE ends, for up to `pie_wait_seconds`
(600 by default), and `refuse` fails at once. Either way, no import request is sent while PIE is on.
The pipeline also retries Unreal requests that time out, so do not retry them by hand.

Never call the Blender MCP for a bake, a variant, or an export. Reruns are cheap: unchanged steps are
cache hits, so rerun after a fix without `force`.

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
- `finalize.job_running` → Another job holds the lock for this cache root. Rerun with `wait_for_lock: true` so finalize waits for the lock itself. If `lock_wait_seconds` runs out first, the error names the job that still holds the lock. Check that job with `get_finalize_job`, and stop its process only when it is stuck.
- `finalize.invalid_batch` → Nothing was started. Each listed entry names its zero-based index and the reason, such as a missing `export_root` or an unknown key. Fix those entries, then rerun the batch.
- `finalize.batch_failed` → One or more collections failed. The message gives the failed and skipped counts. Read each failed collection's error in `result.batch`, fix it, then rerun the whole batch without `force`. Collections that already passed are cache hits.
- `import_ue.editor_busy` → The editor stayed in Play In Editor past the PIE wait limit, or `pie_mode` was `refuse`. No import was sent. Stop the Play In Editor session, then rerun.
- `finalize.job_not_found` → The `job_id` is not in this cache root. Use the id that `finalize_asset` or `run_finalize_step` returned.
- `finalize.blender_not_found` → Set `BLENDER_BIN` to the Blender executable, or `BLENDER_APP` to the app bundle, then rerun.
- `finalize.collection_not_found` → The session or `--blend` has no collection named `<Name>`. Check the name is PascalCase and matches the collection.
- `quality.contract_failed` → Read the findings in the contract report. Fix each one in Blender using `docs/asset-contract.md`, then rerun. A `material_variant.*` finding names the variant and the rule: fix that entry in `<Name>.material-variants.json`, or the material it names.
- `validate.material_variant.declaration_invalid` → The material-variants file is not valid JSON or not the format in `docs/asset-contract.md` section 4. Fix the file, then rerun.
- `finalize.material_variants_not_found` → The `material_variants_path` does not exist. Pass the path of an existing declaration, or omit it to use the one beside the `.blend`.
- `finalize.material_variants_failed` → Unreal could not list the material variants. Read the UE error in the message, confirm the editor is idle, then rerun `list_material_variants`.
- `quality.reimport_mismatch` → The exported FBX re-imported differently from its pre-export report. Read the re-import report, fix the export cause, then rerun.
- `bake.texture.bake_failed` → Read `blender-bake.log`, fix the material it names, then rerun.
- `variants.<code>` → Read the message, fix the mesh or material it names, then rerun.
- `import_ue.failed` → Check the editor Output Log for the import, then rerun `import_ue`.
- `import_ue.failed` with `Unreal MCP did not answer after N attempts over S s` → The editor timed out on every attempt. The pipeline retries a timed-out request up to 4 times, waiting 20 s × the retry number before each one. Check that the editor is responsive, then rerun. `NMG_GAME_DEV_UE_RETRIES` and `NMG_GAME_DEV_UE_RETRY_DELAY_S` change those limits.
- `import_ue.pivot_mismatch` → A child part's pivot moved. Fix it in Blender, then rerun with `force: true` so the UE content is reimported.
- `mcp.blender.unreachable` → Run `scripts/start-blender-mcp.sh`, then rerun.
- `mcp.unreal.unreachable` → Run `scripts/start-unreal-mcp.sh`, then rerun `import_ue`.

Full reference: `docs/mcp/finalize.md`.

## Test fixtures

- `tests/bdd/features/finalize.feature`: the scenarios this skill follows.
- `tests/e2e/test_finalize_e2e.py` (`--runslow`): a fixture crate finalized through Blender and UE 5.8.
