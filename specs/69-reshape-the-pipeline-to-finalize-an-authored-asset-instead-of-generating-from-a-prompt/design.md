# Design: Reshape the pipeline to finalize an authored asset instead of generating from a prompt

**Issue**: #69
**Date**: 2026-10-30
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/30-add-contract-validation-re-import-check-and-review-renders/

## Overview

`nmg_game_dev.pipeline` becomes a finalize orchestrator. It turns a `FinalizeRequest` into six steps. The Blender steps run in headless Blender through a new add-on package, `finalize_core`, which calls the #30, #67, and #33 cores. The UE step runs host-side through the Unreal MCP. One job model, following #7's texture jobs, serves the CLI (blocking) and the `finalize` MCP server (start + poll). A content-addressed cache and an alias index make reruns of an unchanged asset free.

## Architecture

```
agent ─► finalize MCP (finalize_asset | run_finalize_step | get_finalize_job)
CLI   ─► python -m nmg_game_dev.finalize <all|step> [...]        (blocks; same code path)
          └─► pipeline.jobs.start(request, steps) ─► detached `python -m nmg_game_dev.finalize run-job <job_dir>`
                run-job:
                  1. checkpoint: BlenderSessionClient.execute → save_as_mainfile(copy=True) → <job_dir>/checkpoint.blend
                     (or copy --blend file); session_hash = finalize_core.content_hash(<Name>)
                  2. for each Blender step: cache lookup → else
                     blender --background <in.blend> --python scripts/blender/finalize_entry.py -- <step> --job-dir D
                       └─ finalize_core.run_step(step, request) → contract_core / bake_core / variants_core
                       └─ writes <job_dir>/<step>.json and <job_dir>/<step>.blend (mutating steps)
                  3. load-back (session runs only): BlenderSessionClient.execute → finalize_core.load_back(result.blend, <Name>, expected_hash)
                  4. import_ue: UnrealMcpClient.execute_python_code(unreal/import_asset.py payload)
                  status.json updated after every step (atomic temp + rename)
```

Each Blender step uses its own process, and its input `.blend` is the previous step's output, so a crash only loses that step. The session is touched only at checkpoint (read) and load-back (after every Blender step passed).

### Modules

