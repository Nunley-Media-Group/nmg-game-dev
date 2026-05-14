# Requirements: Umbrella - deliver Blender MCP-only recipe asset generation

**Issues**: #27
**Date**: 2026-05-11
**Status**: Draft
**Author**: Rich Nunley

---

## User Story

**As an** internal NMG game developer (primary persona per `steering/product.md`)
**I want** Blender MCP-only recipe asset generation coordinated as a multi-PR v1 feature
**So that** supported asset families are generated through deterministic local Blender recipes with review gates, provenance, and Desktop/Mobile variants, without relying on local model servers or paid/quota-limited providers.

---

## Background

Issue #5 produced the accepted ADR at `docs/decisions/2026-05-02-blender-as-meshy-gap-analysis.md`. That ADR recommends Blender MCP recipe generation as the v1 asset-creation path after evaluating model/provider-backed alternatives and proving the strongest controllable result came from typed asset specs, per-family geometry builders, reusable material and motif libraries, GLB export, and mandatory multi-angle review.

Issue #27 is the implementation umbrella for that direction. The issue body already names the active child issues:

- #31 - Add Blender MCP recipe job orchestration.
- #35 - Add Blender MCP recipe asset generation.
- #29 - Implement Blender procedural material and texture packaging.
- #33 - Build Blender cleanup remesh LOD and variant operators.
- #32 - Support humanoid rigging and animation import.
- #30 - Add asset inspection and review gates.

The recipe catalog is intentionally split into one child issue per recipe type because every family requires Blender visual inspection before it can be called ready:

- #37 - Add potion and bottle recipe family.
- #38 - Add melee weapon recipe family.
- #39 - Add firearm and handheld tool recipe family.
- #40 - Add chest and container recipe family.
- #41 - Add key collectible and pickup recipe family.
- #42 - Add platform and door recipe family.
- #43 - Add modular building piece recipe family.
- #44 - Add road path and sidewalk recipe family.
- #45 - Add streetlight lamp and outdoor lighting recipe family.
- #46 - Add traffic sign and wayfinding recipe family.
- #47 - Add barrier fence and street fixture recipe family.
- #48 - Add environment kit and modular prop recipe family.
- #49 - Add terrain rock and natural ground recipe family.
- #50 - Add foliage and natural asset recipe family.
- #51 - Add furniture and interior dressing recipe family.
- #52 - Add armor clothing and accessory recipe family.
- #53 - Add modular humanoid character recipe family.
- #54 - Add modular creature character recipe family.
- #55 - Add wheeled vehicle recipe family.
- #56 - Add hover vehicle recipe family.
- #57 - Add simple aircraft recipe family.
- #58 - Add watercraft recipe family.
- #59 - Add stylized VFX marker and emissive mesh recipe family.
- #60 - Add prompt-driven recipe refinement workflow.

The umbrella's purpose is coordination, not a single large shipping PR. It defines the shared contract every child issue must preserve: Blender MCP recipe generation is the only v1 happy path for supported asset families; historical model/provider-backed paths remain benchmark evidence only; every generated asset must produce inspectable artifacts, quality metadata, and split Desktop/Mobile outputs before UE import.

---

## Acceptance Criteria

**IMPORTANT: Each criterion becomes a Gherkin BDD test scenario.**

### AC1: Blender MCP-only happy path

**Given** a supported v1 asset request for a prop, kit piece, weapon, pickup, platform, door, container, road, streetlight, sign, potion/bottle, modular character, creature, or modular vehicle
**When** nmg-game-dev runs the asset-generation happy path
**Then** generation is performed through local Blender MCP recipe execution
**And** the workflow does not invoke Hunyuan3D, FLUX, TripoSR, InstantMesh, ComfyUI, Diffusers, Meshy, Hyper3D, Substance, Mixamo, CUDA-only paths, local specialized model servers, hosted generation APIs, or paid/quota-limited providers.

