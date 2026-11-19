# Design: Match sound files case-insensitively, report duplicate sound names, and document refresh errors

**Issue**: #302
**Date**: 2026-11-19
**Status**: Approved
**Author**: Claude (nmg-sdlc write-spec)

---

## Overview

A narrow change to the Audio name-table builder plus documentation. `_sounds` in
`src/nmg_game_dev/audio/tables.py` matches extensions case-insensitively and groups files by stem;
any stem with more than one file raises a new `AudioError` (`audio.duplicate_sound`). Because
`refresh_tables` calls `render_table` (and so `_sounds`) before its write loop, a duplicate leaves
every table untouched. The existing callers already route `AudioError`: the MCP tool returns it as
an error object, `import_audio` turns it into `refresh_warning`, the CLI prints `ERROR [code]` and
exits 1, and `/design scaffold` reports it and exits 1. The rest is description and doc text.

---

## Architecture

```
import_audio ─┐                       ┌─ render_table ─ _sounds (case-insensitive suffix,
refresh CLI  ─┼─ refresh_tables(root) ┤                           duplicate stems → AudioError)
MCP refresh  ─┘                       └─ write loop (never reached on duplicate)
```

---

## Changes

### `src/nmg_game_dev/audio/tables.py`
- Add `DUPLICATE_SOUND: Final = "audio.duplicate_sound"`.
- `_sounds`: accept `path.suffix.lower() in SOUND_SUFFIXES`; collect `files_by_stem: dict[str, list[str]]`
  over the sorted directory listing; if any stem has more than one file, raise
  `AudioError(code=DUPLICATE_SOUND, message=..., remediation=...)` naming every duplicate group's
  file names (sorted), e.g. `Sound name Theme has more than one file under game/assets/Audio/: Theme.ogg, Theme.wav.`;
  remediation: `Keep one file per sound name: rename or delete the extra file (Theme.ogg or Theme.wav), then refresh the audio tables again.`
  Otherwise return `{stem: "res://assets/Audio/<real file name>"}`.
- Update the module and `refresh_tables` docstrings to list `audio.duplicate_sound` and the
  case-insensitive match.

### `src/nmg_game_dev/finalize/mcp_tools.py`
- `refresh_audio_table` docstring lists all five codes. No logic change (it already catches `PipelineError`).

### `src/nmg_game_dev/audio/core.py`
- `import_audio` docstring: refresh_warning covers any refresh error, including a duplicate sound name. No logic change.

### `mcp-servers/finalize/tools.json`
- `refresh_audio_table.description`: replace "or an error object with audio.godot_project_missing"
  with an error-object sentence naming `audio.godot_project_missing`, `audio.backlog_invalid`,
  `audio.table_unreadable`, `audio.table_unwritable`, and `audio.duplicate_sound`.
- `import_audio.description`: mention that a failed table refresh returns `refresh_warning` (code
  and remediation) while the sound is still imported.

### `docs/mcp/finalize.md`
- `refresh_audio_table` section: add `audio.duplicate_sound` (two files under `game/assets/Audio/`
  share a sound name, such as `Theme.wav` and `Theme.ogg`; nothing is written; rename or delete one
  file, then refresh) and note extensions match in any case.
- `import_audio` refresh paragraph: add `audio.duplicate_sound` to the `refresh_warning` codes.

### `docs/mcp/elevenlabs.md`
- Audio component flow step 3 (Refresh): one sentence that a sound name holds one file; two files
  with the same name stop the refresh with `audio.duplicate_sound` until one is renamed or deleted.

### `skills/generate-audio/SKILL.md`
- Flow step 7: after reporting `godot_asset`, when the result has `refresh_warning`, report its
  `message` and `remediation` to the user and say the sound is still imported.
- Failure modes: a `refresh_warning` bullet naming its codes (`audio.backlog_invalid`,
  `audio.table_unreadable`, `audio.table_unwritable`, `audio.duplicate_sound`): the sound was
  imported; the name tables were not refreshed; report the remediation; after fixing, call
  `refresh_audio_table`. Do not re-import.

---

## Alternatives Considered

| Option | Decision |
|--------|----------|
| Prefer `.ogg` over `.wav` on a stem collision | Rejected: the issue requires a reported failure, not a silent choice |
| Detect duplicates only in `refresh_tables` | Rejected: `render_table` also feeds `/design scaffold`, which would still collapse silently |

---

## Testing Strategy

| Layer | Location | Covers |
|-------|----------|--------|
| Unit | `tests/unit/audio/test_tables.py` | uppercase suffix mapped; duplicate stems raise with both names; table bytes unchanged; three-file group named |
| Unit | `tests/unit/test_finalize_mcp.py` | MCP `refresh_audio_table` returns `audio.duplicate_sound`; `tools.json` description names all five codes |
| Unit | `tests/unit/audio/test_core.py` | `import_audio` with a pre-existing same-stem file returns `refresh_warning.code == "audio.duplicate_sound"` and `imported_to_godot` result intact |
| Unit | `tests/unit/test_generate_audio_skill.py` | skill import step names `refresh_warning`, remediation, and still-imported |
| BDD | `tests/bdd/features/audio_table_names.feature` + `tests/bdd/test_audio_table_names_bdd.py` | AC1–AC4 scenarios |

---

## Risks

| Risk | Mitigation |
|------|------------|
| A consumer already has same-stem files and refresh starts failing | Intended: the error names the files and the remediation; import still succeeds with `refresh_warning` |

---

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #302 | 2026-11-19 | Initial feature spec |
