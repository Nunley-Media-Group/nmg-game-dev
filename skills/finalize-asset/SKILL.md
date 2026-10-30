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
   `hero_prop`, `character`, or `environment_piece`). If one is missing, stop with an error that names
   it. Do not guess a category or class.
2. Call `finalize_asset` with `collection`, `category`, `asset_class`, and `export_root`. Add `blend`
   or `budgets_path` when they apply. Pass `force: true` only when the developer asks to rerun every
   step. Pass `wait_seconds: 150` so a small asset returns its result in the same call.
3. If the reply has no `result`, poll `get_finalize_job` with the returned `job_id` until `state` is
   `succeeded` or `failed`. Report `step` and `progress` as they change.
4. On `succeeded`, report each step's `cache_hit`, the Unreal content paths
   `/Game/<Category>/<Name>/Desktop/` and `/Game/<Category>/<Name>/Mobile/`, and `loaded_back`. If
   `loaded_back` is false, say that the session was not updated and name the result `.blend` path.
5. On `failed`, report `error.code`, `error.message`, `error.stage`, and `error.remediation`, then stop.
   A failed step stops the run before UE import. The one exception is `finalize.session_changed`, where
   the UE import still runs.

To run one step, call `run_finalize_step` with `step` set to `validate`, `bake`, `variants`, `export`,
`reimport`, or `import_ue`. It takes the same inputs and returns a result with `step`, `cache_hit`,
`outputs`, and `summary`.

Never call the Blender MCP for a bake, a variant, or an export. Reruns are cheap: unchanged steps are
cache hits, so rerun after a fix without `force`.

## Failure modes and remediation

- `finalize.session_changed` → The session's `<Name>` changed during the job, so nothing was loaded back. Read the result `.blend` named in the message. Revert or re-author the session changes, then rerun.
- `finalize.job_crashed` → A background Blender process exited before its step finished. Read `blender-<step>.log` in the job directory, fix the cause, and rerun. The open session is unchanged.
- `finalize.job_running` → Another job holds the lock for this cache root. Wait for it with `get_finalize_job`, or stop it, then rerun.
- `finalize.job_not_found` → The `job_id` is not in this cache root. Use the id that `finalize_asset` or `run_finalize_step` returned.
- `finalize.blender_not_found` → Set `BLENDER_BIN` to the Blender executable, or `BLENDER_APP` to the app bundle, then rerun.
- `finalize.collection_not_found` → The session or `--blend` has no collection named `<Name>`. Check the name is PascalCase and matches the collection.
- `quality.contract_failed` → Read the findings in the contract report. Fix each one in Blender using `docs/asset-contract.md`, then rerun.
- `quality.reimport_mismatch` → The exported FBX re-imported differently from its pre-export report. Read the re-import report, fix the export cause, then rerun.
- `bake.texture.bake_failed` → Read `blender-bake.log`, fix the material it names, then rerun.
- `variants.<code>` → Read the message, fix the mesh or material it names, then rerun.
- `import_ue.failed` → Check the editor Output Log for the import, then rerun `import_ue`.
- `import_ue.pivot_mismatch` → A child part's pivot moved. Fix it in Blender, then rerun with `force: true` so the UE content is reimported.
- `mcp.blender.unreachable` → Run `scripts/start-blender-mcp.sh`, then rerun.
- `mcp.unreal.unreachable` → Run `scripts/start-unreal-mcp.sh`, then rerun `import_ue`.

Full reference: `docs/mcp/finalize.md`.

## Test fixtures

- `tests/bdd/features/finalize.feature`: the scenarios this skill follows.
- `tests/e2e/test_finalize_e2e.py` (`--runslow`): a fixture crate finalized through Blender and UE 5.8.
