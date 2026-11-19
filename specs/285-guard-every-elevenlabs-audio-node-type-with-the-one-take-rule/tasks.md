# Tasks: Guard every ElevenLabs audio node type with the one-take rule

**Issue**: #285
**Date**: 2026-11-19
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/242-add-a-generate-audio-skill-that-enforces-one-take-instrumental-brief-faithful-elevenlabs-generation/

## Implementation Tasks

### T001: Record the MCP node-type snapshot

**File(s)**: `tests/fixtures/elevenlabs/flow_node_types.json`
**Type**: Create
**Depends**: none
**Acceptance**:
- FR2: the file holds `source`, `captured` (`2026-11-19`), and a `node_types` list of `{"type", "output_modality"}` objects for the 18 types listed in design.md, with the modalities listed there

### T002: Widen the guard's audio node types

**File(s)**: `hooks/generate_audio_guard.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- FR1: `AUDIO_NODE_TYPES` is exactly `("tts", "sfx", "music", "dubbing-audio", "voice-changer", "voice-isolator", "audio-effects", "video-to-music", "composition")`
- Deny reason, reminder text, marker storage, and fail-open behavior are unchanged
- The module and `_is_audio_call` docstrings describe the full set rather than only sfx, music, tts

### T003: Document the guarded node types

**File(s)**: `docs/mcp/elevenlabs.md`, `skills/generate-audio/SKILL.md`
**Type**: Modify
**Depends**: T002
**Acceptance**:
- FR3: `docs/mcp/elevenlabs.md` `## Generation rules` has a `### Guarded node types` table whose `node_type` column lists exactly the nine identifiers in backticks, explains `composition`, and names the unguarded types
- FR4: `skills/generate-audio/SKILL.md` step 5 names all nine identifiers and requires `generations_count: 1` on each; existing phrases asserted by `tests/unit/test_generate_audio_skill.py` stay intact

### T004: Unit tests for the guard set, fixture, and docs

**File(s)**: `tests/unit/test_generate_audio_guard_hook.py`, `tests/unit/test_generate_audio_skill.py`
**Type**: Modify
**Depends**: T001, T002, T003
**Acceptance**:
- AC1: the deny and reminder parametrizations cover all nine node types with counts missing, 0, 2, "1", 1.5, True (deny) and 1 (reminder)
- AC2: a test loads the fixture, derives modality-`audio` types plus `composition`, and asserts the set equals `set(hook.AUDIO_NODE_TYPES)`; a test parses the `### Guarded node types` table in `docs/mcp/elevenlabs.md` and asserts its identifiers equal the same set
- AC3: the non-audio parametrization covers `image-generation`, `video-generation`, `image-transform`, `dubbing-video`, `voice-creation`, `speech-to-text`, `llm` with counts missing, 1, 4: empty output, no marker
- AC4: tests assert every identifier in `AUDIO_NODE_TYPES` appears in the SKILL.md `## Flow` one-take step and in `docs/mcp/elevenlabs.md`, each alongside `generations_count: 1`
- `uv run pytest tests/unit -q` passes

### T005: BDD scenarios for #285

**File(s)**: `tests/bdd/features/generate_audio_node_types.feature`, `tests/bdd/test_generate_audio_node_types_bdd.py`
**Type**: Create
**Depends**: T001, T002, T003
**Acceptance**:
- The feature file carries SCN001-SCN004 from this spec's `feature.gherkin`, with a header comment naming the spec and `# Issue: #285`
- The bindings run the hook as a subprocess with `NMG_GAME_DEV_HOOK_STATE_DIR` under `tmp_path`, as `tests/bdd/test_generate_audio_bdd.py` does, and accept hyphenated `node_type` values
- `uv run pytest tests/bdd -q` passes, and `repository.lint`, `repository.format`, and `repository.types` pass on the new and changed files

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #285 | 2026-11-19 | Initial feature tasks |
