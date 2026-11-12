# Requirements: Export and import rigged-character animation clips through finalize

**Issue**: #138
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley

## User Story

**As a** game developer finalizing a rigged character
**I want** finalize to export every clip on `SK_<Name>` and import it into Unreal as an AnimSequence on the character's skeleton
**So that** animations baked in Blender reach `/Game/<Category>/<Name>/Animations/` through the same pipeline that writes the rest of the character's Content

## Background

`import_animations` bakes clips onto `SK_<Name>` as Blender actions, but finalize has no route that carries them into Unreal:
- the finalize export (`plugins/nmg-game-dev-blender-addon/variants_core/export.py`) writes the skinned mesh with `bake_anim=False`;
- `import_ue` (`src/nmg_game_dev/unreal/import_asset.py`) imports only the Skeletal Mesh, creating `SM_<Name>_Skeleton` and `SM_<Name>_PhysicsAsset` in `/Game/<Category>/<Name>/Desktop`.

`rig_core/retarget.py` stores each baked clip as a fake-user action named after the clip, and records its provenance in the armature's `nmg_animations` property. The six finalize steps in `src/nmg_game_dev/pipeline/steps.py` are cached as a whole on the asset hash. That hash does not cover actions, so there is no per-clip cache.

Characters that share the Manny bone names each get their own skeleton, so one character's clips cannot play on another.

## Acceptance Criteria

### AC1: Finalize exports one animation FBX per clip

**Given** a rigged character whose `SK_<Name>` has clips `Idle` and `Walk`
**When** `finalize all` runs
**Then** `export_anims` writes `<export_root>/<Category>/<Name>/Animations/A_<Name>_Idle.fbx` and `A_<Name>_Walk.fbx`
**And** each file holds the armature named `Armature` and exactly one clip, with no mesh
**And** each file uses the same armature and axis settings as the rigged mesh export (`add_leaf_bones` off, deform-only, primary bone axis Y, secondary X)

### AC2: The clip set is provenance clips plus actions held on the rig

**Given** `SK_<Name>` has a provenance clip `Idle` and a hand-keyed action `Wave` in one of its NLA tracks
**And** the file also holds an action `Other` that is neither in the rig's provenance nor assigned to or stripped on the rig
**When** `export_anims` runs
**Then** `Idle` and `Wave` are exported
**And** `Other` is not exported

### AC3: nmg-animations.json records real clip data

**Given** `export_anims` exported clips for `<Name>`
**When** the step finishes
**Then** `nmg-animations.json` exists in the same `Animations/` folder
**And** it lists, per clip, the clip name, FBX file name, Unreal asset path, frame start, frame end, frame count, and fps measured from the exported action
**And** a provenance clip carries its recorded source (library, file, SHA-256, source skeleton)
**And** a clip with no provenance carries source `authored`

### AC4: Clips import as AnimSequences on the Desktop skeleton

**Given** `import_ue` has created `/Game/<Category>/<Name>/Desktop/SM_<Name>_Skeleton`
**When** `import_anims` runs
**Then** each clip exists as AnimSequence `/Game/<Category>/<Name>/Animations/A_<Name>_<Clip>`
**And** each AnimSequence uses `SM_<Name>_Skeleton`
**And** no additional skeleton, skeletal mesh, or physics asset is created
**And** the finalize result lists the Animations content path and every imported clip

### AC5: An imported clip is checked against the sidecar

**Given** a clip whose `nmg-animations.json` entry records its frame count
**When** `import_anims` imports it and the resulting AnimSequence has a different frame count or a different skeleton
**Then** the step fails with an error that names the clip, the expected value, and the measured value

### AC6: Clips are cached individually

**Given** a finished finalize of a character with clips `Idle` and `Walk`
**When** only `Walk` changes and finalize runs again
**Then** `Walk` is re-exported and re-imported
**And** `Idle` is reported as served from cache and is neither re-exported nor re-imported
**And** the mesh steps' cached results are still served from cache when the meshes and materials are unchanged

### AC7: Force reruns every clip

**Given** a finished finalize with every clip cached
**When** finalize runs with `force`
**Then** every clip is re-exported and re-imported

### AC8: Assets without clips pass through

**Given** an unrigged asset, or a rigged character with no clips
**When** `finalize all` runs
**Then** `export_anims` and `import_anims` succeed and report zero clips
**And** no `Animations/` folder, FBX, or `nmg-animations.json` is written
**And** every other finalize output is unchanged from current behavior

### AC9: The new steps run alone

**Given** a rigged character whose mesh steps have already completed
**When** `run_finalize_step` or the CLI is called with `export_anims` or `import_anims`
**Then** that step runs, with the steps it depends on served from cache, and returns the same result shape as the other steps

### AC10: import_anims needs the Desktop skeleton

**Given** `/Game/<Category>/<Name>/Desktop/SM_<Name>_Skeleton` does not exist
**When** `import_anims` runs
**Then** it fails with `finalize.skeleton_not_found` and a remediation that says to run `import_ue` first
**And** no AnimSequence is created

### AC11: An invalid clip name stops the export

**Given** a rig-held action whose name does not match `^[A-Za-z][A-Za-z0-9_]*$`
**When** `export_anims` runs
**Then** it fails with `finalize.clip_name_invalid` naming the action
**And** no animation FBX or sidecar is written

