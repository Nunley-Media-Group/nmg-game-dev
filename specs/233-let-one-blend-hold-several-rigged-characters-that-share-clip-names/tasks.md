# Tasks: Let one .blend hold several rigged characters that share clip names

**Issue**: #233
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley

## Implementation Tasks

### T001: Resolve and probe clips by bare clip name

**File(s)**: `plugins/nmg-game-dev-blender-addon/finalize_core/anims.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- FR1/FR2: `split_action_name`, `ClipResolution`, and `resolve` exist as in design.md. Provenance clips resolve `<Clip>@SK_<Name>` first, then `<Clip>`
- AC1/AC2: `probe`, `clip_hash`, and `export_clips` use the bare clip name for the name, hash payload, file name `A_<Name>_<Clip>.glb`, and provenance lookup
- AC3/FR7: for unsuffixed actions, probe output (names, hashes, `valid_name`) is identical to before
- AC4/AC5: probe reports `rig_mismatch` and `duplicates`. `export_clips` raises `finalize.clip_rig_mismatch` or `finalize.clip_name_duplicate` before writing any file
- AC6/FR5: `valid_name` is computed on the bare clip name

### T002: Fail the export on host for mismatched and duplicate clips

**File(s)**: `src/nmg_game_dev/pipeline/anims.py`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- AC4/FR3: a non-empty probe `rig_mismatch` raises `PipelineError` `finalize.clip_rig_mismatch` (stage `export_anims`), naming each action, with the design's remediation, before any cache lookup, export run, or sidecar write
- AC5/FR4: a non-empty probe `duplicates` raises `finalize.clip_name_duplicate`, naming each clip and its actions, with the design's remediation, at the same point
- The check order is mismatch, then duplicate, then the existing `finalize.clip_name_invalid`. A probe without the new keys behaves as before

### T003: Import clips as per-rig actions

**File(s)**: `plugins/nmg-game-dev-blender-addon/rig_core/retarget.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- AC7/FR6: `bake_builtin_clip` and `bake_clip` install the baked action as `<Clip>@SK_<Name>`, and provenance stays keyed by `<Clip>`
- AC8: re-importing replaces only `<Clip>@SK_<Name>`; no `.001` copy remains; other rigs' actions and unsuffixed actions are untouched

### T004: Document the clip naming rule and the new failures

**File(s)**: `docs/asset-contract.md`, `docs/rigging-and-animation.md`, `docs/mcp/finalize.md`, `skills/finalize-asset/SKILL.md`, `CHANGELOG.md`
**Type**: Modify
**Depends**: T001, T002, T003
**Acceptance**:
- AC9/FR8: `docs/asset-contract.md` §7 "### Animation clips" states that a clip's name is its action's name minus an optional `@SK_<Name>` suffix, that the pattern applies to the bare name, and that a foreign suffix or two actions for one clip stop the export
- `docs/rigging-and-animation.md` says imported clips are stored as `<Clip>@SK_<Name>` and that re-baking replaces only that rig's action
- `docs/mcp/finalize.md` lists `finalize.clip_rig_mismatch` and `finalize.clip_name_duplicate` in its error table with their remediations, and its export_anims row names them
- `skills/finalize-asset/SKILL.md` failure modes list both codes with remediations
- `CHANGELOG.md` `[Unreleased]` has an `### Added` bullet describing per-rig clip names that ends with `(#233)`
- `claude plugin validate .` passes (`plugin.validate`)

### T005: Blender tests for resolution, export, and import

**File(s)**: `tests/blender/test_finalize_anims.py`, `tests/blender/test_rig_builtin_clips.py`, `tests/blender/test_rig_animation.py`
**Type**: Modify
**Depends**: T001, T003
**Acceptance**:
- AC1: `Idle@SK_StreetThug` on `SK_StreetThug` probes as `Idle` and exports `Animations/A_StreetThug_Idle.glb`, and the record's `name` is `Idle`
- AC2: one file with `SK_StreetThug`/`Idle@SK_StreetThug` and `SK_Cop`/`Idle@SK_Cop` exports each rig's own action (the re-imported clip's keyed values differ per rig)
- AC3: the existing unsuffixed-clip tests pass unchanged, and an unsuffixed clip's hash equals the hash computed with `clip_name == action.name`
- AC4/AC5: probe reports `rig_mismatch == ["Idle@SK_Cop"]` and `duplicates == [{"name": "Idle", "actions": ["Idle", "Idle@SK_StreetThug"]}]` for those setups, and `export_clips` raises the matching codes with no file written
- AC6: `1Idle@SK_StreetThug` probes with name `1Idle` and `valid_name` false
- AC7: built-in import (`test_rig_builtin_clips.py`) and library import (`test_rig_animation.py`) of `Idle` onto `SK_Cop` create `Idle@SK_Cop` and leave `Idle@SK_StreetThug` and StreetThug's provenance unchanged
- AC8: re-importing `Idle` onto StreetThug leaves exactly one `Idle@SK_StreetThug` and no `.001`
- `scripts/run-blender-tests.sh` passes (`gate-blender-headless`)

### T006: Host unit tests and the fake probe

**File(s)**: `tests/finalize_fakes.py`, `tests/unit/pipeline/test_anims.py`
**Type**: Modify
**Depends**: T002
**Acceptance**:
- `FakeStepRunner` accepts `rig_mismatch` and `duplicates` and puts them in probe output
- AC4: a fake probe with `rig_mismatch=["Idle@SK_Cop"]` raises `finalize.clip_rig_mismatch`, and no export step runs and no sidecar exists
- AC5: a fake probe with a duplicate raises `finalize.clip_name_duplicate`, with no export and no sidecar
- The order mismatch → duplicate → invalid holds when several are present
- `uv run pytest tests/unit/pipeline/test_anims.py -q` passes; `repository.lint`, `repository.format`, and `repository.types` pass

### T007: BDD scenarios for every acceptance criterion

**File(s)**: `tests/bdd/features/shared_clip_names.feature`, `tests/bdd/test_shared_clip_names_bdd.py`, `tests/blender/test_shared_clip_names_bdd.py`
**Type**: Create
**Depends**: T004, T005, T006
**Acceptance**:
- The feature file carries SCN001–SCN009 from this spec's `feature.gherkin`, one per AC1–AC9
- `tests/blender/test_shared_clip_names_bdd.py` binds SCN001–SCN003, SCN007, and SCN008 with pytest-bdd against real Blender data. Under plain CPython it skips via `pytest.importorskip("bpy")`. It runs under `gate-blender-headless`
- `tests/bdd/test_shared_clip_names_bdd.py` binds SCN004–SCN006 through `FakeStepRunner`, asserting codes and that no clip file or sidecar is written. It binds SCN009 by reading the four docs for the rule text and both codes
- `uv run pytest tests/bdd/test_shared_clip_names_bdd.py -q` passes (`repository.tests`); `scripts/run-blender-tests.sh` passes (`gate-blender-headless`)

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #233 | 2026-11-18 | Initial feature tasks |
