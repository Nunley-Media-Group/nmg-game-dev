# Design: Export and import rigged-character animation clips through finalize

**Issue**: #138
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley

## Overview

Two steps join the finalize table. Unlike the mesh steps, they are cached per clip:

- **`export_anims`** runs Blender twice, headless:
  1. a **probe** that lists the rig's clips with a content hash for each;
  2. an **export** run for only the clips that missed the cache.
- **`import_anims`** sends one Unreal Python call. That call:
  - imports the clips that missed the cache;
  - verifies every imported clip;
  - lists stale sequences;
  - registers compatible skeletons.

The asset hash (`finalize_core/hashing.py`) does not cover actions. A clip-only change therefore leaves every mesh step's cache entry valid, and the per-clip keys detect it.

The FBX and Unreal settings reuse the rigged mesh export and the ghost1 consumer project's proven clip export and import.

## Architecture

### Step table (`src/nmg_game_dev/pipeline/steps.py`)

- **`StepName`** adds `export_anims` and `import_anims`.
- **`STEP_ORDER`** = `validate, bake, variants, export, export_anims, reimport, import_ue, import_anims`.
- **`STEPS`**:
  - `export_anims` = `StepSpec(kind="blender", mutates_scene=False, per_clip=True)`;
  - `import_anims` = `StepSpec(kind="unreal", mutates_scene=False, per_clip=True)`;
  - other steps keep `per_clip=False`.
- **`DEPENDS`** maps each step to the steps it needs:
  - mesh steps keep their current prefix;
  - `export_anims` → validate, bake, variants;
  - `import_anims` → every other step.
- **`ordered_steps`** returns the dependency closure of the requested steps in `STEP_ORDER` order.
  - Requesting `import_ue` gives the same chain as today.
  - Requesting `export_anims` gives validate, bake, variants, export_anims (AC9).
- **`_STEP_VERSION`** goes to `"4"`.
- **`clip_settings_hash(step, request)`** covers:
  - for export: the step, the version, collection, category, `export_root`, and an `ANIM_EXPORT_OPTIONS` fingerprint;
  - for import: the step, the version, collection, category, `export_root`, and the Desktop skeleton path.
  - `compatible_with` is not in either hash, because registration runs on every `import_anims`.

### Blender: clips (new `plugins/nmg-game-dev-blender-addon/finalize_core/anims.py`)

- **`resolve_clips(collection)`**: when `SK_<Name>` exists in `<Name>`, the clip set is the union of:
  - the names in its `nmg_animations` provenance that resolve to actions;
  - `animation_data.action`;
  - every action in its NLA track strips.
  - It is sorted by name. No armature, or no clips, gives an empty list (FR2, AC8).
- **`clip_hash(armature, action, provenance)`** is the SHA-256 of a canonical JSON of:
  - the clip name;
  - every F-curve's data path, array index, keyframe points (co, handles, interpolation), and modifiers, read through the action's slots and channelbags on layered actions;
  - the rig's bone names, parents, and rest `matrix_local`;
  - the provenance entry;
  - scene fps and `fps_base`.
- **`probe`** returns `{clips: [{name, hash, valid_name}]}`. `valid_name` tests `^[A-Za-z][A-Za-z0-9_]*$` and does not raise.
- **`export_clip(armature, action, path)`**:
  - selects only the armature and temporarily renames it `Armature`;
  - assigns the action and its slot, and mutes NLA tracks;
  - exports with `ANIM_EXPORT_OPTIONS`;
  - restores the name, action, slot, and NLA mute states.
  - It then measures `frame_start`/`frame_end` from `action.frame_range` (rounded) plus `frame_count` and `fps` (`render.fps / render.fps_base`).
- **`ANIM_EXPORT_OPTIONS`**:
  - the `_RIG_FBX_OPTIONS` of `variants_core/export.py` (`add_leaf_bones` False, `use_armature_deform_only` True, primary Y, secondary X, `FBX_SCALE_UNITS`), imported so the two cannot drift;
  - plus `object_types={"ARMATURE"}`, `bake_anim` True, `bake_anim_use_all_actions` False, `bake_anim_use_nla_strips` False, `bake_anim_use_all_bones` True, `bake_anim_force_startend_keying` True, and `bake_anim_simplify_factor` 0.0 (FR3, AC1).
- **Step wiring.**
  - `finalize_core/steps.py` registers `export_anims`. It reads `inputs.mode` (`probe` or `export`) and `inputs.clips` (the names to export), and writes FBX files into `<export_root>/<Category>/<Name>/Animations/`.
  - `scripts/blender/finalize_entry.py` adds `export_anims` to `_STEPS`.
  - The step reads the `variants` result `.blend`.

### Host: per-clip export (`src/nmg_game_dev/pipeline/engine.py`, new `src/nmg_game_dev/pipeline/anims.py`)

The engine routes `per_clip` steps to `run_export_anims` and `run_import_anims` in `pipeline/anims.py`. They are never looked up or stored through the whole-step key or the alias.

**`run_export_anims`:**
1. Run the probe. Any `valid_name` false raises `finalize.clip_name_invalid`, naming the actions, before any export or sidecar write (AC11).
2. Zero clips returns `{clips: [], content_dir: null}` and writes nothing (AC8).
3. Per clip, key = `cache.key("export_anims", clip.hash, clip_settings_hash)`.
   - A hit (and not `force`) restores the cached FBX blob if it is missing.
   - Misses go to one export run.
   - Each miss is stored with outputs `{name, file, frame_start, frame_end, frame_count, fps, source}` and the FBX blob (FR7, AC6, AC7).
