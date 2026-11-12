# Verification Report: Export and import rigged-character animation clips through finalize

**Date**: 2026-11-11
**Issue**: #138
**Reviewer**: Claude (nmg-sdlc verify worker, architecture-reviewer)
**Scope**: Implementation verification against spec

**Verification head**: 6460c5bf2bc7c2e5a971393bcd2553e273ced9ec

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 4 |
| Security | 5 |
| Performance | 4 |
| Testability | 4 |
| Error Handling | 4 |
| **Overall** | 4.3 |

### Implementation Status: Fail
**Total Issues**: 3 (1 High, 2 Medium)

Commit `6460c5b` fixed both blockers from the previous verification:

- **H1 (headless test pollution) is fixed.** `tests/blender/test_finalize_anims.py` now resets with
  `read_homefile(use_empty=True)`, and `gate-blender-headless` passes (196 passed).
- **H2 (AC6 stale clips) is fixed.** `engine.execute` now runs `export_anims` against this run's
  `checkpoint.blend` instead of the cached `variants` `.blend`. A regression test
  (`test_clips_are_probed_and_exported_from_the_current_checkpoint`) checks that the probe and export
  read the checkpoint.

Every acceptance criterion is now met in code and tests. Ten of the 11 registered gates passed or did
not apply, including `gate-ue-compile`.

The required **`plugin.session-smoke` gate failed**, so the status is Fail. The failure is in the
project's smoke provider (`steering/extensions/plugin-session-smoke.mjs`) and the host tooling, not in
#138's code. Herdr 0.9.5's `agent start` reports `agent_not_ready` ("blocked during startup") about
5 s after Claude Code shows its folder-trust dialog. The provider's trust-accept poll does not get
there first, so the run stops before it ever loads the plugin. The cause and a tested repair are
under Remaining Issues H1.

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

- Local verification: Not complete (required `plugin.session-smoke` failed)
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