**Example**:
- Given: `$new-prop Props/ManaPotion standard "glowing blue mana potion"` in a consumer project with Blender MCP available.
- When: the v1 generation path runs.
- Then: the produced artifact comes from a Blender recipe, records recipe provenance, and has no provider-backed generation metadata.

### AC2: Multi-PR child delivery remains traceable

**Given** umbrella issue #27 and the accepted ADR from issue #5
**When** child issues #31, #35, #29, #33, #32, and #30 are implemented across separate PRs
**Then** each child links back to this umbrella spec and the ADR
**And** each child can be reviewed, tested, and merged independently without losing the shared Blender MCP-only contract.

**Example**:
- Given: child issue #29 replaces `texture.not_implemented`.
- When: its PR is opened.
- Then: the PR references this spec, the ADR, and its child issue without claiming the orchestration, recipe-family, rigging, or review-gate children are complete.

### AC3: Recipe jobs are orchestrated with provenance

**Given** a pipeline stage requests a recipe-backed asset generation job
**When** the job is submitted, polled, cancelled, completed, cached, or retried after a listener restart
**Then** nmg-game-dev records structured job status, progress, cancellation state, cache keys, artifact manifests, local output paths, recipe provenance, material provenance, Blender version, MCP version, and review artifact references in serializable sidecars.

**Example**:
- Given: a recipe job completes after Blender MCP is restarted once.
- When: the pipeline stores the artifact.
- Then: the sidecar remains replayable and names the recipe id, recipe version, prompt/spec inputs, seed, generated files, Blender version, and MCP version.

### AC4: Supported recipe families produce reviewable GLBs

**Given** a supported recipe family such as potion/bottle, melee weapon, firearm/tool, chest/container, key/collectible, platform/door, modular building piece, road/path/sidewalk, streetlight/lamp, traffic sign/wayfinding, barrier/fence/street fixture, environmental kit piece, modular prop, modular character, creature, or modular vehicle
**When** the recipe engine runs with the same recipe id, seed, dimensions, style preset, and material preset
**Then** it emits deterministic Blender output, GLB export, object/material/poly statistics, dimensions, and five-angle review renders
**And** unsupported families fail with `unsupported_recipe_family` or equivalent structured remediation instead of falling back to a model/provider backend.

**Example**:
- Given: the same potion recipe id, seed, material preset, and dimensions.
- When: the engine runs twice.
- Then: geometry naming, material slots, output manifest keys, and review artifact paths are stable enough for cache reuse.

### AC5: Materials and PBR packaging are Blender-owned

**Given** a generated mesh from the recipe engine
**When** the material and texture stage runs
**Then** Blender procedural materials, UV unwrap, material-slot assignment, bake-down, GLB export, and PBR channel validation replace the current `texture.not_implemented` placeholder
**And** no Hunyuan3D-Paint, ComfyUI, Diffusers, Material Maker, Substance, hosted texture generation, or text-to-image path is required.

**Example**:
- Given: a recipe-generated chest mesh.
- When: material packaging runs.
- Then: the exported GLB has base-color, metallic-roughness, normal, and optional AO/emissive evidence where available, plus material preset metadata in the sidecar.

### AC6: Cleanup, LOD, and variants are physical outputs

**Given** a generated and textured asset
**When** Blender cleanup, remesh, LOD, texture bake-down, and variant operators run
**Then** Desktop and Mobile outputs are separate physical assets with identical logical names under `Content/<Category>/<Name>/Desktop/` and `Content/<Category>/<Name>/Mobile/`
**And** sidecars record poly counts, texture byte totals, LOD levels, bake settings, and applied mobile budget values.

**Example**:
- Given: `Content/Props/ManaPotion/`.
- When: variant generation finishes.
- Then: the Desktop output retains quality-preserved geometry, the Mobile output is budgeted, and the quality stage has the metrics it needs before UE import.

### AC7: Review gates block bad assets

**Given** generated outputs with missing PBR channels, empty geometry, invalid scale, incoherent recipe geometry, over-budget Mobile variants, or unsupported recipe-family requests
**When** inspection and review gates run
**Then** the workflow writes five-angle renders, turntable renders, material-ball renders, screenshots, and budget/quality reports
**And** failures stop before UE import or shipping workflows continue, with structured remediation suitable for rerun or backlog creation.

