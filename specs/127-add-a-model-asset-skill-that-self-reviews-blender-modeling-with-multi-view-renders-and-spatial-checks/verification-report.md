# Verification Report: Add a /model-asset skill that self-reviews Blender modeling with multi-view renders and spatial checks

**Date**: 2026-11-01
**Issue**: #127
**Reviewer**: Claude (nmg-sdlc verify worker, controller run 32da2d4c-0100-441a-bdc0-c56e0ce96516)
**Scope**: Implementation verification against spec
**Verification head**: d4e67b919609a03e674f1d52adf4db46069c3863

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
**Total Issues**: 0 blocking, 1 low (advisory)

The skill, the spatial inspection core, the operator, the Blender API reference, and the consumer docs meet all eight acceptance criteria. Every applicable registered gate passed at the verification head. Coverage is complete (11 declared, 11 recorded), and the runner reports no ceiling.

The previous report at `6e00e5c` failed because the SCN008 changelog test read only `## [Unreleased]`, and the release bump had moved the #127 entry to `## [0.21.0]`. Commit `d4e67b9` fixes that: the test now reads whichever section holds the #127 bullet. The same commit makes `inspect_asset` return an empty report for a collection with no mesh parts instead of raising a bare `ValueError`. A new headless test covers that case.

---

## Issue Scope

