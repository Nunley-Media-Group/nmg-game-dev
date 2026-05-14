# Tasks: Umbrella - deliver Blender MCP-only recipe asset generation

**Issues**: #27
**Date**: 2026-05-11
**Status**: Planning
**Author**: Rich Nunley

---

## Summary

Issue #27 is an umbrella coordination spec. Its own branch should seal the spec
and transition work to existing child issues; it should not implement the full
recipe engine in one PR.

| Phase | Tasks | Status |
|-------|-------|--------|
| Setup - umbrella seal and orchestration foundation | 4 | [ ] |
| Backend - recipe engine, materials, cleanup, rigging | 6 | [ ] |
| Catalog - recipe families and refinement | 4 | [ ] |
| Integration - review gates, UE import, provider guards | 4 | [ ] |
| Testing - BDD, unit, Blender-headless, visual proof | 4 | [ ] |
| **Total** | **22** | |

---

## Task Format

```
### T[NNN]: [Task Title]

**File(s)**: path/to/file
**Type**: Create | Modify | Delete | Coordinate
**Depends**: T[NNN], T[NNN] (or None)
**Owner Issue(s)**: #N
**Acceptance**:
- [ ] verifiable criterion
```

File paths map to the canonical layout in `steering/structure.md`.

---

## Phase 1: Setup - umbrella seal and orchestration foundation

### T001: Seal the umbrella spec and do not ship implementation on #27

**File(s)**:
- `specs/feature-umbrella-deliver-blender-mcp-only-recipe-asset-generation/requirements.md`
- `specs/feature-umbrella-deliver-blender-mcp-only-recipe-asset-generation/design.md`
- `specs/feature-umbrella-deliver-blender-mcp-only-recipe-asset-generation/tasks.md`
- `specs/feature-umbrella-deliver-blender-mcp-only-recipe-asset-generation/feature.gherkin`
**Type**: Coordinate
**Depends**: None
**Owner Issue(s)**: #27
**Acceptance**:
- [ ] Spec files are complete and internally consistent.
- [ ] `design.md` contains `## Multi-PR Rollout` and names existing child issues.
- [ ] Seal flow commits only this spec directory.
- [ ] No implementation files, version files, or changelog files are changed by the seal commit.

### T002: Implement Blender MCP recipe job orchestration

**File(s)**:
- `src/nmg_game_dev/pipeline/jobs.py`
- `src/nmg_game_dev/pipeline/artifacts.py`
- `src/nmg_game_dev/pipeline/cache.py`
- `tests/unit/pipeline/test_jobs.py`
- `tests/unit/pipeline/test_artifacts.py`
**Type**: Create / Modify
**Depends**: T001
**Owner Issue(s)**: #31
**Acceptance**:
- [ ] `RecipeJob` records id, request hash, recipe id/version, status, progress, cancellation state, timestamps, and resumability.
- [ ] `JobStore` supports submit, poll, cancel, complete, fail, and resume through JSON sidecars.
- [ ] `RecipeArtifactManifest` records GLB, Desktop/Mobile outputs, review paths, statistics, recipe/material provenance, Blender version, and MCP version.
- [ ] Listener restart handling leaves jobs resumable or failed with actionable remediation.
- [ ] Unit tests cover idempotent submit, cache-key stability, cancellation, corrupt sidecars, and restart recovery.

### T003: Add the typed recipe request and registry foundation

**File(s)**:
- `src/nmg_game_dev/recipes/__init__.py`
- `src/nmg_game_dev/recipes/request.py`
- `src/nmg_game_dev/recipes/base.py`
- `src/nmg_game_dev/recipes/registry.py`
- `tests/unit/recipes/test_request.py`
- `tests/unit/recipes/test_registry.py`
**Type**: Create
**Depends**: T002
**Owner Issue(s)**: #35
**Acceptance**:
- [ ] `RecipeRequest` validates `asset_family`, `category`, `name`, `tier`, `description`, `seed`, presets, budgets, and optional refinement prompt.
- [ ] `RecipeFamily` Protocol defines deterministic script generation and fixture proof requirements.
- [ ] `RecipeRegistry` resolves supported families and returns `unsupported_recipe_family` with remediation for missing families.
- [ ] Request and registry tests prove deterministic hashing and fail-before-MCP validation.

### T004: Add the recipe-first pipeline entrypoint

