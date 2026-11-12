# Verification Report: Export and import rigged-character animation clips through finalize

**Date**: 2026-11-11
**Issue**: #138
**Reviewer**: Claude (nmg-sdlc verify worker, architecture-reviewer)
**Scope**: Implementation verification against spec
**Verification head**: 4497464e4034edcebae1d7aa45d2d84d370a6b34

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 3 |
| Architecture (SOLID) | 4 |
| Security | 5 |
| Performance | 4 |
| Testability | 3 |
| Error Handling | 4 |
| **Overall** | 3.8 |

### Implementation Status: Fail
**Total Issues**: 4 (2 High, 2 Medium)

The step table, Blender clip probe and export, host per-clip cache, UE import program, CLI and MCP
surfaces, and docs are all in place, and the host unit and BDD suites pass. Two defects block
delivery:

1. **The registered `gate-blender-headless` gate fails (16 tests).** The new
   `tests/blender/test_finalize_anims.py` calls `bpy.ops.wm.read_factory_settings(use_empty=True)`.
   That disables the session-scoped `nmg_game_dev_blender_addon`, so every later operator test
   (`test_inspect_spatial`, `test_rig_operators`, `test_variants`) fails with
   `Calling operator "bpy.ops.nmggamedev.*" error, could not be found`.
2. **AC6 does not hold against real Blender.** `export_anims` probes and exports the cached
   `variants` `.blend`, not the current checkpoint. The asset hash does not cover actions, so after a
   clip-only change `validate`, `bake`, and `variants` are cache hits and the restored `variants.blend`
   still holds the old actions. The probe then reports the old clip hash and serves the stale clip
   from cache. Added clips are also missed. The host tests pass only because `FakeStepRunner`
   returns probe hashes that do not depend on the input `.blend`.

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

- Local verification: Not complete (`gate-blender-headless` failed; `gate-ue-compile` and `plugin.session-smoke` deferred)
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