| Path | Contents |
|------|----------|
| `src/nmg_game_dev/pipeline/__init__.py` | `finalize(request, *, steps=STEP_ORDER, force=False, cache_dir=None, clients=None, runner=None) -> FinalizeResult`; `run_step(step, request, **same) -> StepResult`; `STEP_ORDER = ("validate", "bake", "variants", "export", "reimport", "import_ue")` |
| `pipeline/request.py` | `FinalizeRequest` (pydantic, frozen): `collection` (PascalCase), `category` (PascalCase), `asset_class` (`small_prop` / `standard_prop` / `hero_prop` / `character` / `environment_piece`), `export_root: Path`, `blend: Path \| None`, `budgets_path: Path \| None`, `device: "GPU" \| "CPU" = "GPU"` |
| `pipeline/result.py` | `StepResult(step, cache_hit, outputs, summary)`, `FinalizeResult(steps, desktop_content_path, mobile_content_path, loaded_back, result_blend)` |
| `pipeline/steps.py` | Step table: name → (kind `blender` / `unreal`, mutates_scene, settings builder, gate). `validate` and `reimport` results go through `quality.contract.gate`; other errors map to `PipelineError` codes `<step>.<code>` from core errors |
| `pipeline/cache.py` | `ArtifactCache.key(step, input_hash, settings_hash)`; blobs may be a directory (copied into `by-key/<k>/files/`); `alias(asset_hash) -> run record` / `put_alias(asset_hash, record)` under `runs/` |
| `pipeline/jobs.py` | `start(request, steps, force) -> job_id`, `status(job_id)`, `wait(job_id, timeout)`, `run_job(job_dir)`; lock and stale-PID handling as in #7; crash detection (process gone, state not terminal → `finalize.job_crashed` with the last step) |
| `pipeline/blender_proc.py` | Resolves the Blender binary (`BLENDER_BIN` → `BLENDER_APP/Contents/MacOS/Blender` → `/Applications/Blender.app/...`, else `finalize.blender_not_found`) and runs one headless step, streaming progress lines `NMG_PROGRESS {json}` into `status.json` |
| `pipeline/clients/blender_session.py` | `BlenderSessionClient(host="127.0.0.1", port=$BLENDER_MCP_PORT or 9876)`: `execute(code) -> dict`, which sends `execute_code` and parses a `NMG_RESULT {json}` line from the output; connection failure → `mcp.blender.unreachable` |
| `pipeline/clients/unreal_mcp.py` | `UnrealMcpClient(url=http://127.0.0.1:$UE_MCP_PORT(8000)/mcp)`: streamable-HTTP JSON-RPC (JSON or SSE), session id, VibeUE `execute_python_code` resolved natively or through `list_toolsets` / `describe_toolset` / `call_tool`, strictly sequential; failure → `mcp.unreal.unreachable` |
| `src/nmg_game_dev/unreal/import_asset.py` | `build_import_code(variant_dir, dest, name, report) -> str`: UE Python run through `execute_python_code` (design § UE import) |
| `src/nmg_game_dev/finalize/__main__.py` | CLI (design § Interfaces) |
| `plugins/nmg-game-dev-blender-addon/finalize_core/__init__.py` | `content_hash(collection) -> str`, `run_step(step, request: dict, job_dir: str) -> dict`, `load_back(result_blend, collection, expected_hash) -> dict` |
| `scripts/blender/finalize_entry.py` | Parses args after `--`, enables the add-on, calls `finalize_core.run_step`, writes `<step>.json`, saves `<step>.blend` for mutating steps, exits 0/1 |
| `mcp-servers/finalize/` | `pyproject.toml` (package `finalize-mcp`, depends on `mcp` and the root `nmg-game-dev` as a path dependency, script `finalize-mcp`), `src/finalize_mcp/server.py` (FastMCP `finalize`), `tools.json` |
| `skills/finalize-asset/SKILL.md` | Skill per the steering template: required MCP `blender`, `unreal`, `finalize`; flow = call `finalize_asset`, poll, report; failure modes = the error codes below |
| `scripts/unreal/build_master_material.py` | Builds `/nmg-game-dev/Materials/M_NmgORM` in a running UE 5.8 through `UnrealMcpClient` and saves it into the plugin's `Content/` |
| `plugins/nmg-game-dev-ue-plugin/Content/Materials/M_NmgORM.uasset` | Generated by the script above |

Removed: `pipeline/prompt.py`, `pipeline/stages/` (all modules), and the e2e `fixture_prompt.json`.

## API / Interface Changes

| Interface | Input | Output / Error | Behavior |
|-----------|-------|----------------|----------|
| `pipeline.finalize(request, ...)` | `FinalizeRequest` | `FinalizeResult` / `PipelineError` | AC1, AC2, AC4, AC6 |
| `pipeline.run_step(step, request, ...)` | step name, request | `StepResult` / `PipelineError` | AC3 |
| `python -m nmg_game_dev.finalize {all,validate,bake,variants,export,reimport,import_ue} --collection N --category C --class K --export-root R [--blend B] [--budgets P] [--device GPU\|CPU] [--force] [--json]` | | exit 0 + result (JSON with `--json`); exit 1 with `ERROR [code] message` and `Remediation: ...`; exit 2 for prerequisites (`finalize.blender_not_found`, `mcp.*.unreachable`) | AC1, AC3, AC6 |
| `python -m nmg_game_dev.finalize run-job <job_dir>` | internal | writes `status.json` | AC2 |
| MCP `finalize_asset(collection, category, asset_class, export_root, blend=None, budgets_path=None, force=False, wait_seconds=0)` | | `{"job_id", "status"}`, plus `"result"` when finished within `wait_seconds` (clamped to 0–150) | AC2, AC3 |
| MCP `run_finalize_step(step, ...same)` | | same | AC3 |
| MCP `get_finalize_job(job_id)` | | `{"job_id", "state", "step", "progress", "message", "result"?, "error"?}`; unknown id → `{"error": {"code": "finalize.job_not_found", ...}}` | AC2, AC3 |

