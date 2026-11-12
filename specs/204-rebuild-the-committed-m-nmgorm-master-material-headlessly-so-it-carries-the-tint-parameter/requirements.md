# Defect Report: The committed M_NmgORM master material drifts from its builder because it can only be rebuilt in a live editor

**Issue**: #204
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/148-let-one-finalized-asset-declare-several-material-variants/

## Reproduction

1. Change the graph in `scripts/unreal/build_master_material.py`, as #148 does by adding the `Tint` vector parameter (default white, multiplying base colour).
2. Look for a way to regenerate `plugins/nmg-game-dev-ue-plugin/Content/Materials/M_NmgORM.uasset` without a running editor. The builder only sends its UE Python through the Unreal MCP endpoint of a live editor.
3. Inspect the committed `M_NmgORM.uasset`. Its name table has `BaseColor`, `Normal`, and `ORM` but no `Tint`.

## Expected vs Actual

| | Description |
|---|-------------|
| **Expected** | The committed master material can be rebuilt from the builder's graph code without a live editor, and the committed asset carries every parameter the builder defines. |
| **Actual** | Only a live editor session can rebuild the asset, so the committed `.uasset` keeps the old three-parameter graph, and `Tint`-based material instances have no visible effect. |

## Acceptance Criteria

### AC1: The master material can be rebuilt headlessly

**Given** UE 5.8 installed and no editor session open on `fixtures/dogfood.uproject`
**When** the developer runs the documented headless rebuild command
**Then** a separate `UnrealEditor-Cmd` process opens `fixtures/dogfood.uproject`, runs the same graph-building UE Python as `build_master_material.py`, saves `M_NmgORM.uasset`, and exits; no running editor is contacted

### AC2: The committed asset carries the Tint parameter

**Given** the rebuilt and committed `M_NmgORM.uasset`
**When** a unit test inspects the asset file
**Then** it finds the `Tint`, `BaseColor`, `Normal` and `ORM` parameter names

### AC3: Existing material instances keep their parent

**Given** material instances parented to `/nmg-game-dev/Materials/M_NmgORM`
**When** the master is rebuilt in place
**Then** the asset keeps its path and package name

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | `build_master_material.py` gains a headless mode that runs its UE Python through `UnrealEditor-Cmd <fixtures/dogfood.uproject> -ExecutePythonScript=...` instead of the MCP endpoint, sharing one graph definition | Must |
| FR2 | `M_NmgORM.uasset` is rebuilt with the `Tint` parameter and committed | Must |
| FR3 | A unit test asserts the committed asset contains the four parameter names | Must |
| FR4 | The headless mode never connects to a running editor or MCP endpoint | Must |

## Out of Scope

- Adding `Tint` or any other change to the graph itself (#148 owns the graph).
- Rebuilding assets other than `M_NmgORM`.
- A registered verification gate that runs the headless rebuild.
- Changing the MCP mode's behavior, flags, or exit codes.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #204 | 2026-11-11 | Initial defect report |