- Artifact: `.nmg-sdlc/verification/138.json` (head `4497464e4034edcebae1d7aa45d2d84d370a6b34`, tree clean, base `main`)
- Coverage: declared 11, recorded 11, complete `true`; no missing, duplicate, or unknown ids
- Ceiling: **Fail**. The required `gate-blender-headless` failed. The artifact's own ceiling field reads
  `Incomplete` because two required gates were deferred, and a required failure caps the status at Fail.

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | One armature-only FBX per clip with rig export settings | Pass | `finalize_core/anims.py` `ANIM_EXPORT_OPTIONS` imports `_RIG_FBX_OPTIONS` and adds `object_types={"ARMATURE"}`; `_export_one` renames the rig to `Armature`. Headless test `test_one_armature_only_fbx_per_clip_and_each_reimports_as_one_clip` passed |
| AC2 | Provenance clips plus rig-held actions; unrelated actions excluded | Pass | `resolve_clips` (provenance, `animation_data.action`, NLA strips); headless `test_the_clip_set_is_provenance_plus_the_rigs_actions_and_excludes_other` passed |
| AC3 | Sidecar records real clip data and sources | Pass | `pipeline/anims.py` `_write_sidecar`; `export_clips` sets `source` to the provenance source or `"authored"`; headless sidecar test and host tests passed |
| AC4 | Clips import as AnimSequences on the Desktop skeleton | Pass (fake UE) | `unreal/import_anims.py` `_import_clip` (`FBXIT_ANIMATION`, Desktop skeleton, non-AnimSequence check); `test_clips_import_as_anim_sequences_on_the_desktop_skeleton` |
| AC5 | Imported clip checked against the sidecar | Pass (fake UE) | `pipeline/anims.py` `_verify` raises `import_anims.clip_mismatch` naming the clip, expected, and measured values |
| AC6 | Clips cached individually | **Fail** | Per-clip keys exist (`run_export_anims`), but `engine._run_per_clip` passes `last_blend`, which is the cached `variants.blend`. A clip-only change leaves the asset hash unchanged, so that `.blend` holds the old actions and the probe never sees the change. Passes only with `FakeStepRunner` (see Remaining Issues H2) |
| AC7 | Force reruns every clip | Pass | `force` bypasses `cache.get` in both per-clip loops; `test_force_reexports_and_reimports_every_clip` |
| AC8 | Assets without clips pass through | Pass | Early return with no write in `run_export_anims`; no Unreal call in `run_import_anims`; `test_an_unrigged_asset_passes_through_with_no_clips` |
| AC9 | New steps run alone | Pass | `DEPENDS` plus the closure in `ordered_steps`; CLI subcommands come from `STEP_ORDER`; MCP step enum; `test_run_step_export_anims_runs_its_prerequisites_and_returns_the_standard_shape`, CLI and MCP tests |
| AC10 | import_anims needs the Desktop skeleton | Pass (fake UE) | `_raise_blocked` gives `finalize.skeleton_not_found` with the run-`import_ue`-first remediation; the UE program returns before any import |
| AC11 | Invalid clip name stops the export | Pass | Host raises `finalize.clip_name_invalid` from the probe before any export or sidecar write; headless probe test passed |
| AC12 | Stale AnimSequences reported, never deleted | Pass (fake UE) | UE program lists `A_<Name>_*` that are not current clips; nothing deletes them |
| AC13 | Compatible skeletons registered on request | Pass (fake UE) | `_add_compatible` in both directions; result `compatible` list |
| AC14 | Compatible registration is idempotent | Pass (fake UE); live risk | Logic is duplicate-free, but `_compatible_paths` compares `str(item)` of UE soft references to plain paths. Not provable without a live editor (Remaining Issues M1) |
| AC15 | Target must exist and match bone names | Pass (fake UE) | `_check_targets` runs before any import or registration |
| AC16 | No registration without compatible_with | Pass | Empty `compatible` list skips registration; no call when there are no clips |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Step table, dependencies, request fields | Complete | `steps.py`, `request.py`, `result.py`; `_STEP_VERSION = "4"` |
| T002 | Blender clip probe and export | Complete | `finalize_core/anims.py`, `finalize_core/steps.py`, `finalize_entry.py` |
| T003 | Host per-clip export and sidecar | Complete with defect | Wired as designed, but runs on the cached `variants` blend (H2) |
| T004 | Unreal clip import, verification, stale, compatible | Complete | `unreal/import_anims.py`, `pipeline/anims.py` |
| T005 | CLI and MCP surface | Complete | `gate-mcp-schema` passed |
| T006 | Documentation | Complete | `docs/mcp/finalize.md` and `SKILL.md` cover everything; the other docs point to them. `plugin.validate` passed |
| T007 | Tests | Incomplete | Test files exist (named `rigged_animations.feature` and `test_finalize_mcp.py` instead of the names in the task). `gate-blender-headless` fails because of `test_finalize_anims.py` (H1) |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 4 | Blender probe and export, host caching, and UE program each sit in their own module |
| Open/Closed | 4 | `per_clip` flag and `DEPENDS` extend the step table without changing the mesh steps' keys |
| Liskov Substitution | 4 | Per-clip steps return the standard `StepResult` shape |
| Interface Segregation | 4 | `UnrealClientFactory` is created lazily, only when there is work |
| Dependency Inversion | 4 | Runner and Unreal client are injected, so fakes can stand in |

### Layer Separation

The layering follows `steering/structure.md`. Skill and MCP entries call the pipeline. The pipeline composes steps and owns caching. Step implementations live in `finalize_core/` and `unreal/`. The MCP server only wraps `mcp_tools.py`.

### Dependency Flow

`pipeline/anims.py` depends on `unreal/import_anims.py` and `pipeline/steps.py`, and there are no cycles. The Blender side imports `_RIG_FBX_OPTIONS` from `variants_core/export.py`, so the two FBX setting sets cannot drift.

---

## Security Assessment

- [x] Authentication: N/A (local tooling)
- [x] Authorization: N/A
- [x] Input validation: `compatible_with` validated against `^[A-Z][A-Za-z0-9]*/[A-Z][A-Za-z0-9]*$`; clip names validated before any file name is built from them
- [x] Injection prevention: UE parameters are embedded as a double-encoded JSON string literal and decoded with `json.loads`, so no data reaches the program as code
- [x] Data protection: no credentials touched

---

## Performance Assessment

- [x] Async patterns: one probe run plus one export run for all misses; one UE call for all clips
- [x] Caching: per-clip keys, so unchanged clips are not exported again. AC6 is correct by design but broken by the input `.blend` choice (H2)
- [x] Resource management: the Unreal client is opened lazily and closed in `finally`
- [x] Query optimization: N/A

---

## Error Handling Assessment

