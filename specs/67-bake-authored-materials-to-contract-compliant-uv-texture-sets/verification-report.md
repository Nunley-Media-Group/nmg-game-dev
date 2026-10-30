# Verification Report: Bake authored materials to contract-compliant UV texture sets

**Date**: 2026-10-30
**Issue**: #67
**Reviewer**: Claude Code (nmg-sdlc verify worker)
**Scope**: Implementation verification against spec

**Verification head**: 9a843bce53f2ea7f162034cf7ba85211a43164a4

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 4 |
| Security | 5 |
| Performance | 4 |
| Testability | 4 |
| Error Handling | 5 |
| **Overall** | 4.5 |

### Implementation Status: Pass

**Total Issues**: 3 (none caused by this change; all recorded under Remaining Issues)

All seven acceptance criteria and all eight tasks are implemented. All five manifest-registered validations passed at this head, and every #67 Blender headless bake test passed. The two failing headless tests are in `tests/blender/test_coexistence.py`, which this branch doesn't touch. They fail because of a third-party host add-on install on this machine and an assertion defect in that test. A probe reproduced the same failure with the nmg add-on never loaded (see Remaining Issues).

---

## Issue Scope

- Active issue: #67
- Spec: `specs/67-bake-authored-materials-to-contract-compliant-uv-texture-sets`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1–AC7]; FR [FR1–FR8]; tasks [T001–T008]; scenarios [SCN001–SCN007]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":67,"specPath":"specs/67-bake-authored-materials-to-contract-compliant-uv-texture-sets","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6","AC7"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6","FR7","FR8"],"tasks":["T001","T002","T003","T004","T005","T006","T007","T008"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006","SCN007"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact

`sdlc-verify-steering.mjs` wrote `.nmg-sdlc/verification/67.json`. It reports `ok: true` and `ceiling: null`, and its coverage is `declared: 5, recorded: 5, complete: true`, with nothing missing, duplicated or unknown.

| Validation | Provider | Required | Result |
|------------|----------|----------|--------|
| `repository.tests` | builtin.command (`uv run pytest tests/unit tests/bdd -q`) | yes | passed |
| `repository.lint` | builtin.command (`uv run ruff check .`) | yes | passed |
| `repository.types` | builtin.command (`uv run mypy src tests`) | yes | passed |
| `plugin.validate` | builtin.command (`claude plugin validate .`) | yes | passed |
| `plugin.session-smoke` | project.plugin-session-smoke (`expectConnected: [blender]`) | yes | passed |

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Any authored material bakes to the BC/N/ORM set, one `UVMap`, rewired `M_<Name>_<Part>`, proof within tolerance | Pass | `bake_core/core.py` (`_bake`, `_bake_unique`, `_pack`), `bake_core/uv.py` (`layout_is_valid`, `joint_unwrap`), `bake_core/rewire.py`, `bake_core/proof.py` (`MEAN_TOLERANCE=0.03`, `OUTLIER_TOLERANCE=0.02`, `OUTLIER_DELTA=0.25`); `tests/blender/test_bake_unique.py::test_ac1_*` (procedural, triplanar, image) pass |
| AC2 | Tiling mode: seamless set, UVs kept, texel density checked | Pass | `bake_core/tiling.py` (`SEAM_TOLERANCE=0.04`, 256/128 px/m), `core.py::_bake_tiling`; `tests/blender/test_bake_tiling.py` (4 tests) pass |
| AC3 | Desktop/Mobile resolutions, identical names, byte totals | Pass | `utils/budgets.py::resolve_budget`, `bake_core/pack.py::pack_set`, `core.py::_result`; `test_ac3_desktop_and_mobile_sizes_and_bytes` passes; `tests/unit/test_blender_budgets.py` passes |
| AC4 | Merge into `M_<Name>_Body` above the Mobile limit | Pass | `core.py` (`merged = mode == "unique" and len(sources) > mobile["materials"]`), `rewire.collapse`; `test_ac4_*` (3 tests) pass |
| AC5 | One `bake_asset` behind the operator, MCP and pipeline stage | Pass | `operators/bake_materials.py` → `bake_asset`; `run_for_mcp`; `src/nmg_game_dev/pipeline/stages/texture.py` returns `StageArtifact` with sidecar; `test_ac5_operator_and_direct_call_share_one_result`, `tests/unit/pipeline/stages/test_texture.py`, `tests/bdd/features/texture_bake.feature` pass |
| AC6 | Fails loudly with `texture.bake_failed` and restores the asset | Pass | `bake_core/inspect.py` (alpha, transmission, emission, unsupported shader, volume/displacement), `uv.py` (`uv_unwrap_failed`), `tiling.py` (`not_seamless`, `texel_density`), `core.py` (`proof_mismatch`), `state.py` rollback; `tests/blender/test_bake_failures.py` (3 tests) and the stage-level BDD scenario pass |
| AC7 | Idempotent cache hit, PNGs untouched | Pass | `bake_core/cache.py` (`hash_asset`, `is_cache_hit` on `baked_hash` plus file existence); `tests/blender/test_bake_cache.py` (4 tests) pass |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Budget table with Desktop and Mobile overrides | Complete | `utils/budgets.py`; `budget_invalid` raised in `core._budgets` |
| T002 | Bake core: inspection, state, UVs, channels, packing | Complete | `bake_core/{errors,inspect,state,uv,bake,pack}.py` |
| T003 | Tiling, merging, rewire, proof, cache, orchestration | Complete | `bake_core/{tiling,rewire,proof,cache,core}.py` |
| T004 | Operator and registration | Complete | `operators/bake_materials.py` is in `REGISTER_CLASSES` and the panel. The design's `property_groups/pipeline_props.py` is untouched because `store_last_result` reuses the existing `last_result` |
| T005 | Pipeline texture stage | Complete | `src/nmg_game_dev/pipeline/stages/texture.py` replaces the placeholder |
| T006 | Docs and changelog | Complete | `docs/skills/bake-materials.md`, contract §4 and §8 step 3, CHANGELOG `[Unreleased]` bullet ending `(#67)` |
| T007 | Pipeline stage tests | Complete | Unit tests plus `texture_bake.feature` (2 scenarios) |
| T008 | Blender headless bake tests | Complete | 5 fixture and test files; all bake tests pass under Blender 5.2.3 LTS |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 4 | Each `bake_core` module owns one concern. `core._bake` is a long orchestration function (~130 lines) but reads linearly |
| Open/Closed | 4 | Channels, tolerances and budgets are constants or tables; new failure reasons are additive |
| Liskov Substitution | 5 | No inheritance beyond the bpy `Operator` |
| Interface Segregation | 5 | Narrow entry points: `bake_asset` and `run_for_mcp` |
| Dependency Inversion | 4 | The pipeline stage talks only to the injected Blender MCP client; the bake core depends on `bpy` directly, as add-on code must |

### Layer Separation

The layering follows `steering/snippets/project-structure.md`. The pipeline stage composes one MCP call and maps errors, and all Blender work lives in the add-on. The operator is a thin adapter over `bake_asset`.

### Dependency Flow

`operators` → `bake_core` → `utils.budgets` / `contract_core.uv`. `src/nmg_game_dev` doesn't import add-on code; it sends a script string through the MCP client.

---

## Security Assessment

- [x] Authentication: N/A (local Blender session)
- [x] Authorization: N/A
- [x] Input validation: collection, class and budgets are validated (`collection_missing`, `budget_invalid`, power-of-two check)
- [x] Injection prevention: the stage builds its script with `!r` on every interpolated value, so names can't break out of the Python literal
- [x] Data protection: no secrets handled; outputs go to the caller's `out_dir`

---

## Performance Assessment

- [x] Async patterns: synchronous by design; background execution is deferred to #69 (out of scope)
- [x] Caching: content-hash manifest skips rebakes (AC7)
- [x] Resource management: float bake images are removed after packing; the proof scene, lights, camera and world are torn down in `finally`; the tiling tile is removed in `finally`
- [x] Query optimization: mesh data is read with `foreach_get`. The UV hashing in `cache.hash_asset` builds a Python list per loop, which is fine for prop-sized meshes but could use `foreach_get` for large meshes (minor)

---

## Error Handling Assessment

Every failure is raised as a `BakeError` with code `texture.bake_failed`, a reason, a target and a remediation. Unexpected exceptions are wrapped as `internal_error`. `BakeState.__exit__` always restores render visibility and settings, and on any exception it also rolls back material slots, face material indices, UV layers, material names and created datablocks. A proof mismatch removes the outputs and manifest it wrote, so no stale cache entry survives. The stage maps the `error` dict to `PipelineError` with stage `texture`, and client failures go through `translate_mcp_errors`.

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1 | Yes (spec SCN001; Blender headless) | Yes | Yes |
| AC2 | Yes (spec SCN002; Blender headless) | Yes | Yes |
| AC3 | Yes (spec SCN003; Blender headless) | Yes | Yes |
| AC4 | Yes (spec SCN004; Blender headless) | Yes | Yes |
| AC5 | Yes (pytest-bdd `texture_bake.feature` and Blender headless) | Yes | Yes |
| AC6 | Yes (pytest-bdd `texture_bake.feature` and Blender headless) | Yes | Yes |
| AC7 | Yes (spec SCN007; Blender headless) | Yes | Yes |

### Coverage Summary

- Feature files: 2 pytest-bdd scenarios (`tests/bdd/features/texture_bake.feature`) plus 7 spec scenarios in `feature.gherkin`, run as Blender headless tests
- Step definitions: implemented
- Unit and BDD suite (`repository.tests`): passed
- Blender headless (`scripts/run-blender-tests.sh`, Blender 5.2.3 LTS): 74 passed, 2 failed. All 20 bake tests passed; the 2 failures are in `test_coexistence.py` (unrelated, see Remaining Issues)

---

## Exercise Test Results

| Field | Value |
|-------|-------|
| **Reason** | Not applicable: the diff doesn't touch `workflows/` or `agents/` (no nmg-sdlc plugin skill changes). The plugin surface is covered by the registered `plugin.validate` and `plugin.session-smoke` validations, both passed |
| **Recommendation** | None |

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| `gate-python-lint` | Pass | `repository.lint` passed (ruff check) |
| `gate-python-types` | Pass | `repository.types` passed (mypy src tests) |
| `gate-python-unit` | Pass | `repository.tests` passed |
| `gate-python-bdd` | Pass | `repository.tests` passed (includes `tests/bdd`) |
| `gate-blender-headless` | Pass (for #67 scope) | Runner exited 0; all #67 bake and registration tests pass. Two pre-existing `test_coexistence.py` failures are environmental and unrelated (see Remaining Issues) |
| `gate-markdown-lint` | Not run | `markdownlint` isn't a registered validation and isn't installed in the gate environment |
| `gate-ue-automation`, `gate-skill-schema`, `gate-mcp-schema`, `gate-shellcheck`, `gate-ship-smoke` | N/A | The diff touches no UE C++, `skills/**/SKILL.md`, `mcp-servers/**`, `*.sh`, or ship paths |

**Gate Summary**: 5/5 applicable registered validations passed. 5 applicable steering gates passed; `gate-blender-headless` passed with 2 unrelated failures noted, and `gate-markdown-lint` wasn't run.

---

## Real Smoke Lifecycle Evidence

No `repository.nmg-sdlc-smoke` or `project.nmg-sdlc-smoke` validation is declared in `steering/manifest.json`. The registered `plugin.session-smoke` provider ran for real and passed at this head, with `blender` connected.

---

## Fixes Applied

None. The verify publication scope allows only this report to change.

## Remaining Issues

### Critical Issues

None.

### High Priority

None.

### Medium Priority

| Severity | Category | Location | Issue | Reason Not Fixed |
|----------|----------|----------|-------|------------------|
| Medium | testability | `scripts/run-blender-tests.sh`, `tests/blender/_runner.py:122` | `_runner.py` calls `sys.exit(result)`, but Blender is launched without `--python-exit-code`, so the script exits 0 even when pytest fails. `gate-blender-headless` can't detect failures from its exit code; this run exited 0 with 2 failures. | Outside this issue's scope and the verify publication scope. Recommend a follow-up issue adding `--python-exit-code 1` |
| Medium | testability | `tests/blender/test_coexistence.py:59,106` | The test enables the host with `default_set=False` and then asserts `addon_utils.check(...)[0]` (loaded_default), which is always False in that mode. It only started running on this machine once `blender_mcp.py` was installed into the user add-ons folder (2026-10-30 12:51), matching a `_HOST_CANDIDATES` entry; before that the module was skipped. A probe under `--factory-startup` with the nmg add-on never loaded reproduced `check("blender_mcp") == (False, True)`. | Pre-existing; not caused by #67. Recommend asserting `check(...)[1]` (loaded_state) in a follow-up |

### Low Priority

| Severity | Category | Location | Issue | Reason Not Fixed |
|----------|----------|----------|-------|------------------|
| Low | build | `uv.lock` | The lock records `nmg-game-dev` 0.7.0 while `pyproject.toml` is 0.10.0 (already stale on `main`), so every `uv run` rewrites `uv.lock`. Verification restored the file after the gate run. | Outside the verify publication scope; regenerate the lockfile in a follow-up or at PR time |

---

## Recommendation

Ready for PR. Track the runner exit-code and coexistence-test defects as follow-up issues.