**Example**:
- Given: a modular prop GLB with empty geometry.
- When: the review gate evaluates it.
- Then: UE import is skipped and the error names the failed check plus the asset/report paths needed for diagnosis.

### AC8: Broad recipe catalog covers normal game asset, character, vehicle, and street-infrastructure needs

**Given** the v1 recipe catalog is considered ready for normal NMG game production
**When** catalog coverage tests run
**Then** tested and proven recipes cover representative normal game assets, modular characters, modular vehicles, roads, streetlights, signs, and streetside infrastructure
**And** each recipe family has a fixture spec, generated GLB, review bundle, sidecar provenance, and automated coverage proving it can be rerun deterministically.

**Example**:
- Given: the catalog includes fixtures for props, weapons, containers, building modules, roads, sidewalks, streetlights, traffic signs, streetside barriers, environment kits, humanoid characters, creatures, wheeled vehicles, hover vehicles, simple aircraft, and watercraft.
- When: the catalog proof suite runs.
- Then: every fixture produces reviewable GLB output and records the recipe/material provenance needed for cache reuse and follow-up tuning.

### AC9: Prompt-driven refinement improves models and textures inside the recipe workflow

**Given** a generated recipe asset and a developer prompt requesting more model detail, silhouette changes, material changes, texture wear, decals, color, or emissive treatment
**When** the refinement workflow runs
**Then** it maps supported prompt details to deterministic recipe/material parameters, reruns the Blender MCP recipe path, and records the refinement prompt, generated output, review bundle, and accepted/rejected state in sidecar provenance.

**Example**:
- Given: a road fixture and the refinement prompt "add cracked asphalt, worn lane paint, and trash near the curb."
- When: prompt-driven refinement runs.
- Then: the regenerated road asset changes only through supported road/material recipe parameters and produces a new review bundle for Blender inspection.

---

## Generated Gherkin Preview

```gherkin
Feature: Blender MCP-only recipe asset generation umbrella
  As an internal NMG game developer
  I want Blender MCP-only recipe asset generation coordinated as a multi-PR v1 feature
  So that supported asset families are generated locally with deterministic recipes, review gates, provenance, and variants

  Scenario: Blender MCP-only happy path
    Given a supported v1 asset request
    When nmg-game-dev runs the asset-generation happy path
    Then generation is performed through local Blender MCP recipe execution
    And no model server, hosted generation API, paid provider, or quota-limited backend is invoked

  Scenario: Multi-PR child delivery remains traceable
    Given umbrella issue #27 and the accepted ADR from issue #5
    When the child issues are implemented across separate PRs
    Then each child links back to the umbrella spec and ADR
    And each child remains independently reviewable

  Scenario: Recipe jobs are orchestrated with provenance
    Given a pipeline stage requests a recipe-backed asset generation job
    When the job is submitted, polled, cancelled, completed, cached, or retried
    Then structured job state and artifact provenance are recorded in serializable sidecars

  Scenario: Supported recipe families produce reviewable GLBs
    Given a supported recipe family request
    When the recipe engine runs with deterministic inputs
    Then it emits Blender output, GLB export, statistics, dimensions, and five-angle review renders
    And unsupported families fail honestly without backend fallback

  Scenario: Materials and PBR packaging are Blender-owned
    Given a generated mesh from the recipe engine
    When the material and texture stage runs
    Then Blender procedural material and PBR packaging replaces the texture placeholder
    And no external texture generation backend is required

  Scenario: Cleanup, LOD, and variants are physical outputs
    Given a generated and textured asset
    When cleanup, remesh, LOD, bake-down, and variant operators run
    Then Desktop and Mobile outputs are separate physical assets with budget metadata

  Scenario: Review gates block bad assets
    Given a generated output with a quality or support failure
    When inspection and review gates run
    Then review artifacts are written
    And the workflow stops before UE import with structured remediation

  Scenario: Broad recipe catalog covers normal game asset, character, vehicle, and street-infrastructure needs
    Given the v1 recipe catalog is considered ready for normal NMG game production
    When catalog coverage tests run
    Then representative asset, character, vehicle, road, streetlight, sign, and street-fixture recipes produce reviewable GLBs
    And each recipe records deterministic provenance and automated coverage

  Scenario: Prompt-driven refinement improves models and textures inside the recipe workflow
    Given a generated recipe asset and a prompt requesting model or texture detail changes
    When the refinement workflow runs
    Then supported prompt details map to deterministic recipe and material parameters
    And the rerun records refinement provenance and review state
```