- Artifact: `.nmg-sdlc/verification/138.json` (head `6460c5bf2bc7c2e5a971393bcd2553e273ced9ec`, tree clean, base `main`, run `d07f47ec-de6c-4fe0-8483-935880e86b8d`)
- Coverage: declared 11, recorded 11, complete `true`; no missing, duplicate, or unknown ids
- Ceiling: **Fail**, because the required `plugin.session-smoke` failed

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | One armature-only FBX per clip with rig export settings | Pass | `finalize_core/anims.py` `ANIM_EXPORT_OPTIONS` imports `_RIG_FBX_OPTIONS` and adds `object_types={"ARMATURE"}`; the rig is renamed `Armature` for export; headless `test_one_armature_only_fbx_per_clip_and_each_reimports_as_one_clip` passed |
| AC2 | Provenance clips plus rig-held actions; unrelated actions excluded | Pass | `resolve_clips`; headless `test_the_clip_set_is_provenance_plus_the_rigs_actions_and_excludes_other` passed |
| AC3 | Sidecar records real clip data and sources | Pass | `pipeline/anims.py` sidecar writer (`asset`, `armature`, `skeleton`, per-clip fields; `source` is the provenance or `"authored"`); headless and host tests passed |
| AC4 | Clips import as AnimSequences on the Desktop skeleton | Pass (fake UE) | `unreal/import_anims.py` `_import_clip` (`FBXIT_ANIMATION`, Desktop skeleton, rejects any non-AnimSequence) |
| AC5 | Imported clip checked against the sidecar | Pass (fake UE) | Host verification raises `import_anims.clip_mismatch` naming the clip, expected value, and measured value |
| AC6 | Clips cached individually | Pass | Per-clip keys in `run_export_anims` and `run_import_anims`. `engine.execute` now passes `checkpoint` to `_run_per_clip`, so a clip-only change is probed from the current scene. Mesh step keys are unchanged. Regression test `test_clips_are_probed_and_exported_from_the_current_checkpoint` |
| AC7 | Force reruns every clip | Pass | `force` bypasses `cache.get` in both per-clip loops; `test_force_reexports_and_reimports_every_clip` |
| AC8 | Assets without clips pass through | Pass | Early return with no writes in `run_export_anims`; no Unreal call in `run_import_anims` |
| AC9 | New steps run alone | Pass | `DEPENDS` closure in `ordered_steps`; CLI subcommands from `STEP_ORDER`; MCP step enum; CLI, MCP, and engine tests |
| AC10 | import_anims needs the Desktop skeleton | Pass (fake UE) | `finalize.skeleton_not_found` with the run-`import_ue`-first remediation; the UE program returns before any import |
| AC11 | Invalid clip name stops the export | Pass | Raised from the probe before any export or sidecar write |
| AC12 | Stale AnimSequences reported, never deleted | Pass (fake UE) | Stale `A_<Name>_*` listed; no delete call exists |
| AC13 | Compatible skeletons registered on request | Pass (fake UE) | `_add_compatible` in both directions; result `compatible` list |
| AC14 | Compatible registration is idempotent | Pass (fake UE); live risk | Duplicate-free logic. A live-editor soft-pointer comparison risk remains (M1) |
| AC15 | Target must exist and match bone names | Pass (fake UE) | `_check_targets` runs before any import or registration |
| AC16 | No registration without compatible_with | Pass | Empty `compatible_with` skips registration |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Step table, dependencies, request fields | Complete | `steps.py`, `request.py`, `result.py`; `_STEP_VERSION = "4"` |
| T002 | Blender clip probe and export | Complete | `finalize_core/anims.py`, `finalize_core/steps.py`, `finalize_entry.py` |
| T003 | Host per-clip export and sidecar | Complete | Runs against the checkpoint since `6460c5b`. The design text names the `variants` result as input, but the checkpoint holds the same `SK_<Name>`, because the variants step changes only meshes |
| T004 | Unreal clip import, verification, stale, compatible | Complete | `unreal/import_anims.py`, `pipeline/anims.py` |
| T005 | CLI and MCP surface | Complete | `gate-mcp-schema` passed |
| T006 | Documentation | Complete | `docs/mcp/finalize.md` updated for the checkpoint input; `plugin.validate` passed |
| T007 | Tests | Complete | Files are named `rigged_animations.feature` and `test_finalize_mcp.py` rather than the names in the task. Headless gate passes |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 4 | Blender probe and export, host caching, and the UE program each live in their own module |
| Open/Closed | 4 | The `per_clip` flag and `DEPENDS` extend the step table without moving mesh step keys |
| Liskov Substitution | 4 | Per-clip steps return the standard `StepResult` shape |
| Interface Segregation | 4 | The Unreal client is created lazily, only when there is work |
| Dependency Inversion | 4 | Runner and Unreal client are injected, so fakes stand in |

### Layer Separation

The layering follows `steering/structure.md`. The skill and MCP entries call the pipeline, which composes the steps and owns caching. The step implementations live in `finalize_core/` and `unreal/`. The MCP server only wraps `mcp_tools.py`.

### Dependency Flow

No cycles. `pipeline/anims.py` depends on `unreal/import_anims.py` and `pipeline/steps.py`. `ANIM_EXPORT_OPTIONS` imports `_RIG_FBX_OPTIONS`, so the rigged mesh export and the clip export cannot drift apart. Reading clips from the checkpoint is sound: nothing in `variants_core/` or `bake_core/` rewrites the `SK_<Name>` armature. Mobile works on copies, and cleanup touches only mesh modifiers.

---

## Security Assessment

- [x] Authentication: N/A (local tooling)
- [x] Authorization: N/A
- [x] Input validation: `compatible_with` matches `^[A-Z][A-Za-z0-9]*/[A-Z][A-Za-z0-9]*$`; clip names are validated before any file name is built
- [x] Injection prevention: UE parameters are embedded as a JSON string literal and decoded with `json.loads`
- [x] Data protection: no credentials touched

