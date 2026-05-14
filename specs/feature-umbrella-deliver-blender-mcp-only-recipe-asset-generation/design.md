# Design: Umbrella - deliver Blender MCP-only recipe asset generation

**Issues**: #27
**Date**: 2026-05-11
**Status**: Draft
**Author**: Rich Nunley

---

## Overview

Issue #27 is an umbrella architecture and rollout contract for replacing the v1
asset-creation happy path with Blender MCP-only recipe generation. The accepted
ADR from issue #5 (`docs/decisions/2026-05-02-blender-as-meshy-gap-analysis.md`)
is the technical source of truth: model/provider-backed systems remain useful
benchmark evidence, but the shipping v1 path is local Blender controlled through
the pinned `ahujasid/blender-mcp` host.

The implementation is intentionally split across child issues. This spec does
not ask one PR to build orchestration, recipe compilation, material packaging,
rigging, cleanup, review gates, and every recipe family. Instead, it defines the
shared architecture every child must preserve: typed asset requests flow through
a recipe job layer, recipe builders emit deterministic Blender Python, Blender
produces GLB and review artifacts, quality gates stop bad assets before UE
import, and sidecars preserve enough provenance for cache reuse, reruns, and
human visual review.

The key design shift is to turn the current `pipeline.run(prompt, source=...)`
shape into a recipe-first pipeline. `source="meshy"` and provider-backed
fallbacks leave the v1 happy path. Unsupported families fail honestly with
structured remediation or become recipe-authoring backlog, not silent reroutes
to Meshy, Hyper3D, Hunyuan3D, FLUX, ComfyUI, or another model/provider backend.

---

## Architecture

### Component Diagram

```
Consumer skill (`$new-prop`, `$new-character`, future recipe skills)
        |
        v
Typed asset request
  - asset_family, category, name, tier, description, seed
  - style/material presets, target budgets, optional refinement prompt
        |
        v
src/nmg_game_dev/pipeline/
  run_recipe(request, *, cache_dir, mcp_clients)
        |
        +--> job orchestration (#31)
        |     submit / poll / cancel / resume / listener restart recovery
        |     cache key + artifact manifest + job status sidecar
        |
        +--> recipe engine (#35)
        |     typed spec -> family builder -> Blender Python script
        |     recipe provenance + deterministic seed + unsupported-family error
        |
        +--> material and PBR packaging (#29)
        |     Blender procedural material presets, UV unwrap, bake-down, GLB export
        |
        +--> cleanup, LOD, and variants (#33)
        |     Desktop output + Mobile output as separate physical artifacts
        |
        +--> rigging / animation import (#32)
        |     constrained humanoid Rigify/library path; unsupported non-biped failures
        |
        +--> review and quality gates (#30)
              five-angle renders, turntable, material ball, stats, budget reports
        |
        v
VibeUE import stage
  Content/<Category>/<Name>/Desktop/
  Content/<Category>/<Name>/Mobile/
```

### Existing System Fit

The current repo already provides the correct landing zones:

| Existing surface | Current state | Umbrella direction |
|------------------|---------------|--------------------|
| `src/nmg_game_dev/pipeline/__init__.py` | Fixed stage chain with `source="blender"` / `source="meshy"` and test-stage overrides. | Keep the stage runner and cache discipline, but add a recipe-first entrypoint and remove Meshy/provider source routing from the v1 happy path. |
| `src/nmg_game_dev/pipeline/stages/generate.py` | `generate_blender()` emits a placeholder `generate_mesh(...)` script; `generate_meshy()` calls Meshy. | Replace Blender generation with recipe-job submission and recipe engine execution. Move Meshy out of the happy path and into historical/benchmark-only code, if retained at all. |
| `src/nmg_game_dev/pipeline/stages/texture.py` | Raises `texture.not_implemented`. | Issue #29 replaces this with Blender procedural material/PBR packaging. |
| `src/nmg_game_dev/pipeline/stages/cleanup.py` | Calls placeholder `cleanup_mesh(...)` through Blender MCP. | Issue #33 backs it with real Blender operators for cleanup, remesh, LOD seed, and variant preparation. |
| `src/nmg_game_dev/pipeline/stages/variants.py` | Computes Desktop/Mobile paths and calls placeholder `produce_variants(...)`. | Issue #33 makes Desktop and Mobile physical outputs real, budgeted, and sidecar-described. |
| `src/nmg_game_dev/pipeline/stages/quality.py` | Validates manifest fields and mobile budget sidecar values. | Issue #30 expands quality into visual review bundles, object/material statistics, invalid-scale checks, empty-geometry checks, and fix prompts. |
| `plugins/nmg-game-dev-blender-addon/` | Registers stubs and uses `ahujasid/blender-mcp` via `execute_blender_code`. | Child issues add real `nmggamedev.*` operators; the add-on still binds no port and remains invoked through the existing host. |
| `plugins/nmg-game-dev-ue-plugin/` | Runtime and editor skeletons exist; VibeUE owns the MCP wire. | Import remains through VibeUE. Recipe generation does not create a new UE MCP bridge. |

