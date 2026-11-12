# Verification Report: Export and import rigged-character animation clips through finalize

**Date**: 2026-11-11
**Issue**: #138
**Reviewer**: Claude (nmg-sdlc verify worker, architecture-reviewer)
**Scope**: Implementation verification against spec

**Verification head**: 1e87224d4c4958f3468e2741088c6ed9d4ec632e

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 4 |
| Security | 5 |
| Performance | 4 |
| Testability | 5 |
| Error Handling | 4 |
| **Overall** | 4.5 |

### Implementation Status: Pass
**Total Issues**: 5 (all Low, none blocking)

This is a fresh verification at `1e87224`. Commit `1e87224` rewrote the project's
`plugin.session-smoke` provider. It now starts a headless stream-json Claude Code session with
`--plugin-dir` and polls `mcp_status` control requests, so it no longer drives a Herdr tab that
failed at the folder-trust dialog. That provider failure was the only blocker in the previous report.
The rewritten gate still requires every expected plugin MCP server to report `connected`, so the
gate is no weaker than before.

All 16 acceptance criteria are implemented and covered by tests. Nine of the 11 registered
validations ran and passed. The other two (`gate-shellcheck` and `gate-ship-smoke`) do not apply to
this diff. Coverage is complete, and no ceiling applies.

---

## Issue Scope

