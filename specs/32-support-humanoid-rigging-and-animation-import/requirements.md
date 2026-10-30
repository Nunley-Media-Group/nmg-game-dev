# Requirements: Humanoid rigging and animation import

**Issue**: #32
**Date**: 2026-10-29
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/30-add-contract-validation-re-import-check-and-review-renders/

## User Story

**As an** NMG game developer
**I want** the agent to rig a humanoid it modeled and bake clips from a local animation library onto it, entirely in Blender
**So that** the character reaches Unreal as a skeletal mesh with animations on a UE5 Mannequin-compatible skeleton, with no paid or rate-limited service involved

## Background

Characters are modeled freeform by the agent through the Blender MCP, and `docs/asset-contract.md` defines the deliverable. Rigging is prompt-driven. From the request and its own model, the agent declares the body type and supplies joint landmarks (world-space points such as pelvis, shoulders, elbows, knees, and ankles). The tooling validates those inputs and builds the rig. It never tries to detect anatomy itself.

The deform skeleton uses UE5 Mannequin bone names and hierarchy, so the exported FBX imports into Unreal as a skeletal mesh whose skeleton matches UE's Manny-based animation. Prepared clips come from a local library folder and are retargeted onto that skeleton and baked in Blender. Every unsupported request reports a status (`fallback required` or `follow-up spike required`) and never calls an external service.

The functions live in the Blender add-on's `rig_core` package. The agent calls them through `execute_blender_code`, and three add-on operators wrap them.

## Acceptance Criteria

### AC1: Humanoid rigging uses local Blender tooling

**Given** a clean humanoid fixture mesh `SM_Hero` in collection `Hero` in a neutral T-pose, and a landmarks dict for it
**When** `rig_humanoid("Hero", body_type="humanoid", landmarks=...)` runs with outbound network connections blocked
**Then** it returns `status: "ok"`, and collection `Hero` contains armature `SK_Hero` whose bones are exactly the 26 UE5 Mannequin deform bones (`root`, `pelvis`, `spine_01`–`spine_05`, `neck_01`, `neck_02`, `head`, `clavicle_{l,r}`, `upperarm_{l,r}`, `lowerarm_{l,r}`, `hand_{l,r}`, `thigh_{l,r}`, `calf_{l,r}`, `foot_{l,r}`, `ball_{l,r}`) in the Mannequin parent hierarchy
**And** `SM_Hero` is parented to `SK_Hero` with an Armature modifier, and every vertex has a non-zero weight on at least one bone
**And** no network connection was attempted and the Rigify add-on was not enabled
**And** running it again replaces the rig, leaving exactly one `SK_Hero` with the same bones

### AC2: Animation import is library-based

**Given** the rigged `Hero` and a local animation library folder whose `library.json` lists an FBX clip `Idle` and a BVH clip `Walk` authored on a Mixamo-named skeleton
**When** `import_animations("Hero", library_dir)` runs and then `export_rigged("Hero", out_dir)` runs
**Then** `out_dir/SM_Hero.fbx` re-imported in a fresh Blender process contains the 26 Mannequin bones with no leaf bones and no extra root node, plus actions for `Idle` and `Walk` with their library frame ranges
**And** at a sampled frame, the world-space rotation of `thigh_l` relative to its rest pose matches the source `LeftUpLeg` within 1°
**And** `out_dir/nmg-animations.json` lists each clip's name, frame range, frame count, and fps, plus provenance: library name, source file path relative to the library, source file SHA-256, and source skeleton

### AC3: Unsupported shapes fail honestly

**Given** one of these requests: a `quadruped` or `non_biped` body type; humanoid landmarks that are asymmetric, out of vertical order, or on the wrong side; a humanoid whose arms are raised above horizontal or whose elbows or knees are bent; a text-driven motion request (`motion_prompt`); or a clip name the library does not list
**When** the matching function runs
**Then** it returns, respectively, `follow-up spike required` with code `rig.unsupported_body`; `fallback required` with `rig.unclear_humanoid`; `fallback required` with `rig.pose_not_neutral`; `follow-up spike required` with `anim.text_motion_unsupported`; or `fallback required` with `anim.clip_not_found`
**And** each result has `message` and `remediation`, every `fallback required` remediation names manual Mixamo rigging only as an optional fallback, no network connection is attempted, and failed rigging leaves the scene unchanged

### AC4: Operators share the implementation

**Given** the add-on is enabled
**When** `nmggamedev.rig_humanoid`, `nmggamedev.import_animations`, or `nmggamedev.export_rigged` runs
**Then** each calls the same `rig_core` function as a direct call, stores the same result JSON on `scene.nmg_game_dev.last_result`, returns `FINISHED` when `status` is `ok`, and otherwise returns `CANCELLED` with the code, message, and remediation reported

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | `rig_core.rig_humanoid(collection, body_type, landmarks)` builds a deform-only UE5 Mannequin-named armature `SK_<Name>` from agent-supplied landmarks and skins every mesh in the collection with automatic weights, using only Blender built-ins (no Rigify) | Must |
| FR2 | `rig_core.import_animations(collection, library_dir, clips=None, motion_prompt=None)` reads `library.json`, imports FBX or BVH clips, retargets them through a built-in `mixamo` or `manny` bone map or the library's custom `bone_map`, and bakes one action per clip with provenance | Must |
| FR3 | Body type, landmark completeness, symmetry, vertical ordering, side convention, bounds, and neutral pose (T or A) are validated before any scene change | Must |
| FR4 | No code path calls Mixamo or any network service. Mixamo appears only in `fallback required` remediation text as an optional manual fallback | Must |
| FR5 | `rig_core.export_rigged(collection, out_dir)` writes `SM_<Name>.fbx` with the deform skeleton, the skinned meshes, and every baked clip, plus material PNGs and `nmg-animations.json` | Must |
| FR6 | Operators `nmggamedev.rig_humanoid`, `nmggamedev.import_animations`, and `nmggamedev.export_rigged` wrap the three functions and are listed in the add-on panel | Must |
| FR7 | Blender headless tests cover humanoid success, library retargeting and export, every unsupported status in AC3, and operator parity | Must |
| FR8 | `docs/asset-contract.md` describes rigged assets, and `docs/rigging-and-animation.md` documents the agent flow, landmark keys, `library.json` format, and statuses | Must |

## Out of Scope

- Quadruped or non-biped auto-rigging, and text-driven custom motion generation (reported as statuses only)
- Detecting landmarks or body type automatically from the mesh
- Rigify control rigs and in-Blender hand-animation tooling
- Finger, facial, twist, and IK helper bones (`ik_foot_root`, `ik_hand_gun`, and similar)
- Producing a Mobile variant of a rigged character (skin-aware decimation, bone reduction), which belongs to #33's variant work
- Importing the skeletal mesh and clips into Unreal, and Unreal-side retargeting (finalize, #69)
- Armature rules in the contract validator (#30)

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #32 | 2026-10-29 | Initial feature spec |
