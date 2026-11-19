# Finalize MCP: finalize an authored asset

The `finalize` MCP server and the `python -m nmg_game_dev.finalize` CLI run one implementation.
It takes a collection the agent authored in Blender and makes it shippable: validate it against
`docs/asset-contract.md`, bake its materials, build Desktop and Mobile variants, export, re-verify
with a fresh headless re-import, load the baked result back into the open session, and import both
variants into the consumer's Godot project with `godot --headless`. Blender work runs in background headless Blender, so an MCP call never runs a
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
| `finalize_asset` | Either `collection` and `export_root`, or `requests` (a batch, exclusive with `collection`). Optional: `category`, `asset_class`, `blend`, `budgets_path`, `material_variants_path`, `compatible_with`, `force`, `wait_seconds`, `fail_fast`, `skip_up_to_date` (batch only, see [Finalize records](#finalize-records-and-the-up-to-date-check-247)), `wait_for_lock`, `lock_wait_seconds` | `{"job_id", "status"}`, plus `result` (a batch's result is `result.batch`) when the job finishes within `wait_seconds`, or `error` when it fails |
| `run_finalize_step` | `step` (one of the eight step names), then the same inputs as `finalize_asset` for one collection, plus `wait_for_lock`, `lock_wait_seconds` | The same shape as `finalize_asset`, for one step |
| `reduce_asset` | `collection`, `asset_class`, optional `blend`, `budgets_path`, `device`, `cage_extrusion`, `max_ray_distance`, `miss_threshold`, `parts`, `wait_seconds` | `{"job_id", "status"}`, plus `result` when the job finishes within `wait_seconds`. See [reduce_asset](#reduce_asset-139). |
| `get_finalize_job` | `job_id` | `{"job_id", "state", "step", "progress", "message", "batch"?, "result"?, "error"?, "warnings"?}` |
| `check_finalized` | One `category` and `collection`, or `assets` (a list of `{category, collection}`, exclusive with them), optional `export_root` | `{"assets": [...]}`, one `{category, collection, up_to_date, reason, record}` per asset, where `record` is `{state, ended_at, error_code}` or `null`. Reads the record only. See [Finalize records](#finalize-records-and-the-up-to-date-check-247) |
| `list_material_variants` | `category`, `collection`, optional `export_root` | A list of `{"name", "material", "desktop", "mobile"}` rows, sorted by material then name; `[]` when the asset has no material variants |
| `import_audio` | `file`, `name`, `kind` (`sfx` or `music`), optional `loop`, `max_seconds`, `loudness_lufs`, `loop_crossfade_ms`, `finish` | The audio import result, with `refreshed_tables`. See [elevenlabs.md](elevenlabs.md) |
| `refresh_audio_table` | optional `project` (default `CLAUDE_PROJECT_DIR`, else the working directory) | `{"refreshed_tables": [...]}`, the project-relative Audio name tables whose text changed. See [refresh_audio_table](#refresh_audio_table-237) |
| `game_screenshot` | `path`, optional `after` (0 to 60 seconds, default 3), optional `options` (launch options for the game) | `{"path", "width", "height"}` for the saved PNG. See [game_screenshot](#game_screenshot-251) |

`material_variants_path` names the asset's `<Name>.material-variants.json` declaration. Without it, a
`--blend` run uses the file beside the blend when one exists. A session run has no blend, so it declares
no material variants unless the path is given. In a batch, each `requests` entry sets its own
`material_variants_path` and `compatible_with`; those top-level parameters apply to one collection only. A path that does not
exist returns `finalize.material_variants_not_found`. The format and the rules are in `docs/asset-contract.md` section 4.
During `import_godot`, finalize writes one `M_<Name>_<Part>_<Variant>.tres` material per declared
variant into each variant folder and records it as `material_resource` in `nmg-variants.json`.

`list_material_variants` reads only `<export_root>/<Category>/<Name>/nmg-variants.json`, where
`export_root` defaults to `$CLAUDE_PROJECT_DIR/game/assets`. It never starts Godot. Each row gives the
variant's material slot and the `res://` path of its `.tres` in each variant folder, or `null` for a
folder that does not hold it. A missing or invalid sidecar returns `finalize.material_variants_failed`
in the `error` object.

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
python -m nmg_game_dev.finalize {all,validate,bake,variants,export,export_anims,reimport,import_godot,import_anims} \
  (--collection Crate [--collection Barrel ...] | --batch FILE) --export-root <dir> \
  [--category Props] [--class standard_prop] [--blend B] [--budgets P] [--material-variants P] \
  [--device GPU|CPU] [--compatible-with Category/Name ...] [--force] [--fail-fast] \
  [--wait [--wait-limit S]] [--json]

python -m nmg_game_dev.finalize material-variants --category Props --collection Crate \
  [--export-root <dir>] [--json]

python -m nmg_game_dev.finalize check --category Props --collection Crate \
  [--export-root <dir>] [--json]
```

`--export-root` is required with `--collection`. A `--batch` entry may set its own.
`--material-variants` applies to a single `--collection`; a `--batch` entry sets `material_variants_path`.
`--compatible-with` may repeat, once for each character named in [Animation clips](#animation-clips).
Like `--material-variants`, it applies to a single `--collection`; a `--batch` entry sets `compatible_with`.

`material-variants` prints the rows that `list_material_variants` returns, one line per variant, or the
JSON array with `--json`. It reads files only, so it needs neither Blender nor Godot.

| Exit | Meaning |
|------|---------|
| `0` | Success. With `--json`, stdout is the result |
| `1` | A step or a collection failed, or `check` found the asset not up to date. stderr shows `ERROR [code] message` and `Remediation: ...`. A batch prints one line per collection |
| `2` | A prerequisite is missing (`finalize.blender_not_found`, `godot.not_found`, or `mcp.blender.unreachable`), or the arguments are wrong (for `check`, a name that is not PascalCase) |

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
`collection`. The top-level `category`, `asset_class`, `export_root`, `blend`, and `budgets_path` fill
in any key an entry omits.

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

**Skipping up-to-date items.** With `--skip-up-to-date` (CLI) or `skip_up_to_date: true` (MCP, with `requests`), an item that passes the [up-to-date check](#finalize-records-and-the-up-to-date-check-247) runs no step. Its state is `up_to_date`, its record is left as it was, and it is counted under `result.batch.up_to_date`. It does not count as a failure. Without the option every item runs. The option applies to a batch only: one `collection` with it fails with `finalize.invalid_request`.

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

## Godot import

`import_godot` and `import_anims` run Godot headless through `godot --headless --audio-driver Dummy
--path <project>`. There is no editor to wait for, no live-editor bridge, and no retry loop: a
failure is reported at once with its code.

1. **Binary.** Godot is resolved from `GODOT_BIN` (it must be executable), then `godot` on `PATH`,
   then `/Applications/Godot.app/Contents/MacOS/Godot`. Otherwise the step fails with
   `godot.not_found`. Godot 4 tracks its latest stable release and is never pinned.
2. **Project.** The Godot project is the nearest folder at or above `export_root` that holds
   `project.godot`; in a consumer project that is `game/`, with `export_root` `game/assets`. None
   fails with `import_godot.project_missing`.
3. **Import.** `godot --headless --path game --import` imports the new files. A non-zero exit, or any
   output line that starts with `ERROR:`, fails with `import_godot.import_failed`, and the message
   holds the first such line.
4. **Probe.** A GDScript probe (`extends SceneTree`, run with `-s`) loads each variant's `.glb` and
   prints one `NMG_RESULT {json}` line: every `MeshInstance3D`'s name, triangle count, material
   slots, and bounds. Finalize compares it with the variant's `nmg-asset.json`. Any difference in
   names, triangles, or slots, or bounds off by more than 1 mm, fails with `import_godot.mismatch`,
   which names the mesh and the field.

## Request

Every entry point takes one `FinalizeRequest`:

| Field | Meaning |
|-------|---------|
| `collection` | The asset's collection name `<Name>`, PascalCase. The session (or `--blend`) must hold it. |
| `category` | Optional. The asset category, PascalCase. Files land in `<export_root>/<Category>/<Name>/`, which is `res://assets/<Category>/<Name>/` in Godot. When omitted, taken from the design backlog. |
| `asset_class` | Optional. One of `small_prop`, `standard_prop`, `hero_prop`, `character`, `environment_piece`, or `terrain`. Sets the texture sizes and the material limit. For `terrain`, it sets the heightmap size and the layer limit. When omitted, taken from the design backlog. |
| `export_root` | Folder that receives `<Category>/<Name>/Desktop/` and `<Category>/<Name>/Mobile/`. In a consumer project it is `game/assets`, inside the Godot project. |
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

Finalize runs the steps in this order, validate → bake → variants → export → export_anims → reimport →
import_godot → import_anims, and each step can also run alone:

| Step | Runs in | Reads and writes | Gate or output |
|------|---------|------------------|----------------|
| `validate` | Blender, read-only | Checkpoint | Contract report, gated by `quality.contract_failed` |
| `bake` | Blender, writes a copy | Checkpoint to `bake.blend` | Contract texture sets and the bake proof |
| `variants` | Blender, writes a copy | `bake.blend` to `variants.blend` | Triangle counts per variant |
| `export` | Blender, read-only | `variants.blend` to `<Variant>/<Name>.glb`, the PNG sets, both `nmg-asset.json` files, and `nmg-variants.json` | Pre-export contract report, gated by `quality.contract_failed` |
| `export_anims` | Blender, read-only | `checkpoint.blend` (the session's current actions) to `Animations/A_<Name>_<Clip>.glb` and `nmg-animations.json` | One `.glb` per clip, cached per clip. Fails with `finalize.clip_rig_mismatch`, `finalize.clip_name_duplicate`, or `finalize.clip_name_invalid` before any file is written |
| `reimport` | Blender, factory startup | Exported `.glb` files | Re-import report per variant, gated by `quality.reimport_mismatch` |
| `import_godot` | Godot, headless | Material-variant `.tres` files, then `--import` and the asset probe | Outputs `desktop_resource_path` and `mobile_resource_path` (`res://assets/<Category>/<Name>/<Variant>/<Name>.glb`) and the probe results under `imports`. Fails with `godot.not_found`, `import_godot.project_missing`, `import_godot.import_failed`, or `import_godot.mismatch` |
| `import_anims` | Godot, headless | Each changed clip's `.import` file (`importer="animation_library"`), then `--import` and the animation probe | Clip and frame-count check against the sidecar, failing with `import_anims.clip_mismatch` or `import_anims.failed`. Compatible-skeleton report |

`export_anims` runs after `export`, and `import_anims` runs after `import_godot`. `finalize all` runs
both. Load-back sits between `reimport` and `import_godot`. It is not a step in its own right.

A character without clips passes through both animation steps. Each reports zero clips, writes
nothing under `Animations/`, and starts no Godot process. Every other output is the same as before.

### Animation clips

`export_anims` exports every clip on `SK_<Name>`, which is the rig's provenance clips plus the actions
held in its slot or NLA tracks. Unrelated actions in the file are not exported. A clip's name is its
action's name minus an optional `@SK_<Name>` suffix, so one .blend can hold several characters that
each have an `Idle` (`docs/asset-contract.md`, section 7).

- **Layout.** `<export_root>/<Category>/<Name>/Animations/A_<Name>_<Clip>.glb` holds one clip each.
  `<Clip>` is the bare clip name.
  Each file holds the armature only, no mesh, and exactly one action, sampled on every frame.
- **Sidecar.** `nmg-animations.json` sits beside the clip files. The top level holds `asset` and
  `armature`. Each entry in `clips` holds `name`, `file`, `asset_path`, `frame_start`, `frame_end`,
  `frame_count`, `fps`, and `source`. The `source` is the provenance `source` dict (`library`,
  `file`, `sha256`, `skeleton`), or `"authored"` for a clip with no provenance.
- **Import.** For each changed clip, `import_anims` writes `A_<Name>_<Clip>.glb.import` with
  `importer="animation_library"`, runs the headless import, and runs a probe that loads each clip as
  an `AnimationLibrary`. The probe reports each clip's animation and its frame count
  (`round(length * fps)`). A wrong or absent clip fails with `import_anims.clip_mismatch`, which
  names the clip, the expected value, and the measured value. A probe failure fails with
  `import_anims.failed`.
- **Compatible skeletons.** With `compatible_with`, every bone track in each clip must exist in each
  compatible character's Desktop skeleton. The probe reads the `Skeleton3D` bone names from that
  character's Desktop `.glb`. A missing character fails with `finalize.skeleton_not_found`, and a
  missing bone fails with `finalize.skeleton_mismatch`, which lists the bones. The result lists the
  checked characters under `compatible`.

The result's `animations` entry carries the clips (each with `name`, `asset_path`,
`export_cache_hit`, and `import_cache_hit`) and `compatible`. It is `null` when no clip step ran.

`run_finalize_step` returns a result with `step`, `cache_hit`, `outputs`, and `summary`. When a step
fails, no later step runs, and nothing is imported into Godot.

## Terrain

`asset_class` `terrain` runs the same steps. Five of them do different work, and each variant becomes
chunked `.glb` meshes plus a `.tscn` scene with heightmap collision. The rules are in
`docs/asset-contract.md` section 9.

| Step | Terrain |
|------|---------|
| `validate` | Runs the `terrain.*` rules and the texel density check in place of the mesh and budget checks. The validation report gains a `terrain` object |
| `variants` | Derives the Mobile heightmap and layer set from the Desktop grid. No `_Mobile` collection is created |
| `export` | Writes `<Name>_Chunk_<row>_<col>.glb` chunks of 63 quads, the RGBA splat map, the layer textures, and the 16-bit heightmap. Writes `nmg-variants.json` with `"terrain": true`, and `nmg-asset.json` in both variant folders |
| `reimport` | Decodes each variant's PNGs and checks them against the pre-export heights. Its findings use the rule `reimport.terrain` |
| `import_godot` | Writes `<Variant>/<Name>.tscn`: every chunk instanced under a `Node3D`, the splat `ShaderMaterial`, and a `StaticBody3D` with `HeightMapShape3D` collision built from the same heightfield. Godot generates the chunk LODs on import. The terrain probe checks the collision and chunk height ranges against the sidecar within 5 cm (`import_godot.terrain_height_mismatch`); a missing chunk fails with `import_godot.mismatch` |

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
   The `export`, `reimport`, and `import_godot` steps still run, because they use the job's files and
   not the session.
5. **Crash.** If a background process exits before its step finishes, the job fails with
   `finalize.job_crashed` naming the step. The open session is unchanged.

Job files live under `<cache_root>/jobs/<job_id>/`: `request.json`, `status.json`,
`checkpoint.blend`, `<step>.json`, `<step>.blend`, and `blender-<step>.log`. A batch keeps its items in
`items/<index>-<collection>/`, and its `job.json` holds the item list. One job runs per cache root at a
time. A second start fails with `finalize.job_running` unless it waits for the lock (see
[Waiting for the lock](#waiting-for-the-lock)). A batch is one job, so its items hold the lock together.

## Finalize records and the up-to-date check (#247)

Each finished run (`succeeded` or `failed`) writes a record of its result inside the consumer project, so a
queue runner can find an asset's last run by name and skip the ones that are done.

**Location.** `<consumer>/.nmg/finalize/<Category>/<Name>.json`, where `<consumer>` is the parent of the
directory that holds `project.godot` (for a consumer project, the project root above `game/`). The record
is written atomically, and it replaces the previous record for the same asset. The consumer's
`.gitignore` ignores `.nmg/`, which `/onboard-consumer` adds.

**Fields.** `schema_version` (1), `category`, `collection`, `job_id`, `state` (`succeeded` or `failed`),
`started_at` and `ended_at` (UTC, ISO 8601), `nmg_game_dev_version`, `full_run` (true when the run was every
step), `steps` (each with `step` and `cache_hit`), `source` (`{"blend", "mtime"}` for a saved `.blend`,
`mtime` read when the run started, or `null` for the open session), `imported` (the `res://` paths of the
Desktop and Mobile variants and of each animation clip the run imported), `content_hash` (the asset's
content hash when the run recorded one, or `null`), `logs`, and `error` (`code`, `message`,
`remediation`, `stage`, or `null`).

**Logs.** `<consumer>/.nmg/finalize/<Category>/<Name>.logs/` holds a copy of the run's `job.log` and of each
`blender-<step>.log`. `logs` in the record names them, relative to the record's folder. The copies stay after
the job directory under the cache root is deleted. The next run of the asset replaces the whole `<Name>.logs/`
folder, so it only ever holds the latest run's logs. In a batch, each item's record and logs are written
before the next item starts, and an item skipped by fail-fast leaves its earlier record unchanged.

**Check.** `python -m nmg_game_dev.finalize check --category Props --collection Crate` prints
`Props/Crate: up to date`, or `Props/Crate: not up to date (<reason>)`. With `--json` it prints
`{"category", "collection", "up_to_date", "reason", "record"}`. It exits `0` when the asset is up to date,
`1` when it is not, and `2` for a name that is not PascalCase. The MCP tool `check_finalized` takes one
`category` and `collection`, or an `assets` list, and returns `{"assets": [...]}`. Each entry has `category`,
`collection`, `up_to_date`, `reason`, and `record` (`state`, `ended_at`, `error_code`, or `null` without a
record). `export_root` defaults to `<project>/game/assets` in both forms.

An asset is up to date when all of these hold, checked in this order:

1. Its record exists and parses. The rule stops at the first failure below.
2. The last run succeeded (`state: succeeded`).
3. The last run was a full run (`full_run: true`).
4. The record names a source `.blend` (`source` is not `null`).
5. That `.blend` exists.
6. The `.blend` was last modified no later than the run started.
7. Every `res://` path in `imported` exists under the Godot project, and its `.import` file sits beside it.

Each failure gives one reason: `project_missing` (no Godot project holds `export_root`), `no_record`,
`record_unreadable` (the file is not valid JSON or does not match the record format), `last_run_failed`,
`not_full_run`, `no_source_blend`, `source_missing`, `source_newer` (the `.blend` changed after the run began),
or `import_missing`. A passing check gives `up_to_date` with the reason `up_to_date`.

The check reads only the record and file metadata. It does not start Blender or Godot, does not take the cache
lock, and writes nothing, so it answers while another finalize job runs.

**Caveat.** The check compares modification times, not content. A `.blend` saved with no change to its
content reports `source_newer` and is not up to date. A rerun of that asset is then a full cache hit, because
the step cache keys on content, so it finishes quickly with every step served from cache.

**How it differs from the step cache.** The step cache (see [Cache behavior](#cache-behavior)) decides what a run
recomputes: each step is reused when its inputs are unchanged. The up-to-date check decides whether a run is
needed at all, from the last record. The check is cheap and reads no cache, so it suits a queue runner that
skips finished assets. The step cache still decides what a rerun costs.

**Batch skip.** `skip_up_to_date` (CLI `--skip-up-to-date`, MCP `finalize_asset` with `requests`) runs the same
check before each item, and skips the items that pass it. See [Batches](#batches).

## Cache behavior

Each step has a content-addressed cache key:

- `input_hash` is the asset's content hash for the first step, and the previous step's output hash
  after that. The asset hash covers the mesh, materials, images, and transforms of `<Name>` and its
  Mobile collection.
- `settings_hash` covers the asset class, the resolved budget, the device and the bake version (bake
  only), the export root (export and import only), the category, and the step version. `validate` and
  `export` also cover the material-variants declaration and the bytes of each base-colour texture it
  names, so editing a variant reruns those two steps and leaves `bake` and `variants` cached.

An alias index under `runs/` maps the asset hash to each step's key. A rerun with no change finds
every step in the cache, reports `cache_hit: true` for each, and skips `import_godot`. Load-back is
skipped too, because the session already holds the result. The post-load-back hash is also recorded,
so the rerun after load-back is also a full hit.

A change to any mesh, material, or image misses the cache from the first affected step onward. Steps
before it still hit. `--force` (or `force` on the tools) ignores the cache and reruns every step.

The wait options are not part of any cache key, so changing them reuses every cached step. The
`import_godot` key covers the collection, the category, and the export root. The step version is part
of every key, so no cache entry written before Godot became the engine can satisfy `import_godot`. Each batch item is cached under its own asset hash, exactly as a
single collection is.

The two animation steps are cached per clip, not as a whole, and they do not change the input hash
of the steps after them:

- **Export.** A clip's key covers its content hash (keyframes through the action's slots, the rig's
  bones and rest pose, the provenance entry, and the scene frame rate) and the export settings. A
  change to `Walk` re-exports only `Walk`. `Idle` is served from cache and is not re-exported.
- **Import.** A clip's key covers its exported output and the character's Desktop variant. A clip
  whose key is unchanged is served from cache and is not re-imported, so changing `Walk` re-imports
  only `Walk`.
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
| `GODOT_BIN` | unset | Godot 4 executable for `import_godot` and `import_anims`. Wins when it is executable; otherwise `godot` on `PATH`, then `/Applications/Godot.app` |
| `FFMPEG_BIN` | unset | ffmpeg executable for music imports in `import_audio`. Wins when it is executable; otherwise `ffmpeg` on `PATH` |

Blender is resolved in this order: `BLENDER_BIN`, then `BLENDER_APP/Contents/MacOS/Blender`, then
`/Applications/Blender.app/Contents/MacOS/Blender`. If none is executable, the job fails with
`finalize.blender_not_found`.

## Error codes

| Code | Meaning | Remediation |
|------|---------|-------------|
| `finalize.session_changed` | `<Name>` changed in the session after the checkpoint, so load-back was refused. The export, reimport, and `import_godot` steps still ran. | Read the result `.blend` named in the message. Revert or re-author the session changes, then rerun finalize to load the result back. |
| `reduce.session_changed` | `<Name>` changed in the session during a reduce job, so the reduced asset was not loaded back. The result `.blend` is named in the message. | Open the result `.blend`, or revert the session changes and rerun `reduce_asset`. |
| `reduce.bake_misses` | A part's unbaked share is above `miss_threshold`. The scene is unchanged. | Raise `max_ray_distance` or `cage_extrusion` for the part named in the message, then rerun. |
| `reduce.invalid_request` / `reduce.invalid_override` | An argument or a per-part override is invalid. Nothing starts. | Fix the argument or override named in the message, then rerun. |
| `reduce.<code>` | Any other reduce refusal, such as `reduce.rigged`, `reduce.class_unsupported`, or `reduce.overrides_exceed_budget`. | See the error table in [`docs/skills/reduce-to-budget.md`](../skills/reduce-to-budget.md#errors). |
| `finalize.job_crashed` | A background Blender process exited before its step finished. The step is named in the error. | Read `blender-<step>.log` in the job directory. Fix the cause and rerun. The open session is unchanged. |
| `finalize.job_running` | Another finalize job holds the lock for this cache root. With `wait_for_lock`, the wait limit ran out first. The message names the job that holds the lock. | Rerun with `wait_for_lock` (CLI `--wait`) so finalize waits for the lock. If the holder is stuck, check it with `get_finalize_job` and stop its process. |
| `finalize.invalid_batch` | A batch entry is invalid, or the batch file is not a JSON array. The message gives each invalid entry's zero-based index and reason. Nothing was started. | Fix each listed entry, then rerun the batch. |
| `finalize.batch_failed` | One or more collections in the batch failed, and the rest may have been skipped. The message gives the counts. | Read each failed collection's `error` in `result.batch`, fix it, then rerun the batch. Collections that already passed are cache hits. |
| `finalize.job_not_found` | No job has that id in this cache root. | Use the `job_id` that `finalize_asset` or `run_finalize_step` returned. |
| `finalize.invalid_request` | `category` or `asset_class` is omitted, and no asset entry in `docs/design/backlog.json` supplies it. The message names the argument and the backlog path. | Pass the argument, or add the asset's design doc, run `python -m nmg_game_dev.design sync`, then rerun. |
| `finalize.record_not_written` | The run finished, but its record or log copies under `<consumer>/.nmg/finalize/` could not be written, or no Godot project holds `export_root`. The run's `state`, `result`, and `error` are unchanged. The warning is in `result.warnings` on success, or in the job's `warnings` on failure. A failed write also removes an older record for the asset, so the check cannot report that older run as current. | Check that `<consumer>/.nmg/finalize` is writable and that `export_root` is inside the Godot project, then rerun the asset. |
| `finalize.blender_not_found` | No Blender executable at `BLENDER_BIN`, `BLENDER_APP`, or `/Applications/Blender.app`. | Set `BLENDER_BIN` to the Blender executable, or `BLENDER_APP` to the app bundle, then rerun. |
| `finalize.collection_not_found` | The session, or `--blend`, has no collection named `<Name>`. | Check that the collection name matches `--collection` and is PascalCase. |
| `quality.contract_failed` | A contract report failed. Its findings name each rule and target. A `material_variant.*` finding names the variant and the rule. | Fix each finding in Blender, or in `<Name>.material-variants.json`, using `docs/asset-contract.md`, then rerun. |
| `finalize.material_variants_not_found` | The `material_variants_path` does not exist. | Pass the path of an existing declaration, or omit it to use the one beside the `.blend`. |
| `validate.material_variant.declaration_invalid` | The material-variants file is not valid JSON, or does not match the format in `docs/asset-contract.md` section 4. | Fix the file, then rerun. |
| `finalize.material_variants_failed` | `nmg-variants.json` for the asset is missing or invalid. The message names the path. | Finalize the asset into that export root first, or pass the `export_root` it was finalized into. |
| `quality.reimport_mismatch` | An exported `.glb` re-imported differently from its pre-export report, or a terrain's PNGs decoded differently from its pre-export heights. | Read the re-import report in the job directory, fix the export cause, then rerun. |
| `bake.texture.bake_failed` | A texture bake failed. | Read `blender-bake.log` and fix the material it names, then rerun. |
| `variants.<code>` | Variant generation failed. The code names the cause. | Read the message, fix the mesh or material it names, then rerun. |
| `godot.not_found` | No Godot binary at `GODOT_BIN`, `godot` on `PATH`, or `/Applications/Godot.app`. | Install Godot 4 (latest stable) or set `GODOT_BIN` to its executable. |
| `import_godot.project_missing` | No `project.godot` at or above `export_root`. | Run `/onboard-consumer` to create `game/project.godot`, or pass an export root inside the Godot project (`game/assets`). |
| `import_godot.import_failed` | The headless `--import` exited non-zero or printed an `ERROR:` line. The first such line is in the message. | Fix the file the error names, then rerun `import_godot`. |
| `import_godot.mismatch` | A probed variant's mesh names, triangles, material slots, or bounds differ from its `nmg-asset.json`, or a terrain chunk is missing. The message names the mesh and the field. | Rerun finalize with `force` so the variant is re-exported and re-imported. |
| `import_godot.terrain_height_mismatch` | A terrain scene's collision or chunk height range differs from the sidecar by more than 5 cm. | Re-export the terrain with `force`. If it persists, check the heightmap encoding and the spacing in `nmg-variants.json`. |
| `finalize.clip_name_invalid` | A clip's bare name (its action name minus any `@SK_<Name>` suffix) does not match `^[A-Za-z][A-Za-z0-9_]*$`. The message names it. Nothing was exported. | Rename the action to start with a letter and use only letters, digits, and underscores, then rerun. |
| `finalize.clip_rig_mismatch` | An action on `SK_<Name>` carries an `@` suffix naming another rig, such as `Idle@SK_Cop` on `SK_StreetThug`. The message names each action. Nothing was exported. | Rename each action to `<Clip>@SK_<Name>` for this rig, or remove the suffix, then rerun finalize. |
| `finalize.clip_name_duplicate` | Two actions on `SK_<Name>` give the same clip name, such as `Idle` and `Idle@SK_<Name>`. The message names the clip and both actions. Nothing was exported. | Keep one action per clip on `SK_<Name>`: delete or rename the extra action, then rerun finalize. |
| `finalize.skeleton_not_found` | `import_anims` found no Desktop skeleton for the character, or a `compatible_with` target has none. | For the character, run `import_godot` first, then rerun. For a target, finalize that character first, or remove it from `compatible_with`. |
| `finalize.skeleton_mismatch` | A clip has a bone track that a `compatible_with` target's skeleton lacks. The message lists the bones. | Only register characters rigged with the same bone names. |
| `import_anims.clip_mismatch` | A clip is absent from its imported `AnimationLibrary`, or its frame count differs from the sidecar. The message names the clip, the expected value, and the measured value. | Re-export the clip, then rerun `import_anims` with `force`. |
| `import_anims.failed` | The clip import or the animation probe failed. | Run `godot --headless --path game --import` and read its errors, confirm the clip `.glb` files exist, then rerun `import_anims`. |
| `mcp.blender.unreachable` | The Blender MCP session on `BLENDER_MCP_PORT` is not reachable. | Run `scripts/start-blender-mcp.sh`, then rerun. |

## import_audio

`import_audio` is a tool on this server, and it is not a finalize step. It stores a saved sound file,
the output of the official ElevenLabs MCP server, as a 16-bit WAV under `SourceArt/Audio/`. A sound
effect is then copied to `game/assets/Audio/<Name>.wav` and imported headless as an `AudioStreamWAV`.
A music track is encoded with ffmpeg to Ogg Vorbis at `game/assets/Audio/<Name>.ogg` and imported
headless as an `AudioStreamOggVorbis`, looping when `loop` is true. It runs synchronously and returns
the result at once, with no job to poll. The CLI, `python -m nmg_game_dev.audio import`, runs the
same function. The flow, the formats, the result fields, and the error codes are in
[elevenlabs.md](elevenlabs.md).

Before import the game copy is finished (trim, cut, loop crossfade, and loudness match), unless
`finish` is `false`. The optional parameters are `max_seconds` (above 0), `loudness_lufs` (from -40
to -5, default -16 for `sfx` and -18 for `music`), `loop_crossfade_ms` (zero or more, default 500),
and `finish` (default `true`). A parameter you leave out, `loop` included, comes from the sound's entry in
`SourceArt/Audio/audio.json`. The result carries `finish`, `settings`, and `refreshed_tables`.

A successful import also refreshes each Audio component's name table (#237), so the sound is in the
table without a separate call. `refreshed_tables` lists the project-relative tables whose text
changed. When the tables cannot be refreshed, because `docs/design/backlog.json` or a table file
cannot be read, or a table cannot be written, the import still succeeds: `refreshed_tables` is
empty and a `refresh_warning` carries the refresh error's code (`audio.backlog_invalid`,
`audio.table_unreadable`, or `audio.table_unwritable`) with its remediation. See [refresh_audio_table](#refresh_audio_table-237).

## refresh_audio_table (#237)

`refresh_audio_table` rebuilds each `game/systems/*/audio_table.tres` that declares
`NmgAudioTable`, from the sounds under `game/assets/Audio/` and the region `music` fields in the
design backlog. It returns `{"refreshed_tables": [...]}`, and writes nothing when the tables are
already current. Its errors, with the `audio` stage, are `audio.godot_project_missing` when
`game/project.godot` is missing, and `audio.backlog_invalid` when `docs/design/backlog.json` is not
a backlog `/design` wrote (rerun `python -m nmg_game_dev.design sync`), `audio.table_unreadable`
when a table file cannot be read, and `audio.table_unwritable` when a table cannot be replaced. A
project with no `NmgAudioTable` returns `{"refreshed_tables": []}` without reading the backlog, and
an `audio_table.tres` whose first line does not declare `NmgAudioTable` (a binary file included)
is left alone. The CLI, `python -m nmg_game_dev.audio refresh [--project DIR]`,
runs the same function. The flow is in [elevenlabs.md](elevenlabs.md#the-audio-component).

Its errors come back as `{"error": {"code", "message", "remediation", "stage"}}`, with the `audio`
stage and the codes `audio.invalid_request`, `audio.unsupported_format`, `audio.asset_exists`,
`audio.decode_failed`, `audio.ffmpeg_not_found`, `audio.import_failed`, and `audio.settings_invalid`.
A missing Godot binary is not an error: the result carries
`imported_to_godot: false` and a `warning` with `godot.not_found`.

## game_screenshot (#251)

`game_screenshot` saves a PNG of the running consumer game, so an asset can be reviewed under the
game's own lighting and materials. It runs `game/project.godot` in a window with your `options` after
`--`, plus `--nmg-test-saves` and `--nmg-shot=<absolute path>`, so `NmgLaunch` writes the root
viewport to `path` after `after` seconds and quits. A relative `path` resolves against the consumer
root. The window needs a display.

```json
{"path": "build/shots/forest.png", "after": 3, "options": ["--at=Forest", "--hour=18"]}
```

On success it returns `{"path", "width", "height"}`, with the absolute path and the size read from the
PNG header. A failure returns `{"error": {"code", "message", "remediation", "stage"}}`:

- `shot.invalid_after`: `after` is outside 0 to 60 seconds.
- `shot.invalid_path`: `path` is a folder, or its folder cannot be created or written to.
- `godot.project_missing`: there is no `game/project.godot`.
- `godot.not_found`: no Godot binary (`GODOT_BIN`, then `godot` on PATH, then `/Applications/Godot.app`).
- `shot.no_image`: the game exited, or ran past `after` plus 60 seconds, without writing the PNG. The
  message carries the game's last 20 output lines.

The CLI, `python -m nmg_game_dev.godot shot <path> [--after S] [-- <options>]`, runs the same capture
and prints the same JSON. The launch options, the smoke run, and the autoload are in
[docs/onboarding/run-and-capture.md](../onboarding/run-and-capture.md).

## Versions

Blender 5.2 LTS, the Blender MCP server, and Godot 4 all track their latest stable releases, as in
`docs/mcp/blender.md`. Nothing here pins a version.
