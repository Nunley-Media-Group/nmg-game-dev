# Verification Report: Built-in procedural clip library for import_animations

**Date**: 2026-11-11
**Issue**: #136
**Reviewer**: Claude (nmg-sdlc architecture-reviewer, verify stage)
**Scope**: Implementation verification against spec

**Verification head**: 7c90b39143d44ee05a34d866e2ba9c1e98152986

---

## Executive Summary

The branch adds a pure-Python pose solver (`rig_core/procedural.py`), 24 built-in clip definitions (`rig_core/builtin_clips.py`), a `library="builtin"` path through `import_animations` and `bake_builtin_clip` (`rig_core/retarget.py`), a `library_source` choice on the `nmggamedev.import_animations` operator, documentation, CPython unit tests, and headless Blender tests on two rigs of different proportions and rest arm angles. All 13 acceptance criteria are met and backed by passing tests. All 8 applicable registered gates passed at the verification head, and gate coverage is complete (11 declared, 11 recorded, ceiling none).

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
**Total Issues**: 4 (all low severity, none blocking)

---

## Issue Scope

- Active issue: #136
- Spec: `specs/136-add-a-built-in-procedural-clip-library-to-import-animations`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1–AC13]; FR [FR1–FR15]; tasks [T001–T007]; scenarios [SCN001–SCN013]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":136,"specPath":"specs/136-add-a-built-in-procedural-clip-library-to-import-animations","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6","AC7","AC8","AC9","AC10","AC11","AC12","AC13"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6","FR7","FR8","FR9","FR10","FR11","FR12","FR13","FR14","FR15"],"tasks":["T001","T002","T003","T004","T005","T006","T007"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006","SCN007","SCN008","SCN009","SCN010","SCN011","SCN012","SCN013"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

- Runner: `sdlc-verify-steering.mjs --project . --issue 136 --base main --controller-run-id 45d1f08e-7170-40d8-a63b-ee989ef37e03`
- Artifact: `.nmg-sdlc/verification/136.json`
- Identity: head `7c90b39143d44ee05a34d866e2ba9c1e98152986`, clean tree, steering `sha256:119992c8…c5096a9`, spec `sha256:dc98e242…9955478`
- Coverage: declared 11, recorded 11, complete `true`, missing/duplicate/unknown none
- Ceiling: none

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Built-in library bakes with no files; actions named per clip; keys on targeted bones; rig at rest | Pass | `rig_core/retarget.py` `import_animations` / `bake_builtin_clip`; `tests/blender/test_rig_builtin_clips.py::test_scn001_scn002_*` patches `open`, `Path.read_bytes`, `Path.read_text`, checks every `targets(clip)` bone has a `rotation_quaternion` curve, no `__nmg_tmp_` action, and rest pose, on both rigs |
| AC2 | Starter set present (19 named clips) | Pass | `rig_core/builtin_clips.py` `BUILTIN_CLIPS` (24 clips); unit `test_ac2_every_named_clip_is_defined_and_the_set_has_24_clips`; Blender SCN001/SCN002 asserts the result lists them |
| AC3 | Subset request bakes only those clips | Pass | `_select_builtin`; `test_scn003_a_subset_bakes_only_the_requested_clips` (only `Idle`, `Walk` actions exist) |
| AC4 | One definition fits any proportions and A-pose angle within 2° | Pass | `procedural.solve` builds local rotation as `R⁻¹·P⁻¹·A·R` from the rig's own rest; unit `test_ac4_*` on every key of every clip on two synthetic skeletons; Blender `test_scn004_*` on the evaluated pose of both rigs (T-pose rig and 45°-down rig with different limbs and shoulders) |
| AC5 | Pelvis displacement = offset × leg length | Pass | `solve` returns `rest.rotations["pelvis"]ᵀ · (off × leg_length)`; unit `test_ac5_*`; Blender `test_scn005_*` on `Jump` and `Down`, tolerance 1e-4 |
| AC6 | Walk/Run mirrored halves; Idle/FightIdle/Walk/Run loop | Pass | `expand` with `mirror_half`; loop closure enforced; unit mirror and loop tests; Blender `test_scn006_*` compares first/last full-pose signatures and reflected limb directions |
| AC7 | Provenance shape; sidecar and FBX action | Pass | `bake_builtin_clip` provenance `source={"library":"builtin","file":None,"sha256":clip_digest(clip),"skeleton":"manny"}`; `test_scn007_*` reads the result, the `export_rigged` `nmg-animations.json`, and the re-imported FBX action list |
| AC8 | Repeatable bake: replace, identical keys and provenance, no temp data | Pass | `_install` replaces by name; `test_scn008_*` compares key tables, provenance, and action names |
| AC9 | Unknown built-in clip → `anim.clip_not_found`, names listed, nothing baked | Pass | `_select_builtin` resolves every name before any bake; `test_scn009_*` |
| AC10 | Both / neither / unknown library value → `anim.library_invalid`, scene unchanged | Pass | `_builtin_selected` runs before the rig lookup and any scene change; `test_scn010_*` checks all three cases, actions, provenance property, and rest pose |
| AC11 | File libraries unchanged; mixed with built-in in one sidecar | Pass | File path unchanged apart from the rename `library` → `library_data`; existing file-library Blender tests pass; `test_scn011_*` mixes `build_library` clips with built-in `Jump` |
| AC12 | `anim.rig_missing` / `anim.text_motion_unsupported` still apply | Pass | Check order prompt → selection → rig; `test_scn012_*` |
| AC13 | Operator can select the built-in library | Pass | `operators/import_animations.py` `library_source` enum (`FOLDER` default, `BUILTIN`); `tests/blender/test_rig_operators.py::test_scn013_*` asserts `FINISHED`, stored result, and baked actions |

### Functional Requirements

| FR | Status | Evidence |
|----|--------|----------|
| FR1 | Pass | `library="builtin"`; no file access (SCN001 patch) |
| FR2 | Pass | 24 clips, superset of the 19 required |
| FR3 | Pass | `pose(dir=, rot=, off=)` format in `builtin_clips.py` |
| FR4 | Pass | `procedural.solve`; AC4 tests on two rigs |
| FR5 | Pass | Non-targeted bones get local identity (`R⁻¹·P⁻¹·P·R`), so they stay at rest relative to their parent; see Remaining Issues #1 on keying |
| FR6 | Pass | `ClipDef.mirror_half`, `mirror`, `expand` |
| FR7 | Pass | `loop=True` on the four clips; `expand` rejects a loop that does not close |
| FR8 | Pass | `_select_builtin` |
| FR9 | Pass | Provenance shape; `export_rigged` unchanged and writes it |
| FR10 | Pass | `_builtin_selected` / `_library_invalid` |
| FR11 | Pass | Positional `import_animations(collection, library_dir)` still works; existing tests green |
| FR12 | Pass | Operator `library_source` |
| FR13 | Pass | Deterministic solve; `_install` replace; SCN008 |
| FR14 | Pass | `docs/rigging-and-animation.md` "Built-in library" section, codes and operator inputs; `docs/asset-contract.md` built-in `source` |
| FR15 | Pass | `tests/blender/rig_fixtures.py` second humanoid builder; every Blender scenario is parametrized over both rigs |

### Scenarios

SCN001–SCN012 map to `tests/blender/test_rig_builtin_clips.py` (each parametrized over both rigs) with CPython oracles in `tests/unit/test_builtin_clips.py`; SCN013 maps to `tests/blender/test_rig_operators.py::test_scn013_import_operator_bakes_the_builtin_library_and_finishes`. All 13 scenarios are covered and pass.

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Pure pose solver | Complete | No `bpy`/`mathutils`; `RestSkeleton.from_bones` leg length; `solve`; `continuous` |
| T002 | Built-in clip definitions | Complete | `AUTHORED_FPS = 30`; `pose`, `merge`, `derive`, `mirror`, `expand`, `targets`, `clip_digest`; 24 clips |
| T003 | Built-in library in import_animations | Complete | Keys every Manny bone rather than targeted bones only (Remaining Issues #1) |
| T004 | Operator library selection | Complete | |
| T005 | Documentation | Complete | |
| T006 | Unit tests | Complete | 16 tests; `tests/unit/test_builtin_clips.py` loads `rig_core` modules through a synthetic package, no `bpy` |
| T007 | Blender tests on two rigs | Complete | |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 5 | Data (`builtin_clips.py`), math (`procedural.py`), and Blender keying (`retarget.py`) are separate modules |
| Open/Closed | 4 | New clips are data entries; library selection is a string switch, which is adequate for two sources |
| Liskov Substitution | 5 | Built-in provenance has the same shape as file provenance, so `export_rigged` handles both unchanged |
| Interface Segregation | 4 | `import_animations` gains one keyword-only argument; positional file calls untouched |
| Dependency Inversion | 4 | The solver depends only on a `RestSkeleton` value, not on `bpy`; `retarget.py` adapts Blender bones into it |

### Layer Separation

Step-implementation code stays in `rig_core/`, matching the existing rig layer. The pure modules import only the standard library and `.skeleton`, so the math is testable under plain CPython, which the unit tests do.

### Dependency Flow

`retarget.py` → `builtin_clips.py`, `procedural.py` → `skeleton.py`. No cycles, and no new third-party dependency.

---

## Security Assessment

- [x] Authentication: not applicable
- [x] Authorization: not applicable
- [x] Input validation: `library` value, folder/builtin exclusivity, and clip names validated before any scene change
- [x] Injection prevention: no shell, eval, or path construction from input on the built-in path
- [x] Data protection: no file or network access on the built-in path (asserted by test)

---

## Performance Assessment

- [x] Async patterns: not applicable (synchronous Blender data operations)
- [x] Caching: `RestSkeleton` read once per clip
- [x] Resource management: temporary action removed on any exception; replaced on success
- [x] Query optimization: 26 bones × a few keys per clip of pure-Python 3×3 math; negligible next to `keyframe_insert`

---

## Testability and Error Handling

- Testability (5): the solver and definitions are pure and covered on two synthetic skeletons for every key of every clip; Blender tests check the evaluated pose, not only stored values.
- Error handling (4): every user-facing failure returns a structured `RigError` with code and remediation. An internal authoring defect (a `loop` clip that does not close) raises `ValueError` from `expand`, which `import_animations` does not convert; it is unreachable with the shipped definitions and is pinned by the unit tests (Remaining Issues #3).

---

## Test Coverage

- BDD scenarios: 13/13 acceptance criteria covered
- Step definitions: Implemented as pytest tests named per scenario (`test_scnNNN_*`), as for other Blender-side rig specs
- Test execution: Pass (`repository.tests` 985 passed, 9 skipped; `gate-blender-headless` 212 passed; `tests/unit/test_builtin_clips.py` 16 passed in a direct rerun)

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` | Pass | `uv run pytest tests/unit tests/bdd -q`: 985 passed, 9 skipped |
| `repository.lint` | Pass | `uv run ruff check .`: All checks passed |
| `repository.format` | Pass | `uv run ruff format --check .`: 314 files already formatted |
| `repository.types` | Pass | `uv run mypy src tests`: no issues in 198 source files |
| `gate-blender-headless` | Pass | `scripts/run-blender-tests.sh`: 212 passed |
| `gate-ue-compile` | Pass | `Build.sh DogfoodEditor Mac Development`: Result Succeeded |
| `gate-mcp-schema` | Not applicable | No `mcp-servers/**` change |
| `gate-shellcheck` | Not applicable | No `scripts/**.sh` change |
| `gate-ship-smoke` | Not applicable | No ship path change |
| `plugin.validate` | Pass | `claude plugin validate .`: Validation passed with warnings |
| `plugin.session-smoke` | Pass | Plugin loaded via `--plugin-dir`; `nmg-game-dev:blender` connected |

**Gate Summary**: 8/8 applicable passed, 0 failed, 0 incomplete (3 not applicable). No `repository.nmg-sdlc-smoke` or `project.nmg-sdlc-smoke` validation is declared in `steering/manifest.json`, so no smoke lifecycle evidence is required.

Note: the runner's `--base main` resolved against the local `main` ref, which differs from `origin/main`, so `gate-ue-compile`, `plugin.validate`, and `plugin.session-smoke` were applicable although this issue's own diff does not touch their paths. They ran and passed.

---

## Exercise Test Results

Not applicable: the change touches no nmg-sdlc `workflows/` or `agents/` paths.

---

## Fixes Applied

| Severity | Category | Location | Issue | Fix | Routing |
|----------|----------|----------|-------|-----|---------|
| — | — | — | No fixes were needed | — | — |

---

## Remaining Issues

| # | Severity | Category | Location | Issue | Reason Not Fixed |
|---|----------|----------|----------|-------|------------------|
| 1 | Low | Spec drift | `rig_core/retarget.py` `bake_builtin_clip` | T003 says keys go on targeted bones only; the code keys every Manny bone (identity for untargeted ones) so a clip never inherits a rotation from the previously played action. AC1 and FR5 still hold, and the docs and docstring state this. | Deliberate, documented, and safer for playback; the spec text could be updated in a follow-up |
| 2 | Low | Spec drift | `rig_core/builtin_clips.py` `expand` | Design says `loop=True` appends the first pose at the end; the code instead requires authored keys to close and raises otherwise. AC6/FR7 hold. `Down`, `Held`, `Talk`, and `Ride` also set `loop=True`, beyond the four the spec names. | Behavior meets the ACs; no change needed |
| 3 | Low | Error handling | `rig_core/retarget.py` → `expand` | A non-closing loop clip raises `ValueError`, not a structured `RigError`. | Reachable only through an internal definition defect, which the unit tests catch |
| 4 | Info | Gate scope | `.nmg-sdlc/verification/136.json` | Base ref `main` is the stale local ref, widening applicable gates. | Extra gates passed; no effect on the result |

---

## Recommendation

Ready for PR.