**File(s)**:
- `src/nmg_game_dev/pipeline/__init__.py`
- `src/nmg_game_dev/pipeline/stages/_base.py`
- `tests/unit/pipeline/test_run_recipe.py`
**Type**: Modify
**Depends**: T002, T003
**Owner Issue(s)**: #35
**Acceptance**:
- [ ] `run_recipe(request, *, cache_dir=None, mcp_clients=None, stage_overrides=None) -> PipelineResult` exists.
- [ ] `run_recipe` uses the job/manifest schema from T002.
- [ ] New consumer asset-generation paths do not require or invoke `source="meshy"`.
- [ ] Stage overrides remain available for deterministic tests.
- [ ] Unit tests prove provider-backed stages are not invoked by the recipe happy path.

---

## Phase 2: Backend - recipe engine, materials, cleanup, rigging

### T005: Implement direct Blender MCP recipe script execution

**File(s)**:
- `src/nmg_game_dev/pipeline/stages/generate.py`
- `src/nmg_game_dev/recipes/compiler.py`
- `plugins/nmg-game-dev-blender-addon/operators/recipe_execute.py`
- `tests/unit/pipeline/stages/test_generate_recipe.py`
**Type**: Modify / Create
**Depends**: T003, T004
**Owner Issue(s)**: #35
**Acceptance**:
- [ ] Blender generation compiles a `RecipeScript` from a `RecipeRequest` and executes it through `ctx.mcp_clients.blender.run_script(...)`.
- [ ] Script generation is constrained by recipe builders and never concatenates raw prompt text into executable Blender Python.
- [ ] Generated sidecars include recipe id/version, seed, selected presets, Blender version, MCP version, and raw output paths.
- [ ] Unsupported family requests fail before Blender MCP is called.

### T006: Replace `texture.not_implemented` with Blender material and PBR packaging

**File(s)**:
- `src/nmg_game_dev/pipeline/stages/texture.py`
- `src/nmg_game_dev/materials/__init__.py`
- `src/nmg_game_dev/materials/presets.py`
- `plugins/nmg-game-dev-blender-addon/operators/materials_package.py`
- `tests/blender/test_material_packaging.py`
**Type**: Modify / Create
**Depends**: T005
**Owner Issue(s)**: #29
**Acceptance**:
- [ ] The texture stage assigns Blender-owned procedural materials and no longer raises `texture.not_implemented`.
- [ ] UV unwrap, bake-down, material-slot assignment, and GLB PBR channel validation are exercised in Blender-headless tests.
- [ ] Sidecars record material preset ids/versions and PBR channel evidence.
- [ ] Hunyuan3D-Paint, ComfyUI, Diffusers, Material Maker, Substance, hosted texture generation, and text-to-image paths are not required.

### T007: Implement cleanup, remesh, LOD, and physical variants

**File(s)**:
- `src/nmg_game_dev/pipeline/stages/cleanup.py`
- `src/nmg_game_dev/pipeline/stages/variants.py`
- `src/nmg_game_dev/variants/__init__.py`
- `plugins/nmg-game-dev-blender-addon/operators/cleanup_desktop.py`
- `plugins/nmg-game-dev-blender-addon/operators/optimize_mobile.py`
- `plugins/nmg-game-dev-blender-addon/operators/generate_variants.py`
- `tests/blender/test_variant_outputs.py`
**Type**: Modify
**Depends**: T005, T006
**Owner Issue(s)**: #33
**Acceptance**:
- [ ] Desktop outputs preserve quality and Mobile outputs apply decimation/LOD/texture bake-down budgets.
- [ ] Outputs are separate physical assets under `Content/<Category>/<Name>/Desktop/` and `Content/<Category>/<Name>/Mobile/`.
- [ ] Sidecars record poly counts, texture byte totals, LOD levels, bake settings, and target budgets.
- [ ] Cross-variant reference guards fail before UE import.

### T008: Implement constrained humanoid rigging and animation import

**File(s)**:
- `src/nmg_game_dev/rigging/__init__.py`
- `src/nmg_game_dev/rigging/humanoid.py`
- `plugins/nmg-game-dev-blender-addon/operators/rigging_humanoid.py`
- `tests/blender/test_humanoid_rigging.py`
**Type**: Create
**Depends**: T005, T006
**Owner Issue(s)**: #32
**Acceptance**:
- [ ] Supported humanoid recipe outputs can run through a constrained Rigify/library import path.
- [ ] Non-biped, quadruped, deformable prop, and text-driven custom motion requests fail with structured unsupported errors.
- [ ] Sidecars record rigging template, imported animation references, and unsupported scope failures.
- [ ] Blender-headless tests prove supported and unsupported cases.

