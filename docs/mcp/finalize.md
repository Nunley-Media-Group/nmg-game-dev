# Finalize MCP: finalize an authored asset

The `finalize` MCP server and the `python -m nmg_game_dev.finalize` CLI run one implementation.
It takes a collection the agent authored in Blender and makes it shippable: validate it against
`docs/asset-contract.md`, bake its materials, build Desktop and Mobile variants, export, re-verify
with a fresh headless re-import, load the baked result back into the open session, and import both
variants into Unreal. Blender work runs in background headless Blender, so an MCP call never runs a
bake, variant, or export for longer than the 180 s Blender MCP timeout.

`.mcp.json` declares the server:

```json
"finalize": {
  "command": "uv",
  "args": ["run", "--project", "${CLAUDE_PLUGIN_ROOT}/mcp-servers/finalize", "finalize-mcp"]
}
```

## Tools

| Tool | Input | Returns |
|------|-------|---------|
| `finalize_asset` | `collection`, `category`, `asset_class`, `export_root`, optional `blend`, `budgets_path`, `force`, `wait_seconds` | `{"job_id", "status"}`, plus `result` when the job finishes within `wait_seconds` |
| `run_finalize_step` | `step` (one of the six step names), then the same inputs as `finalize_asset` | The same shape as `finalize_asset`, for one step |
| `get_finalize_job` | `job_id` | `{"job_id", "state", "step", "progress", "message", "result"?, "error"?}` |

`wait_seconds` is clamped to 0–150. A value of 0 returns the job id at once. `get_finalize_job`
reports `state` as `queued`, `running`, `succeeded`, or `failed`, and `progress` as a number from 0
to 1. An unknown `job_id` returns `finalize.job_not_found`.

Errors come back as `{"error": {"code", "message", "remediation", "stage"}}`. The server writes
logs to stderr only, because stdout is the MCP channel.

## CLI

```text
python -m nmg_game_dev.finalize {all,validate,bake,variants,export,reimport,import_ue} \
  --collection Crate --category Props --class standard_prop --export-root <dir> \
  [--blend B] [--budgets P] [--device GPU|CPU] [--force] [--json]
```

| Exit | Meaning |
|------|---------|
| `0` | Success. With `--json`, stdout is the result |
| `1` | A step failed. stderr shows `ERROR [code] message` and `Remediation: ...` |
| `2` | A prerequisite is missing: `finalize.blender_not_found` or `mcp.*.unreachable` |

`python -m nmg_game_dev.finalize run-job <job_dir>` is the internal job runner. The MCP tools and the
CLI start it for you, so you do not run it by hand.

## Request

Every entry point takes one `FinalizeRequest`:

| Field | Meaning |
|-------|---------|
| `collection` | The asset's collection name `<Name>`, PascalCase. The session (or `--blend`) must hold it. |
| `category` | The Unreal category, PascalCase. Content lands in `/Game/<Category>/<Name>/`. |
| `asset_class` | One of `small_prop`, `standard_prop`, `hero_prop`, `character`, or `environment_piece`. Sets the texture sizes and the material limit. |
| `export_root` | Folder that receives `<Category>/<Name>/Desktop/` and `<Category>/<Name>/Mobile/`. |
| `blend` | Optional saved `.blend` to finalize instead of the open session. |
| `budgets_path` | Optional `nmg-budgets.json` with budget overrides. |
| `device` | `GPU` (default) or `CPU` for the bake. |

## Steps

Finalize runs the steps in this order, and each step can also run alone:

| Step | Runs in | Reads and writes | Gate or output |
|------|---------|------------------|----------------|
| `validate` | Blender, read-only | Checkpoint | Contract report, gated by `quality.contract_failed` |
| `bake` | Blender, writes a copy | Checkpoint to `bake.blend` | Contract texture sets and the bake proof |
| `variants` | Blender, writes a copy | `bake.blend` to `variants.blend` | Triangle counts per variant and LOD |
| `export` | Blender, read-only | `variants.blend` to the FBX folders and `nmg-variants.json` | Pre-export contract report, gated by `quality.contract_failed` |
| `reimport` | Blender, factory startup | Exported FBX | Re-import report per variant, gated by `quality.reimport_mismatch` |
| `import_ue` | Unreal MCP | Exported folders to `/Game/<Category>/<Name>/{Desktop,Mobile}/` | Pivot check, failing with `import_ue.pivot_mismatch` |

Load-back sits between `reimport` and `import_ue`. It is not a step in its own right.

`run_finalize_step` returns a result with `step`, `cache_hit`, `outputs`, and `summary`. When a step
fails, no later step runs, and nothing is imported into Unreal.

## Job flow and load-back

1. **Checkpoint.** The job saves the open session's scene as a copy, `checkpoint.blend`, and hashes
   the `<Name>` collection. A `--blend` run hashes the file instead.
2. **Blender steps.** Each Blender step runs in its own `blender --background` process against the
   previous output. A crash loses only that step. Progress lines update `status.json` after every
   step, so `get_finalize_job` can report it.
3. **Load-back.** After `reimport` passes, the baked `<Name>` and `<Name>_Mobile` collections replace
   the session's copies. This happens only when the session's `<Name>` is unchanged since the
   checkpoint. The old collections are renamed, the baked copies are appended and linked, and then
   the old ones are removed. If anything fails, the old names are restored.
