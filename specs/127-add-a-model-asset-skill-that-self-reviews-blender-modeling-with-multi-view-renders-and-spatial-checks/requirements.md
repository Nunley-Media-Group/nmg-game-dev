# Requirements: Add a /model-asset skill that self-reviews Blender modeling with multi-view renders and spatial checks

**Issue**: #127
**Date**: 2026-11-01
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/69-reshape-the-pipeline-to-finalize-an-authored-asset-instead-of-generating-from-a-prompt/

## User Story

**As an** NMG game developer authoring an asset with Claude in Blender
**I want** a modeling skill that makes the agent plan, block out, inspect its work numerically and from several rendered views, and fix problems with small edits until the checks pass
**So that** freeform-authored assets come out structurally sound (no floating or broken parts, within budget) before I run /finalize-asset

## Background

Assets are authored freeform in Blender through the Blender MCP (`execute_blender_code`, `look`). The add-on already has `contract_core/render.py::render_review` (front, back, side, and three-quarter renders; operator `nmggamedev.render_review`), `contract_core/validate.py` (`validate_asset`, `triangle_count`, per-class budgets from `docs/asset-contract.md` section 6 through `utils/budgets.py::resolve_budget`), and `contract_core/geometry.py::geometry_findings` (loose vertices, zero-area faces, duplicates, inconsistent normals). Nothing reports relationships between parts (floating parts, gaps, interpenetration), non-manifold edges, or triangle headroom during authoring, and no skill covers the modeling stage before `/finalize-asset`. The skill must stay asset-type agnostic.

## Acceptance Criteria

### AC1: Skill is discoverable and declares its contract

**Given** the nmg-game-dev plugin is installed
**When** the skill list is read
**Then** `skills/model-asset/SKILL.md` exists with frontmatter `name: model-asset`, a one-line `description` that names freeform Blender modeling through the Blender MCP, `required_mcp: [blender]`, and `unattended_safe: true`

### AC2: Skill defines a fully autonomous plan → blockout → inspect → fix loop

**Given** a developer asks Claude to model an asset in Blender
**When** the skill runs
**Then** its Flow instructs the agent, in order, to: inspect the scene; write a plan with real-world dimensions in metres, the target collection name, and the `asset_class`; keep one generating script per asset and change it with localized edits rather than regenerating; block out; run the spatial inspection and multi-view review renders and read them with `look`; fix every blocking finding and repeat until none remain; detail and add materials, re-running the inspection after each pass; and finish by presenting the final multi-view renders and inspection summary
**And** the Flow has no step that waits for developer approval
**And** the skill contains no per-asset-type recipe

### AC3: Spatial inspection reports part relationships, manifoldness, and budget

**Given** a collection whose mesh parts include one part separated from all others by more than the gap tolerance, one pair of interpenetrating parts, a part with non-manifold edges, and a triangle total above its `asset_class` Desktop budget
**When** the spatial inspection runs on that collection with that `asset_class`
**Then** it returns a JSON-serializable report listing each part's world-space bounds, a blocking `floating` finding naming the separated part and its gap distance, a non-blocking `interpenetration` finding naming the pair, a blocking `non_manifold` finding with the edge count, and a blocking `over_budget` finding with the triangle count and budget
**And** it includes the existing `geometry_findings` results for each part

### AC4: Clean asset passes the inspection

**Given** a collection whose parts all touch or overlap a connected neighbour, are manifold, and are within budget
**When** the spatial inspection runs
**Then** the report has no blocking findings and reports remaining triangle headroom against the budget

### AC5: Inspection fails with structured errors

**Given** a collection name that does not exist, or an `asset_class` not in the budgets
**When** the spatial inspection runs
**Then** it raises a structured error with `code` (`inspect.collection_missing` or `inspect.unknown_asset_class`), `message`, and `remediation`, and changes nothing in the open file

### AC6: Inspection is callable from the live session

**Given** the nmg-game-dev Blender add-on is enabled in the session the Blender MCP drives
**When** the agent invokes the inspection through `execute_blender_code` as the SKILL.md documents
**Then** the report is returned without modifying the scene, and an add-on operator exposes the same inspection

### AC7: Blender API reference snippets run on the supported Blender

**Given** `skills/model-asset/references/blender-api.md`
**When** each fenced Python snippet in it is executed in headless Blender
**Then** every snippet completes without error, and the reference covers bmesh construction, modifier stacks (including applying them), Geometry Nodes node-group creation, looking up shader nodes by type, and API changes since Blender 4.x that affect modeling

### AC8: Consumer docs describe the skill

**Given** the skill ships
**When** a consumer reads the docs
**Then** `docs/skills/model-asset.md` describes the loop, the inspection report fields and blocking rules, and its failure codes, and `CHANGELOG.md` has an entry for the skill

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | `skills/model-asset/SKILL.md` with the frontmatter in AC1 and Failure modes and remediation for `inspect.collection_missing`, `inspect.unknown_asset_class`, and `mcp.blender.unreachable` | Must |
| FR2 | Autonomous loop Flow per AC2, using `execute_blender_code`, `look`, the review renders, and the spatial inspection; no approval waits; asset-type agnostic | Must |
| FR3 | Add-on spatial inspection returning per-part world bounds, floating (blocking, with gap distance), interpenetration (non-blocking), non-manifold (blocking), over-budget (blocking) findings, triangle headroom, and existing geometry findings | Must |
| FR4 | Add-on operator `nmggamedev.inspect_spatial` exposing the inspection, registered with the add-on | Must |
| FR5 | Structured errors per AC5; the inspection is read-only on the open file | Must |
| FR6 | `skills/model-asset/references/blender-api.md` with runnable snippets per AC7 | Must |
| FR7 | `docs/skills/model-asset.md` and a CHANGELOG entry | Must |

## Out of Scope

- Changes to `/finalize-asset`, the finalize pipeline, or the asset contract rules
- Meshy routing or texture-model calls from the skill
- Automated visual scoring of renders (the agent reads them with `look`)
- Per-asset-type recipes or templates
- A searchable index over the full Blender manual

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #127 | 2026-11-01 | Initial feature spec |