- Active issue: #138
- Spec: `specs/138-export-and-import-rigged-character-animation-clips-through-finalize`
- Manifest: `implicit single issue`
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1–AC16]; FR [FR1–FR15]; tasks [T001–T007]; scenarios [SCN001–SCN016]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":138,"specPath":"specs/138-export-and-import-rigged-character-animation-clips-through-finalize","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6","AC7","AC8","AC9","AC10","AC11","AC12","AC13","AC14","AC15","AC16"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6","FR7","FR8","FR9","FR10","FR11","FR12","FR13","FR14","FR15"],"tasks":["T001","T002","T003","T004","T005","T006","T007"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006","SCN007","SCN008","SCN009","SCN010","SCN011","SCN012","SCN013","SCN014","SCN015","SCN016"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

- Artifact: `.nmg-sdlc/verification/138.json`: head `1e87224d4c4958f3468e2741088c6ed9d4ec632e`, tree clean, base `main`, controller run `19935d05-e718-4699-aaee-32edd3c10a71`
- Steering hash `sha256:af4524ef…d318b`; spec hash `sha256:1b267fc9…f4ce5`
- Coverage: 11 declared, 11 recorded, complete `true`. No ids are missing, duplicated, or unknown.
- Ceiling: none (`null`)

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | One animation FBX per clip, armature-only, rig axis settings | Pass | `finalize_core/anims.py:32` (`ANIM_EXPORT_OPTIONS` spreads `_RIG_FBX_OPTIONS`, plus `object_types={"ARMATURE"}` and bake options), `:195` `_export_one` (renames the rig to `Armature` and mutes NLA). Blender test `test_one_armature_only_fbx_per_clip_and_each_reimports_as_one_clip` |
| AC2 | Clip set is provenance plus actions held on the rig; `Other` excluded | Pass | `finalize_core/anims.py:74` `resolve_clips`. Blender test `test_the_clip_set_is_provenance_plus_the_rigs_actions_and_excludes_other` |
| AC3 | `nmg-animations.json` with measured data and source | Pass | `pipeline/anims.py:264` `_write_sidecar`. `export_clips` sets `source` to the provenance dict or `"authored"`. Blender test `test_the_sidecar_fields_match_the_exported_actions_and_sources` |
| AC4 | AnimSequences on the Desktop skeleton; no extra assets; result lists them | Pass | `unreal/import_anims.py:107` `_import_clip` (`FBXIT_ANIMATION`, Desktop skeleton, non-AnimSequence check). `engine.py:400` `_animations_result`. `tests/unit/test_unreal_import_anims.py` |
| AC5 | A frame-count or skeleton difference fails, naming the clip, expected, and measured | Pass | `pipeline/anims.py:368` `_verify` → `import_anims.clip_mismatch`. `test_a_clip_key_count_difference_reports_expected_and_measured` |
| AC6 | Clips cached individually; mesh steps stay cached | Pass | Per-clip keys in `pipeline/anims.py:87`/`:166`. `engine.py:190` keeps per-clip steps out of the whole-step key and `input_hash`, and probes this run's `checkpoint.blend`. Unit and BDD SCN006 tests, plus `test_clips_are_probed_and_exported_from_the_current_checkpoint` |
| AC7 | `force` reruns every clip | Pass | `force` skips `cache.get` in both runners. BDD SCN007 |
| AC8 | No clips: zero clips, nothing written, no UE call | Pass | `pipeline/anims.py:115` (returns before writing), `:182` (no client call). BDD SCN008 |
| AC9 | The new steps run alone via MCP/CLI with dependencies from cache | Pass | `steps.py:90` `DEPENDS`, `:114` `ordered_steps` closure. CLI `_STEP_HELP`, MCP `tools.json` enum. `test_finalize_cli.py`, `test_finalize_mcp.py`, BDD SCN009 |
| AC10 | Missing Desktop skeleton gives `finalize.skeleton_not_found` with the run-`import_ue` remediation | Pass | The UE program returns before any import. `pipeline/anims.py:336` `_raise_blocked`. `test_a_reply_that_reports_no_desktop_skeleton_fails_before_any_clip` |
| AC11 | Invalid clip name gives `finalize.clip_name_invalid`, nothing written | Pass | `pipeline/anims.py:108` raises after the probe, before any export or sidecar write. Blender test `test_an_invalid_clip_name_is_reported_by_the_probe_and_writes_nothing`; BDD SCN011 |
| AC12 | Stale sequences reported, never deleted | Pass | `unreal/import_anims.py:173` only appends to `stale`; the program has no delete call. `test_the_program_lists_stale_sequences_and_never_deletes` |
| AC13 | Two-way compatible registration | Pass | `unreal/import_anims.py:82` `_add_compatible`, applied to both skeletons. BDD SCN013 |
| AC14 | Registration is idempotent | Pass | `_add_compatible` appends only when the path is absent. BDD SCN014 |
| AC15 | Missing or mismatched target: correct code, nothing changed | Pass | `unreal/import_anims.py:91` `_check_targets` runs before any import or registration. `test_a_compatible_bone_mismatch_names_the_bones`; BDD SCN015 |
| AC16 | No `compatible_with` means no registration | Pass | Empty `PARAMS["compatible"]` skips the loop and the save. BDD SCN016 |

### Functional requirements

FR1–FR14 are covered by the AC evidence above. FR10's error codes all carry a message, a remediation,
and a stage (`PipelineError`).

FR15 (documentation) is met across the five documents taken together:

- `docs/mcp/finalize.md` and `skills/finalize-asset/SKILL.md` describe both steps, the layout, the
  name, the sidecar, caching and `force`, stale reporting, `compatible_with`, and all four error
  codes.
- `mcp-servers/finalize/tools.json` carries the step enum and the `compatible_with` schema.
- `docs/asset-contract.md` gives the clip contract, and `docs/rigging-and-animation.md` gives the
  workflow step. Both link to `docs/mcp/finalize.md` for the error codes (see Remaining Issues L1).

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Step table, dependencies, request fields | Complete | `steps.py`, `request.py` (`compatible_with` pattern, dedupe, self-reference rejected), `result.py` |
| T002 | Blender clip probe and export | Complete | `finalize_core/anims.py`, `finalize_core/steps.py` (`_export_anims` probe/export modes), `finalize_entry.py` |
| T003 | Host per-clip export and sidecar | Complete | `pipeline/anims.py`, `engine.py`. Reads `checkpoint.blend` rather than the variants `.blend`; see L4 |
| T004 | Unreal import, verification, stale, compatible | Complete | `unreal/import_anims.py`, `pipeline/anims.py` |
| T005 | CLI and MCP surface | Complete | `__main__.py` (`--compatible-with`, repeatable), `mcp_tools.py`, `server.py`, `tools.json`. `gate-mcp-schema` passed |
| T006 | Documentation | Complete | Four docs and SKILL.md updated. `plugin.validate` passed |
| T007 | Tests | Complete | 24 unit tests in `test_anims.py`, 11 in `test_unreal_import_anims.py`, 7 headless Blender tests, and 16 BDD scenarios in `rigged_animations.feature`. No test touches a live editor |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 4 | Blender probe/export, host cache/sidecar, and UE program generation are separate modules. `engine.execute` grows a per-clip branch but delegates the work |
| Open/Closed | 4 | `StepSpec.per_clip` and `DEPENDS` extend the step table without changing mesh-step keys. `ordered_steps` gives the same six-step chain for `import_ue` |
| Liskov Substitution | 5 | Per-clip steps return the same `StepResult` shape as the other steps |
| Interface Segregation | 4 | `run_import_anims` takes a client factory, so it is called only when there is work |
| Dependency Inversion | 4 | The Unreal client is injected (`FinalizeClients.unreal`) and the Blender runner comes through `StepRunner`, so both can be faked |

### Layer Separation

The change follows the steering layers. Step implementations live in `finalize_core/` and
`src/nmg_game_dev/unreal/`, composition and caching in `pipeline/`, and the MCP server only forwards
arguments. The host never imports `bpy`: the export options fingerprint comes back from the probe.

### Dependency Flow

`pipeline/anims.py` → `unreal/import_anims.py` and `pipeline/steps.py`. There are no cycles.
`finalize_core/anims.py` imports `_RIG_FBX_OPTIONS` from `variants_core/export.py`, so the clip and
mesh exports cannot drift apart. It is a private name used across modules, but the design calls for
it.

---

## Security Assessment

- [x] Authentication: no new credentials or external services.
- [x] Authorization: not applicable (local tooling).
- [x] Input validation: clip names are checked against `^[A-Za-z][A-Za-z0-9_]*$` before any write.
  `compatible_with` items are checked against `^[A-Z][A-Za-z0-9]*/[A-Z][A-Za-z0-9]*$` in pydantic and
  in the MCP schema, and a request cannot name itself.
- [x] Injection prevention: UE parameters are embedded as a doubly JSON-encoded string and read
  with `json.loads`, never by string interpolation into code.
- [x] Data protection: nothing sensitive is logged. The smoke provider spawns `claude` with
  `shell: false`.

---

## Performance Assessment

- [x] Async patterns: Blender work stays in background `blender --background` processes. There is
  one probe run plus at most one export run per finalize.
- [x] Caching: each clip has its own content-addressed key. A clip-only change leaves the mesh steps'
  keys valid.
- [x] Resource management: an owned `UnrealMcpClient` is closed in `finally`. The smoke provider
  removes its temporary project and stops the session in `finally`.
- [x] Query optimization: all clips go to UE in one Python call.

The probe always runs, even when every clip is cached. That costs one headless Blender start per
finalize, which is acceptable.

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1–AC16 | Yes (SCN001–SCN016 in `tests/bdd/features/rigged_animations.feature`) | Yes (`tests/bdd/test_rigged_animations_bdd.py`) | Yes |

### Coverage Summary

- Feature files: 16 scenarios, one per AC, matching `feature.gherkin`
- Step definitions: implemented
- Unit tests: `repository.tests` gave 1027 passed, 13 skipped
- Headless Blender tests: `gate-blender-headless` gave 196 passed, including all 7 in `tests/blender/test_finalize_anims.py`
- Integration/E2E: no live UE run, by design (steering: no live editors in SDLC work). The UE program is checked by compiling it and through fake replies.

---

## Exercise Test Results

| Field | Value |
|-------|-------|
| **Reason** | Not applicable. The diff touches no nmg-sdlc `workflows/` or `agents/`. `skills/finalize-asset/SKILL.md` documents this project's own skill, and `plugin.validate` and `plugin.session-smoke` cover it |
| **Recommendation** | None |

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` | Pass | `uv run pytest tests/unit tests/bdd -q`: 1027 passed, 13 skipped |
| `repository.lint` | Pass | `uv run ruff check .`: All checks passed |
| `repository.format` | Pass | `uv run ruff format --check .`: 317 files already formatted |
| `repository.types` | Pass | `uv run mypy src tests`: no issues in 202 source files |
| `gate-blender-headless` | Pass | `scripts/run-blender-tests.sh`: 196 passed (Blender 5.2) |
| `gate-ue-compile` | Pass | `Build.sh DogfoodEditor Mac Development`: Result: Succeeded (UE 5.8) |
| `gate-mcp-schema` | Pass | `validate-mcp-tools.py`: MCP tools match tools.json for every server |
| `gate-shellcheck` | Not applicable | No `scripts/**.sh` changed |
| `gate-ship-smoke` | Not applicable | No ship paths changed |
| `plugin.validate` | Pass | `claude plugin validate .`: Validation passed with warnings (directory-listing advisories only: LICENSE, icon, privacy URL) |
| `plugin.session-smoke` (real smoke) | Pass | Headless `claude -p --input-format stream-json --plugin-dir <checkout>` in an ephemeral git project. `mcp_status` reported `plugin:nmg-game-dev:blender` `connected` (source `plugin`), which is the expected server |

**Gate Summary**: 9/9 applicable gates passed, 0 failed, 0 incomplete (2 not applicable)

---

## Fixes Applied

| Severity | Category | Location | Original Issue | Fix Applied | Routing |
|----------|----------|----------|----------------|-------------|---------|
| — | — | — | None in this pass. The verify publication scope allows only this report, and nothing blocking was found | — | — |

Earlier fixes on this branch (before this verification): `6460c5b` (export clips from the current
checkpoint, AC6; headless add-on registration) and `1e87224` (headless session-smoke provider).

## Remaining Issues

### Critical Issues
None.

### High Priority
None.

### Medium Priority
None.

### Low Priority

| ID | Severity | Category | Location | Issue | Impact | Reason Not Fixed |
|----|----------|----------|----------|-------|--------|------------------|
| L1 | Low | Documentation | `docs/rigging-and-animation.md`, `docs/asset-contract.md` | These two docs do not list the four error codes or (in asset-contract) `compatible_with` themselves. They link to `docs/mcp/finalize.md`, which covers everything | A reader has to follow one link | FR15 is met across the five documents. The verify scope is report-only |
| L2 | Low | Testability | `src/nmg_game_dev/unreal/import_anims.py` | The reference-bone, sampled-key, and `compatible_skeletons` reads have not been run against a live UE 5.8 editor | A UE API mismatch would surface as `import_anims.failed` or `clip_mismatch` on first real use | No live editors in SDLC work, by steering. The code fails closed. Cover with the manual E2E run before release |
| L3 | Low | Error Handling | `src/nmg_game_dev/unreal/import_anims.py:107` | The non-AnimSequence check runs after `import_asset_tasks`, so a stray asset would already exist when the step fails | The step fails correctly, but the stray asset is left in the folder | Unlikely with `import_mesh=False` and the skeleton set. The design accepts post-check detection |
| L4 | Low | Spec drift | `src/nmg_game_dev/pipeline/engine.py:190` | `export_anims` reads this run's `checkpoint.blend`, not the variants `.blend` named in design.md | The design text is out of date. The behavior is correct and needed for AC6, and the code comment explains it | The spec files are read-only in verify. Update design.md in a follow-up |
| L5 | Low | Correctness | `plugins/nmg-game-dev-blender-addon/finalize_core/anims.py` `_slot_of` | An NLA-strip action not assigned to the rig is hashed and exported through its first slot, not the strip's slot | Only matters for multi-slot actions, which `import_animations` does not create | Edge case; out of scope |

---

## Positive Observations

- The per-clip cache never moves the mesh steps' `input_hash`, so a clip edit cannot invalidate
  bake or variants.
- `ordered_steps` keeps the `import_ue` chain identical to the old behavior, and a test pins it.
- The UE program checks everything before it changes anything, and it never deletes.
- The clip export imports the rig export's FBX settings, so the two cannot drift.

---

## Recommendations Summary

### Before PR (Must)
- [x] None

### Short Term (Should)
- [ ] Run the manual E2E finalize of a rigged character against UE 5.8 to confirm the UE API reads (L2).
- [ ] Update design.md to say `export_anims` reads the checkpoint (L4).

### Long Term (Could)
- [ ] List the error codes in `docs/rigging-and-animation.md` too (L1).

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `src/nmg_game_dev/pipeline/anims.py` | 0 | |
| `src/nmg_game_dev/pipeline/engine.py` | 1 (L4) | |
| `src/nmg_game_dev/pipeline/steps.py` | 0 | |
| `src/nmg_game_dev/pipeline/request.py`, `result.py` | 0 | |
| `src/nmg_game_dev/unreal/import_anims.py` | 2 (L2, L3) | |
| `plugins/nmg-game-dev-blender-addon/finalize_core/anims.py` | 1 (L5) | |
| `plugins/nmg-game-dev-blender-addon/finalize_core/steps.py`, `scripts/blender/finalize_entry.py` | 0 | |
| `src/nmg_game_dev/finalize/__main__.py`, `mcp_tools.py`, `service.py`; `mcp-servers/finalize/*` | 0 | |
| `docs/*`, `skills/finalize-asset/SKILL.md` | 1 (L1) | |
| `steering/extensions/plugin-session-smoke.mjs`, `steering/snippets/project-tech.md` | 0 | Gate still requires `connected` |
| Tests (`tests/unit/**`, `tests/bdd/**`, `tests/blender/test_finalize_anims.py`, `tests/finalize_fakes.py`) | 0 | |

---

## Recommendation

**Ready for PR**

Every acceptance criterion passes with code and test evidence. Every applicable registered gate,
including the real `plugin.session-smoke`, passed at `1e87224d4c4958f3468e2741088c6ed9d4ec632e`, and
the verification artifact is complete with no ceiling. The remaining items are low-severity and do
not block delivery.