---

## Performance Assessment

- [x] Async patterns: one probe run plus one export run for all misses; one UE call for all clips
- [x] Caching: per-clip keys, with clip-only changes now detected from the checkpoint
- [x] Resource management: the Unreal client opens lazily and closes in `finally`
- [x] Query optimization: N/A

---

## Error Handling Assessment

The codes `finalize.clip_name_invalid`, `finalize.skeleton_not_found`, `finalize.skeleton_mismatch`, `import_anims.clip_mismatch`, `import_anims.failed`, and `export_anims.bad_envelope` all carry a message, remediation, and stage. The UE program runs every check before it changes anything. `_sampled_keys` falls back to frame-count APIs (M2).

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1–AC16 | Yes (SCN001–SCN016) | Yes | Yes |

### Coverage Summary

- Feature file: `tests/bdd/features/rigged_animations.feature`, 16 scenarios, with steps in `tests/bdd/test_rigged_animations_bdd.py`
- Unit and BDD: 1027 passed, 13 skipped
- Blender headless: 196 passed, including `tests/blender/test_finalize_anims.py`

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
| `repository.lint` | Pass | `ruff check .`: All checks passed |
| `repository.format` | Pass | `ruff format --check .`: 317 files already formatted |
| `repository.types` | Pass | `mypy src tests`: no issues in 202 source files |
| `gate-blender-headless` | Pass | `scripts/run-blender-tests.sh`: 196 passed |
| `gate-ue-compile` | Pass | DogfoodEditor compiled against `/Users/Shared/Epic Games/UE_5.8` |
| `gate-mcp-schema` | Pass | MCP tools match `tools.json` for every server |
| `gate-shellcheck` | Not applicable | No `scripts/**.sh` changed |
| `gate-ship-smoke` | Not applicable | No ship paths changed |
| `plugin.validate` | Pass | `claude plugin validate .`: passed with warnings |
| `plugin.session-smoke` | **Fail** | `herdr agent start ... -- --plugin-dir <checkout>` returned `agent_not_ready`: "blocked during startup and is not ready for prompts". No `/mcp` check ran |

**Gate Summary**: 8/9 applicable gates passed, 1 failed

### Smoke diagnosis

I reproduced the failure outside the gate in disposable Herdr tabs, each in a fresh `git init` temp project. All the tabs were closed afterwards.

1. With the provider's exact `herdr agent start` arguments, Claude Code shows the folder-trust dialog ("Yes, I trust this folder"). Herdr 0.9.5 exits with status 1 and `agent_not_ready` after about 4.9 s.
2. The provider (`steering/extensions/plugin-session-smoke.mjs`) accepts the trust dialog only inside a `while (started === null)` loop that polls every 2 s. Once `agent start` has returned, the loop exits, and then `started.status !== 0` fails the gate. The evidence has no "trust ephemeral project" entry, so the poll never saw the dialog before Herdr gave up.
3. After that `agent_not_ready` result, sending `down enter` to the pane accepted the trust dialog. The session then became ready (`interactive_ready: true`), `herdr agent prompt <label> /mcp` succeeded, and the `/mcp` panel rendered.

This is a defect in the project's smoke provider and its Herdr interaction, not in #138's change. The branch changes only `skills/finalize-asset/SKILL.md` and the plugin manifest version among the smoke's trigger paths.

---

## Fixes Applied

None. This worker may write only `verification-report.md`.

## Remaining Issues

### High Priority

