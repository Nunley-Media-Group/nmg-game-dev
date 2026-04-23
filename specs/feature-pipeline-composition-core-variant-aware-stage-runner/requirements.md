# Requirements: Pipeline composition core — variant-aware stage runner

**Issues**: #4
**Date**: 2026-04-23
**Status**: Draft
**Author**: Rich Nunley

---

## User Story

**As an** internal NMG game developer (primary persona per `steering/product.md`)
**I want** a single Python entrypoint that composes Blender-first and Meshy-supplement pipeline stages into variant-aware, cacheable, idempotent runs
**So that** downstream skills (`new-prop`, `new-character`, etc.) can produce Desktop + Mobile assets without speaking MCP directly and without re-doing expensive upstream work on every iteration

---

## Background

`steering/structure.md` § Pipeline Flow describes the authoring pipeline as a fixed ordered chain: generate → texture → cleanup → variant → quality gate → import. `steering/product.md` makes three properties non-negotiable for this chain: **variants are first-class from the first generation step** (no retrofit pass), **every stage is idempotent/resumable/cacheable** (generation is expensive), and **quality is automatic** (the chain fails fast with a remediation prompt, never silently passes a bad asset through to UE import).

Issue #1 already shipped the top-level package `src/nmg_game_dev/` with empty `__init__.py` stubs for `pipeline/`, `variants/`, `quality/`, and `ship/`, plus the `.mcp.json` MCP pins that every stage will talk to. This feature fills three of those stubs — `pipeline/`, `variants/`, `quality/` — with the composition layer and its supporting types, cache, and errors. `ship/` is filled by a separate issue (#6). The texture stage lands as an abstract interface here; the concrete implementation is picked by the #5 spike and slots into the interface without changing any other stage. Every future skill that generates an asset (`new-prop`, `new-character`, etc.) will call into `pipeline.run(...)` rather than touching MCP tools directly (`steering/structure.md` § Anti-Patterns).

---

## Acceptance Criteria

**IMPORTANT: Each criterion becomes a Gherkin BDD test scenario.**

### AC1: Run a Blender-first pipeline end-to-end on a fixture

