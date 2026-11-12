# Verification Report: Export and import rigged-character animation clips through finalize

**Date**: 2026-11-12
**Issue**: #138
**Reviewer**: Claude (nmg-sdlc architecture-reviewer, verify stage)
**Scope**: Implementation verification against the approved spec, re-run after merging `origin/main` (#217, #218, #219) into the issue branch
**Verification head**: fd3235ff7ff3934dfc00b5a4feba7f288c735f6d

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 4 |
| Security | 5 |
| Performance | 4 |
| Testability | 5 |
| Error Handling | 5 |
| **Overall** | 4.7 |

### Implementation Status: Pass
**Total Issues**: 2 (both Low, non-blocking)

All 16 acceptance criteria, 15 functional requirements, and 7 tasks are implemented. The merge of
`origin/main` (reduce-to-budget #139/#219, texture job queue #211/#218, import_ue rename refusal
#203/#217) left the #138 surface intact: the merge commit only resolved `CHANGELOG.md`,
`docs/mcp/finalize.md`, `skills/finalize-asset/SKILL.md`, and the CLI usage docstring, each keeping
both sides. All 11 manifest-registered validations have a terminal result: 10 applicable and passed,
and `gate-ship-smoke` not applicable (no ship paths changed).

---

## Issue Scope

- Active issue: #138
- Spec: `specs/138-export-and-import-rigged-character-animation-clips-through-finalize`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1–AC16]; FR [FR1–FR15]; tasks [T001–T007]; scenarios [SCN001–SCN016]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":138,"specPath":"specs/138-export-and-import-rigged-character-animation-clips-through-finalize","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6","AC7","AC8","AC9","AC10","AC11","AC12","AC13","AC14","AC15","AC16"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6","FR7","FR8","FR9","FR10","FR11","FR12","FR13","FR14","FR15"],"tasks":["T001","T002","T003","T004","T005","T006","T007"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006","SCN007","SCN008","SCN009","SCN010","SCN011","SCN012","SCN013","SCN014","SCN015","SCN016"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact

- Artifact: `.nmg-sdlc/verification/138.json` (runner `sdlc-verify-steering.mjs --base main`, controller run `f39c03e1-dad3-42ce-8555-47b1cddaeb94`)
- Identity: head `fd3235ff7ff3934dfc00b5a4feba7f288c735f6d`, steering `sha256:6db9aabc…d474d4`, spec `sha256:1b267fc9…4ff33e`
- Coverage: declared 11, recorded 11, complete `true`; no missing, duplicate, or unknown ids
- Ceiling: none

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | One armature-only FBX per clip, rig export settings | Pass | `finalize_core/anims.py` `ANIM_EXPORT_OPTIONS` spreads `_RIG_FBX_OPTIONS` from `variants_core/export.py` plus `object_types={"ARMATURE"}`, `bake_anim` True, NLA/all-actions off; `_export_one` renames rig to `Armature`, mutes NLA, assigns one action. Headless proof: `tests/blender/test_finalize_anims.py` (SCN001 re-imports each FBX: one armature, no mesh, one action) |
| AC2 | Clip set = provenance + rig-held actions | Pass | `resolve_clips` reads `nmg_animations`, `animation_data.action`, and NLA strips only; `tests/blender/test_finalize_anims.py` (SCN002: `Idle`, `Wave` exported, `Other` not) |
| AC3 | Sidecar records measured clip data | Pass | `pipeline/anims.py` `_write_sidecar` (asset, armature, skeleton, per-clip name/file/asset_path/frame_start/frame_end/frame_count/fps/source); `export_clips` sets provenance `source` or `"authored"`; `tests/unit/pipeline/test_anims.py`, SCN003 |
| AC4 | AnimSequences on Desktop skeleton, nothing else created | Pass | `unreal/import_anims.py` `_import_clip` (`import_mesh` False, `FBXIT_ANIMATION`, `skeleton` = Desktop skeleton, destination `A_<Name>_<Clip>`), non-AnimSequence objects fail the step; result `animations.content_path` + clips from `engine._animations_result`; `tests/unit/test_unreal_import_anims.py`, SCN004 |
| AC5 | Imported clip checked against sidecar | Pass | `pipeline/anims.py` `_verify` raises `import_anims.clip_mismatch` naming clip, field, expected, measured; SCN005 |
| AC6 | Per-clip caching | Pass | `run_export_anims`/`run_import_anims` keys = clip hash / export output hash + `clip_settings_hash`; engine skips whole-step cache and alias for `per_clip` steps and leaves `input_hash` unchanged; `tests/unit/pipeline/test_anims.py`, SCN006 |
| AC7 | Force reruns every clip | Pass | `force` bypasses `cache.get` in both runners; SCN007 |
| AC8 | No-clip assets pass through | Pass | `run_export_anims` returns before any write when probe is empty; `run_import_anims` makes no Unreal call with no clips and no `compatible_with`; SCN008 |
| AC9 | New steps run alone | Pass | `steps.DEPENDS`/`ordered_steps`; CLI subcommands in `finalize/__main__.py`; `run_finalize_step` in `finalize/mcp_tools.py` and `mcp-servers/finalize/.../server.py`; `tests/unit/test_finalize_cli.py`, `tests/unit/test_finalize_mcp.py`, SCN009 |
| AC10 | Missing Desktop skeleton | Pass | UE program sets `blocked` before any import; `_raise_blocked` raises `finalize.skeleton_not_found` with "Run import_ue … first"; SCN010 |
| AC11 | Invalid clip name stops export | Pass | `run_export_anims` raises `finalize.clip_name_invalid` after the probe, before the export run and sidecar write; Blender `export_clips` double-checks; SCN011 |
| AC12 | Stale sequences reported, not deleted | Pass | UE program lists `A_<Name>_*` not in current clips into `stale`; no delete call exists; SCN012 |
| AC13 | Two-way compatible registration | Pass | `_add_compatible` both directions, saves both skeletons, result `compatible`; SCN013 |
| AC14 | Idempotent registration | Pass | `_add_compatible` appends only when the path is absent; SCN014 |
| AC15 | Target must exist and match bones | Pass | `_check_targets` runs before any import or registration; `finalize.skeleton_not_found` / `finalize.skeleton_mismatch` with differing bones; SCN015 |
| AC16 | No `compatible_with`, no registration | Pass | `compatible` param list empty, registration loop no-ops; SCN016 |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Step table, dependencies, request fields | Complete | `STEP_ORDER` has 8 steps, `per_clip` flag, `_STEP_VERSION` "4", `clip_settings_hash`, `FinalizeRequest.compatible_with` validator, `FinalizeResult.animations` |
| T002 | Blender clip probe and export | Complete | `finalize_core/anims.py`, `finalize_core/steps.py` `_export_anims` (probe/export modes), `scripts/blender/finalize_entry.py` accepts `export_anims` |
| T003 | Host per-clip export and sidecar | Complete | `pipeline/anims.py` `run_export_anims`; engine `_run_per_clip` |
| T004 | Unreal clip import, verification, stale, compatible | Complete | `unreal/import_anims.py`, `pipeline/anims.py` `run_import_anims` |
| T005 | CLI and MCP surface | Complete | CLI subcommands + repeatable `--compatible-with`; both MCP tools take `compatible_with`; `gate-mcp-schema` passed |
| T006 | Documentation | Complete | `docs/mcp/finalize.md` and `skills/finalize-asset/SKILL.md` carry the full surface; `docs/asset-contract.md` ("Animation clips") and `docs/rigging-and-animation.md` (step 7) describe the layout and point to `docs/mcp/finalize.md`; `plugin.validate` passed |
| T007 | Tests | Complete | 24 tests in `tests/unit/pipeline/test_anims.py`, 11 in `tests/unit/test_unreal_import_anims.py`, 7 headless in `tests/blender/test_finalize_anims.py`, 16 bound BDD scenarios in `tests/bdd/features/rigged_animations.feature` |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 4 | Clean split: Blender core (probe/export), host orchestration + cache (`pipeline/anims.py`), UE program builder (`unreal/import_anims.py`). `engine.py` (566 lines) grows another branch but delegates all clip work |
| Open/Closed | 4 | New steps added by table entry plus `per_clip` flag; engine branches on the flag instead of the step name |
| Liskov Substitution | 5 | `UnrealPythonClient` protocol and `StepRunner` let fakes substitute for UE and Blender |
| Interface Segregation | 5 | `run_import_anims` takes a lazy client factory and only calls it when there is work |
| Dependency Inversion | 4 | Cache, runner, and client injected; `_run_per_clip` instantiates `UnrealMcpClient` as a default when none is injected, matching `_run_import` |

### Layer Separation

Matches `steering/structure.md`: step implementations live in `finalize_core/` and `src/nmg_game_dev/unreal/`, composition and caching in `src/nmg_game_dev/pipeline/`, and the MCP server and CLI wrap `finalize/service.py` without logic. The skill calls the finalize tools only.

### Dependency Flow

Host imports `ANIM_EXPORT_OPTIONS` indirectly through the probe-reported `options` fingerprint, so the host never imports `bpy`. Blender side imports `_RIG_FBX_OPTIONS` rather than copying it, preventing drift from the mesh export.

---

## Security Assessment

- [x] Authentication: not applicable (local tooling).
- [x] Authorization: not applicable.
- [x] Input validation: `compatible_with` items validated as PascalCase `<Category>/<Name>` and may not name the asset itself; clip names validated against `^[A-Za-z][A-Za-z0-9_]*$` before they become file or asset names.
- [x] Injection prevention: UE program parameters are passed as a double-encoded JSON literal (`json.dumps(json.dumps(params))`) and parsed with `json.loads`, never string-interpolated into code.
- [x] Data protection: no credentials touched.

## Performance Assessment

- [x] Async patterns: per-clip export batches all misses into one Blender run; import is one UE Python call.
- [x] Caching: per-clip keys on content hash; mesh-step keys unaffected by clip changes; `force` bypass.
- [x] Resource management: owned `UnrealMcpClient` closed in `finally`.
- [ ] Probe: the `export_anims` probe runs a background Blender process on every finalize, even when all clips will hit the cache (documented: "The probe itself is never cached"). Acceptable trade-off for correctness; noted as Low.

## Testability

Fakes (`tests/finalize_fakes.py`, `tests/unit/fake_unreal.py`) cover the host; the UE program is checked by text and by fake replies; Blender behavior is proved headless. No test drives a live editor, per project memory and T007.

## Error Handling

Every failure raises `PipelineError` with `code`, `message`, `remediation`, `stage`. UE exceptions are captured into `RESULT["error"]` and the single `NMG_RESULT` line, then mapped to `import_anims.failed`. Unreadable bone or compatible-skeleton reads fail closed with nothing registered. A clip's cache entry is written only after its checks pass.

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1–AC16 | Yes (SCN001–SCN016 in `tests/bdd/features/rigged_animations.feature`) | Yes (`tests/bdd/test_rigged_animations_bdd.py`) | Yes |

### Coverage Summary

- Feature files: 16 scenarios for #138 (spec `feature.gherkin` mirrors them)
- Step definitions: Implemented
- Python unit + BDD: 1459 passed, 14 skipped (`repository.tests`)
- Headless Blender: 357 passed, 4 skipped (`gate-blender-headless`)

---

## Exercise Test Results

| Field | Value |
|-------|-------|
| **Reason** | Not applicable: no nmg-sdlc `workflows/` or `agents/` changes in this repo. The plugin surface this branch changes (`skills/`, `.claude-plugin/`) is covered by the registered `plugin.validate` and `plugin.session-smoke` gates, both passed |
| **Recommendation** | None |

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` | Pass | `uv run pytest tests/unit tests/bdd -q` exited 0: 1459 passed, 14 skipped |
| `repository.lint` | Pass | `uv run ruff check .`: All checks passed |
| `repository.format` | Pass | `uv run ruff format --check .`: 393 files already formatted |
| `repository.types` | Pass | `uv run mypy src tests`: no issues in 249 source files |
| `gate-blender-headless` | Pass | `scripts/run-blender-tests.sh` exited 0: 357 passed, 4 skipped |
| `gate-ue-compile` | Pass | DogfoodEditor compiled against `/Users/Shared/Epic Games/UE_5.8` with `-WaitMutex -NoUBA` |
| `gate-mcp-schema` | Pass | MCP tools match tools.json for every server under mcp-servers/ |
| `gate-shellcheck` | Pass | `shellcheck -S style` on every `scripts/**.sh` exited 0 |
| `gate-ship-smoke` | Not applicable | No ship paths in the change set |
| `plugin.validate` | Pass | `claude plugin validate .` exited 0 |
| `plugin.session-smoke` | Pass | Plugin loaded via `--plugin-dir` in an ephemeral project; `nmg-game-dev:blender` connected |

**Gate Summary**: 10/10 applicable gates passed, 0 failed, 0 incomplete (1 not applicable)

---

## Fixes Applied

None. No defect in scope was found, and the verify publication scope allows writing only this report.

## Remaining Issues

### Critical Issues
None.

### High Priority
None.

### Medium Priority
None.

### Low Priority

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Release housekeeping |
| **Location** | `CHANGELOG.md:9-20` |
| **Issue** | After the merge, the #138 entry sits under the already-released `## [0.24.0]`/`## [0.22.1]` headings inherited from `main` rather than under `## [Unreleased]`, and `main`'s own CHANGELOG has malformed stacked headings |
| **Impact** | Cosmetic; delivery's prepare-version step rewrites the release section |
| **Reason Not Fixed** | Outside the verify stage's writable scope; owned by deliver's version preparation |

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Performance |
| **Location** | `src/nmg_game_dev/pipeline/anims.py` `run_export_anims` |
| **Issue** | The clip probe launches a background Blender process on every finalize, even when every clip will be a cache hit |
| **Impact** | A few seconds per finalize of a rigged character; within the ≤ 5 min character budget |
| **Reason Not Fixed** | Design choice: the asset hash does not cover actions, so the probe is the only way to detect clip changes |

---

## Positive Observations

- Per-clip steps never move the mesh steps' input hash, so a clip-only edit keeps every mesh step cached.
- The UE program checks every precondition (own skeleton, every compatible target) before it imports or registers anything, and emits one machine-readable result line even on failure.
- Export settings are imported from the mesh export, so clips and meshes cannot drift onto different axis or leaf-bone settings.
- `_export_one` restores the rig's name, action, slot, NLA mutes, and scene range in `finally`.

---

## Recommendations Summary

### Before PR (Must)
- None.

### Short Term (Should)
- Let deliver's version preparation place the #138 CHANGELOG entry correctly.

### Long Term (Could)
- Consider folding action content into a cheap session-side fingerprint so an all-cached rerun can skip the probe process.

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `src/nmg_game_dev/pipeline/steps.py` | 0 | Step table, `DEPENDS`, `clip_settings_hash` |
| `src/nmg_game_dev/pipeline/anims.py` | 1 (Low) | Per-clip export/import, sidecar, verification |
| `src/nmg_game_dev/pipeline/engine.py` | 0 | `per_clip` branch, `_animations_result`; intact after merge with #219 |
| `src/nmg_game_dev/unreal/import_anims.py` | 0 | UE program |
| `plugins/nmg-game-dev-blender-addon/finalize_core/anims.py` | 0 | Probe, hash, export |
| `plugins/nmg-game-dev-blender-addon/finalize_core/steps.py` | 0 | `_export_anims` dispatch |
| `src/nmg_game_dev/pipeline/request.py`, `result.py` | 0 | `compatible_with`, `animations` |
| `src/nmg_game_dev/finalize/__main__.py`, `mcp_tools.py`, `service.py`, `mcp-servers/finalize/**` | 0 | CLI and MCP surface |
| `docs/asset-contract.md`, `docs/mcp/finalize.md`, `docs/rigging-and-animation.md`, `skills/finalize-asset/SKILL.md` | 0 | FR15 docs |
| `CHANGELOG.md` | 1 (Low) | Merge placement |

---

## Recommendation

**Ready for PR**

Every acceptance criterion is implemented and covered by a passing test, and every applicable registered validation passed at head `fd3235ff7ff3934dfc00b5a4feba7f288c735f6d`. The two remaining items are Low and do not block delivery.