- Active issue: #127
- Spec: `specs/127-add-a-model-asset-skill-that-self-reviews-blender-modeling-with-multi-view-renders-and-spatial-checks`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1–AC8]; FR [FR1–FR7]; tasks [T001–T008]; scenarios [SCN001–SCN008]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":127,"specPath":"specs/127-add-a-model-asset-skill-that-self-reviews-blender-modeling-with-multi-view-renders-and-spatial-checks","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6","AC7","AC8"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6","FR7"],"tasks":["T001","T002","T003","T004","T005","T006","T007","T008"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006","SCN007","SCN008"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

- Runner: `sdlc-verify-steering.mjs --project . --issue 127 --base main --controller-run-id 32da2d4c-0100-441a-bdc0-c56e0ce96516`
- Artifact: `.nmg-sdlc/verification/127.json`; identity head `d4e67b919609a03e674f1d52adf4db46069c3863`, tree clean, spec hash `sha256:d7aa03c8d785862a30b46eb2ff756367fdb7cefa3f5307a19eea6ec5b656fa15`, steering hash `sha256:119992c8134117285b9116c3a61b6f610bfebaf708cd5e20ad1f72d83c5096a9`
- Coverage: declared 11, recorded 11, complete true; missing, duplicate, and unknown are all empty
- Runner ceiling: none

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Skill discoverable, declares contract | Pass | `skills/model-asset/SKILL.md:1-7`: `name: model-asset`, a one-line description naming freeform modeling through the Blender MCP, `required_mcp: [blender]`, `unattended_safe: true`. SCN001 passes under `repository.tests` |
| AC2 | Autonomous plan → blockout → inspect → fix loop | Pass | `SKILL.md` Flow steps 1–8 run in the required order (scene inspection, plan in metres with `asset_class`, one generating script with localized edits, blockout, `inspect_asset` + `render_review` + `look`, blocking fix loop, detail and materials with re-inspection, final presentation). No step waits for approval, and the skill has no per-asset-type recipe. SCN002 passes |
| AC3 | Inspection reports part relationships, manifoldness, budget | Pass | `plugins/nmg-game-dev-blender-addon/inspect_core/spatial.py` `inspect_asset`, `_findings`, `_floating`, `_part_report`: per-part world bounds, blocking `floating` with `gap`, non-blocking `interpenetration`, blocking `non_manifold` with `edges`, blocking `over_budget` with `triangles`/`budget`, and per-part `geometry_findings`. SCN003 passes under `gate-blender-headless` |
| AC4 | Clean asset passes | Pass | `passed` is true exactly when no finding is blocking, and `triangles.headroom = budget - total`. SCN004 passes, including a part that reaches the body only through an Array modifier, because measurement uses evaluated meshes |
| AC5 | Structured errors, no changes | Pass | `ContractError` with `inspect.unknown_asset_class` / `inspect.collection_missing`, `message`, and `remediation` is raised before any mesh is evaluated. Evaluated mesh copies are removed in `finally`. SCN005 passes with a scene snapshot check. A collection with no mesh parts now returns an empty report (new test) |
| AC6 | Callable from the live session; operator | Pass | The documented snippet runs exec'd in-process in SCN006. `nmggamedev.inspect_spatial` (`operators/inspect_spatial.py`) is registered in `REGISTER_CLASSES` and on the main panel, and the registration test expects 11 operators. Live check against the user's Blender 5.2.3 LTS through the Blender MCP: `from nmg_game_dev_blender_addon.inspect_core import inspect_asset` imports, and a missing collection raises `ContractError inspect.collection_missing` with no scene change |
| AC7 | API reference snippets run headless | Pass | `skills/model-asset/references/blender-api.md` covers bmesh construction, modifier stacks including apply, Geometry Nodes node groups, shader nodes by type, and "Changes since Blender 4.x". `tests/blender/test_model_asset_api_reference.py` runs every snippet under `gate-blender-headless` |
| AC8 | Consumer docs + CHANGELOG | Pass | `docs/skills/model-asset.md` documents the loop, every report field, the blocking rules table, and both `inspect.*` codes. `CHANGELOG.md` `## [0.21.0] - 2026-11-01` → `### Added` has the `/model-asset` entry ending `(#127)`. SCN008 passes |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Spatial inspection core | Complete | `inspect_core/__init__.py`, `inspect_core/spatial.py` |
| T002 | Operator and registration | Complete | Operator, `operators/__init__.py`, add-on `REGISTER_CLASSES`, main panel, and `inspect` summary lines |
| T003 | Blender API reference | Complete | `skills/model-asset/references/blender-api.md` |
| T004 | model-asset skill | Complete | `skills/model-asset/SKILL.md` |
| T005 | Consumer docs and CHANGELOG | Complete | The entry was written under `[Unreleased]` and moved to `[0.21.0]` by the release bump (VERSION 0.21.0, synced across plugin.json, blender_manifest.toml, and the .uplugin) |
| T006 | Headless Blender tests | Complete | `tests/blender/inspect_fixtures.py`, `test_inspect_spatial.py`, `test_addon_registration.py` |
| T007 | API reference snippet test | Complete | `tests/blender/test_model_asset_api_reference.py` |
| T008 | Skill and docs unit tests | Complete | `tests/unit/test_model_asset_skill.py` |

---

## Architecture Assessment

| Area | Score (1-5) | Notes |
|------|-------------|-------|
| SOLID Principles | 4 | The core (`inspect_core`) stays separate from the operator, which is thin and only calls the core. Budget resolution reuses `utils/budgets.resolve_budget`, and geometry reuses `contract_core.geometry_findings`. `spatial.py` holds measurement, pair relations, and component grouping in one module of about 340 lines; that is acceptable at this size |
| Security | 5 | No network, subprocess, or credential handling. The only file read is the optional `nmg-budgets.json` through the existing budget loader |
| Performance | 4 | Pair checks are O(n²) over parts with BVH acceleration, which is fine for single-asset part counts. `_gap_to` queries every vertex of each part against the other part's BVH, so very dense parts cost more but remain bounded |
| Testability | 5 | Headless fixtures build defective, clean, Array-modifier, and empty cases. Scene snapshots prove the inspection is read-only. Unit tests check SKILL.md structure and docs |
| Error Handling | 5 | Structured `ContractError` with `code`/`message`/`remediation`; budget override errors are re-raised with their own code; the operator returns `CANCELLED` with an ERROR report; evaluated copies and bmesh are freed in `finally` |

**Average**: 4.6

---

## Test Results

### Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` | Pass | `uv run pytest tests/unit tests/bdd -q`: 942 passed, 9 skipped |
| `repository.lint` | Pass | `uv run ruff check .`: All checks passed |
| `repository.format` | Pass | `uv run ruff format --check .`: 306 files already formatted |
| `repository.types` | Pass | `uv run mypy src tests`: no issues in 195 source files |
| `gate-blender-headless` | Pass | `scripts/run-blender-tests.sh`: 179 passed |
| `gate-ue-compile` | Pass | DogfoodEditor compiled against `/Users/Shared/Epic Games/UE_5.8` (applies because of the `.uplugin` version bump) |
| `gate-mcp-schema` | Not applicable | No `mcp-servers/**` or validator changes |
| `gate-shellcheck` | Not applicable | No `scripts/**.sh` changes |
| `gate-ship-smoke` | Not applicable | No ship paths changed |
| `plugin.validate` | Pass | `claude plugin validate .` exited 0. Its warnings (root CLAUDE.md is not loaded as context; no LICENSE for directory submission) predate this change |
| `plugin.session-smoke` | Pass | Plugin loaded via `--plugin-dir` in an ephemeral Herdr project; `nmg-game-dev:blender` connected |

**Gate Summary**: 8/8 applicable passed, 0 failed, 0 incomplete (3 not applicable)

### BDD coverage

- Scenarios: 8/8 acceptance criteria covered (SCN001–SCN008)
- Step implementations: unit tests (SCN001, SCN002, SCN008) and headless Blender tests (SCN003–SCN007)
- Execution: Pass

### Exercise testing

Not applicable: this repository is not the nmg-sdlc plugin, and the diff touches no `workflows/` or `agents/` paths. The shipped `skills/model-asset` skill is covered by `plugin.validate`, `plugin.session-smoke`, the structural unit tests, and the live-session check under AC6.

### Smoke

The manifest declares no `repository.nmg-sdlc-smoke` or `project.nmg-sdlc-smoke`. The registered `plugin.session-smoke` passed.

---

## Fixes Applied

| Severity | Category | Location | Issue | Fix | Routing |
|----------|----------|----------|-------|-----|---------|
| — | — | — | None this pass. The prior failure was already fixed in `d4e67b9` before this verification | — | — |

## Remaining Issues

| Severity | Category | Location | Issue | Reason Not Fixed |
|----------|----------|----------|-------|------------------|
| Low | Correctness (advisory) | `inspect_core/spatial.py` `_gap_to` | The gap is measured from each part's vertices to the other part's surface, so two parts that touch only edge-to-edge (no vertex within tolerance, e.g. crossed bars resting on each other) could be reported as `floating`. Common contacts (faces resting on faces, parts sharing vertices) are measured correctly | It is advisory, and the false positive is conservative (it blocks rather than passes). The agent can see it in the renders. A follow-up could add an edge-to-edge distance check |

## Recommendation

Ready for PR.
