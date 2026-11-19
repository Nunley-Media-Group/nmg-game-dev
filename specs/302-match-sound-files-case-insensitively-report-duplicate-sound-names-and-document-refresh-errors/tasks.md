# Tasks: Match sound files case-insensitively, report duplicate sound names, and document refresh errors

**Issue**: #302
**Date**: 2026-11-19
**Status**: Approved
**Author**: Claude (nmg-sdlc write-spec)

---

## Summary

| Phase | Tasks |
|-------|-------|
| Implementation | T001–T002 |
| Documentation | T003–T004 |
| Testing | T005–T007 |

---

### T001: Match extensions case-insensitively and reject duplicate stems

**File(s)**: `src/nmg_game_dev/audio/tables.py`
**Type**: Modify
**Depends**: None
**Acceptance**:
- [ ] `_sounds` maps `Click.WAV` to `res://assets/Audio/Click.WAV` (AC1)
- [ ] Two or more files sharing a stem raise `AudioError` code `audio.duplicate_sound` whose message names every such file and whose remediation says to rename or delete the extra file, then refresh again (AC2)
- [ ] `refresh_tables` raises before writing, so an existing table's bytes are unchanged (AC2)
- [ ] Module and `refresh_tables` docstrings list `audio.duplicate_sound`

### T002: Update caller docstrings for the new code

**File(s)**: `src/nmg_game_dev/finalize/mcp_tools.py`, `src/nmg_game_dev/audio/core.py`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- [ ] `refresh_audio_table` docstring names all five refresh error codes
- [ ] `import_audio` docstring says `refresh_warning` carries any refresh error, including `audio.duplicate_sound`

### T003: List every refresh error code in the tool descriptions

**File(s)**: `mcp-servers/finalize/tools.json`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- [ ] `refresh_audio_table` description names `audio.godot_project_missing`, `audio.backlog_invalid`, `audio.table_unreadable`, `audio.table_unwritable`, and `audio.duplicate_sound` (AC3)
- [ ] `import_audio` description says a failed table refresh returns `refresh_warning` with code and remediation while the sound is still imported
- [ ] `uv run python scripts/validate-mcp-tools.py` passes

### T004: Document the duplicate-name resolution and handle refresh_warning in the skill

**File(s)**: `docs/mcp/finalize.md`, `docs/mcp/elevenlabs.md`, `skills/generate-audio/SKILL.md`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- [ ] `docs/mcp/finalize.md` refresh_audio_table section documents `audio.duplicate_sound`, that nothing is written, and the rename-or-delete resolution; its import_audio paragraph lists `audio.duplicate_sound` among `refresh_warning` codes (AC2)
- [ ] `docs/mcp/elevenlabs.md` Refresh step states one file per sound name and the `audio.duplicate_sound` resolution
- [ ] `skills/generate-audio/SKILL.md` import step says to report `refresh_warning` with its remediation and that the sound is still imported; failure modes add a `refresh_warning` bullet (AC4)

### T005: Unit tests for the table builder, MCP tool, and import

**File(s)**: `tests/unit/audio/test_tables.py`, `tests/unit/test_finalize_mcp.py`, `tests/unit/audio/test_core.py`
**Type**: Modify
**Depends**: T001, T003
**Acceptance**:
- [ ] Test: uppercase `.WAV` and `.OGG` files are mapped by stem to their real file names (AC1)
- [ ] Test: `Theme.wav` + `Theme.ogg` raises `audio.duplicate_sound` naming both files and leaves the table bytes unchanged (AC2)
- [ ] Test: MCP `refresh_audio_table` returns `{"error": {"code": "audio.duplicate_sound", "stage": "audio", ...}}` (AC2)
- [ ] Test: the `tools.json` `refresh_audio_table` description contains all five codes (AC3)
- [ ] Test: `import_audio` with a same-stem file already in `game/assets/Audio/` returns `refresh_warning.code == "audio.duplicate_sound"` and still returns `godot_asset` (FR3)
- [ ] `uv run pytest tests/unit -q` passes

### T006: Skill contract test for refresh_warning

**File(s)**: `tests/unit/test_generate_audio_skill.py`
**Type**: Modify
**Depends**: T004
**Acceptance**:
- [ ] Test: the Flow import step mentions `refresh_warning`, its remediation, and that the sound is still imported (AC4)

### T007: BDD scenarios

**File(s)**: `tests/bdd/features/audio_table_names.feature`, `tests/bdd/test_audio_table_names_bdd.py`
**Type**: Create
**Depends**: T001, T003, T004
**Acceptance**:
- [ ] Scenarios for AC1–AC4 from `specs/302-…/feature.gherkin` bound with pytest-bdd against temp projects (no Godot runs)
- [ ] `uv run pytest tests/bdd -q` passes
- [ ] `uv run ruff check .`, `uv run ruff format --check .`, and `uv run mypy src tests` pass

---

## Dependency Graph

```
T001 ──┬──▶ T002
       ├──▶ T003 ──┐
       ├──▶ T004 ──┼──▶ T006
       │           ▼
       └─────────▶ T005, T007
```

---

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #302 | 2026-11-19 | Initial feature spec |
