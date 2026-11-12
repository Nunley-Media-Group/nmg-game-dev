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
| `finalize_asset` | Either `collection` and `export_root`, or `requests` (a batch, exclusive with `collection`). Optional: `category`, `asset_class`, `blend`, `budgets_path`, `material_variants_path`, `compatible_with`, `force`, `wait_seconds`, `fail_fast`, `wait_for_lock`, `lock_wait_seconds`, `pie_mode`, `pie_wait_seconds` | `{"job_id", "status"}`, plus `result` (a batch's result is `result.batch`) when the job finishes within `wait_seconds`, or `error` when it fails |
| `run_finalize_step` | `step` (one of the eight step names), then the same inputs as `finalize_asset` for one collection, plus `wait_for_lock`, `lock_wait_seconds`, `pie_mode`, `pie_wait_seconds` | The same shape as `finalize_asset`, for one step |
| `reduce_asset` | `collection`, `asset_class`, optional `blend`, `budgets_path`, `device`, `cage_extrusion`, `max_ray_distance`, `miss_threshold`, `parts`, `wait_seconds` | `{"job_id", "status"}`, plus `result` when the job finishes within `wait_seconds`. See [reduce_asset](#reduce_asset-139). |
| `get_finalize_job` | `job_id` | `{"job_id", "state", "step", "progress", "message", "batch"?, "result"?, "error"?}` |
| `list_material_variants` | `category`, `collection` | A list of `{"name", "material", "desktop", "mobile"}` rows, sorted by material then name; `[]` when the asset has no material variants or is not in Content |
| `import_audio` | `file`, `name`, `kind` (`sfx` or `music`), optional `loop` | The audio import result. See [elevenlabs.md](elevenlabs.md) |

`material_variants_path` names the asset's `<Name>.material-variants.json` declaration. Without it, a
`--blend` run uses the file beside the blend when one exists. A session run has no blend, so it declares
no material variants unless the path is given. In a batch, each `requests` entry sets its own
`material_variants_path` and `compatible_with`; those top-level parameters apply to one collection only. A path that does not
exist returns `finalize.material_variants_not_found`. The format and the rules are in `docs/asset-contract.md` section 4.
Each variant's `import_ue` result lists the imported instances in `material_variants`, one entry per
instance, and names any variant parameter the master material lacks in `warnings`.

`list_material_variants` reads the `nmg.*` metadata tags that finalize writes on each variant instance in
`/Game/<Category>/<Name>/Desktop` and `/Game/<Category>/<Name>/Mobile`. Each row gives the variant's
material slot and its instance path in each folder, or `null` for a folder that does not hold it. An
unreachable Unreal MCP endpoint returns `mcp.unreal.unreachable` in the `error` object.

`wait_seconds` is clamped to 0–150. A value of 0 returns the job id at once. `get_finalize_job`
reports `state` as `queued`, `waiting`, `running`, `succeeded`, or `failed`, and `progress` as a number
from 0 to 1. A job that is waiting for the lock reports `waiting`. An unknown `job_id` returns
`finalize.job_not_found`.

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
  (--collection Crate [--collection Barrel ...] | --batch FILE) --export-root <dir> \
  [--category Props] [--class standard_prop] [--blend B] [--budgets P] [--material-variants P] \
  [--device GPU|CPU] [--compatible-with Category/Name ...] [--force] [--fail-fast] \
  [--wait [--wait-limit S]] [--pie wait|refuse] [--pie-wait-limit S] [--json]

python -m nmg_game_dev.finalize material-variants --category Props --collection Crate [--json]
```

`--export-root` is required with `--collection`. A `--batch` entry may set its own.
`--material-variants` applies to a single `--collection`; a `--batch` entry sets `material_variants_path`.
`--compatible-with` may repeat, once for each character named in [Animation clips](#animation-clips).
Like `--material-variants`, it applies to a single `--collection`; a `--batch` entry sets `compatible_with`.

`material-variants` prints the rows that `list_material_variants` returns, one line per variant, or the
JSON array with `--json`. It needs the Unreal MCP endpoint, and it exits `2` when that endpoint is
unreachable.

| Exit | Meaning |
|------|---------|
| `0` | Success. With `--json`, stdout is the result |
| `1` | A step or a collection failed. stderr shows `ERROR [code] message` and `Remediation: ...`. A batch prints one line per collection |
| `2` | A prerequisite is missing (`finalize.blender_not_found` or `mcp.*.unreachable`), or the arguments are wrong |

`python -m nmg_game_dev.finalize run-job <job_dir>` is the internal job runner. The MCP tools and the
CLI start it for you, so you do not run it by hand.

## Batches

Several collections run as one job. They are finalized one at a time, in the order given, under one job
lock, which the job keeps until the last collection finishes. Each collection gets its own directory,
`items/<index>-<collection>/`, so its step cache and design-backlog marking work exactly as they do for a
single collection.

**CLI.** Repeat `--collection`, or pass `--batch <file.json>`, a JSON array of request objects with the
`finalize_asset` keys:

```text
python -m nmg_game_dev.finalize all --collection Crate --collection Barrel --collection Lamp \
  --category Props --class standard_prop --export-root <dir> [--fail-fast] [--json]
```

```json
[
  {"collection": "Crate", "category": "Props", "asset_class": "standard_prop", "export_root": "<dir>"},
  {"collection": "Barrel", "category": "Props", "asset_class": "hero_prop", "export_root": "<dir>"}
]
```

The asset options on the command line fill in any key an entry leaves out. `--batch` cannot be combined
with `--collection`.

**MCP.** Pass `requests`, a list of the same objects, to `finalize_asset`. It is exclusive with
`collection`. The top-level `category`, `asset_class`, `export_root`, `blend`, `budgets_path`, `pie_mode`,
and `pie_wait_seconds` fill in any key an entry omits.

**Validation first.** Every entry is checked before anything starts. One invalid entry rejects the whole
batch with `finalize.invalid_batch`. Its message gives each invalid entry's zero-based index and reason,
and no job directory is written.

**Progress.** `get_finalize_job` reports `batch`: `total`, `completed` (items that reached a final state),
`current` (the collection running now) and `current_index`, and each item's `state`, one of `pending`,
`running`, `succeeded`, `failed`, or `skipped`.

**Failures.** A failed collection does not stop the batch unless `--fail-fast` or `fail_fast: true` is
set. With fail-fast, the remaining collections are reported as `skipped`. A batch whose items all succeed
ends `succeeded`. Otherwise it ends `failed` with `finalize.batch_failed`, and the message gives the failed
and skipped counts.

**Result.** The finished job's `result.batch` lists every item with its `collection`, `state`, and, for a
failure, its `error` (`code`, `message`, `remediation`, `stage`). It also holds the `succeeded`, `failed`,
and `skipped` counts. The CLI prints one line per collection, such as `Crate: succeeded`, and a failed
collection's `[code] message (stage)` line under it, then a `Batch:` count line. With `--json` it prints
`{"batch": ...}`. The exit code is `0` only when every item succeeded, and `1` otherwise.

## Waiting for the lock

Only one finalize job runs per cache root. By default a second start fails at once with
`finalize.job_running`, and the error names the job that holds the lock. To have finalize wait instead,
pass `--wait` on the CLI, or `wait_for_lock: true` to `finalize_asset` or `run_finalize_step`. The same
applies to a batch.

- The job starts in state `waiting`, and its `message` names the holder. Its own process checks for the
  lock every 2 to 5 seconds, with jitter, and runs as soon as the lock is free. A lock left by a dead
  process is cleared on each check.
- `--wait-limit SECONDS` or `lock_wait_seconds` caps the wait. When the limit runs out first, the job
  fails with `finalize.job_running`, and the message names the job that still holds the lock. Without a
  limit, the job waits for as long as the holder runs.
- The MCP call returns at once. Poll `get_finalize_job`, or pass `wait_seconds` (0 to 150) to get the
  result in the same call when the job finishes in time. The CLI blocks until the job is terminal.

## Unreal import: retries and the PIE preflight

Two checks run around each `import_ue` request, so a busy editor does not fail a run that would have
succeeded a moment later.

**Retries.** A request that the editor does not answer within the 120 s request timeout is retried. Before
each retry the pipeline waits 20 s × the retry number, pings the editor with a 10 s timeout, and re-sends
the same import code only once the ping answers. The default is 4 retries. An import result records
`attempts`, the number of attempts it took. When every attempt times out, the step fails with
`import_ue.failed`, and the message gives the number of attempts and the seconds waited. Only timeouts are
retried. HTTP errors, an unreachable editor (`mcp.unreal.unreachable`), and failures the editor reports
are not retried.

A re-sent import is safe. The import template replaces existing textures and meshes and reuses existing
material instances, so a retried import leaves one asset, not a duplicate. The pivot check runs once, on
the reply that succeeded.

**PIE preflight.** Before each variant's import, finalize asks the editor whether it is in Play In Editor
(PIE). That check has a 10 s timeout, and a check that times out counts as busy. `pie_mode` decides what
happens while PIE is on:

- `wait` (the default) checks every 5 seconds until PIE ends, for up to `pie_wait_seconds` (600 by
  default). On the CLI, `--pie wait` and `--pie-wait-limit`.
- `refuse` fails at once.

Either way, PIE still on at the limit fails with `import_ue.editor_busy`. No import request is sent while
PIE is reported.

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
| `material_variants_path` | Optional `<Name>.material-variants.json`. Found beside `blend` when omitted (see the tools section). |
| `device` | `GPU` (default) or `CPU` for the bake. |
| `compatible_with` | Optional `<Category>/<Name>` characters whose skeleton the clips may also play on (see [Animation clips](#animation-clips)). |

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
| `export_anims` | Blender, read-only | `checkpoint.blend` (the session's current actions) to `Animations/A_<Name>_<Clip>.fbx` and `nmg-animations.json` | One FBX per clip, cached per clip. Fails with `finalize.clip_name_invalid` |
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

## reduce_asset (#139)

`reduce_asset` reduces a generated collection to its class's Desktop triangle budget and bakes its
look onto the reduced mesh. It runs as a background job, like finalize, and shares its lock, status,
and `get_finalize_job`. The originals move to the hidden `<Name>_High` collection, which finalize
never reads. The reduced `<Name>` then passes `finalize_asset` with no reduce-specific arguments.

| Input | Meaning |
|-------|---------|
| `collection` | The asset's collection `<Name>`, PascalCase. |
| `asset_class` | `small_prop`, `standard_prop`, `hero_prop`, `character`, or `environment_piece`. Any other value, including `terrain`, is refused with `reduce.class_unsupported`. |
| `blend` | Optional saved `.blend` to reduce instead of the open session. |
| `budgets_path` | Optional `nmg-budgets.json`. Defaults to the project's file when it exists. |
| `device` | `GPU` (default) or `CPU`. |
| `cage_extrusion` | Asset-wide bake cage in metres. Default 0.03. |
| `max_ray_distance` | Asset-wide bake ray distance in metres. Default 0.10. |
| `miss_threshold` | Largest unbaked share per part, from 0 to 1. Default 0.01. |
| `parts` | Per-part overrides keyed by object name: `share` (above 0, at most 1) or `tris` (at least 1), plus optional `cage_extrusion` and `max_ray_distance`. A part takes `share` or `tris`, never both. |
| `wait_seconds` | Clamped to 0–150. A value of 0 returns the job id at once. |

The result has the same shape from the MCP tool, the CLI (`python -m nmg_game_dev.finalize reduce`),
the panel operator, and `reduce_core.run_for_mcp`. It holds `state` (`reduced` or `within_budget`),
the per-part `parts` table with source, target, and final triangles, the cage and ray values each
part used, `unbaked_share`, the texture paths, a one-line `summary`, and for a job `kind: "reduce"`,
`loaded_back`, and `result_blend`. The full description is in
[`docs/skills/reduce-to-budget.md`](../skills/reduce-to-budget.md).

A session run loads the reduced `<Name>` and `<Name>_High` back into Blender only when the session's
`<Name>` still matches the checkpoint. Otherwise the job fails with `reduce.session_changed`.

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
`checkpoint.blend`, `<step>.json`, `<step>.blend`, and `blender-<step>.log`. A batch keeps its items in
`items/<index>-<collection>/`, and its `job.json` holds the item list. One job runs per cache root at a
time. A second start fails with `finalize.job_running` unless it waits for the lock (see
[Waiting for the lock](#waiting-for-the-lock)). A batch is one job, so its items hold the lock together.

## Cache behavior

Each step has a content-addressed cache key:

- `input_hash` is the asset's content hash for the first step, and the previous step's output hash
  after that. The asset hash covers the mesh, materials, images, and transforms of `<Name>` and its
  Mobile collection.
- `settings_hash` covers the asset class, the resolved budget, the device (bake only), the export
  root (export and import only), the category, and the step version. `validate` and `export` also cover
  the material-variants declaration and the bytes of each base-colour texture it names, so editing a
  variant reruns those two steps and leaves `bake` and `variants` cached.

An alias index under `runs/` maps the asset hash to each step's key. A rerun with no change finds
every step in the cache, reports `cache_hit: true` for each, and skips `import_ue`. Load-back is
skipped too, because the session already holds the result. The post-load-back hash is also recorded,
so the rerun after load-back is also a full hit.

A change to any mesh, material, or image misses the cache from the first affected step onward. Steps
before it still hit. `--force` (or `force` on the tools) ignores the cache and reruns every step.

The wait options and the PIE options (`pie_mode`, `pie_wait_seconds`) are not part of any cache key, so
changing them reuses every cached step. Each batch item is cached under its own asset hash, exactly as a
single collection is.

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
| `NMG_GAME_DEV_UE_RETRIES` | `4` | Retries for an `import_ue` request that times out. Zero disables retries |
| `NMG_GAME_DEV_UE_RETRY_DELAY_S` | `20` | Base delay in seconds. The wait before retry *k* is this value × *k* |

Blender is resolved in this order: `BLENDER_BIN`, then `BLENDER_APP/Contents/MacOS/Blender`, then
`/Applications/Blender.app/Contents/MacOS/Blender`. If none is executable, the job fails with
`finalize.blender_not_found`.

## Error codes

| Code | Meaning | Remediation |
|------|---------|-------------|
| `finalize.session_changed` | `<Name>` changed in the session after the checkpoint, so load-back was refused. The export, reimport, and `import_ue` steps still ran. | Read the result `.blend` named in the message. Revert or re-author the session changes, then rerun finalize to load the result back. |
| `reduce.session_changed` | `<Name>` changed in the session during a reduce job, so the reduced asset was not loaded back. The result `.blend` is named in the message. | Open the result `.blend`, or revert the session changes and rerun `reduce_asset`. |
| `reduce.bake_misses` | A part's unbaked share is above `miss_threshold`. The scene is unchanged. | Raise `max_ray_distance` or `cage_extrusion` for the part named in the message, then rerun. |
| `reduce.invalid_request` / `reduce.invalid_override` | An argument or a per-part override is invalid. Nothing starts. | Fix the argument or override named in the message, then rerun. |
| `reduce.<code>` | Any other reduce refusal, such as `reduce.rigged`, `reduce.class_unsupported`, or `reduce.overrides_exceed_budget`. | See the error table in [`docs/skills/reduce-to-budget.md`](../skills/reduce-to-budget.md#errors). |
| `finalize.job_crashed` | A background Blender process exited before its step finished. The step is named in the error. | Read `blender-<step>.log` in the job directory. Fix the cause and rerun. The open session is unchanged. |
| `finalize.job_running` | Another finalize job holds the lock for this cache root. With `wait_for_lock`, the wait limit ran out first. The message names the job that holds the lock. | Rerun with `wait_for_lock` (CLI `--wait`) so finalize waits for the lock. If the holder is stuck, check it with `get_finalize_job` and stop its process. |
| `finalize.invalid_batch` | A batch entry is invalid, or the batch file is not a JSON array. The message gives each invalid entry's zero-based index and reason. Nothing was started. | Fix each listed entry, then rerun the batch. |
| `finalize.batch_failed` | One or more collections in the batch failed, and the rest may have been skipped. The message gives the counts. | Read each failed collection's `error` in `result.batch`, fix it, then rerun the batch. Collections that already passed are cache hits. |
| `import_ue.editor_busy` | The editor was in Play In Editor past the PIE wait limit, or `pie_mode` was `refuse`. No import request was sent. | Stop the Play In Editor session, then rerun finalize. |
| `finalize.job_not_found` | No job has that id in this cache root. | Use the `job_id` that `finalize_asset` or `run_finalize_step` returned. |
| `finalize.invalid_request` | `category` or `asset_class` is omitted, and no asset entry in `docs/design/backlog.json` supplies it. The message names the argument and the backlog path. | Pass the argument, or add the asset's design doc, run `python -m nmg_game_dev.design sync`, then rerun. |
| `finalize.blender_not_found` | No Blender executable at `BLENDER_BIN`, `BLENDER_APP`, or `/Applications/Blender.app`. | Set `BLENDER_BIN` to the Blender executable, or `BLENDER_APP` to the app bundle, then rerun. |
| `finalize.collection_not_found` | The session, or `--blend`, has no collection named `<Name>`. | Check that the collection name matches `--collection` and is PascalCase. |
| `quality.contract_failed` | A contract report failed. Its findings name each rule and target. A `material_variant.*` finding names the variant and the rule. | Fix each finding in Blender, or in `<Name>.material-variants.json`, using `docs/asset-contract.md`, then rerun. |
| `finalize.material_variants_not_found` | The `material_variants_path` does not exist. | Pass the path of an existing declaration, or omit it to use the one beside the `.blend`. |
| `validate.material_variant.declaration_invalid` | The material-variants file is not valid JSON, or does not match the format in `docs/asset-contract.md` section 4. | Fix the file, then rerun. |
| `finalize.material_variants_failed` | Unreal could not list the material variants. The UE error is in the message. | Confirm the editor is idle and the asset is in Content, then rerun `list_material_variants`. |
| `quality.reimport_mismatch` | An exported FBX re-imported differently from its pre-export report. | Read the re-import report in the job directory, fix the export cause, then rerun. |
| `bake.texture.bake_failed` | A texture bake failed. | Read `blender-bake.log` and fix the material it names, then rerun. |
| `variants.<code>` | Variant generation failed. The code names the cause. | Read the message, fix the mesh or material it names, then rerun. |
| `import_ue.failed` | The Unreal import call failed, or the editor did not answer any attempt. The message gives the attempts and seconds when every retry timed out. | Check the editor Output Log for the import, then rerun `import_ue`. For timeouts, make sure the editor is responsive. `NMG_GAME_DEV_UE_RETRIES` and `NMG_GAME_DEV_UE_RETRY_DELAY_S` change the retry limits. |
| `import_ue.pivot_mismatch` | A child part's local bounds differ from the Blender part by more than 0.01 cm. | Fix the pivot in Blender, then rerun finalize with `--force` so the UE content is reimported. |
| `finalize.clip_name_invalid` | A clip's action name does not match `^[A-Za-z][A-Za-z0-9_]*$`. The message names it. Nothing was exported. | Rename the action to start with a letter and use only letters, digits, and underscores, then rerun. |
| `finalize.skeleton_not_found` | `import_anims` found no Desktop skeleton for the character, or a `compatible_with` target has none. Nothing was imported or registered. | For the character, run `import_ue` first, then rerun. For a target, finalize that character first, or remove it from `compatible_with`. |
| `finalize.skeleton_mismatch` | A `compatible_with` target's bone names differ from this character's. The message lists the differing bones. Nothing was registered. | Only register characters rigged with the same bone names. |
| `import_anims.clip_mismatch` | A clip's AnimSequence has a different skeleton or frame count from the sidecar. The message names the clip, the expected value, and the measured value. | Re-export the clip, then rerun `import_anims` with `force`. |
| `import_anims.failed` | The Unreal import call for the clips failed, or a non-AnimSequence asset was created. | Check the editor Output Log, confirm the clip FBX files exist, then rerun `import_anims`. |
| `mcp.blender.unreachable` | The Blender MCP session on `BLENDER_MCP_PORT` is not reachable. | Run `scripts/start-blender-mcp.sh`, then rerun. |
| `mcp.unreal.unreachable` | The Unreal MCP endpoint on `UE_MCP_PORT` is not reachable. | Run `scripts/start-unreal-mcp.sh`, then rerun `import_ue`. |

## import_audio

`import_audio` is a fourth tool on this server, and it is not a finalize step. It stores a saved sound
file, the output of the official ElevenLabs MCP server, as a 16-bit WAV under `SourceArt/Audio/`. It
then imports that WAV into Unreal as a SoundWave at `/Game/Audio/<SFX|Music>/SW_<name>`. It runs
synchronously and returns the result at once, with no job to poll. The CLI, `python -m
nmg_game_dev.audio import`, runs the same function. The flow, the formats, the result fields, and the
error codes are in [elevenlabs.md](elevenlabs.md).

Its errors come back as `{"error": {"code", "message", "remediation", "stage"}}`, with the `audio`
stage and the codes `audio.invalid_request`, `audio.unsupported_format`, `audio.asset_exists`,
`audio.decode_failed`, and `audio.import_failed`. An unreachable Unreal endpoint is not an error:
the result carries `imported_to_unreal: false` and a `warning` with `mcp.unreal.unreachable`.

## Versions

Blender 5.2 LTS, UE 5.8, the Blender MCP server, and VibeUE all track their latest releases, as in
`docs/mcp/blender.md` and `docs/mcp/unreal.md`. Nothing here pins a version.
