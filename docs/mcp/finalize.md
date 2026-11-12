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
| `finalize_asset` | `collection`, `export_root`, optional `category`, `asset_class`, `blend`, `budgets_path`, `force`, `wait_seconds`, `compatible_with` | `{"job_id", "status"}`, plus `result` when the job finishes within `wait_seconds` |
| `run_finalize_step` | `step` (one of the eight step names), then the same inputs as `finalize_asset` | The same shape as `finalize_asset`, for one step |
| `get_finalize_job` | `job_id` | `{"job_id", "state", "step", "progress", "message", "result"?, "error"?}` |

`wait_seconds` is clamped to 0–150. A value of 0 returns the job id at once. `get_finalize_job`
reports `state` as `queued`, `running`, `succeeded`, or `failed`, and `progress` as a number from 0
to 1. An unknown `job_id` returns `finalize.job_not_found`.

`category` and `asset_class` are optional on `finalize_asset` and `run_finalize_step`. When one is
omitted, finalize takes it from the design backlog. See [Backlog fallback](#backlog-fallback).

`compatible_with` is optional. It is a list of `<Category>/<Name>` strings, such as
`["Characters/Guard"]`, and each item is PascalCase. It names characters whose Desktop skeleton this
character's animation clips may also play on. `import_anims` registers both directions. Duplicates
are dropped, and a character may not name itself.

Errors come back as `{"error": {"code", "message", "remediation", "stage"}}`. The server writes
logs to stderr only, because stdout is the MCP channel.

## CLI

```text
python -m nmg_game_dev.finalize {all,validate,bake,variants,export,export_anims,reimport,import_ue,import_anims} \
  --collection Crate --export-root <dir> [--category Props] [--class standard_prop] \
  [--blend B] [--budgets P] [--device GPU|CPU] [--compatible-with Category/Name ...] \
  [--force] [--json]
```

`--compatible-with` may repeat, once for each character named in [Animation clips](#animation-clips).

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
| `category` | Optional. The Unreal category, PascalCase. Content lands in `/Game/<Category>/<Name>/`. When omitted, taken from the design backlog. |
| `asset_class` | Optional. One of `small_prop`, `standard_prop`, `hero_prop`, `character`, or `environment_piece`. Sets the texture sizes and the material limit. When omitted, taken from the design backlog. |
| `export_root` | Folder that receives `<Category>/<Name>/Desktop/` and `<Category>/<Name>/Mobile/`. |
| `blend` | Optional saved `.blend` to finalize instead of the open session. |
| `budgets_path` | Optional `nmg-budgets.json` with budget overrides. |
| `device` | `GPU` (default) or `CPU` for the bake. |

## Backlog fallback

When `category` or `asset_class` is omitted, finalize reads the design backlog,
`docs/design/backlog.json` under the project root (`CLAUDE_PROJECT_DIR` when set, else the working
directory). It takes the value from the asset entry whose `asset_name` equals `collection`. Asset
entries have the types `character`, `vehicle`, `prop`, and `environment`. The backlog is written by
`python -m nmg_game_dev.design sync`. See `docs/design-contract.md`.

- An explicit argument always wins over the backlog.
- If an argument is still missing and no asset entry matches, the call fails with
  `finalize.invalid_request`. The error names the missing argument and the backlog path it checked.
- A `finalize_asset` job that succeeds sets the matching entry's `status` to `finalized`.
  `run_finalize_step` never changes the backlog.
- If the backlog cannot be updated after a successful job, the job still succeeds. Its result's
  `warnings` list holds `design.backlog_update_failed`.
- The cache key is the same whether a value came from the backlog or from an argument.

## Steps

Finalize runs the steps in this order, and each step can also run alone:

| Step | Runs in | Reads and writes | Gate or output |
|------|---------|------------------|----------------|
| `validate` | Blender, read-only | Checkpoint | Contract report, gated by `quality.contract_failed` |
| `bake` | Blender, writes a copy | Checkpoint to `bake.blend` | Contract texture sets and the bake proof |
| `variants` | Blender, writes a copy | `bake.blend` to `variants.blend` | Triangle counts per variant and LOD |
| `export` | Blender, read-only | `variants.blend` to the FBX folders and `nmg-variants.json` | Pre-export contract report, gated by `quality.contract_failed` |
| `export_anims` | Blender, read-only | `variants.blend` to `Animations/A_<Name>_<Clip>.fbx` and `nmg-animations.json` | One FBX per clip, cached per clip. Fails with `finalize.clip_name_invalid` |
| `reimport` | Blender, factory startup | Exported FBX | Re-import report per variant, gated by `quality.reimport_mismatch` |
| `import_ue` | Unreal MCP | Exported folders to `/Game/<Category>/<Name>/{Desktop,Mobile}/` | Pivot check, failing with `import_ue.pivot_mismatch` |
| `import_anims` | Unreal MCP | Clip FBX to `/Game/<Category>/<Name>/Animations/A_<Name>_<Clip>` on the Desktop skeleton | Skeleton and frame-count check against the sidecar, failing with `import_anims.clip_mismatch`. Stale and compatible-skeleton reports |

`export_anims` runs after `export`, and `import_anims` runs after `import_ue`. `finalize all` runs
both. Load-back sits between `reimport` and `import_ue`. It is not a step in its own right.

A character without clips passes through both animation steps. Each reports zero clips, writes
nothing under `Animations/`, and makes no Unreal call. Every other output is the same as before.

### Animation clips

`export_anims` exports every clip on `SK_<Name>`, which is the rig's provenance clips plus the actions
held in its slot or NLA tracks. Unrelated actions in the file are not exported.

- **Layout.** `<export_root>/<Category>/<Name>/Animations/A_<Name>_<Clip>.fbx` holds one clip each.
  Each file has an armature named `Armature`, no mesh, and exactly one clip. The armature and axis
  settings match the rigged mesh export: `add_leaf_bones` off, deform-only, primary bone axis Y,
  secondary X.
- **Sidecar.** `nmg-animations.json` sits beside the FBX files. The top level holds `asset`,
  `armature` (`Armature`), and `skeleton` (`/Game/<Category>/<Name>/Desktop/SM_<Name>_Skeleton`).
  Each entry in `clips` holds `name`, `file`, `asset_path`, `frame_start`, `frame_end`,
  `frame_count`, `fps`, and `source`. The `source` is the provenance `source` dict (`library`,
  `file`, `sha256`, `skeleton`), or `"authored"` for a clip with no provenance.
- **Import.** `import_anims` imports each clip as the AnimSequence
  `/Game/<Category>/<Name>/Animations/A_<Name>_<Clip>` on `SM_<Name>_Skeleton`. It creates no other
  skeleton, skeletal mesh, or physics asset. It checks each clip's skeleton and frame count against
  the sidecar. A difference fails the step with `import_anims.clip_mismatch`, which names the clip,
  the expected value, and the measured value.
- **Stale sequences.** `import_anims` lists AnimSequences named `A_<Name>_*` that are no longer
  clips under `stale` in the result. It never deletes them.
- **Compatible skeletons.** With `compatible_with`, `import_anims` checks each target's Desktop
  skeleton before it changes anything. A missing target fails with `finalize.skeleton_not_found`,
  and differing bone names fail with `finalize.skeleton_mismatch`, which lists the differing bones.
  Otherwise each skeleton gains the other in its `compatible_skeletons`, once, in both directions.
  Both characters keep their own skeleton assets. The result lists the registered skeletons under
  `compatible`.

The result's `animations` entry carries `content_path`, `clips` (each with `name`, `asset_path`,
`export_cache_hit`, and `import_cache_hit`), `stale`, and `compatible`. It is `null` when no clip step
ran.

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

The two animation steps are cached per clip, not as a whole, and they do not change the input hash
of the steps after them:

- **Export.** A clip's key covers its content hash (keyframes through the action's slots, the rig's
  bones and rest pose, the provenance entry, and the scene frame rate) and the export settings. A
  change to `Walk` re-exports only `Walk`. `Idle` is served from cache and is not re-exported.