### Data Flow

```
1. Skill parses the user's asset request into a typed RecipeRequest.
2. The pipeline computes a recipe cache key from:
   - normalized request fields,
   - recipe id/version,
   - material preset id/version,
   - target budget values,
   - Blender and Blender MCP versions.
3. Job orchestration submits a Blender MCP recipe job or resumes an existing one.
4. Recipe engine selects the family builder and emits constrained Blender Python.
5. Blender runs the script through the pinned MCP host and writes raw Blender output.
6. Material packaging assigns procedural materials, unwraps, bakes, and exports GLB.
7. Cleanup and variant operators produce separate Desktop and Mobile artifacts.
8. Review gates write renders, turntable/material evidence, stats, and budget reports.
9. Quality success permits VibeUE import; quality failure stops before UE import.
10. Sidecars record job status, recipe/material provenance, output paths, review paths,
    budget data, accepted/rejected state, and rerun hints.
```

### Failure Flow

```
Unsupported family -> unsupported_recipe_family
  - no provider fallback
  - remediation names the missing family and backlog child issue target

Blender MCP unavailable -> mcp.blender.unreachable
  - no Meshy fallback
  - remediation points to scripts/start-blender-mcp.sh and /tmp/blender-mcp.log

Quality/review failure -> quality.<condition> or review.<condition>
  - UE import skipped
  - sidecar links review artifacts and fix/backlog prompt

Listener restart during job -> job.listener_restarted
  - orchestration reattaches when possible
  - otherwise marks job resumable/failed with artifact manifest state intact
```

---

## API / Interface Changes

### New Typed Request

Add a recipe-oriented request model in `src/nmg_game_dev/pipeline/prompt.py` or a
new `src/nmg_game_dev/recipes/request.py` module:

```python
class RecipeRequest(BaseModel):
    model_config = {"frozen": True}

    asset_family: str
    category: str
    name: str
    tier: Literal["standard", "hero"]
    description: str
    seed: int | None = None
    style_preset: str | None = None
    material_preset: str | None = None
    target_budgets: dict[str, int] | None = None
    refinement_prompt: str | None = None
```

`Prompt` can remain as a compatibility wrapper during migration, but child issues
must route new asset-generation work through `RecipeRequest` because `category`
and `description` alone are not enough to select deterministic family builders.

### New Pipeline Entrypoint

Add a recipe-first entrypoint rather than expanding `source`:

```python
def run_recipe(
    request: RecipeRequest,
    *,
    cache_dir: Path | None = None,
    mcp_clients: McpClients | None = None,
    stage_overrides: dict[StageName, Stage] | None = None,
) -> PipelineResult:
    """Run Blender MCP-only recipe generation through review and UE import."""
```

`pipeline.run(..., source="blender")` may delegate to `run_recipe()` after
callers migrate. `source="meshy"` must not be used by the v1 happy path. If it
remains temporarily for historical tests, tests must prove recipe-backed skills
do not call it.

### Job Orchestration Interfaces (#31)