4. **Refusal.** If the session's `<Name>` changed during the job, nothing is replaced. The run
   reports `finalize.session_changed` with the result `.blend` path, and `loaded_back` is false.
   The `export`, `reimport`, and `import_ue` steps still run, because they use the job's files and
   not the session.
5. **Crash.** If a background process exits before its step finishes, the job fails with
   `finalize.job_crashed` naming the step. The open session is unchanged.

Job files live under `<cache_root>/jobs/<job_id>/`: `request.json`, `status.json`,
`checkpoint.blend`, `<step>.json`, `<step>.blend`, and `blender-<step>.log`. One job runs per cache
root at a time. A live lock makes a second start fail with `finalize.job_running`.

## Cache behavior

Each step has a content-addressed cache key:

- `input_hash` is the asset's content hash for the first step, and the previous step's output hash
  after that. The asset hash covers the mesh, materials, images, and transforms of `<Name>` and its
  Mobile collection.
- `settings_hash` covers the asset class, the resolved budget, the device (bake only), the export
  root (export and import only), the category, and the step version.

An alias index under `runs/` maps the asset hash to each step's key. A rerun with no change finds
every step in the cache, reports `cache_hit: true` for each, and skips `import_ue`. Load-back is
skipped too, because the session already holds the result. The post-load-back hash is also recorded,
so the rerun after load-back is also a full hit.

A change to any mesh, material, or image misses the cache from the first affected step onward. Steps
before it still hit. `--force` (or `force` on the tools) ignores the cache and reruns every step.

## Environment

| Variable | Default | Used by |
|----------|---------|---------|
| `NMG_GAME_DEV_CACHE_DIR` | `~/.cache/nmg-game-dev` | Cache root: `by-key/`, `runs/`, and `jobs/` |
| `BLENDER_BIN` | unset | Blender executable. Wins when it is executable |
| `BLENDER_APP` | `/Applications/Blender.app` | Blender app bundle. Its `Contents/MacOS/Blender` is used |
| `BLENDER_MCP_PORT` | `9876` | The live Blender session, for checkpoint and load-back |
| `UE_MCP_PORT` | `8000` | The Unreal MCP endpoint for `import_ue` |

Blender is resolved in this order: `BLENDER_BIN`, then `BLENDER_APP/Contents/MacOS/Blender`, then
`/Applications/Blender.app/Contents/MacOS/Blender`. If none is executable, the job fails with
`finalize.blender_not_found`.

## Error codes

| Code | Meaning | Remediation |
|------|---------|-------------|
| `finalize.session_changed` | `<Name>` changed in the session after the checkpoint, so load-back was refused. The export, reimport, and `import_ue` steps still ran. | Read the result `.blend` named in the message. Revert or re-author the session changes, then rerun finalize to load the result back. |
| `finalize.job_crashed` | A background Blender process exited before its step finished. The step is named in the error. | Read `blender-<step>.log` in the job directory. Fix the cause and rerun. The open session is unchanged. |
| `finalize.job_running` | Another finalize job holds the lock for this cache root. | Wait for it with `get_finalize_job`, or stop it, then rerun. |
| `finalize.job_not_found` | No job has that id in this cache root. | Use the `job_id` that `finalize_asset` or `run_finalize_step` returned. |
| `finalize.blender_not_found` | No Blender executable at `BLENDER_BIN`, `BLENDER_APP`, or `/Applications/Blender.app`. | Set `BLENDER_BIN` to the Blender executable, or `BLENDER_APP` to the app bundle, then rerun. |
| `finalize.collection_not_found` | The session, or `--blend`, has no collection named `<Name>`. | Check that the collection name matches `--collection` and is PascalCase. |
| `quality.contract_failed` | A contract report failed. Its findings name each rule and target. | Fix each finding in Blender, using `docs/asset-contract.md`, then rerun. |
| `quality.reimport_mismatch` | An exported FBX re-imported differently from its pre-export report. | Read the re-import report in the job directory, fix the export cause, then rerun. |
| `bake.texture.bake_failed` | A texture bake failed. | Read `blender-bake.log` and fix the material it names, then rerun. |
| `variants.<code>` | Variant generation failed. The code names the cause. | Read the message, fix the mesh or material it names, then rerun. |
| `import_ue.failed` | The Unreal import call failed. | Check the editor Output Log for the import, then rerun `import_ue`. |
| `import_ue.pivot_mismatch` | A child part's local bounds differ from the Blender part by more than 0.01 cm. | Fix the pivot in Blender, then rerun finalize with `--force` so the UE content is reimported. |
| `mcp.blender.unreachable` | The Blender MCP session on `BLENDER_MCP_PORT` is not reachable. | Run `scripts/start-blender-mcp.sh`, then rerun. |
| `mcp.unreal.unreachable` | The Unreal MCP endpoint on `UE_MCP_PORT` is not reachable. | Run `scripts/start-unreal-mcp.sh`, then rerun `import_ue`. |

## Versions

Blender 5.2 LTS, UE 5.8, the Blender MCP server, and VibeUE all track their latest releases, as in
`docs/mcp/blender.md` and `docs/mcp/unreal.md`. Nothing here pins a version.
