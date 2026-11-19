# Design: Let one .blend hold several rigged characters that share clip names

**Issue**: #233
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley

## Overview

Clip identity moves from "action name" to "action name minus an optional `@SK_<Name>` suffix". Two places change:

- Resolving and probing in `finalize_core/anims.py` (Blender). It reports clips under their bare names, plus any rig-mismatched and duplicate actions it finds.
- Checking in `src/nmg_game_dev/pipeline/anims.py` (host). It turns those probe findings into `finalize.*` errors before any cache lookup or export, the same way `finalize.clip_name_invalid` works today.

Clip import (`rig_core/retarget.py::_install`) writes `<Clip>@<rig name>` and replaces only that action. Unsuffixed files produce byte-identical probe output, so their clip hashes and cache keys do not change.

## Architecture

```text
finalize_entry (Blender, export_anims mode=probe)
  anims.resolve(collection) ─► ClipResolution{clips: {clip → action}, rig_mismatch: [action], duplicates: {clip → [action]}}
  anims.probe(collection)   ─► {clips: [{name: clip, hash, valid_name}], rig_mismatch: [...], duplicates: [{name, actions}], options}
host run_export_anims
  1. rig_mismatch non-empty → PipelineError finalize.clip_rig_mismatch
  2. duplicates non-empty   → PipelineError finalize.clip_name_duplicate
  3. any valid_name false   → PipelineError finalize.clip_name_invalid   (unchanged)
  4. cache check + export (mode=export, names = bare clip names)
finalize_entry (export_anims mode=export)
  anims.export_clips(collection, names, out) uses resolve().clips[name]
```

### `finalize_core/anims.py`

- `split_action_name(action_name: str) -> tuple[str, str | None]`: split at the first `@` and return `(bare, suffix)`. With no `@` the suffix is `None`.
- `@dataclass(frozen=True) ClipResolution` with `clips: dict[str, bpy.types.Action]`, `rig_mismatch: list[str]` (sorted action names), and `duplicates: dict[str, list[str]]` (clip name → sorted action names).
- `resolve(collection_name) -> ClipResolution`:
  1. For each provenance key `clip`, the candidate is `bpy.data.actions.get(f"{clip}@SK_{collection}")`, falling back to `bpy.data.actions.get(clip)`. Use it when found.
  2. For each action the rig holds (its active action and every NLA strip action), split its name. A suffix that is not `None` and not `SK_{collection}` adds the action name to `rig_mismatch`; that action is not a clip. Otherwise the clip name is the bare name.
  3. When two distinct actions resolve to one clip name, record every action for that clip under `duplicates` and drop the clip from `clips`. The same action reached twice, for example through provenance and an NLA strip, is not a duplicate.
- `resolve_clips(collection_name)` keeps its signature and returns `resolve().clips` values sorted by clip name.
- `probe()` lists `resolve().clips` as `{name: clip, hash: clip_hash(rig, clip, action, provenance.get(clip)), valid_name: valid_clip_name(clip)}`. It adds `rig_mismatch` (a list) and `duplicates` (a list of `{name, actions}` sorted by name).
- `clip_hash(rig, clip_name, action, provenance)` puts `clip_name` in the payload's `"clip"` field. For an unsuffixed action that is the same string as before, so AC3's hashes do not move.
- `export_clips()` builds its name → action map from `resolve().clips`. Before its existing checks, it raises `AnimError("finalize.clip_rig_mismatch", …)` or `AnimError("finalize.clip_name_duplicate", …)` when the resolution has either problem. This mirrors its defensive `finalize.clip_name_invalid` check.

### `src/nmg_game_dev/pipeline/anims.py`

`run_export_anims` reads `probe.get("rig_mismatch")` and `probe.get("duplicates")`, treating a missing key as empty, and raises `PipelineError` with `stage="export_anims"` before the existing invalid-name check:

| Code | Message | Remediation |
|------|---------|-------------|
| `finalize.clip_rig_mismatch` | `Actions <names> on SK_<Name> carry an @ suffix for another rig, so nothing was exported.` | `Rename each action to <Clip>@SK_<Name> for this rig, or remove the suffix, then rerun finalize.` |
| `finalize.clip_name_duplicate` | `Clip <clip> comes from more than one action on SK_<Name> (<actions>), so nothing was exported.` (one clause per clip) | `Keep one action per clip on SK_<Name>: delete or rename the extra action, then rerun finalize.` |

### `rig_core/retarget.py`

`_install(armature, action, clip_name)` computes `target = f"{clip_name}@{armature.name}"` (the armature is `SK_<Name>`). It clears the rig's active action, removes `bpy.data.actions.get(target)` when present, then sets `action.name = target` and `use_fake_user = True`. An unsuffixed `clip_name` action and other rigs' suffixed actions are never touched. `bake_builtin_clip` and `bake_clip` keep provenance keyed by `clip.name`. Their docstrings change to "install it as action `<clip>@SK_<Name>`".

### Test fake

`tests/finalize_fakes.py::FakeStepRunner` takes optional `rig_mismatch: Sequence[str] = ()` and `duplicates: Sequence[Mapping[str, Any]] = ()`. The probe output includes them, so host tests can drive AC4 and AC5.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Raise the new errors from Blender (`AnimError` in `probe`) | Rejected | `envelope_outputs` would surface them as `export_anims.finalize.*`; host-side checks keep the `finalize.*` codes and match `clip_name_invalid` |
| Name imported actions `<Clip>@<Name>` without `SK_` | Rejected | The issue fixes the suffix as `@SK_<Name>`, the rig object's name |
| Delete a legacy unsuffixed `<Clip>` action on re-import | Rejected | Another rig may still resolve it through the provenance fallback; renaming legacy actions is out of scope |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #233 | 2026-11-18 | Initial feature design |