### T009: Add recipe proof fixture harness

**File(s)**:
- `src/nmg_game_dev/recipes/fixtures.py`
- `tests/recipes/fixtures/`
- `tests/blender/test_recipe_fixtures.py`
**Type**: Create
**Depends**: T003, T005
**Owner Issue(s)**: #35
**Acceptance**:
- [ ] Each recipe family can declare fixture specs with deterministic seed, dimensions, style preset, material preset, and expected manifest keys.
- [ ] Fixture runs emit GLB, statistics, review bundle paths, and provenance sidecars.
- [ ] The harness supports visual-inspection children without pretending visual acceptance is fully automatable.

### T010: Preserve Blender add-on and MCP host boundaries

**File(s)**:
- `plugins/nmg-game-dev-blender-addon/mcp_server/manifest.py`
- `scripts/start-blender-mcp.sh`
- `tests/blender/test_coexistence.py`
**Type**: Modify
**Depends**: T005, T006, T007, T008
**Owner Issue(s)**: #29, #30, #32, #33, #35
**Acceptance**:
- [ ] New `nmggamedev.*` operators remain callable through the existing `ahujasid/blender-mcp` host.
- [ ] The nmg add-on still binds no TCP port.
- [ ] `start-blender-mcp.sh` continues to launch only the external Blender MCP host.
- [ ] Coexistence tests cover the expanded operator surface.

---

## Phase 3: Catalog - recipe families and refinement

### T011: Implement normal prop and interactable recipe families

**File(s)**:
- `src/nmg_game_dev/recipes/families/potion_bottle.py`
- `src/nmg_game_dev/recipes/families/melee_weapon.py`
- `src/nmg_game_dev/recipes/families/firearm_tool.py`
- `src/nmg_game_dev/recipes/families/container.py`
- `src/nmg_game_dev/recipes/families/pickup.py`
- `src/nmg_game_dev/recipes/families/platform_door.py`
- `tests/recipes/fixtures/props/`
**Type**: Create
**Depends**: T009
**Owner Issue(s)**: #37, #38, #39, #40, #41, #42
**Acceptance**:
- [ ] Each family exposes a deterministic builder, fixture spec, generated GLB, review bundle, and provenance sidecar.
- [ ] Unsupported prompt details fail or become backlog-ready remediation, not provider fallback.
- [ ] Each family receives Blender visual inspection before completion.

### T012: Implement environment, street, terrain, foliage, and interior recipe families

**File(s)**:
- `src/nmg_game_dev/recipes/families/modular_building.py`
- `src/nmg_game_dev/recipes/families/road_sidewalk.py`
- `src/nmg_game_dev/recipes/families/streetlight.py`
- `src/nmg_game_dev/recipes/families/sign_wayfinding.py`
- `src/nmg_game_dev/recipes/families/street_fixture.py`
- `src/nmg_game_dev/recipes/families/environment_kit.py`
- `src/nmg_game_dev/recipes/families/terrain_rock.py`
- `src/nmg_game_dev/recipes/families/foliage.py`
- `src/nmg_game_dev/recipes/families/furniture.py`
- `tests/recipes/fixtures/environment/`
**Type**: Create
**Depends**: T009
**Owner Issue(s)**: #43, #44, #45, #46, #47, #48, #49, #50, #51
**Acceptance**:
- [ ] Modular building, road, sidewalk, streetlight, sign, barrier, environment kit, terrain, foliage, and furniture recipes produce reviewable GLBs.
- [ ] Sidecars include dimensions and material/motif provenance appropriate for environment and street-infrastructure use.
- [ ] Each family has fixture coverage and visual proof.

### T013: Implement character, creature, vehicle, and VFX marker recipe families

**File(s)**:
- `src/nmg_game_dev/recipes/families/armor_accessory.py`
- `src/nmg_game_dev/recipes/families/humanoid_character.py`
- `src/nmg_game_dev/recipes/families/creature_character.py`
- `src/nmg_game_dev/recipes/families/wheeled_vehicle.py`
- `src/nmg_game_dev/recipes/families/hover_vehicle.py`
- `src/nmg_game_dev/recipes/families/simple_aircraft.py`
- `src/nmg_game_dev/recipes/families/watercraft.py`
- `src/nmg_game_dev/recipes/families/vfx_marker.py`
- `tests/recipes/fixtures/characters_vehicles/`
**Type**: Create
**Depends**: T008, T009
**Owner Issue(s)**: #52, #53, #54, #55, #56, #57, #58, #59
**Acceptance**:
- [ ] Character, creature, vehicle, and VFX marker builders produce deterministic, reviewable fixture outputs.
- [ ] Humanoid output integrates with the constrained rigging path where supported.
- [ ] Creature and non-humanoid scope is explicit and fails honestly where rigging/animation is unsupported.