| Field | Value |
|-------|-------|
| **Severity** | High (H1) |
| **Category** | Verification infrastructure (required gate `plugin.session-smoke`) |
| **Location** | `steering/extensions/plugin-session-smoke.mjs` (start and trust loop, around lines 88–109) |
| **Issue** | Herdr 0.9.5 `agent start` fails fast with `agent_not_ready` while Claude Code's trust dialog is up. The provider treats any non-zero `agent start` as failure and never accepts the dialog, so the required gate cannot pass on this host |
| **Impact** | Verification cannot reach Pass for any change that touches the smoke's paths |
| **Fix** | When `agent start` returns `agent_not_ready`, read the pane. If `TRUST_DIALOG` matches, send `TRUST_ACCEPT_KEYS`, then wait until the agent is ready (poll `herdr agent list` for `interactive_ready`, or rerun `agent start`), and only then prompt `/mcp`. Accepting the dialog after the blocked result was confirmed by hand to give a ready session. Alternatively, pre-trust the ephemeral project before starting the agent. Then rerun the full registered gate |
| **Reason Not Fixed** | Outside this worker's writable scope (report only) |

### Medium Priority

| Field | Value |
|-------|-------|
| **Severity** | Medium (M1) |
| **Category** | Correctness (AC14), live UE only |
| **Location** | `src/nmg_game_dev/unreal/import_anims.py` `_compatible_paths`, `_add_compatible` |
| **Issue** | `compatible_skeletons` holds soft object pointers. `str(item).split(".")[0]` may not give the plain asset path in UE Python, so the duplicate check could miss |
| **Impact** | Possible duplicate registration against a live editor. Fakes cannot show this |
| **Reason Not Fixed** | Needs live UE evidence, and SDLC work does not touch live editors. Check by hand before release |

| Field | Value |
|-------|-------|
| **Severity** | Medium (M2) |
| **Category** | Error handling, live UE only |
| **Location** | `src/nmg_game_dev/unreal/import_anims.py` `_sampled_keys` |
| **Issue** | It falls back to `get_number_of_frames` / `get_num_frames`, which can be one less than the sidecar's inclusive `frame_count` |
| **Impact** | Possible false `import_anims.clip_mismatch`. It fails closed |
| **Reason Not Fixed** | Needs live UE evidence |

---

## Positive Observations

- The H2 fix is small and well commented, and its regression test ties the per-clip steps to the checkpoint path.
- `DEPENDS` keeps the six-step chain for `import_ue` the same as before.
- The UE program checks everything before it changes anything, and it never deletes stale sequences.

---

## Recommendations Summary

### Before PR (Must)
- [ ] H1: make `plugin-session-smoke.mjs` accept the trust dialog after Herdr reports `agent_not_ready`, then rerun the full registered gate

### Short Term (Should)
- [ ] M1 and M2: confirm against UE 5.8 by hand before release

### Long Term (Could)
- [ ] Update the design's `export_anims` input from the `variants` blend to the checkpoint, and align the T007 test file names

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `src/nmg_game_dev/pipeline/engine.py` | 0 | H2 from the last report is fixed |
| `src/nmg_game_dev/pipeline/anims.py`, `steps.py`, `request.py`, `result.py` | 0 | |
| `src/nmg_game_dev/unreal/import_anims.py` | 2 | M1, M2 |
| `plugins/nmg-game-dev-blender-addon/finalize_core/anims.py`, `steps.py` | 0 | |
| `scripts/blender/finalize_entry.py` | 0 | |
| `src/nmg_game_dev/finalize/__main__.py`, `mcp_tools.py`, `service.py` | 0 | |
| `mcp-servers/finalize/src/finalize_mcp/server.py`, `tools.json` | 0 | |
| `tests/blender/test_finalize_anims.py`, `tests/unit/pipeline/test_anims.py` | 0 | H1 from the last report is fixed; checkpoint regression test added |
| `steering/extensions/plugin-session-smoke.mjs` | 1 | H1 (not part of the #138 diff) |

---

## Recommendation

**Needs fixes**

The #138 implementation meets all 16 acceptance criteria, and every code gate passes. The required
`plugin.session-smoke` gate fails because its provider does not handle Herdr 0.9.5's fail-fast
`agent_not_ready` on the trust dialog. Repair the provider, then rerun the full registered gate.