New codes `finalize.clip_name_invalid`, `finalize.skeleton_not_found`, `finalize.skeleton_mismatch`, `import_anims.clip_mismatch`, `import_anims.failed`, and `export_anims.bad_envelope` all carry a message, remediation, and stage. The UE program always prints one `NMG_RESULT` line and runs every check before it changes anything. `_sampled_keys` falls back to `get_number_of_frames`, which in UE5 can return one less than the sampled key count. That would show up as a false `clip_mismatch` rather than a silent pass (M2).

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1–AC5 | Yes (SCN001–SCN005) | Yes | Yes |
| AC6 | Yes (SCN006) | Yes | Yes with fakes; behavior wrong against real Blender (H2) |
| AC7–AC16 | Yes (SCN007–SCN016) | Yes | Yes |

### Coverage Summary

- Feature files: `tests/bdd/features/rigged_animations.feature`, 16 scenarios
- Step definitions: Implemented (`tests/bdd/test_rigged_animations_bdd.py`)
- Unit tests: `tests/unit/pipeline/test_anims.py`, `tests/unit/test_unreal_import_anims.py`, plus updates to steps, engine, CLI, and MCP tests. Unit and BDD totals: 1026 passed, 13 skipped
- Blender headless: `tests/blender/test_finalize_anims.py` passed by itself; the full suite has 16 failures caused by it (H1)

---

## Exercise Test Results