### T014: Implement prompt-driven recipe refinement

**File(s)**:
- `src/nmg_game_dev/recipes/refinement.py`
- `src/nmg_game_dev/materials/refinement.py`
- `tests/unit/recipes/test_refinement.py`
- `tests/blender/test_recipe_refinement.py`
**Type**: Create
**Depends**: T006, T009, T011, T012, T013
**Owner Issue(s)**: #60
**Acceptance**:
- [ ] Supported refinement prompts map to deterministic recipe/material parameter changes.
- [ ] Unsupported refinement requests fail with structured remediation.
- [ ] Sidecars record original prompt, refinement prompt, changed parameters, review bundle, and accepted/rejected state.
- [ ] Tests prove refinement never leaves the Blender MCP recipe workflow.

---

## Phase 4: Integration - review gates, UE import, provider guards

### T015: Implement review artifacts and quality gate expansion

**File(s)**:
- `src/nmg_game_dev/review/__init__.py`
- `src/nmg_game_dev/review/artifacts.py`
- `src/nmg_game_dev/pipeline/stages/quality.py`
- `plugins/nmg-game-dev-blender-addon/operators/review_artifacts.py`
- `tests/blender/test_review_artifacts.py`
- `tests/unit/review/test_artifacts.py`
**Type**: Create / Modify
**Depends**: T002, T007, T009
**Owner Issue(s)**: #30
**Acceptance**:
- [ ] Five-angle renders, turntable renders, material-ball renders, object/material/poly statistics, and budget reports are written for generated assets.
- [ ] Empty geometry, invalid scale, missing PBR channels, over-budget Mobile variants, and unsupported families stop before UE import.
- [ ] Failure sidecars include paths and remediation suitable for rerun or backlog creation.

### T016: Wire recipe outputs to UE import without changing the VibeUE boundary

**File(s)**:
- `src/nmg_game_dev/pipeline/stages/import_ue.py`
- `plugins/nmg-game-dev-ue-plugin/Source/NmgGameDevRuntime/Public/NmgAssetResolver.h`
- `plugins/nmg-game-dev-ue-plugin/Source/NmgGameDevRuntime/Private/NmgAssetResolver.cpp`
- `tests/unit/pipeline/stages/test_import_ue.py`
- `plugins/nmg-game-dev-ue-plugin/Source/NmgGameDevRuntime/Tests/NmgAssetResolver.spec.cpp`
**Type**: Modify
**Depends**: T007, T015
**Owner Issue(s)**: #30, #33
**Acceptance**:
- [ ] UE import consumes Desktop/Mobile paths from the recipe manifest after quality passes.
- [ ] The VibeUE bridge remains the only UE MCP wire; nmg-game-dev does not add an HTTP MCP module.
- [ ] Runtime `UNmgAssetResolver` assumptions still match split-variant outputs.
- [ ] Tests prove import is skipped when review/quality fails.

### T017: Add provider/model backend guardrails

**File(s)**:
- `src/nmg_game_dev/pipeline/__init__.py`
- `src/nmg_game_dev/pipeline/stages/generate.py`
- `tests/unit/pipeline/test_provider_guards.py`
- `tests/bdd/features/blender_mcp_recipe_umbrella.feature`
**Type**: Modify / Create
**Depends**: T004, T005
**Owner Issue(s)**: #35
**Acceptance**:
- [ ] Recipe-backed consumer skills cannot route to Meshy, Hyper3D, Hunyuan3D, FLUX, ComfyUI, Diffusers, Substance, Mixamo, CUDA-only paths, hosted APIs, or paid/quota-limited providers.
- [ ] Legacy Meshy-supplement tests are removed, renamed as benchmark-only, or explicitly isolated from v1 happy-path coverage.
- [ ] Tests inspect sidecar provenance and MCP fake call counts to prove no provider invocation.

### T018: Add consumer-skill error surfacing hooks

**File(s)**:
- `skills/new-prop/SKILL.md`
- `skills/new-character/SKILL.md`
- `skills/generate-texture/SKILL.md`
- `skills/spec-to-assets/SKILL.md`
- `docs/skills/asset-generation.md`
**Type**: Create / Modify
**Depends**: T004, T015, T017
**Owner Issue(s)**: Child skill issues when opened
**Acceptance**:
- [ ] Missing Blender MCP, unsupported families, rejected assets, and over-budget variants produce concise actionable remediation.
- [ ] Skills expose review artifact paths rather than raw logs.
- [ ] Skills do not ask for provider credentials for the v1 happy path.