Errors are returned as `{"error": {"code", "message", "remediation", "stage"}}` from the MCP tools and logged to stderr only.

Error codes: `finalize.session_changed`, `finalize.job_crashed`, `finalize.job_running`, `finalize.job_not_found`, `finalize.blender_not_found`, `finalize.collection_not_found`, `quality.contract_failed`, `quality.reimport_mismatch`, `bake.texture.bake_failed`, `variants.<code>`, `import_ue.failed`, `import_ue.pivot_mismatch`, `mcp.blender.unreachable`, `mcp.unreal.unreachable`.

### Steps

| Step | Kind | Input `.blend` → output | Calls | Gate / outputs |
|------|------|-------------------------|-------|----------------|
| `validate` | blender, read-only | checkpoint | `contract_core.validate_asset(collection, asset_class, budgets_path)` | `quality.contract.gate(report, "contract")`; outputs `report` path |
| `bake` | blender, mutating | checkpoint → `bake.blend` | `bake_core.bake_asset(collection, asset_class, <job_dir>/bake, budgets_path, device)` | outputs bake result (texture paths, bytes, proof) |
| `variants` | blender, mutating | `bake.blend` → `variants.blend` | `variants_core.cleanup_desktop(collection)` then `build_mobile(collection, resolve_budget(...))` | outputs tris per variant and per LOD |
| `export` | blender, read-only | `variants.blend` | `contract_core.validate_asset` on Desktop+Mobile (pre-export report), then `variants_core.export_variants(...)` and `write_sidecars(...)` into `<export_root>/<Category>/<Name>/` | contract gate; outputs FBX paths, `nmg-variants.json`, pre-export report |
| `reimport` | blender, isolated | none | `contract_core.reimport_check(variant_dir, pre_report)` per variant in `--factory-startup` | `gate(report, "reimport")` per variant |
| `import_ue` | unreal | none | `UnrealMcpClient.execute_python_code(build_import_code(...))` per variant | outputs UE content paths; pivot check |

`result.blend` = the last mutating step's output (`variants.blend`), used for load-back.

### Load-back (session runs)

`finalize_core.load_back(result_blend, collection, expected_hash)` runs in the open session through `BlenderSessionClient`:
1. Recompute `content_hash(<Name>)`. If it differs from `expected_hash`, return `{"loaded": false, "reason": "session_changed"}`. The pipeline then raises `finalize.session_changed` with `result_blend` in the message, but only after the export/reimport/import steps have run, because those use the job's files, not the session.
2. Otherwise, rename the session's `<Name>` and `<Name>_Mobile` collections (and their objects, meshes, and materials) with a `__nmg_old_` prefix, append the two collections from `result_blend` with `bpy.data.libraries.load(link=False)`, link them to the scene, and then delete the `__nmg_old_` datablocks. On any exception, restore the old names and remove the appended blocks.
3. Return `{"loaded": true, "hash": content_hash(<Name>)}`. This post-load hash is recorded as an alias (design § Cache).

Ordering: load-back happens after `reimport` passes and before `import_ue`. A load-back refusal still lets `import_ue` run, and the result has `loaded_back = false`.

### Cache