---

## Functional Requirements

| ID | Requirement | Priority | Notes |
|----|-------------|----------|-------|
| FR1 | Create and maintain this umbrella feature spec for #27, referencing ADR `docs/decisions/2026-05-02-blender-as-meshy-gap-analysis.md` and coordinating child issues #31, #35, #29, #33, #32, and #30. | Must | This spec is a coordination contract, not a single implementation PR. |
| FR2 | Declare Blender MCP recipe generation as the only v1 asset-generation happy path for supported asset families. | Must | Model/provider paths remain historical benchmark evidence only. |
| FR3 | Require recipe job orchestration covering submit, poll, cancel, progress, cache keys, artifact manifests, recipe provenance, material provenance, and safe listener restart handling. | Must | Owned by #31. |
| FR4 | Require typed asset specs, per-family recipe builders, reusable part/motif libraries, deterministic seeds, GLB export, and unsupported-family errors. | Must | Owned primarily by #35. |
| FR5 | Require Blender procedural material generation and PBR packaging that replaces `texture.not_implemented`. | Must | Owned by #29. |
| FR6 | Require Blender-native cleanup, remesh, LOD, texture bake-down, and physical Desktop/Mobile variant outputs. | Must | Owned by #33. |
| FR7 | Require constrained local humanoid rigging and animation-library import while explicitly failing unsupported non-biped and text-driven custom motion requests. | Must | Owned by #32. |
| FR8 | Require inspection/review artifacts, budget reports, structured remediation, and fail-before-import behavior. | Must | Owned by #30. |
| FR9 | Require BDD, unit, Blender-headless, and integration coverage appropriate to each child issue's blast radius. | Must | Every AC in this umbrella must map to at least one Gherkin scenario. |
| FR10 | Require a broad tested recipe catalog for normal game asset, street-infrastructure, character, creature, and vehicle requirements, with fixture specs and proven generated outputs for each representative family. | Must | #35 owns the recipe engine/catalog harness; each recipe type has its own additional child issue linked to #27. |
| FR11 | Require prompt-driven refinement for supported model detail and texture/material detail changes, with deterministic reruns and review-loop provenance. | Must | Owned by #60. |

---

## Non-Functional Requirements

| Aspect | Requirement |
|--------|-------------|
| **Performance** | Preserve `steering/tech.md` authoring targets: standard prop generation should fit the <= 90 s target on an M-series Mac when the recipe is implemented and cached stages are warm; hero character work keeps the <= 5 min target. |
| **Security** | Do not require API keys or credentials for v1 happy-path asset generation. External provider credentials must not be read, logged, or silently used by this path. |
| **Reliability** | Jobs must be idempotent, resumable, cacheable, and replayable from sidecar provenance. Partial failures must leave enough state for diagnosis or safe rerun. |
| **Platforms** | Produce Desktop and Mobile physical variants from the first implementation path, following `steering/structure.md` split-variant convention. |
| **Observability** | Review artifacts and sidecars must make recipe inputs, outputs, budgets, material choices, and failure reasons inspectable without rerunning generation. |

---

## UI/UX Requirements

This umbrella does not require a broad in-app UI. Child issues may add narrow surfaces where they are the right control shape:

| Element | Requirement |
|---------|-------------|
| **Skill interaction** | Consumer-facing asset skills must fail fast with actionable remediation when Blender MCP is unavailable, a recipe family is unsupported, or a quality gate rejects output. |
| **Inspection surface** | Review outputs must be easy to open from an `inspect-artifact` skill or asset-reviewer surface, with links/paths to renders, turntables, material evidence, and budget reports. |
| **Blender add-on surface** | Blender operators should remain available through the existing nmg add-on and callable through the pinned `ahujasid/blender-mcp` host. |
| **Error states** | Unsupported or rejected assets must produce backlog-ready failure detail, not raw tracebacks or silent fallback. |

---

## Data Requirements

### Input Data

| Field | Type | Validation | Required |
|-------|------|------------|----------|
| `asset_family` | string / enum | Must resolve to a supported recipe family (asset, character, or vehicle) or return `unsupported_recipe_family`. | Yes |
| `category` | string | Must map to a consumer content category. | Yes |
| `name` | string | Must produce a stable asset/logical name. | Yes |
| `tier` | enum | `standard` or `hero` until additional tiers are specified. | Yes |
| `description` | string | Non-empty creative intent; recipe parser extracts constrained parameters from it. | Yes |
| `seed` | int or null | When present, deterministic recipe output must reuse it. | No |
| `style_preset` | string / enum | Must resolve to a recipe-supported style or fail with remediation. | No |
| `material_preset` | string / enum | Must resolve to Blender-owned material presets or fail before export. | No |
| `target_budgets` | object | Must include Mobile poly/texture constraints when overriding defaults. | No |
| `refinement_prompt` | string | Optional prompt for supported model-detail, silhouette, material, texture, wear, decal, color, or emissive changes. Unsupported requests fail with structured remediation. | No |

### Output Data

| Field | Type | Description |
|-------|------|-------------|
| `job_id` | string | Stable recipe job id for submit/poll/cancel. |
| `recipe_id` | string | Selected asset-family recipe. |
| `recipe_version` | string | Version of the recipe contract used for generation. |
| `seed` | int | Deterministic seed used by geometry/material builders. |
| `glb_path` | path | Generated or packaged GLB output. |
| `desktop_path` | path | Desktop physical variant output. |
| `mobile_path` | path | Mobile physical variant output. |
| `review_paths` | object | Front/right/back/three-quarter/top renders plus turntable/material-ball artifacts where available. |
| `statistics` | object | Object count, material count, vertices/faces, dimensions, texture byte totals, LOD levels, and budget results. |
| `provenance` | object | Recipe inputs, material presets, Blender version, MCP version, source files, and cache keys. |

---

## Dependencies

### Internal Dependencies

- [x] `docs/decisions/2026-05-02-blender-as-meshy-gap-analysis.md` - Accepted ADR from issue #5.
- [x] `specs/feature-scaffold-plugin-repo-session-start-hooks/` - Plugin shell, `.mcp.json`, and launch-script contract.
- [x] `specs/feature-blender-add-on-skeleton-blender-mcp-wiring/` - Blender add-on and `ahujasid/blender-mcp` invocation seam.
- [x] `specs/feature-pipeline-composition-core-variant-aware-stage-runner/` - Pipeline stage runner, `StageArtifact`, cache, variants, and quality scaffolding.
- [ ] #31 - Add Blender MCP recipe job orchestration.
- [ ] #35 - Add Blender MCP recipe asset generation.
- [ ] #29 - Implement Blender procedural material and texture packaging.
- [ ] #33 - Build Blender cleanup remesh LOD and variant operators.
- [ ] #32 - Support humanoid rigging and animation import.
- [ ] #30 - Add asset inspection and review gates.
- [ ] #37 - Add potion and bottle recipe family.
- [ ] #38 - Add melee weapon recipe family.
- [ ] #39 - Add firearm and handheld tool recipe family.
- [ ] #40 - Add chest and container recipe family.
- [ ] #41 - Add key collectible and pickup recipe family.
- [ ] #42 - Add platform and door recipe family.
- [ ] #43 - Add modular building piece recipe family.
- [ ] #44 - Add road path and sidewalk recipe family.
- [ ] #45 - Add streetlight lamp and outdoor lighting recipe family.
- [ ] #46 - Add traffic sign and wayfinding recipe family.
- [ ] #47 - Add barrier fence and street fixture recipe family.
- [ ] #48 - Add environment kit and modular prop recipe family.
- [ ] #49 - Add terrain rock and natural ground recipe family.
- [ ] #50 - Add foliage and natural asset recipe family.
- [ ] #51 - Add furniture and interior dressing recipe family.
- [ ] #52 - Add armor clothing and accessory recipe family.
- [ ] #53 - Add modular humanoid character recipe family.
- [ ] #54 - Add modular creature character recipe family.
- [ ] #55 - Add wheeled vehicle recipe family.
- [ ] #56 - Add hover vehicle recipe family.
- [ ] #57 - Add simple aircraft recipe family.
- [ ] #58 - Add watercraft recipe family.
- [ ] #59 - Add stylized VFX marker and emissive mesh recipe family.
- [ ] #60 - Add prompt-driven recipe refinement workflow.