| Symbol | Location | Purpose |
|--------|----------|---------|
| `RecipeJob` | `src/nmg_game_dev/pipeline/jobs.py` | Immutable job id, request hash, recipe id/version, status, progress, cancellation state, created/updated timestamps. |
| `JobStore` | `src/nmg_game_dev/pipeline/jobs.py` | Sidecar-backed submit/poll/cancel/resume state under the artifact cache or consumer project cache. |
| `RecipeArtifactManifest` | `src/nmg_game_dev/pipeline/artifacts.py` | Canonical manifest for GLB, review renders, stats, sidecars, and Desktop/Mobile outputs. |
| `submit_recipe_job()` | `src/nmg_game_dev/pipeline/jobs.py` | Starts or resumes a Blender MCP job with idempotent cache keys. |

### Recipe Engine Interfaces (#35 and recipe children)

| Symbol | Location | Purpose |
|--------|----------|---------|
| `RecipeFamily` | `src/nmg_game_dev/recipes/base.py` | Protocol implemented by every family builder. |
| `RecipeContext` | `src/nmg_game_dev/recipes/base.py` | Request, seed, dimensions, style/material presets, output root, and budget context. |
| `RecipeScript` | `src/nmg_game_dev/recipes/base.py` | Generated Blender Python plus provenance metadata. |
| `RecipeRegistry` | `src/nmg_game_dev/recipes/registry.py` | Maps `asset_family` to the active builder; returns `unsupported_recipe_family` when missing. |
| Family modules | `src/nmg_game_dev/recipes/families/*.py` | Potion/bottle, weapons, containers, roads, signs, vehicles, characters, etc. |

Every family module must expose deterministic fixture specs and generated proof
bundles before its child issue can be verified.

### Blender Add-on Operators

Child issues add real operators under `plugins/nmg-game-dev-blender-addon/` while
preserving the no-second-MCP-host decision:

| Operator family | Owner | Expected location |
|-----------------|-------|-------------------|
| Recipe execution helpers | #35 and recipe children | `plugins/nmg-game-dev-blender-addon/operators/recipe_*.py` |
| PBR/material packaging | #29 | `plugins/nmg-game-dev-blender-addon/operators/materials_*.py` |
| Cleanup/remesh/LOD/variants | #33 | Existing cleanup/optimize/generate-variants operators, expanded from stubs. |
| Rigging/animation import | #32 | `plugins/nmg-game-dev-blender-addon/operators/rigging_*.py` |
| Review renders/statistics | #30 | `plugins/nmg-game-dev-blender-addon/operators/review_*.py` |

Pipeline code invokes these through `ctx.mcp_clients.blender.run_script(...)`
using the pinned `ahujasid/blender-mcp` host's Python execution surface.

---

## Database / Storage Changes

No database is introduced.

The artifact cache and sidecar surface expand:

| Path / object | Change |
|---------------|--------|
| `${NMG_GAME_DEV_CACHE_DIR:-~/.cache/nmg-game-dev}/by-key/` | Continue to store content-addressed stage artifacts. |
| `sidecar.json` | Add job, recipe, material, Blender/MCP version, review paths, budget, and accepted/rejected fields. |
| `review/` subdirectory under each artifact entry | Store five-angle renders, turntables, material-ball renders, screenshots, and stats JSON. |
| `proof/` fixtures for recipe families | Store deterministic fixture specs and generated proof metadata used by BDD/headless tests. |

Sidecars must remain JSON-serializable. They are audit artifacts, not hidden
runtime state; downstream skills and verification should be able to inspect them
without rerunning Blender.

---

## State Management

Job state is file-backed and resumable, not in-memory-only:

```
Queued -> Running -> Completed
                 -> Cancelled
                 -> Failed(resumable=true|false)
                 -> ReviewRejected
```

State transitions are owned by the job orchestration child issue. Later child
issues append evidence to the job manifest rather than inventing parallel state
files. A completed job must be replayable from sidecar data: request, recipe
version, material version, seed, generated files, Blender version, MCP version,
review bundle, and final Desktop/Mobile paths.

---

## UI Components

No broad UI is introduced by this umbrella.

Expected user-facing surfaces are narrow:

| Surface | Owner | Design requirement |
|---------|-------|--------------------|
| Consumer asset skills | Child skill issues | Report actionable errors for missing Blender MCP, unsupported families, rejected assets, and over-budget variants. |
| Blender add-on panel/operators | #29, #30, #32, #33, #35, recipe children | Keep operators callable through `bpy.ops.nmggamedev.*`; panel additions are secondary to scriptability. |
| Review/inspection output | #30 | Expose artifact paths and review bundles in a way an `inspect-artifact` skill can open without parsing raw logs. |

---

## Multi-PR Rollout

This umbrella must be sealed before implementation children proceed. Child
issues already exist; do not create duplicate children when sealing this spec.

| Phase | Issue(s) | Purpose | Unblocked by |
|-------|----------|---------|--------------|
| Orchestration foundation | #31 | Recipe job lifecycle, cache keys, sidecars, artifact manifests, progress, cancellation, listener restart handling. | Umbrella spec seal. |
| Recipe engine foundation | #35 | Typed recipe request, registry, deterministic script emission, unsupported-family errors, GLB export contract. | #31. |
| Material/PBR packaging | #29 | Blender-owned materials, UV unwrap, bake-down, GLB PBR channel validation, removal of `texture.not_implemented`. | #35 where script output shape is needed. |
| Cleanup and variants | #33 | Real cleanup/remesh/LOD/bake-down and physical Desktop/Mobile outputs. | #31 and #35. |
| Review gates | #30 | Renders, turntables, object/material/poly stats, budget reports, reject/fix prompts, fail-before-import. | #31, #33; can build in parallel with recipe families once manifests stabilize. |
| Rigging/animation import | #32 | Constrained humanoid Rigify/library workflow and explicit unsupported non-biped/custom-motion failures. | #35 and material/variant conventions. |
| Recipe catalog | #37-#59 | One visual-inspection child per recipe family: potions, weapons, tools, containers, pickups, doors, building pieces, roads, street infrastructure, environment kits, terrain, foliage, furniture, armor/accessories, characters, creatures, vehicles, VFX markers. | #35 plus relevant material/review surfaces. |
| Prompt refinement | #60 | Map supported prompt refinements to deterministic recipe/material parameter changes with accepted/rejected review state. | #35, #29, #30. |

Delivery rule: each child PR references issue #27, this spec directory, and the
ADR from issue #5. A child may ship a narrow vertical slice only when its BDD,
unit, and Blender-headless evidence proves it preserves the Blender MCP-only
contract.

---

## Alternatives Considered

| Option | Description | Pros | Cons | Decision |
|--------|-------------|------|------|----------|
| Keep Meshy as fallback | Continue the current `source="meshy"` supplement as a fallback when Blender recipes cannot satisfy a request. | Useful benchmark and familiar pipeline path. | Violates issue #27 and ADR #5; requires paid/quota-limited credentials; hides missing recipe work. | Rejected for v1 happy path. |
| Local specialized model stack | Productize Hunyuan3D, FLUX, TripoSR/InstantMesh, Diffusers, ComfyUI, or similar local models. | Some spike evidence produced plausible assets. | Heavy hardware/runtime complexity, CUDA gaps, licensing/provider uncertainty, and weaker controllability than recipe output. | Rejected for v1 happy path. |
| One broad implementation PR | Build every recipe engine, operator, material, rigging, review, and family in one branch. | Avoids temporary interfaces. | Too large to review, hard to test visually, high merge risk. | Rejected; umbrella plus child PRs selected. |
| Blender MCP recipe jobs | Typed request -> deterministic recipe builder -> Blender MCP execution -> review/quality -> UE import. | Local, cacheable, reviewable, provider-independent, matches the potion v2 proof and steering. | Requires deliberate recipe-family authoring; not arbitrary prompt-to-3D. | Selected. |

---

## Security Considerations

