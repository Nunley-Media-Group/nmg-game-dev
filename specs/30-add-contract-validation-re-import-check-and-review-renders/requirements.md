# Requirements: Contract validation, re-import check, and review renders

**Issue**: #30
**Date**: 2026-10-29
**Status**: Approved
**Author**: Rich Nunley

## User Story

**As an** NMG game developer
**I want** a contract validator, a re-import check, and review renders that the agent can run mid-session and that finalize can use as a gate
**So that** contract violations are caught by tooling, and the agent's self-review always looks at the same kind of renders

## Background

Assets are modeled freeform through the Blender MCP; `docs/asset-contract.md` defines what a finished asset must satisfy (sections 1–7) and the "before you say it's done" routine (section 8: validate, review renders, texture proof, re-import check). Today each agent session writes its own validator and render script. This issue makes them standard parts of the Blender add-on with one implementation, callable three ways:

- as add-on operators (and plain functions through the Blender MCP's `execute_blender_code`);
- through a Python CLI that runs headless Blender;
- through a Python gate helper the finalize pipeline (#69) calls.

Budgets and Mobile naming come from the add-on's budget table and variant conventions introduced by #33.

## Acceptance Criteria

### AC1: Validation reports every checkable contract rule

**Given** an asset collection in Blender and its asset class
**When** contract validation runs
**Then** it returns a JSON report with `passed`, per-object snapshots, and one finding per violated rule, covering:
- collection contents and naming (`<Name>`, `SM_<Name>` root, `SM_<Name>_<Part>` children, no lights or cameras in the asset collection), scene units (metric, scale 1.0), root and child-part transforms, root origin at bottom center at world origin;
- loose vertices, zero-area faces, duplicate vertices, inconsistent normals;
- exactly one UV map named `UVMap`, plus UV overlap for unique-bake classes (overlap is allowed for `environment_piece`);
- material node types (only Image Texture, Normal Map, Separate Color, Principled BSDF, Material Output), Image Texture nodes sampling `UVMap`, and `M_<Name>_<Part>` / `T_<Name>_<Part>_{BC,N,ORM}` naming with power-of-two square images;
- triangle count, material count, and max texture size against the class budget, or minimum texel density for `environment_piece`;
- matching object, material, and image names between Desktop and Mobile when a `<Name>_Mobile` collection exists

**And** each finding has `rule`, `target` (object, material, or image name), `message`, and `remediation`

### AC2: Each failure class is detected

**Given** fixture assets with:
- an unapplied root rotation;
- an origin away from bottom center;
- a mesh with no UV map;
- overlapping UVs on a `standard_prop`;
- a material using a Noise Texture;
- a material using Geometry/Position coordinates (triplanar-style);
- a `standard_prop` whose `SM_Crate_Mobile` LOD0 has 4,000 triangles (Mobile budget 3,000);
- a Mobile object whose suffix-stripped name differs from the Desktop name

**When** validation runs on each
**Then** each report fails with the matching rule id: `transform.root_applied`, `pivot.bottom_center`, `uv.single_map`, `uv.overlap`, `material.node_types`, `material.uv_coordinates`, `budget.tris`, and `variants.names_match`
**And** a compliant fixture passes with no findings

### AC3: The re-import check compares exported FBX against the pre-export report

**Given** an exported variant folder with `SM_<Name>.fbx`, its PNG textures, and the validation report written before export
**When** the re-import check runs in a fresh headless Blender process (`--background --factory-startup`)
**Then** it passes when BC and N textures resolve beside the FBX, the ORM PNG is present, `UVMap` exists, and names, dimensions (within 0.1%), child-part pivots (within 0.1 mm), and triangle counts match the report
**And** when a texture file is deleted from the folder it fails with rule `reimport.texture_missing` naming the file

### AC4: Review renders are written to a known folder

**Given** an asset collection (and its `<Name>_Mobile` collection, when present)
**When** review renders run with an output folder
**Then** `<out>/<variant>/<Name>_{front,back,side,three_quarter}.png` are written for each present variant (`desktop`, `mobile`) at the requested resolution (default 1024)
**And** the camera frames the asset's bounding box and the lighting rig is the same for every view and variant
**And** the user's scenes are unchanged afterward

### AC5: The texture proof sheet compares baked, re-imported, and pre-bake looks

**Given** a variant folder with exported FBX and textures, and optionally a pre-bake render
**When** the texture proof runs
**Then** it re-imports the FBX in a scratch scene, wires `T_*_ORM` through Separate Color (G → Roughness, B → Metallic) the way the Unreal import does, renders the three-quarter view, and writes `<out>/<variant>/<Name>_proof.png`
**And** the proof sheet places the pre-bake render (when given), the baked in-scene render, and the re-imported render side by side with labels

### AC6: The gate helper stops finalize on failure

**Given** a failing validation report or a failing re-import report
**When** `nmg_game_dev.quality.contract.gate(report, kind)` is called with `kind` `contract` or `reimport`
**Then** it raises `PipelineError` with code `quality.contract_failed` or `quality.reimport_mismatch`, stage `quality`, a message listing each finding's rule and target, and the report attached
**And** a passing report returns without raising

### AC7: One implementation is reachable from operators and the CLI

**Given** the add-on is enabled
**When** `nmggamedev.validate_contract`, `nmggamedev.reimport_check`, or `nmggamedev.render_review` runs, or `python -m nmg_game_dev.contract validate|reimport|render --blend <file> ...` runs
**Then** each calls the same `contract_core` function and writes the same JSON report and files
**And** the CLI exits 0 on pass, 1 on a failing report, and 2 with a remediation when Blender can't be found

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | `contract_core.validate_asset(collection, asset_class, budgets_path=None)` implementing AC1, generic across classes (no per-asset-type rules) | Must |
| FR2 | `contract_core.reimport_check(variant_dir, pre_report)` run in a fresh headless Blender process; operators spawn `bpy.app.binary_path` | Must |
| FR3 | `contract_core.render_review(collection, out_dir, resolution=1024)` and `render_texture_proof(variant_dir, out_dir, pre_bake=None)` | Must |
| FR4 | Operators, `execute_blender_code`-callable functions, and `python -m nmg_game_dev.contract` share the implementation | Must |
| FR5 | Pydantic `ContractReport` / `Finding` models and `gate()` in `src/nmg_game_dev/quality/contract.py` | Must |
| FR6 | Blender headless tests with a fixture per failure class in AC2, plus the re-import missing-texture case | Must |

## Out of Scope

- Subjective art-direction judgment as a gate; renders inform review, only contract checks block
- Turntables, material-ball renders, and a separate inspection skill
- Wiring the gate into the finalize pipeline (#69); baking and producing the pre-bake render (#67); producing variants (#33)

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #30 | 2026-10-29 | Initial feature spec |
