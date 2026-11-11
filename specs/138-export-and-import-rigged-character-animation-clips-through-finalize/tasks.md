# Tasks: Export and import rigged-character animation clips through finalize

**Issue**: #138
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley

## Implementation Tasks

### T001: Step table, dependencies, and request fields

**File(s)**: `src/nmg_game_dev/pipeline/steps.py`, `src/nmg_game_dev/pipeline/request.py`, `src/nmg_game_dev/pipeline/result.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- `export_anims` (Blender) and `import_anims` (Unreal) are in `STEP_ORDER` after `export` and after `import_ue`, and are flagged `per_clip`.
- `ordered_steps` returns the dependency closure:
  - `import_ue` and earlier requests give today's chains;
  - `export_anims` needs validate, bake, and variants;
  - `import_anims` needs every step.
- `_STEP_VERSION` is `"4"`, and `clip_settings_hash` is added.
- `FinalizeRequest.compatible_with` validates `<Category>/<Name>` items.
- `FinalizeResult.animations` holds `content_path`, `clips` with export and import cache-hit flags, `stale`, and `compatible` (FR1, FR12, FR14).

### T002: Blender clip probe and export

**File(s)**: `plugins/nmg-game-dev-blender-addon/finalize_core/anims.py`, `plugins/nmg-game-dev-blender-addon/finalize_core/steps.py`, `scripts/blender/finalize_entry.py`
**Type**: Create, Modify
**Depends**: T001
**Acceptance**:
- `resolve_clips` returns provenance clips plus the rig's assigned and NLA-strip actions, sorted. Unrelated actions are excluded, and there are none without `SK_<Name>` (AC2, AC8, FR2).
- `clip_hash` covers the clip's keyframes (through action slots), the rig rest pose, the provenance, and fps.
- `probe` reports `valid_name` per clip.
- `export_clip` writes an armature-only `A_<Name>_<Clip>.fbx` holding exactly that clip:
  - armature `Armature`;
  - `_RIG_FBX_OPTIONS` imported from `variants_core/export.py`, plus `object_types={"ARMATURE"}`, `bake_anim` True, `use_all_actions` False, `use_nla_strips` False, `use_all_bones` True, `force_startend_keying` True, `simplify_factor` 0.
- After export, the name, action, slot, and NLA state are restored. It measures frame start, end, count, and fps (AC1, AC3, FR3).
- `finalize_entry.py` accepts `export_anims`, in modes `probe` and `export`.

### T003: Host per-clip export and sidecar

**File(s)**: `src/nmg_game_dev/pipeline/anims.py`, `src/nmg_game_dev/pipeline/engine.py`
**Type**: Create, Modify
**Depends**: T001, T002
**Acceptance**:
- The engine runs `per_clip` steps through `pipeline/anims.py`, outside the whole-step cache and the alias. Mesh steps keep their keys, so a clip-only change serves them from cache (AC6).
- An invalid name raises `finalize.clip_name_invalid` naming the action, before any FBX or sidecar write (AC11).
- Per-clip keys of the clip hash plus `clip_settings_hash`: hits restore the blob, misses export in one Blender run, and `force` exports all (AC6, AC7, FR7).
- `nmg-animations.json` holds `asset`, `armature`, `skeleton`, and per-clip `name`, `file`, `asset_path`, `frame_start`, `frame_end`, `frame_count`, `fps`, and `source` (provenance or `"authored"`) (AC3, FR4).
- Zero clips writes nothing and reports zero (AC8, FR8).

### T004: Unreal clip import, verification, stale, and compatible skeletons

**File(s)**: `src/nmg_game_dev/unreal/import_anims.py`, `src/nmg_game_dev/pipeline/anims.py`
**Type**: Create, Modify
**Depends**: T003
**Acceptance**:
- A missing Desktop skeleton gives `finalize.skeleton_not_found`, with the run-`import_ue`-first remediation and no import (AC10).
- Compatible targets are all checked before any change: a missing target gives `finalize.skeleton_not_found`, and differing bone names give `finalize.skeleton_mismatch` listing the bones (AC15).
- Misses import as `A_<Name>_<Clip>` in `/Game/<Category>/<Name>/Animations`, using `FbxImportUI` `import_mesh` False, `import_as_skeletal` True, `import_animations` True, `FBXIT_ANIMATION`, and the Desktop skeleton. A created non-AnimSequence asset fails (AC4, FR5).
- Each clip's skeleton and sampled key count are compared with the sidecar. A difference gives `import_anims.clip_mismatch`, naming the clip, expected, and measured (AC5, FR6).
- Stale `A_<Name>_*` sequences are listed and not deleted (AC12, FR11).
- Compatible registration is two-way and duplicate-free, and is skipped when `compatible_with` is empty (AC13, AC14, AC16, FR13).
- No Unreal call is made with zero clips and no `compatible_with` (AC8).
- Per-clip import caching works like export, with `force` reimporting all (AC6, AC7).

### T005: CLI and MCP surface

**File(s)**: `src/nmg_game_dev/finalize/__main__.py`, `src/nmg_game_dev/finalize/mcp_tools.py`, `mcp-servers/finalize/src/finalize_mcp/server.py`, `mcp-servers/finalize/tools.json`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- The CLI has `export_anims` and `import_anims` subcommands and a repeatable `--compatible-with`.
- `run_finalize_step` accepts both steps, and both tools accept `compatible_with`.
- Results include `animations`. The single-step result shape matches the other steps (AC9, FR9, FR12).
- `uv run python scripts/validate-mcp-tools.py` (`gate-mcp-schema`) passes.

### T006: Documentation

**File(s)**: `docs/asset-contract.md`, `docs/mcp/finalize.md`, `docs/rigging-and-animation.md`, `skills/finalize-asset/SKILL.md`
**Type**: Modify
**Depends**: T003, T004, T005
**Acceptance**:
- Each document describes:
  - the two steps and their order;
  - the `Animations/` layout and the `A_<Name>_<Clip>` name;
  - the sidecar fields;
  - per-clip caching and `force`;
  - stale reporting;
  - `compatible_with`;
  - the codes `finalize.skeleton_not_found`, `finalize.clip_name_invalid`, `finalize.skeleton_mismatch`, and `import_anims.clip_mismatch` (FR15).
- `claude plugin validate .` (`plugin.validate`) passes.

### T007: Tests

**File(s)**: `tests/unit/pipeline/test_steps.py`, `tests/unit/pipeline/test_anims.py`, `tests/unit/test_unreal_import_anims.py`, `tests/unit/test_finalize_cli.py`, `tests/unit/test_finalize_mcp_tools.py`, `tests/bdd/features/rigged_finalize.feature`, `tests/finalize_fakes.py`, `tests/blender/test_finalize_anims.py`
**Type**: Create, Modify
**Depends**: T002, T003, T004, T005, T006
**Acceptance**:
- No test launches or connects to a live Blender GUI session or Unreal editor:
  - host tests use `tests/finalize_fakes.py` and a fake Unreal Python client that records the code it receives;
  - Blender tests run headless through `gate-blender-headless`.
- SCN001 (Blender): `Idle` and `Walk` give two armature-only FBX files, and re-importing each in the same headless process shows one armature named `Armature`, no mesh, and one action.
- SCN002 (Blender): `Idle` (provenance) and `Wave` (NLA) are exported, and `Other` is not.
- SCN003: the sidecar fields match the exported actions, with provenance source and `"authored"` sources.
- SCN004–SCN005 (fake UE):
  - the import code requests `FBXIT_ANIMATION` against the Desktop skeleton into `Animations/A_<Name>_<Clip>`;
  - a result with a non-AnimSequence asset fails;
  - a key-count or skeleton difference raises `import_anims.clip_mismatch`, naming the clip, expected, and measured.
- SCN006–SCN007: after a run, changing only `Walk`'s hash re-exports and re-imports `Walk`, serves `Idle` from cache, and leaves mesh steps as cache hits. `force` reruns both.
- SCN008: unrigged and clip-less rigs report zero clips, write no `Animations/`, and make no Unreal call. Mesh outputs are unchanged.
- SCN009: `run_finalize_step` and the CLI accept `export_anims` and `import_anims`.
- SCN010–SCN016 (fake UE): a missing skeleton, an invalid clip name, stale reporting without deletion, two-way registration, idempotent re-registration, a missing or mismatched target with no change, and no registration without `compatible_with`.
- `ordered_steps(("import_ue",))` equals today's six-step chain.
- `repository.tests`, `repository.lint`, `repository.format`, `repository.types`, `gate-blender-headless`, `gate-mcp-schema`, and `plugin.validate` pass.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #138 | 2026-11-11 | Initial feature tasks |