---

## Phase 5: Testing - BDD, unit, Blender-headless, visual proof

### T019: Create umbrella BDD feature file

**File(s)**: `specs/feature-umbrella-deliver-blender-mcp-only-recipe-asset-generation/feature.gherkin`
**Type**: Create
**Depends**: T001
**Owner Issue(s)**: #27
**Acceptance**:
- [ ] Every acceptance criterion from `requirements.md` maps to one Gherkin scenario.
- [ ] Scenarios cover provider guardrails, child traceability, orchestration provenance, recipe output, material packaging, variants, review gates, catalog coverage, and prompt refinement.
- [ ] Feature file uses Given/When/Then and is valid Gherkin syntax.

### T020: Implement automated BDD and unit coverage per child issue

**File(s)**:
- `tests/bdd/features/blender_mcp_recipe_umbrella.feature`
- `tests/bdd/steps/test_blender_mcp_recipe_umbrella.py`
- `tests/unit/**`
**Type**: Create / Modify
**Depends**: T002, T003, T004, T005, T006, T007, T015, T017
**Owner Issue(s)**: #31, #35, #29, #33, #30, #60
**Acceptance**:
- [ ] BDD coverage proves every umbrella AC as child work lands.
- [ ] Unit tests cover request validation, job lifecycle, recipe registry, provider guards, manifest schema, sidecar serialization, and quality gate failure modes.
- [ ] Test fixtures use fake MCP clients for fast guardrail coverage and Blender-headless runs for artifact claims.

### T021: Add Blender-headless proof and visual-inspection evidence per recipe family

**File(s)**:
- `tests/blender/test_recipe_fixtures.py`
- `tests/recipes/fixtures/**`
- `docs/review/**`
**Type**: Create / Modify
**Depends**: T009, T011, T012, T013
**Owner Issue(s)**: #37 through #59
**Acceptance**:
- [ ] Every recipe family has a fixture spec, generated GLB, review bundle, sidecar provenance, and repeatability evidence.
- [ ] Visual-inspection children include reviewer evidence and are not marked automatable unless inspection is genuinely automated.
- [ ] Generated proof artifacts include enough metadata for cache reuse and follow-up tuning.

### T022: Verify umbrella closeout across children

**File(s)**:
- `specs/feature-umbrella-deliver-blender-mcp-only-recipe-asset-generation/tasks.md`
- `specs/feature-umbrella-deliver-blender-mcp-only-recipe-asset-generation/feature.gherkin`
- `verification-report.md` (created during `$nmg-sdlc:verify-code` on the final child/umbrella closeout)
**Type**: Coordinate
**Depends**: T020, T021
**Owner Issue(s)**: #27 and final unblocked child issue
**Acceptance**:
- [ ] All child PRs link to #27, this spec, and ADR #5.
- [ ] No v1 happy-path test or sidecar proves provider/model fallback use.
- [ ] Catalog fixture coverage matches the child issue list in #27.
- [ ] Final verification report states which children closed the umbrella and any remaining unsupported families.

---

## Dependency Graph

```
T001
  |
  +--> T002 --> T003 --> T004 --> T005
                         |         |
                         |         +--> T006 --> T007 --> T015 --> T016
                         |         |                    |
                         |         |                    +--> T018
                         |         |
                         |         +--> T008
                         |         |
                         |         +--> T009 --> T011 --> T021
                         |                    +--> T012 --> T021
                         |                    +--> T013 --> T021
                         |                    +--> T014
                         |
                         +--> T017

T019 --> T020 --> T022
T021 -----------^
```

---

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #27 | 2026-05-11 | Initial feature spec |

---

## Validation Checklist

Before moving to IMPLEMENT phase:

- [x] Each task has single responsibility.
- [x] Dependencies are mapped across child issues.
- [x] Tasks can be completed independently once their dependencies land.
- [x] Acceptance criteria are verifiable.
- [x] File paths reference actual project structure from `steering/structure.md`.
- [x] Test tasks are included for BDD, unit, Blender-headless, and visual proof.
- [x] No circular dependencies.
- [x] Tasks are in logical execution order.
- [x] Umbrella seal behavior is explicit: #27 seals specs, child branches implement code.
