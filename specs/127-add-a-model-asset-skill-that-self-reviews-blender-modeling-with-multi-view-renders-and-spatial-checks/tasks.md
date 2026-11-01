# Tasks: Add a /model-asset skill that self-reviews Blender modeling with multi-view renders and spatial checks

**Issue**: #127
**Date**: 2026-11-01
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/69-reshape-the-pipeline-to-finalize-an-authored-asset-instead-of-generating-from-a-prompt/

## Implementation Tasks

### T001: Spatial inspection core

**File(s)**: `plugins/nmg-game-dev-blender-addon/inspect_core/__init__.py`, `plugins/nmg-game-dev-blender-addon/inspect_core/spatial.py`
**Type**: Create
**Depends**: none
**Acceptance**:
- `inspect_asset(collection, asset_class, budgets_path=None, *, gap_tolerance=0.001)` returns the report shape in design.md, with per-part world bounds, `tris`, `non_manifold_edges`, and `geometry` from `geometry_findings` (AC3, FR3)
- Emits blocking `floating` (with `gap`), non-blocking `interpenetration` (with both part names), blocking `non_manifold` (with `edges`), and blocking `over_budget` (with `triangles` and `budget`) findings; `passed` is true exactly when no blocking finding exists; `triangles.headroom` is `budget - total` (AC3, AC4, FR3)
- Uses evaluated meshes (modifiers applied in the copy) and the Desktop budget from `resolve_budget(..., variant="desktop")`, so `nmg-budgets.json` overrides apply
- Raises `ContractError` with `inspect.collection_missing` or `inspect.unknown_asset_class`, and leaves no new datablock or scene change on any path (AC5, FR5)

### T002: Inspection operator and registration

**File(s)**: `plugins/nmg-game-dev-blender-addon/operators/inspect_spatial.py`, `plugins/nmg-game-dev-blender-addon/operators/__init__.py`, `plugins/nmg-game-dev-blender-addon/__init__.py`, `plugins/nmg-game-dev-blender-addon/panels/main_panel.py`
**Type**: Create, Modify
**Depends**: T001
**Acceptance**:
- `nmggamedev.inspect_spatial` takes `collection_name`, `asset_class` (`ASSET_CLASS_ITEMS`), `budgets_path`, and `gap_tolerance`, stores the report with `store_last_result`, and returns `CANCELLED` with an ERROR report on `ContractError` (AC6, FR4)
- The operator is in `REGISTER_CLASSES` and the main panel (FR4)

### T003: Blender API reference

**File(s)**: `skills/model-asset/references/blender-api.md`
**Type**: Create
**Depends**: none
**Acceptance**:
- Covers bmesh construction, modifier stacks including applying them, Geometry Nodes node-group creation, shader-node lookup by type, and a "Changes since Blender 4.x" section, each with self-contained fenced `python` snippets (AC7, FR6)

### T004: model-asset skill

**File(s)**: `skills/model-asset/SKILL.md`
**Type**: Create
**Depends**: T001, T002, T003
**Acceptance**:
- Frontmatter per AC1; Flow steps in the AC2 order, invoking `inspect_asset` through `execute_blender_code`, `render_review`, and `look`; no step waits for developer approval; no per-asset-type recipe (AC1, AC2, FR1, FR2)
- Documents the operator alternative and Failure modes and remediation for `inspect.collection_missing`, `inspect.unknown_asset_class`, and `mcp.blender.unreachable` (AC6, FR1)

### T005: Consumer docs and CHANGELOG

**File(s)**: `docs/skills/model-asset.md`, `CHANGELOG.md`
**Type**: Create, Modify
**Depends**: T004
**Acceptance**:
- `docs/skills/model-asset.md` describes the loop, every report field, the blocking rules (`floating`, `non_manifold`, `over_budget` block; `interpenetration` and per-part geometry findings do not), and the failure codes (AC8, FR7)
- `CHANGELOG.md` `[Unreleased]` has an `### Added` bullet for the skill ending with `(#127)` (AC8, FR7)

### T006: Headless Blender tests for the inspection and operator

**File(s)**: `tests/blender/inspect_fixtures.py`, `tests/blender/test_inspect_spatial.py`, `tests/blender/test_addon_registration.py`
**Type**: Create, Modify
**Depends**: T001, T002
**Acceptance**:
- SCN003 / AC3: a defective fixture (main body, one part 0.05 m away, an interpenetrating pair, an open-box part touching the body, total tris above the `small_prop` Desktop budget of 2000) yields each finding with the right `blocking`, part names, `gap` ≈ 0.05, `edges`, `triangles`, and `budget`; `json.dumps(report)` succeeds; each part carries `geometry`
- SCN004 / AC4: a clean fixture (touching and overlapping manifold parts within budget) has no blocking findings and a positive `headroom`; a part that reaches the body only through an Array modifier is not floating
- SCN005 / AC5: missing collection and unknown class raise `ContractError` with the two codes, `message`, and `remediation`, and the scene snapshot (objects, transforms, datablock counts) is unchanged
- SCN006 / AC6: the documented `execute_blender_code` snippet, exec'd in-process, returns the report and leaves the scene snapshot unchanged; `bpy.ops.nmggamedev.inspect_spatial` stores the same report in `last_result`; the registration test expects 11 operators including `nmggamedev.inspect_spatial`
- Passes under validation `gate-blender-headless` (`scripts/run-blender-tests.sh`)

### T007: API reference snippet test

**File(s)**: `tests/blender/test_model_asset_api_reference.py`
**Type**: Create
**Depends**: T003
**Acceptance**:
- SCN007 / AC7: extracts every fenced `python` block from `skills/model-asset/references/blender-api.md`, runs each with `exec` in its own namespace after clearing the scene (`contract_fixtures.clear_scene`), parametrized per snippet, and all pass
- Asserts coverage: snippets contain `bmesh.new`, `modifiers.new`, `modifier_apply`, `GeometryNodeTree`, and `.type ==`, and the file has a "Changes since Blender 4" heading
- Passes under validation `gate-blender-headless`

### T008: Skill and docs unit tests

**File(s)**: `tests/unit/test_model_asset_skill.py`
**Type**: Create
**Depends**: T004, T005
**Acceptance**:
- SCN001 / AC1: `parse_frontmatter` (from `tests/ship_fakes.py`) reads `name: model-asset`, a one-line description containing "freeform" and "Blender MCP", `required_mcp` `[blender]`, and `unattended_safe` `true`
- SCN002 / AC2: in the Flow section, the markers for scene inspection, plan (metres, `asset_class`), one generating script, blockout, `inspect_asset` + `render_review` + `look`, blocking fix loop, materials, and final presentation appear in that order; the Flow contains none of "wait for the developer", "ask the developer", "developer approv"; the skill names no asset types from a fixed noun list (chair, table, sword, crate, barrel, lamp, tree, house, door)
- SCN008 / AC8: `docs/skills/model-asset.md` names the four rules and both `inspect.*` codes; `CHANGELOG.md` `[Unreleased]` contains `(#127)`
- Passes under validation `repository.tests`; lint, format, and types pass under `repository.lint`, `repository.format`, `repository.types`

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #127 | 2026-11-01 | Initial feature tasks |