- **Import.** A clip's key covers its exported output and the Desktop skeleton path. A clip whose
  sequence already exists is served from cache and is not re-imported. A clip whose sequence has
  been deleted from the project is imported again.
- **Mesh steps.** A clip-only change leaves every mesh step's key valid, so the mesh steps stay cache
  hits.
- **Probe.** `export_anims` always runs its Blender probe, because the probe lists the clips and
  their hashes that the keys need. The probe itself is never cached.
- **Force.** `force` reruns every clip in both steps.

A clip step reports `cache_hit: true` only when every clip was served from cache. A step with no
clips reports `cache_hit` from the step before it.

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
| `finalize.invalid_request` | `category` or `asset_class` is omitted, and no asset entry in `docs/design/backlog.json` supplies it. The message names the argument and the backlog path. | Pass the argument, or add the asset's design doc, run `python -m nmg_game_dev.design sync`, then rerun. |
| `finalize.blender_not_found` | No Blender executable at `BLENDER_BIN`, `BLENDER_APP`, or `/Applications/Blender.app`. | Set `BLENDER_BIN` to the Blender executable, or `BLENDER_APP` to the app bundle, then rerun. |
| `finalize.collection_not_found` | The session, or `--blend`, has no collection named `<Name>`. | Check that the collection name matches `--collection` and is PascalCase. |
| `quality.contract_failed` | A contract report failed. Its findings name each rule and target. | Fix each finding in Blender, using `docs/asset-contract.md`, then rerun. |
| `quality.reimport_mismatch` | An exported FBX re-imported differently from its pre-export report. | Read the re-import report in the job directory, fix the export cause, then rerun. |
| `bake.texture.bake_failed` | A texture bake failed. | Read `blender-bake.log` and fix the material it names, then rerun. |
| `variants.<code>` | Variant generation failed. The code names the cause. | Read the message, fix the mesh or material it names, then rerun. |
| `import_ue.failed` | The Unreal import call failed. | Check the editor Output Log for the import, then rerun `import_ue`. |
| `import_ue.pivot_mismatch` | A child part's local bounds differ from the Blender part by more than 0.01 cm. | Fix the pivot in Blender, then rerun finalize with `--force` so the UE content is reimported. |
| `finalize.clip_name_invalid` | A clip's action name does not match `^[A-Za-z][A-Za-z0-9_]*$`. The message names it. Nothing was exported. | Rename the action to start with a letter and use only letters, digits, and underscores, then rerun. |
| `finalize.skeleton_not_found` | `import_anims` found no Desktop skeleton for the character, or a `compatible_with` target has none. Nothing was imported or registered. | For the character, run `import_ue` first, then rerun. For a target, finalize that character first, or remove it from `compatible_with`. |
| `finalize.skeleton_mismatch` | A `compatible_with` target's bone names differ from this character's. The message lists the differing bones. Nothing was registered. | Only register characters rigged with the same bone names. |
| `import_anims.clip_mismatch` | A clip's AnimSequence has a different skeleton or frame count from the sidecar. The message names the clip, the expected value, and the measured value. | Re-export the clip, then rerun `import_anims` with `force`. |
| `import_anims.failed` | The Unreal import call for the clips failed, or a non-AnimSequence asset was created. | Check the editor Output Log, confirm the clip FBX files exist, then rerun `import_anims`. |
| `mcp.blender.unreachable` | The Blender MCP session on `BLENDER_MCP_PORT` is not reachable. | Run `scripts/start-blender-mcp.sh`, then rerun. |
| `mcp.unreal.unreachable` | The Unreal MCP endpoint on `UE_MCP_PORT` is not reachable. | Run `scripts/start-unreal-mcp.sh`, then rerun `import_ue`. |

## Versions

Blender 5.2 LTS, UE 5.8, the Blender MCP server, and VibeUE all track their latest releases, as in
`docs/mcp/blender.md` and `docs/mcp/unreal.md`. Nothing here pins a version.