### External Dependencies

- [x] `ahujasid/blender-mcp` pinned in `.mcp.json`.
- [x] Local Blender 4.x, with 4.2 LTS as the oldest supported version.

### Blocked By

- [x] Issue #5 - ADR accepted and committed.

---

## Out of Scope

- Hunyuan3D, FLUX, TripoSR, InstantMesh, ComfyUI, Diffusers, Meshy, Hyper3D, Substance, Material Maker, Mixamo, CUDA-only paths, local specialized model servers, hosted generation APIs, and paid/quota-limited providers as v1 happy-path generation, texture, rigging, or fallback backends.
- Replacing or forking `ahujasid/blender-mcp`.
- Promising arbitrary prompt-to-3D outside the tested recipe catalog.
- Quadruped, creature, or non-biped auto-rigging unless a specific tested recipe family is added.
- Text-driven custom motion generation.
- Treating prompt-driven refinement as automatable; accepted output still requires Blender visual inspection.
- Shipping all child work in one implementation PR.
- Reopening issues #28 or #34 for v1; they remain closed as not planned for the Blender MCP-only direction.

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Supported-family happy path | 100% of supported families route through Blender MCP recipes only. | Proven by BDD/unit tests and sidecar provenance checks. |
| Provider/model fallback prevention | 0 silent routes to model/provider-backed generation in v1 happy path. | Tests cover unsupported backend requests and inspect sidecars for source provenance. |
| Review artifact coverage | Every generated asset has five-angle renders plus statistics and budget reports before UE import. | Review-gate tests and artifact manifest assertions. |
| Variant discipline | Every generated asset produces separate Desktop and Mobile physical outputs. | Variant path assertions and cook-manifest-ready sidecar checks. |
| Recipe catalog breadth | Representative normal game assets, street infrastructure, modular characters, creatures, and modular vehicles have tested/proven recipe fixtures. | Catalog proof suite output and fixture-generated review bundles. |
| Recipe issue traceability | Every recipe type in the catalog has its own child issue linked to umbrella #27. | GitHub child issue list plus PR/spec references. |
| Refinement workflow | Supported prompts can refine model detail and texture/material detail without leaving the Blender MCP recipe path. | Refinement BDD tests and review-bundle provenance for accepted/rejected iterations. |
| Child traceability | Every child PR references #27, this spec, and the ADR. | PR/spec verification during `$nmg-sdlc:verify-code` and `$nmg-sdlc:open-pr`. |

---

## Open Questions

None.

---

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #27 | 2026-05-11 | Initial feature spec |

---

## Validation Checklist

Before moving to PLAN phase:

- [x] User story follows "As a / I want / So that" format.
- [x] All acceptance criteria use Given/When/Then format.
- [x] No implementation details beyond required architecture constraints appear in acceptance criteria.
- [x] All criteria are testable and unambiguous.
- [x] Success metrics are measurable.
- [x] Edge cases and error states are specified.
- [x] Dependencies are identified.
- [x] Out of scope is defined.
- [x] Open questions are documented or resolved.
