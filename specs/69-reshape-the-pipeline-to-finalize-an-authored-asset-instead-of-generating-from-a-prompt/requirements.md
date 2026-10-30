# Requirements: Reshape the pipeline to finalize an authored asset instead of generating from a prompt

**Issue**: #69
**Date**: 2026-10-30
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/30-add-contract-validation-re-import-check-and-review-renders/

## User Story

**As an** NMG game developer working with an agent in Blender
**I want** one command, plus each of its steps as an individual agent tool, that takes an asset I've finished authoring and makes it shippable: validate, bake, build variants, export, re-verify, import into Unreal
**So that** freeform authoring ends in a contract-compliant asset in UE without the agent re-inventing that tooling every session

## Background

Assets are authored freeform by the agent through the Blender MCP; `docs/asset-contract.md` defines what "done" means. The current pipeline core assumes the opposite. `pipeline.run(prompt, source)` starts with a `generate` stage calling Blender functions that don't exist, and its cache is keyed on a prompt hash.

This issue replaces it with a finalize pipeline over an authored collection. The steps are contract validation and the re-import check (#30), the bake (#67), and cleanup, Mobile variant, and export (#33), over the toolchain from #68. Blender MCP calls time out after 180 s, so the Blender steps run in a background headless Blender against a checkpoint of the session and load their results back into the open session. FBX doesn't carry ORM wiring or Unreal's Flip Green Channel setting, so the UE import finishes the materials.

## Acceptance Criteria

### AC1: Finalize starts from an authored asset

**Given** a collection `<Name>` in the open Blender session (or in a saved `.blend` given with `--blend`), a category, an asset class, and an export root
**When** finalize runs
**Then** it runs `validate → bake → variants → export → reimport → import_ue` in that order and returns a result listing each step's outcome and the UE content paths
**And** the package exposes no `Prompt` type, `generate` stage, `source` argument, or Meshy routing

### AC2: Long steps run in the background and load back

**Given** a finalize run or single step started from an agent session
**When** it runs
**Then** the session's scene is saved as a checkpoint copy, and every Blender step runs in a background `blender --background` process against that checkpoint, writing progress (`state`, `step`, `progress` 0–1, `message`) that the agent can poll
**And** when the Blender steps succeed, the baked `<Name>` and the `<Name>_Mobile` collection are loaded back into the open session, replacing the old ones, unless the session's `<Name>` changed since the checkpoint. In that case nothing is replaced, and the run reports `finalize.session_changed` with the result `.blend` path
**And** if the background process exits without finishing, the job fails with `finalize.job_crashed` naming the step, and the open session is unchanged

### AC3: Each step is an agent tool too

**Given** an authoring session
**When** the agent runs one step (`validate`, `bake`, `variants`, `export`, `reimport`, or `import_ue`) through `python -m nmg_game_dev.finalize <step>` or the `finalize` MCP tool `run_finalize_step`
**Then** the same step implementation finalize uses runs, and returns a structured result with `step`, `cache_hit`, `outputs`, and `summary`
**And** the MCP tools return a job id immediately, or the finished result when it completes within `wait_seconds` (at most 150), and `get_finalize_job(job_id)` reports status and the result

### AC4: Content-addressed caching

**Given** an asset that was already finalized and is unchanged (before or after its results were loaded back)
**When** finalize runs again
**Then** every step is a cache hit keyed on the asset's content (mesh, materials, images, transforms), the asset class, the resolved budgets, and the step settings, and no step's work is redone
**And** a change to any mesh, material, or image misses the cache from the first affected step onward, and `--force` reruns every step

### AC5: UE import completes the materials

**Given** exported Desktop and Mobile folders and the UE 5.8 editor with the Unreal MCP and VibeUE
**When** the `import_ue` step runs
**Then** the meshes and textures land in `/Game/<Category>/<Name>/Desktop/` and `/Game/<Category>/<Name>/Mobile/` with identical asset names in both folders
**And** `T_*_N` textures have Flip Green Channel set and normal-map compression; `T_*_ORM` textures are linear with masks compression; `T_*_BC` textures are sRGB
**And** each material slot `M_<Name>_<Part>` gets a material instance `MI_<Name>_<Part>` of `/nmg-game-dev/Materials/M_NmgORM` with `BaseColor`, `Normal`, and `ORM` set (ORM R=AO, G=roughness, B=metallic)
**And** each child part is its own static mesh whose local bounds match the Blender part's local bounds (meters → centimeters, Y negated) within 0.01 cm

### AC6: Failures stop the run

**Given** any step fails (a failing contract or re-import report, a bake error, a variants error, a crashed job, or a UE error)
**When** finalize is running
**Then** it stops with a `PipelineError` carrying `code`, `message`, `remediation`, and `stage`; no later step runs; and nothing is imported into UE unless every earlier step passed

### AC7: Steering matches

**Given** `steering/snippets/project-product.md`, `project-tech.md`, and `project-structure.md`
**When** they are read
**Then** they describe freeform authoring plus finalize and contain no `new-prop`, `new-character`, `generate_mesh`, `source="meshy"`, or prompt-to-asset journey
**And** the tech snippet's long-running Blender work section names the job runner, the `finalize` MCP tools, and the CLI instead of pointing at #69

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | Replace `pipeline.run(prompt, source)` with `pipeline.finalize(request)` and `pipeline.run_step(step, request)` over a `FinalizeRequest`; remove `Prompt`, the `generate`/`texture`/`cleanup`/`variants`/`quality`/`import_ue` stage modules, and source routing | Must |
| FR2 | Host-side job runner (detached `python -m nmg_game_dev.finalize run-job`) that checkpoints the session, runs Blender steps in `blender --background` via `scripts/blender/finalize_entry.py`, reports progress, detects crashes, and loads results back | Must |
| FR3 | `python -m nmg_game_dev.finalize` CLI and the `finalize` MCP server (`finalize_asset`, `run_finalize_step`, `get_finalize_job`) over one implementation; `skills/finalize-asset/SKILL.md` | Must |
| FR4 | Per-step content-addressed cache keys and a finalized-hash alias index | Must |
| FR5 | UE import through the Unreal MCP (`execute_python_code`) that imports textures with the right settings, creates `MI_<Name>_<Part>` instances of the plugin-owned `M_NmgORM`, and preserves part pivots; `M_NmgORM.uasset` built by a repo script | Must |
| FR6 | Real clients: a Blender session socket client and an Unreal MCP HTTP client | Must |
| FR7 | Steering tech snippet and a steering guard test per AC7; `docs/mcp/finalize.md` | Must |
| FR8 | Unit and BDD tests with fake clients and fake runners; Blender-backed tests under `tests/blender/`; a live e2e test | Must |

## Out of Scope

- The step implementations themselves: contract validation and re-import (#30), bake (#67), cleanup/variants/export (#33)
- Texture generation (#7)
- Composing multi-asset scenes or levels
- Removing UE content when a cached `import_ue` step is skipped (use `--force` to reimport)

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #69 | 2026-10-30 | Initial feature spec |