**Given** the Blender MCP is reachable (pinned via #1's `.mcp.json`, launched via #1's `start-blender-mcp.sh`)
**And** a fixture prompt `{ category: "Props", name: "TestCrate", tier: "standard", description: "wooden supply crate" }`
**When** `pipeline.run(prompt, source="blender")` is called
**Then** mesh, texture, cleanup, variant, and quality-gate stages execute in that order
**And** the resulting Desktop + Mobile variant file paths are returned

### AC2: Run a Meshy-supplement pipeline end-to-end on a fixture

**Given** the Meshy MCP is reachable (pinned via #1's `.mcp.json`)
**When** `pipeline.run(prompt, source="meshy")` is called
**Then** generation happens via Meshy, and cleanup + variant + quality-gate happen via Blender, and import happens via UE
**And** the result paths follow the same shape as the Blender-first run (identical Desktop/Mobile path convention per `steering/structure.md` § split-variant asset convention)

### AC3: Idempotent re-entry at a partial failure point

**Given** a pipeline run that previously failed at the variant stage
**When** the same prompt is re-run
**Then** upstream stages (generate, texture, cleanup) are served from the content-addressed cache
**And** the run resumes at the variant stage without re-invoking upstream MCPs

### AC4: Quality gate failure halts the run with remediation

**Given** a generated asset whose mobile variant exceeds its polycount or texture budget
**When** the quality-gate stage runs
**Then** the pipeline raises a `PipelineError` whose `.code`, `.message`, and `.remediation` fields describe the failing budget and the suggested next action
**And** the UE import stage is not invoked
**And** no partial asset is written to the consumer's UE `Content/` tree

### Generated Gherkin Preview

```gherkin
Feature: Pipeline composition core — variant-aware stage runner
  As an internal NMG game developer
  I want a single Python entrypoint that composes Blender-first and Meshy-supplement stages
  So that downstream skills produce Desktop + Mobile assets idempotently

  Scenario: Run a Blender-first pipeline end-to-end on a fixture
    Given the Blender MCP is reachable
    And a fixture prompt for category Props, name TestCrate, tier standard
    When pipeline.run is called with source "blender"
    Then mesh, texture, cleanup, variant, and quality-gate stages execute in order
    And Desktop + Mobile variant paths are returned

  Scenario: Run a Meshy-supplement pipeline end-to-end on a fixture
    Given the Meshy MCP is reachable
    When pipeline.run is called with source "meshy"
    Then generation happens via Meshy, cleanup and variants via Blender, import via UE
    And the result paths follow the same Desktop/Mobile convention

  Scenario: Idempotent re-entry at a partial failure point
    Given a pipeline run that failed at the variant stage
    When the same prompt is re-run
    Then upstream stages are served from cache
    And the run resumes at the variant stage

  Scenario: Quality gate failure halts the run with remediation
    Given a generated asset that exceeds its mobile budget
    When the quality-gate stage runs
    Then the pipeline raises PipelineError with .code, .message, .remediation
    And no UE import is attempted
```

---

## Functional Requirements

| ID | Requirement | Priority | Notes |
|----|-------------|----------|-------|
| FR1 | `src/nmg_game_dev/pipeline/__init__.py` exposes `run(prompt: Prompt, source: Literal["blender","meshy"]) -> PipelineResult` as the single public entrypoint; fills #1's empty stub without re-creating the directory or touching `src/nmg_game_dev/__init__.py`. | Must | |
| FR2 | `src/nmg_game_dev/pipeline/prompt.py` defines a typed `Prompt` model (pydantic or dataclass — design phase decides) with fields `category`, `name`, `tier`, `description`. Required on all public functions per `steering/tech.md` § Python. | Must | |
| FR3 | `src/nmg_game_dev/pipeline/stages/` contains one module per stage: `generate.py`, `texture.py` (abstract — concrete impl lands in #5), `cleanup.py`, `variants.py`, `quality.py`, `import_ue.py`. Each stage talks to exactly one MCP or one tool per `steering/structure.md` § Layer Responsibilities. | Must | |
| FR4 | `src/nmg_game_dev/pipeline/cache.py` provides a content-addressed artifact cache rooted at `${NMG_GAME_DEV_CACHE_DIR:-~/.cache/nmg-game-dev}`. Cache keys derive deterministically from `(stage, prompt hash, upstream artifact hash)`. | Must | |
| FR5 | `src/nmg_game_dev/variants/` fills #1's stub with Desktop/Mobile path helpers that return paths under `Content/<Category>/<Name>/{Desktop,Mobile}/` per `steering/structure.md` § split-variant asset convention. Never emit cross-variant references. | Must | |
| FR6 | `src/nmg_game_dev/quality/` fills #1's stub with budget-check and manifest-prep gate implementations. Gates are deterministic, pass/fail with remediation strings — no content rewriting per `steering/structure.md` § Layer Responsibilities. | Must | |
| FR7 | A `PipelineError` exception type exposes `.code`, `.message`, and `.remediation` fields, matching the MCP-server error contract in `steering/tech.md` § API / Interface Standards. Every stage failure surfaces as this type. | Must | |
| FR8 | `tests/unit/` covers each stage module with the MCP layer mocked (no real Blender/UE/Meshy required). Ships the BDD fixtures used by AC1–AC4. | Must | |
| FR9 | `tests/bdd/features/pipeline_*.feature` files cover AC1–AC4 with pytest-bdd step definitions under `tests/bdd/steps/` per `steering/tech.md` § BDD Testing. | Must | |
| FR10 | `tests/e2e/` contains an optional full-stack run against the fixture UE + Blender installs, gated behind `pytest --runslow`. Not required to pass on every commit. | Should | |

---

## Non-Functional Requirements

| Aspect | Requirement |
|--------|-------------|
| **Performance** | `pipeline.run(...)` overhead (excluding MCP call time) ≤ 200 ms end-to-end for a fully-cached re-run. Raw MCP time dominates cold runs and is bounded by the `steering/product.md` Success Metrics (≤ 90 s for a standard prop, ≤ 5 min for a hero character). |
| **Security** | No credentials or API keys handled by this package — stages receive pre-configured MCP clients from #1's `.mcp.json`. Error messages never echo env-var values. |
| **Reliability** | Every stage is idempotent: re-running with identical inputs produces identical outputs served from cache. A partial-failure re-entry serves completed upstream stages from cache and resumes at the first uncompleted stage. |
| **Platforms** | Python 3.11+ per `steering/tech.md`; runs on the host developer machine (macOS primary, Linux/Windows allowed). No dependency on Blender's bundled Python — this package lives under `src/`, not `plugins/nmg-game-dev-blender-addon/`. |
| **Type safety** | `mypy --strict` clean per `steering/tech.md`; `from __future__ import annotations` at every module top. |
| **Lint** | `ruff check` and `ruff format --check` clean (`gate-python-lint`). |

---

## Data Requirements

### Input Data

| Field | Type | Validation | Required |
|-------|------|------------|----------|
| `prompt.category` | `str` | Matches `^[A-Z][A-Za-z0-9]*$` (e.g., `Props`, `Weapons`, `Guards`) | Yes |
| `prompt.name` | `str` | Matches `^[A-Z][A-Za-z0-9]*$` (e.g., `TestCrate`, `Katana`) | Yes |
| `prompt.tier` | `Literal["standard","hero"]` | Enum value | Yes |
| `prompt.description` | `str` | Non-empty, trimmed ≤ 512 chars | Yes |
| `source` | `Literal["blender","meshy"]` | Enum value | Yes |

### Output Data

| Field | Type | Description |
|-------|------|-------------|
| `result.desktop_path` | `pathlib.Path` | Absolute path to the generated desktop variant in the consumer project's `Content/<Category>/<Name>/Desktop/` folder (after UE import). |
| `result.mobile_path` | `pathlib.Path` | Absolute path to the generated mobile variant in the consumer project's `Content/<Category>/<Name>/Mobile/` folder (after UE import). |
| `result.stages_executed` | `list[str]` | Stage names that actually ran this invocation (vs. served from cache). Enables observability + test assertions. |
| `result.cache_hits` | `list[str]` | Stage names that were served from cache. |

---

## Dependencies

### Internal Dependencies
- [ ] #1 — repo scaffolding, `nmg_game_dev` package, empty `pipeline/`, `variants/`, `quality/` stubs, `.mcp.json` MCP pins, `start-blender-mcp.sh` launcher. **Must be merged first.**

### External Dependencies
- [ ] Blender MCP (`blender-mcp@1.5.6`) reachable on `BLENDER_MCP_PORT` (default 9876).
- [ ] VibeUE MCP bridge (`mcp-remote@0.1.38` → `127.0.0.1:8088/mcp`) reachable when `source` invokes the import stage.
- [ ] Meshy MCP (`meshy-mcp-server@1.2.3`) + `MESHY_API_KEY` reachable when `source="meshy"`.

### Blocked By
- [ ] Issue #1 — repo scaffolding + stubs + MCP pins must land before this can be merged.

### Blocks
- Issue #5 — texture-gen spike will slot its implementation into this feature's abstract texture interface.
- Every future skill that composes stages (`new-prop`, `new-character`, `cleanup-asset-desktop`, `optimize-asset-for-mobile`, etc.).

---

## Out of Scope

Explicitly not included in this feature:

- **Concrete texture-generation implementation.** The texture stage is abstract here; the real tool is picked by the #5 spike and lands in a follow-up PR.
- **Ship/build/notarize orchestration.** `src/nmg_game_dev/ship/` is filled by #6, not here.
- **Consumer-facing skills** (`new-prop`, `new-character`, etc.). This feature ships the composition layer they will call into; the skills themselves are separate v1 issues.
- **Retargeting, animation import, level dressing.** Covered by dedicated skills/features in v1.
- **Cache eviction / GC.** Cache is append-only in v1; eviction is a post-v1 refinement unless disk pressure surfaces it during v1 consumer adoption.
- **Parallel stage execution.** Stages run sequentially per `steering/structure.md` Pipeline Flow; any future parallelization is a separate spec.
- **Consumer project's cook-manifest gates.** The `quality/` module prepares manifest inputs; the actual `gate-cook-manifest-*` checks run during `/ship`, not here.

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Cached re-run overhead | ≤ 200 ms (excluding MCP time) | `pytest --benchmark` on the cached-resume AC3 scenario |
| Unit test coverage per stage module | ≥ 80% line coverage | `pytest --cov=src/nmg_game_dev/pipeline` |
| BDD coverage of acceptance criteria | 4/4 ACs have at least one Gherkin scenario | `tests/bdd/features/pipeline_*.feature` review |
| `mypy --strict` | 0 errors | CI |

---

## Open Questions

- [ ] **Prompt model — pydantic vs. dataclass?** Design phase decision. Pydantic buys validation at the boundary but adds a dependency; dataclass keeps the package dep-light but pushes validation into `__post_init__`. Trade-off decided in design.md.
- [ ] **Cache key scope — per-machine vs. per-project?** Defaulting to per-user (`~/.cache/nmg-game-dev`) matches `NMG_GAME_DEV_CACHE_DIR` default in `steering/tech.md`, but consumer projects may want project-local caches for reproducibility. Design phase decides whether to expose a per-project override path.
- [ ] **Stage module signatures — free functions vs. Protocol classes?** Affects how #5's concrete texture impl slots in. Design phase picks the interface shape.

---

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #4 | 2026-04-23 | Initial feature spec |

---

## Validation Checklist

Before moving to PLAN phase:

- [x] User story follows "As a / I want / So that" format
- [x] All acceptance criteria use Given/When/Then format
- [x] No implementation details in requirements (stage ordering is a product contract, not an implementation detail)
- [x] All criteria are testable and unambiguous
- [x] Success metrics are measurable
- [x] Edge cases and error states are specified (AC3 partial re-entry, AC4 quality-gate halt)
- [x] Dependencies are identified
- [x] Out of scope is defined
- [x] Open questions are documented (or resolved)