- `asset_hash = finalize_core.content_hash(collection)`: SHA-256 over objects of `<Name>` (and `<Name>_Mobile` when present) sorted by name. It covers `matrix_world`, vertex coordinates, polygon indices, material indices, UV layers, modifier stacks (type plus properties), each material's node tree in canonical form (as in #67's bake hash), and image file bytes. The session computes it at checkpoint; `--blend` runs compute it in a headless pass.
- `settings_hash` = SHA-256 of canonical JSON of `{asset_class, resolved budget, device (bake only), export_root (export/import only), category, step version}`.
- Step key: `ArtifactCache.key(step, input_hash, settings_hash)`, where `input_hash` is `asset_hash` for the first step and the previous step's output `content_hash()` for the rest. Directory outputs (bake textures, export folders) are stored as directory blobs.
- Alias index `runs/<asset_hash>.json` = `{"steps": {step: key}, "result_blend", "content_paths"}`. It's written once for the checkpoint hash and once for the post-load-back hash. When a run's `asset_hash` matches an alias whose step entries all exist, every step is served from cache (`cache_hit: true`), `import_ue` is skipped, and load-back is skipped because the session already holds the result. `force=True` bypasses lookups and still writes.

### UE import (`unreal/import_asset.py`)

UE Python executed per variant, with JSON parameters embedded and the result printed as `NMG_RESULT {json}`:
1. Import every `T_*.png` into `<dest>` with `AssetImportTask(automated=True, replace_existing=True, save=True)`. Then set `_BC`: `srgb=True`; `_N`: `flip_green_channel=True`, `compression_settings=TC_NORMALMAP`, `srgb=False`; `_ORM`: `srgb=False`, `compression_settings=TC_MASKS`.
2. Import `SM_<Name>.fbx` with `FbxImportUI(import_materials=False, import_textures=False, import_as_skeletal=False)`, static mesh data `combine_meshes=False`, `transform_vertex_to_absolute=False`, `bake_pivot_in_vertex=False`.
3. For each static mesh material slot named `M_<Name>_<Part>`, create or reuse `MI_<Name>_<Part>` in `<dest>`, parented to `/nmg-game-dev/Materials/M_NmgORM`. Set texture parameters `BaseColor`, `Normal`, and `ORM` to the imported textures and assign it to the slot. Save all.
4. Report each static mesh's local bounding box. The host compares each child part `SM_<Name>_<Part>` with the pre-export report snapshot (meters ×100, Y negated) within 0.01 cm; a mismatch raises `import_ue.pivot_mismatch`.

`<dest>` = `/Game/<Category>/<Name>/Desktop` and `/Game/<Category>/<Name>/Mobile`.

`M_NmgORM`: a surface material with texture parameters `BaseColor` (Color sampler) → Base Color, `Normal` (Normal sampler) → Normal, and `ORM` (Masks sampler) with R → Ambient Occlusion, G → Roughness, B → Metallic. `scripts/unreal/build_master_material.py` creates it with `MaterialFactoryNew` and `MaterialEditingLibrary` under `/nmg-game-dev/Materials/` and saves it. Running it again overwrites the asset.

## Data / Storage Changes

Job directory `<cache_root>/jobs/<job_id>/`: `request.json`, `status.json` (`{"job_id", "state": "queued"|"running"|"succeeded"|"failed", "step", "progress", "message", "steps": {step: StepResult}, "result"?, "error"?}`), `checkpoint.blend`, `<step>.json`, `<step>.blend`, `blender-<step>.log`. One active finalize job per cache root (`jobs/lock` holding a PID); a live lock → `finalize.job_running`.

`.mcp.json` gains `"finalize": {"command": "uv", "args": ["run", "--project", "${CLAUDE_PLUGIN_ROOT}/mcp-servers/finalize", "finalize-mcp"], "description": "..."}`. Existing entries stay unchanged.

`mcp-servers/finalize/tools.json` lists the three tools with descriptions and input schemas.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Every Blender step in its own headless process, chained by `.blend` files | Selected | Isolates crashes per step and never blocks or mutates the open session mid-run |
| Run short steps inside the session through MCP | Rejected | Two execution paths; validate on large assets can still exceed 180 s |
| Start + poll tools with optional `wait_seconds` | Selected | Follows the #7 job pattern; quick steps return in one call |
| Plugin-owned `M_NmgORM.uasset` | Selected | Interview decision; consumers' `/Game` stays free of framework assets |
| Overwrite the session even if the developer edited during the job | Rejected | Would silently discard work; refusal keeps the result `.blend` |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #69 | 2026-10-30 | Initial feature design |