| Field | Value |
|-------|-------|
| **Reason** | Not applicable. The diff touches no nmg-sdlc `workflows/` or `agents/`. `skills/finalize-asset/SKILL.md` is documentation for this project's own skill, and `plugin.validate` covers it |
| **Recommendation** | None |

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` | Pass | `uv run pytest tests/unit tests/bdd -q`: 1026 passed, 13 skipped |
| `repository.lint` | Pass | `ruff check .`: All checks passed |
| `repository.format` | Pass | `ruff format --check .`: 317 files already formatted |
| `repository.types` | Pass | `mypy src tests`: no issues in 202 source files |
| `gate-blender-headless` | **Fail** | `scripts/run-blender-tests.sh`: 16 failed, 180 passed. All failures are `bpy.ops.nmggamedev.* could not be found` / `Scene has no attribute nmg_game_dev` in `test_inspect_spatial`, `test_rig_operators`, `test_variants` |
| `gate-ue-compile` | Incomplete | Deferred until required local validations pass |
| `gate-mcp-schema` | Pass | MCP tools match `tools.json` for every server |
| `gate-shellcheck` | Not applicable | No `scripts/**.sh` changed |
| `gate-ship-smoke` | Not applicable | No ship paths changed |
| `plugin.validate` | Pass | `claude plugin validate .`: passed with warnings |
| `plugin.session-smoke` | Incomplete | Deferred until required local validations pass |

**Gate Summary**: 6/9 applicable gates passed, 1 failed, 2 incomplete

Root-cause check for `gate-blender-headless`: `test_inspect_spatial.py` alone passes (11 passed). Run after a copy of `test_finalize_anims.py`, its add-on-dependent test fails with `'Scene' object has no attribute 'nmg_game_dev'`. With `read_factory_settings` replaced by `read_homefile(use_empty=True)` in that copy, the test passes. The experiment ran in a temporary directory that was then removed, and the working tree stayed clean.

---

## Fixes Applied

None. This worker may write only `verification-report.md`, so code fixes go back to implementation.

## Remaining Issues

### High Priority

| Field | Value |
|-------|-------|
| **Severity** | High (H1) |
| **Category** | Testing |
| **Location** | `tests/blender/test_finalize_anims.py:120` |
| **Issue** | `bpy.ops.wm.read_factory_settings(use_empty=True)` resets preferences and disables the add-on enabled by the session-scoped `enabled_addon` fixture in `tests/blender/conftest.py`. Every later test that uses `nmggamedev` operators or `Scene.nmg_game_dev` then fails |
| **Impact** | The required `gate-blender-headless` fails (16 tests) |
| **Fix** | Use `bpy.ops.wm.read_homefile(use_empty=True)`, which was confirmed to keep the add-on registered, or clear the objects and actions with `bpy.data` before each FBX re-import |
| **Reason Not Fixed** | Outside this verify worker's writable scope (report only) |

| Field | Value |
|-------|-------|
| **Severity** | High (H2) |
| **Category** | Architecture / Correctness (AC6, FR7) |
| **Location** | `src/nmg_game_dev/pipeline/engine.py` (`execute` → `_run_per_clip(run, step, outputs_by_step, last_blend, ...)`) |
| **Issue** | `export_anims` probes and exports `last_blend`, the `variants` result. `content_hash` (`finalize_core/hashing.py`) does not cover actions. After a clip-only edit, `validate`, `bake`, and `variants` are cache hits, and `_restore_missing` restores the old `variants.blend`, which holds the old actions. The probe returns the old clip hash, so the changed clip is served stale from cache. A clip added after the first finalize is never seen |
| **Impact** | Unreal silently keeps outdated animations. This contradicts AC6 and the docs ("changing one clip re-imports only that clip") |
| **Fix** | Run the `export_anims` probe and export against the current checkpoint (`checkpoint.blend`), which holds the session's current actions. `variants_core` changes only meshes, not `SK_<Name>`. Add a host test whose fake probe reads its hashes from the input `.blend` path, so a stale-blend regression fails |
| **Reason Not Fixed** | Changes source outside this worker's writable scope, and the approved design names the `variants` blend as input, so implementation should decide the fix |

### Medium Priority

| Field | Value |
|-------|-------|
| **Severity** | Medium (M1) |
| **Category** | Error Handling / Correctness (AC14) |
| **Location** | `src/nmg_game_dev/unreal/import_anims.py` `_compatible_paths`, `_add_compatible` |
| **Issue** | `compatible_skeletons` holds soft object pointers. `str(item).split(".")[0]` may not give the plain asset path in UE Python, so the "already present" check could miss and a duplicate could be appended on each run. Appending `unreal.SoftObjectPath` to that array may also need a `SoftObjectPtr` type |
| **Impact** | Possible duplicate registration against a live editor. Fakes cannot show this |
| **Reason Not Fixed** | Needs live UE evidence, and SDLC work does not touch live editors. Recommend a manual check before release |

| Field | Value |
|-------|-------|
| **Severity** | Medium (M2) |
| **Category** | Error Handling |
| **Location** | `src/nmg_game_dev/unreal/import_anims.py` `_sampled_keys` |
| **Issue** | It falls back to `get_number_of_frames` / `get_num_frames` when `get_number_of_sampled_keys` is missing. Those return frames, which can be one less than the sidecar's inclusive `frame_count` |
| **Impact** | Possible false `import_anims.clip_mismatch` against a live editor. It fails closed |
| **Reason Not Fixed** | Needs live UE evidence |

---

## Positive Observations

- `DEPENDS` keeps the six-step chain for `import_ue` the same as before, and `export_anims` does not pull in `reimport` or `import_ue`.
- Per-clip steps leave `input_hash` untouched, so the mesh steps' keys are unchanged, as designed.
- The UE program runs every check (own skeleton, compatible targets, clip measurement) before it registers anything. Stale sequences are reported and never deleted.
- `ANIM_EXPORT_OPTIONS` imports `_RIG_FBX_OPTIONS` rather than copying them.

---

## Recommendations Summary

### Before PR (Must)
- [ ] H1: stop `test_finalize_anims.py` from disabling the add-on, then rerun `gate-blender-headless`
- [ ] H2: run `export_anims` against the current checkpoint, and add a regression test that ties the fake probe to its input `.blend`

### Short Term (Should)
- [ ] M1 and M2: confirm against UE 5.8 by hand before release (soft-pointer comparison, sampled key count)

### Long Term (Could)
- [ ] Bring the T007 test file names back in line with the spec (`rigged_finalize.feature`, `test_finalize_mcp_tools.py`) or update the spec

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `src/nmg_game_dev/pipeline/engine.py` | 1 | H2 |
| `src/nmg_game_dev/pipeline/anims.py` | 0 | |
| `src/nmg_game_dev/pipeline/steps.py` | 0 | |
| `src/nmg_game_dev/pipeline/request.py`, `result.py` | 0 | |
| `src/nmg_game_dev/unreal/import_anims.py` | 2 | M1, M2 |
| `plugins/nmg-game-dev-blender-addon/finalize_core/anims.py`, `steps.py` | 0 | |
| `scripts/blender/finalize_entry.py` | 0 | |
| `src/nmg_game_dev/finalize/__main__.py`, `mcp_tools.py`, `service.py` | 0 | |
| `mcp-servers/finalize/src/finalize_mcp/server.py`, `tools.json` | 0 | |
| `tests/blender/test_finalize_anims.py` | 1 | H1 |
| `tests/finalize_fakes.py` | 0 | The fake probe ignores the input `.blend`, which hides H2 |
| `docs/*.md`, `skills/finalize-asset/SKILL.md` | 0 | FR15 covered |

---

## Recommendation

**Needs fixes**

The required Blender headless gate fails because of test pollution from the new test (H1). The
per-clip cache does not detect clip-only changes against real Blender (H2), so AC6 fails. Both are
small, local fixes. After them, rerun the full registered gate, including the deferred
`gate-ue-compile` and `plugin.session-smoke`.