- [x] **Authentication**: Blender MCP-only happy path does not require API keys.
- [x] **Authorization**: No new permission model; local Blender/VibeUE processes remain under the developer's user account.
- [x] **Input Validation**: `RecipeRequest` validates family/category/name/tier/description/presets before any MCP call.
- [x] **Data Sanitization**: Blender Python emitted by recipe builders is generated from constrained typed specs, not raw prompt concatenation.
- [x] **Sensitive Data**: Sidecars must never record provider credentials, signing credentials, or API keys.
- [x] **Supply Chain**: No new hosted provider or local model package becomes a v1 dependency through this umbrella.

---

## Performance Considerations

- [x] **Caching**: Cache keys include request, recipe/material versions, seed, budgets, Blender version, and MCP version.
- [x] **Resume**: Job sidecars allow reruns after listener restarts and partial failures without redoing completed stages.
- [x] **Authoring budgets**: Standard prop targets remain <= 90 seconds once implemented and warm-cached; hero character work keeps the <= 5 minute target.
- [x] **Render/review overhead**: Review artifacts are mandatory, but child issues should make review generation skippable only in test fixtures, never in the real happy path.
- [x] **Mobile budgets**: Mobile poly/texture checks run before UE import and before build/ship workflows.

---

## Testing Strategy

| Layer | Type | Coverage |
|-------|------|----------|
| Request and registry | Unit | `RecipeRequest` validation, family lookup, unsupported-family errors, deterministic seed handling. |
| Job orchestration | Unit + integration | Submit/poll/cancel/resume, cache keys, sidecar manifest schema, listener restart recovery. |
| Recipe engine | Unit + Blender-headless | Script generation, recipe provenance, deterministic fixture output keys, GLB export. |
| Materials/PBR | Blender-headless | UV unwrap, material slot assignment, bake-down, PBR channel presence, GLB export metadata. |
| Cleanup/variants | Blender-headless + unit | Desktop/Mobile physical outputs, poly/texture stats, no cross-variant references. |
| Review gates | Unit + Blender-headless | Empty geometry, invalid scale, missing PBR, over-budget Mobile, review bundle paths, fail-before-import. |
| Recipe catalog | BDD + visual evidence | One fixture spec and generated proof bundle per family child issue. |
| Pipeline | pytest-bdd | Every acceptance criterion in `feature.gherkin`, including no provider/model backend invocation. |

BDD tests should prefer scripted fakes for non-visual unit coverage and
Blender-headless fixture runs for any claim about generated artifacts. Recipe
family children that require subjective visual inspection should not be labelled
automatable unless their inspection gate is explicitly manual.

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Recipe output quality varies by family. | High | High | One child per family, mandatory Blender visual proof, unsupported-family failures until evidence exists. |
| Current Meshy supplement tests conflict with Blender MCP-only v1. | Medium | Medium | Keep benchmark tests separate or mark legacy; add tests proving consumer skills do not invoke provider paths. |
| Sidecar schema drifts across children. | Medium | High | #31 owns the manifest schema first; later children append through that schema. |
| Prompt refinement becomes arbitrary prompt-to-code. | Medium | High | #60 maps prompts only to supported recipe/material parameters and records rejected unsupported requests. |
| Review artifacts slow iteration. | Medium | Medium | Cache by recipe/material version and seed; keep review mandatory for real runs but allow deterministic fixture substitutes in unit tests. |
| Humanoid scope expands beyond proven Rigify/library path. | Medium | Medium | #32 explicitly fails non-biped, quadruped, and text-driven custom motion requests unless future specs prove them. |

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

Before moving to TASKS phase:

- [x] Architecture follows existing project patterns from `steering/structure.md`.
- [x] API/interface changes document typed requests, pipeline entrypoints, job orchestration, recipe engine, and Blender operators.
- [x] Database/storage changes are scoped to artifact cache and sidecars; no database added.
- [x] State management is clear and sidecar-backed.
- [x] UI components are intentionally narrow and scriptability-first.
- [x] Security considerations address provider credentials and generated Blender Python.
- [x] Performance impact is analyzed through caching, resume, review, and budget gates.
- [x] Testing strategy covers BDD, unit, Blender-headless, and visual proof requirements.
- [x] Alternatives were considered and documented.
- [x] Risks are identified with mitigations.