### AC12: Stale AnimSequences are reported, never deleted

**Given** `/Game/<Category>/<Name>/Animations/` holds `A_<Name>_Run` from an earlier finalize and `Run` is no longer a clip on the rig
**When** `import_anims` runs
**Then** `A_<Name>_Run` still exists
**And** the step result lists it under `stale`

### AC13: Compatible skeletons are registered on request

**Given** character `B` is already finalized with skeleton `SM_B_Skeleton`, and the finalize request for character `A` sets `compatible_with` to `["<CategoryB>/B"]`
**When** `import_anims` runs for `A`
**Then** `SM_B_Skeleton` is in `SM_A_Skeleton`'s compatible skeletons, and `SM_A_Skeleton` is in `SM_B_Skeleton`'s
**And** both characters keep their own skeleton assets
**And** the finalize result lists the registered skeletons

### AC14: Compatible registration is idempotent

**Given** `A` and `B` are already registered as compatible
**When** finalize runs again for `A` with the same `compatible_with`
**Then** each skeleton lists the other exactly once

### AC15: A compatible target must exist and match bone names

**Given** `compatible_with` names a character whose Desktop skeleton does not exist, or whose bone names differ from `SM_<Name>_Skeleton`'s
**When** `import_anims` runs
**Then** it fails with `finalize.skeleton_not_found` or `finalize.skeleton_mismatch` respectively, naming the target and, for a mismatch, the differing bones
**And** neither skeleton's compatible list is changed

### AC16: Without compatible_with nothing is registered

**Given** a finalize request that omits `compatible_with`
**When** finalize runs
**Then** no skeleton's compatible list is changed

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | Add finalize steps `export_anims` (Blender) and `import_anims` (Unreal). `export_anims` runs after `export`, `import_anims` runs after `import_ue`, and `finalize all` runs both | Must |
| FR2 | `export_anims` resolves the clip set as the rig's `nmg_animations` provenance clips plus every action assigned to `SK_<Name>` or present in its NLA tracks | Must |
| FR3 | `export_anims` writes one armature-only FBX per clip, `A_<Name>_<Clip>.fbx`, in `<export_root>/<Category>/<Name>/Animations/`, with the armature named `Armature`, `add_leaf_bones` off, a deform-only armature, primary bone axis Y, secondary X, and exactly that clip baked | Must |
| FR4 | `export_anims` writes `nmg-animations.json` beside the FBX files, with asset, armature, skeleton asset path, and per-clip name, file, Unreal asset path, frame start, frame end, frame count, fps, and source | Must |
| FR5 | `import_anims` imports each clip as AnimSequence `/Game/<Category>/<Name>/Animations/A_<Name>_<Clip>` against `/Game/<Category>/<Name>/Desktop/SM_<Name>_Skeleton` and creates no other asset | Must |
| FR6 | `import_anims` compares each imported AnimSequence's frame count and skeleton with the sidecar and fails on a difference | Must |
| FR7 | Each clip's export and import are cached per clip, on the clip's content and the export or import settings. Unchanged clips are cache hits, and `force` bypasses the cache | Must |
| FR8 | Both steps succeed with zero clips, and write nothing, for an unrigged asset or a rig with no clips | Must |
| FR9 | Both steps are accepted by `run_finalize_step` and the `python -m nmg_game_dev.finalize` CLI | Must |
| FR10 | Error codes `finalize.skeleton_not_found`, `finalize.clip_name_invalid`, and `finalize.skeleton_mismatch` are returned with message, remediation, and stage | Must |
| FR11 | `import_anims` reports, under `stale`, AnimSequences named `A_<Name>_*` in the Animations folder that are not current clips, and does not delete them | Must |
| FR12 | The finalize request accepts optional `compatible_with`, a list of `<Category>/<Name>` strings, through the MCP tools and the CLI | Should |
| FR13 | When `compatible_with` is set, `import_anims` registers each named character's Desktop skeleton and `SM_<Name>_Skeleton` as compatible skeletons in both directions, idempotently, after checking that the target exists and has the same bone names | Should |
| FR14 | The finalize result carries an `animations` entry with the content path, the clips (with per-clip cache hit), `stale`, and the registered compatible skeletons | Must |
| FR15 | `docs/asset-contract.md`, `docs/mcp/finalize.md`, `docs/rigging-and-animation.md`, `skills/finalize-asset/SKILL.md`, and `mcp-servers/finalize/tools.json` describe the two steps, the `Animations/` layout, the `A_<Name>_<Clip>` name, the sidecar fields, `compatible_with`, and the new error codes | Must |

## Out of Scope

- Deleting or renaming stale AnimSequences.
- Importing a character's meshes or clips against another character's skeleton asset (one shared skeleton).
- Retargeting between skeletons with different bone names.
- Mobile-specific animation assets; Mobile uses the Desktop skeleton's AnimSequences.
- Creating Animation Blueprints, montages, blend spaces, or root-motion settings.
- Animation compression or curve settings beyond the Unreal import defaults.
- Changing the `export_rigged` operator or `import_animations`.
- Non-humanoid rigs.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #138 | 2026-11-11 | Initial feature spec |
