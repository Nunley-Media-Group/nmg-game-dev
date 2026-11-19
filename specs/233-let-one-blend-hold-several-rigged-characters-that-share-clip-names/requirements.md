# Requirements: Let one .blend hold several rigged characters that share clip names

**Issue**: #233
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley

## User Story

**As a** developer authoring a whole cast of rigged characters in one .blend
**I want** each character's animation clips named per rig
**So that** every character can have its own `Idle`, `Walk`, and so on, and finalize exports them without splitting the file into one .blend per character

## Background

Blender action names are unique per file. `export_anims` (`plugins/nmg-game-dev-blender-addon/finalize_core/anims.py`) uses each action's name as the clip name and validates it against `^[A-Za-z][A-Za-z0-9_]*$`, so two characters in one file cannot both have an `Idle` clip. A per-rig name such as `Idle@SK_StreetThug` fails `finalize.clip_name_invalid`.

Clip import has the same limit. `rig_core/retarget.py` names each imported clip's action after the bare clip name, and first deletes any existing action with that name. Importing `Idle` onto a second character in the same file therefore removes the first character's `Idle`. Each rig's `nmg_animations` provenance is keyed by the bare clip name.

This change makes the clip name an action's name minus an optional `@SK_<Name>` suffix, and makes clip import write suffixed actions.

## Acceptance Criteria

### AC1: An @-suffixed action exports under its bare clip name

**Given** rig `SK_StreetThug` holds action `Idle@SK_StreetThug`
**When** `export_anims` probes and exports StreetThug's clips
**Then** the clip is named `Idle`, the file is `Animations/A_StreetThug_Idle.glb`, and `nmg-animations.json` lists it as `Idle`

### AC2: Two characters in one file each export their own clip

**Given** one .blend holds `SK_StreetThug` with `Idle@SK_StreetThug` and `SK_Cop` with `Idle@SK_Cop`
**When** finalize exports each character's clips
**Then** StreetThug gets `A_StreetThug_Idle.glb` from its own action and Cop gets `A_Cop_Idle.glb` from its own action

### AC3: Unsuffixed action names keep working

**Given** a rig whose actions have no `@` suffix, for example `Idle`
**When** `export_anims` runs
**Then** the clip names, files, sidecar, and clip hashes are the same as before this change

### AC4: A suffix naming another rig stops the export

**Given** rig `SK_StreetThug` holds action `Idle@SK_Cop`
**When** `export_anims` runs
**Then** it fails with `finalize.clip_rig_mismatch`, a message naming the action, and a remediation, before writing any clip file or sidecar

### AC5: Two actions giving one clip name stop the export

**Given** rig `SK_StreetThug` holds both `Idle` and `Idle@SK_StreetThug`
**When** `export_anims` runs
**Then** it fails with `finalize.clip_name_duplicate`, a message naming the clip and both actions, and a remediation, before writing any clip file or sidecar

### AC6: The bare clip name is still validated

**Given** rig `SK_StreetThug` holds action `1Idle@SK_StreetThug`
**When** `export_anims` runs
**Then** it fails `finalize.clip_name_invalid`, with the pattern checked against `1Idle`, the clip name with the suffix removed

### AC7: Importing a clip onto one character leaves the others alone

**Given** one .blend holds `SK_StreetThug` and `SK_Cop`, and StreetThug already has an imported `Idle`
**When** `Idle` is imported onto Cop, from the built-in library or an animation library
**Then** Cop gets action `Idle@SK_Cop`, StreetThug's `Idle@SK_StreetThug` action and provenance are unchanged, and each rig's provenance is keyed by `Idle`

### AC8: Re-importing a clip replaces only that rig's action

**Given** `SK_StreetThug` already has `Idle@SK_StreetThug`
**When** `Idle` is imported onto StreetThug again
**Then** StreetThug's previous `Idle@SK_StreetThug` action is replaced, no `Idle@SK_StreetThug.001` is left, and no other rig's action changes

### AC9: The rule is documented

**Given** `docs/asset-contract.md` §7 "Animation clips", `docs/rigging-and-animation.md`, `docs/mcp/finalize.md`, and `skills/finalize-asset/SKILL.md`
**When** a reader looks up how clip names are derived
**Then** the docs state the `<Clip>@SK_<Name>` rule, that the suffix is optional, that the pattern applies to the bare clip name, and the `finalize.clip_rig_mismatch` and `finalize.clip_name_duplicate` failures with their remediations

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | A clip's name is its action's name with an optional `@SK_<Name>` suffix removed, where `<Name>` is the asset being finalized. Probe, clip hash, export file name, sidecar, and provenance lookup all use that clip name | Must |
| FR2 | Provenance clips resolve to the rig's `<Clip>@SK_<Name>` action, falling back to an action named `<Clip>` | Must |
| FR3 | An action held by the rig whose `@` suffix is not `SK_<Name>` fails the export with `finalize.clip_rig_mismatch` before any file is written | Must |
| FR4 | Two distinct actions on one rig that resolve to the same clip name fail the export with `finalize.clip_name_duplicate` before any file is written | Must |
| FR5 | `^[A-Za-z][A-Za-z0-9_]*$` is checked against the bare clip name and still fails `finalize.clip_name_invalid` | Must |
| FR6 | Built-in and library clip import store each baked clip as action `<Clip>@SK_<Name>`, replace only that rig's previous action for the clip, and keep provenance keyed by the bare clip name | Must |
| FR7 | Files authored with unsuffixed action names export unchanged | Must |
| FR8 | `docs/asset-contract.md` §7 "Animation clips", `docs/rigging-and-animation.md`, `docs/mcp/finalize.md`, and `skills/finalize-asset/SKILL.md` describe the naming rule and the two new failure codes | Must |

## Out of Scope

- Deriving clip names from NLA track or strip names
- Renaming existing unsuffixed actions in consumer files automatically
- Changing the exported file layout (`A_<Name>_<Clip>.glb`), the sidecar fields, or the Godot animation library paths
- Removing stale animation libraries from the Godot project

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #233 | 2026-11-18 | Initial feature spec |