4. Write `nmg-animations.json` from the per-clip outputs (FR4, AC3):
   - top level: `asset`, `armature: "Armature"`, and `skeleton: "/Game/<Category>/<Name>/Desktop/SM_<Name>_Skeleton"`;
   - each clip: `name`, `file`, `asset_path: "/Game/<Category>/<Name>/Animations/A_<Name>_<Clip>"`, `frame_start`, `frame_end`, `frame_count`, `fps`, and `source`.
   - `source` is the provenance `source` dict, or `"authored"` when the clip has no provenance.

**`run_import_anims`:**
- Zero clips and an empty `compatible_with` makes no Unreal call and returns zero clips (AC8, AC16).
- Otherwise, per clip, key = `cache.key("import_anims", <export clip output hash>, clip_settings_hash)`. It sends `build_anim_import_code(...)` for the misses (all of them under `force`) and the clip list, plus `compatible_with`.

### Unreal: import code (new `src/nmg_game_dev/unreal/import_anims.py`)

`build_anim_import_code(params)` returns UE Python that prints `NMG_RESULT {...}`. It is run through the existing Unreal MCP client (`UnrealPythonRunner`), and its result is parsed with `parse_nmg_result`.

1. **Skeleton check.** If the Desktop skeleton is missing, it returns error `skeleton_not_found`, and the host raises `finalize.skeleton_not_found` with remediation "Run import_ue for <Category>/<Name> first, then rerun import_anims". Nothing is imported (AC10).
2. **Compatible targets are checked first.** Each `compatible_with` target must exist, or the host raises `finalize.skeleton_not_found`. Its reference bone names must equal this skeleton's, or the host raises `finalize.skeleton_mismatch` listing the differing bones. Nothing is registered or imported on failure (AC15).
3. **Import.** Each miss is imported through an `AssetImportTask`:
   - `destination_path` `/Game/<Category>/<Name>/Animations` and `destination_name` `A_<Name>_<Clip>`;
   - `replace_existing` True, `automated` True, `save` True;
   - `FbxImportUI`: `import_mesh` False, `import_as_skeletal` True, `import_animations` True, `import_materials` False, `import_textures` False, `mesh_type_to_import` `FBXIT_ANIMATION`, `skeleton` set to the Desktop skeleton.
4. **Created-assets check.** Any imported object that is not an AnimSequence fails the step (AC4).
5. **Verify every clip, cached ones included.** The host compares the AnimSequence's skeleton path and its sampled key count with the sidecar `frame_count`. A difference raises `import_anims.clip_mismatch`, naming the clip, the field, the expected value, and the measured value (AC5).
6. **Stale.** It lists AnimSequences in the Animations folder named `A_<Name>_*` that are not in the clip list. They are returned as `stale` and never deleted (AC12).
7. **Compatible registration.** For each target, it adds the other skeleton to each skeleton's `compatible_skeletons` only when the path is absent, then saves both. The registered paths are returned (AC13, AC14). With no `compatible_with`, nothing is touched (AC16).

### Request and interfaces

- **`FinalizeRequest`** (`pipeline/request.py`) gains `compatible_with: tuple[str, ...] = ()`. Each item must match `^[A-Z][A-Za-z0-9]*/[A-Z][A-Za-z0-9]*$`.
- **`FinalizeResult`** (`pipeline/result.py`) gains `animations: dict | None` (FR14):
  - `content_path`: `/Game/<Category>/<Name>/Animations` or `null`;
  - `clips`: `[{name, asset_path, export_cache_hit, import_cache_hit}]`;
  - `stale`;
  - `compatible`.
  - Each per-clip step's `StepResult.cache_hit` is true only when every clip hit.
- **CLI** (`finalize/__main__.py`): the step commands come from `STEP_ORDER`, and `--compatible-with <Category>/<Name>` may repeat.
- **MCP** (`finalize/mcp_tools.py`, `mcp-servers/finalize/src/finalize_mcp/server.py`, `mcp-servers/finalize/tools.json`):
  - `finalize_asset` and `run_finalize_step` accept `compatible_with`;
  - the `run_finalize_step` step enum gains the two steps.

## Error Codes

| Code | Raised by | Remediation |
|------|-----------|-------------|
| `finalize.clip_name_invalid` | host, from probe data | Rename the action to match `^[A-Za-z][A-Za-z0-9_]*$`, then rerun |
| `finalize.skeleton_not_found` | host, from the UE result | Run `import_ue` first (own skeleton), or finalize the named character first (compatible target) |
| `finalize.skeleton_mismatch` | host, from the UE result | Only register characters rigged with the same bone names |
| `import_anims.clip_mismatch` | host verification | Re-export the clip and rerun `import_anims` with `force` |

All carry message, remediation, and stage (FR10).

## Docs

Five documents describe the two steps, the `Animations/` layout, `A_<Name>_<Clip>`, the sidecar fields, `compatible_with`, and the error codes (FR15):
- `docs/asset-contract.md` (animation naming);
- `docs/mcp/finalize.md`;
- `docs/rigging-and-animation.md`;
- `skills/finalize-asset/SKILL.md`;
- `mcp-servers/finalize/tools.json`.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Per-clip cache with a Blender probe | Selected | Clip changes do not change the asset hash, so the whole-step cache would serve stale clips |
| Hash actions into the asset hash | Rejected | A clip edit would re-run every mesh step (AC6) |
| Strict prefix ordering | Rejected | Would make `import_ue` run `export_anims`, changing current behavior (AC8) |
| ghost1 `Anim/` folder and `loop` field | Rejected | The issue fixes `Animations/` and the sidecar fields |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #138 | 2026-11-11 | Initial feature design |
