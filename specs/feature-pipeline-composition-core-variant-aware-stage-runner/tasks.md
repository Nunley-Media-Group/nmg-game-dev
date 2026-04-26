# Tasks: Pipeline composition core — variant-aware stage runner

**Issues**: #4
**Date**: 2026-04-23
**Status**: Planning
**Author**: Rich Nunley

---

## Summary

This feature is a pure-Python composition layer — no frontend code. The standard 5-phase template is collapsed to four phases matching the design's deliverable groups.

| Phase | Tasks | Status |
|-------|-------|--------|
| Setup — types, Protocol, cache, error contract, DI | 6 | [ ] |
| Backend — six stage modules | 6 | [ ] |
| Integration — variants/, quality/, pipeline.run() orchestrator | 3 | [ ] |
| Testing — unit + BDD + e2e scaffold | 5 | [ ] |
| **Total** | **20** | |

---

## Task Format

```
### T[NNN]: [Task Title]

**File(s)**: path/to/file
**Type**: Create | Modify | Delete
**Depends**: T[NNN], T[NNN] (or None)
**Acceptance**:
- [ ] verifiable criterion
```

File paths map to the canonical layout in `steering/structure.md` § Project Layout.

---

## Phase 1: Setup — types, Protocol, cache, error contract, DI

### T001: Add pydantic dependency

**File(s)**: `pyproject.toml`
**Type**: Modify
**Depends**: None
**Acceptance**:
- [ ] `project.dependencies` includes `pydantic>=2,<3`
- [ ] `pip install -e .` resolves without conflicts
- [ ] `ruff check` and `ruff format --check` pass

### T002: Implement `Prompt` model

**File(s)**: `src/nmg_game_dev/pipeline/prompt.py`
**Type**: Create
**Depends**: T001
**Acceptance**:
- [ ] `class Prompt(BaseModel)` with `model_config = {"frozen": True}`
- [ ] Fields: `category` (regex `^[A-Z][A-Za-z0-9]*$`), `name` (same regex), `tier` (`Literal["standard","hero"]`), `description` (`min_length=1, max_length=512`, trimmed)
- [ ] `stable_hash() -> str` returns SHA-256 over `model_dump_json(sort_keys=True)`
- [ ] `from __future__ import annotations` at top
- [ ] Passes `mypy --strict`

### T003: Implement `PipelineResult` model

**File(s)**: `src/nmg_game_dev/pipeline/result.py`
**Type**: Create
**Depends**: T001
**Acceptance**:
- [ ] `class PipelineResult(BaseModel)` with fields `desktop_path: Path`, `mobile_path: Path`, `stages_executed: list[str]`, `cache_hits: list[str]`
- [ ] Passes `mypy --strict`

### T004: Implement `PipelineError`

**File(s)**: `src/nmg_game_dev/pipeline/errors.py`
**Type**: Create
**Depends**: None
**Acceptance**:
- [ ] `class PipelineError(Exception)` with `__init__(code, message, remediation, stage)`
- [ ] All four fields are public attributes and typed `str`
- [ ] Matches the MCP-server error contract in `steering/tech.md` § API / Interface Standards
- [ ] Passes `mypy --strict`

### T005: Implement `Stage` Protocol + `StageContext` + `StageArtifact`

**File(s)**: `src/nmg_game_dev/pipeline/stages/__init__.py`, `src/nmg_game_dev/pipeline/stages/_base.py`
**Type**: Create
**Depends**: T002, T004
**Acceptance**:
- [ ] `_base.py` defines `@dataclass(frozen=True) class StageContext` with fields `prompt: Prompt`, `upstream_artifact: StageArtifact | None`, `cache_dir: Path`, `mcp_clients: McpClients`
- [ ] `@dataclass(frozen=True) class StageArtifact` with `stage: str`, `blob_path: Path`, `sidecar: dict[str, object] | None`, method `content_hash() -> str` (SHA-256 over blob bytes + canonical sidecar JSON)
- [ ] `class Stage(Protocol): __call__(ctx: StageContext) -> StageArtifact`
- [ ] `class McpClients` is a frozen dataclass holding `blender: BlenderMcp`, `unreal: UnrealMcp`, `meshy: MeshyMcp | None` (Meshy optional because Blender-first runs don't need it)
- [ ] `stages/__init__.py` re-exports `Stage`, `StageContext`, `StageArtifact`
- [ ] Passes `mypy --strict`

### T006: Implement `ArtifactCache`

**File(s)**: `src/nmg_game_dev/pipeline/cache.py`
**Type**: Create
**Depends**: T005
**Acceptance**:
- [ ] `class ArtifactCache(root: Path)` resolves `root` to `${NMG_GAME_DEV_CACHE_DIR:-~/.cache/nmg-game-dev}` when called with no arg
- [ ] `key(stage, prompt_hash, upstream_hash) -> str` returns hex SHA-256 over the tuple
- [ ] `get(key) -> StageArtifact | None` — returns `None` on miss, loads blob path + sidecar JSON on hit
- [ ] `put(key, artifact)` — atomic write-then-rename into `{root}/by-key/{first-2-hex}/{full-sha}/`
- [ ] Corrupted-entry detection: if `sidecar.json` fails to parse, log warning and treat as miss
- [ ] Passes `mypy --strict`

---

## Phase 2: Backend — six stage modules

### T007: Implement `generate` stage (Blender + Meshy branches)

**File(s)**: `src/nmg_game_dev/pipeline/stages/generate.py`
**Type**: Create
**Depends**: T005
**Acceptance**:
- [ ] Module-level functions `generate_blender(ctx) -> StageArtifact` and `generate_meshy(ctx) -> StageArtifact`, both satisfying the `Stage` Protocol
- [ ] `generate_blender` calls `ctx.mcp_clients.blender` to produce an initial mesh blob; no other MCP touched
- [ ] `generate_meshy` calls `ctx.mcp_clients.meshy`; raises `PipelineError("mcp.meshy.unreachable", …)` if `ctx.mcp_clients.meshy` is `None`
- [ ] Connection / timeout errors from the MCP client are translated into `PipelineError("mcp.{server}.{condition}", …)` with a `remediation` pointing at `scripts/start-blender-mcp.sh` or the Meshy env-var guidance
- [ ] Unit-testable with a fake `McpClients`

### T008: Implement `texture` stage (abstract interface for #5)

**File(s)**: `src/nmg_game_dev/pipeline/stages/texture.py`
**Type**: Create
**Depends**: T005
**Acceptance**:
- [ ] `def texture(ctx: StageContext) -> StageArtifact` defined but raises `PipelineError("texture.not_implemented", message="texture stage awaits the #5 spike pick", remediation="Track #5; this stage is a placeholder in #4.", stage="texture")`
- [ ] Module docstring links to issue #5 and `requirements.md` FR3
- [ ] Passes `mypy --strict`
- [ ] **Note**: BDD scenarios for AC1/AC2 use a test-fixture texture stage substituted via the DI seam (see T018). AC1/AC2 do NOT depend on the real texture stage landing in #4.

### T009: Implement `cleanup` stage

**File(s)**: `src/nmg_game_dev/pipeline/stages/cleanup.py`
**Type**: Create
**Depends**: T005
**Acceptance**:
- [ ] `def cleanup(ctx: StageContext) -> StageArtifact` satisfies the `Stage` Protocol
- [ ] Calls only `ctx.mcp_clients.blender` for structural cleanup (no decimation, no texture reduction — that's `variants`)
- [ ] Translates Blender MCP errors into `PipelineError` with stage `cleanup`
- [ ] Unit-testable with a fake `BlenderMcp`

### T010: Implement `variants` stage

**File(s)**: `src/nmg_game_dev/pipeline/stages/variants.py`
**Type**: Create
**Depends**: T005, T014
**Acceptance**:
- [ ] `def variants(ctx: StageContext) -> StageArtifact` satisfies the `Stage` Protocol
- [ ] Produces Desktop (structural-cleanup-only) and Mobile (decimated, LOD-chained, texture-baked, bone-reduced) outputs via `ctx.mcp_clients.blender`
- [ ] Uses `nmg_game_dev.variants.{desktop_path,mobile_path}` helpers from T014 to compute target folders
- [ ] Calls `nmg_game_dev.variants.assert_no_cross_reference(artifact)` before returning; raises `PipelineError("variants.cross_reference", …)` on violation
- [ ] Sidecar records poly counts and texture byte totals per variant (feeds the `quality` stage)

### T011: Implement `quality` stage

**File(s)**: `src/nmg_game_dev/pipeline/stages/quality.py`
**Type**: Create
**Depends**: T005, T015
**Acceptance**:
- [ ] `def quality(ctx: StageContext) -> StageArtifact` satisfies the `Stage` Protocol
- [ ] No MCP calls — pure local checks using `nmg_game_dev.quality.check_mobile_budget` and `check_manifest` (T015)
- [ ] On failure: raises `PipelineError("quality.mobile_budget_exceeded", …)` or `PipelineError("quality.manifest_malformed", …)` with `remediation` describing the specific budget miss
- [ ] On pass: artifact sidecar carries the `BudgetReport` + `ManifestReport` for downstream observability

### T012: Implement `import_ue` stage

**File(s)**: `src/nmg_game_dev/pipeline/stages/import_ue.py`
**Type**: Create
**Depends**: T005
**Acceptance**:
- [ ] `def import_ue(ctx: StageContext) -> StageArtifact` satisfies the `Stage` Protocol
- [ ] Calls `ctx.mcp_clients.unreal` (VibeUE bridge) to import Desktop + Mobile outputs into `Content/<Category>/<Name>/{Desktop,Mobile}/`
- [ ] Sidecar records the actual imported `desktop_path` and `mobile_path` — these feed `PipelineResult`
- [ ] Translates UE MCP errors into `PipelineError` with stage `import_ue`

---

## Phase 3: Integration — variants/, quality/, pipeline.run() orchestrator

### T013: Implement `pipeline.run()` orchestrator

**File(s)**: `src/nmg_game_dev/pipeline/__init__.py`
**Type**: Modify (replaces the #1 stub; does NOT re-create the directory)
**Depends**: T006, T007, T008, T009, T010, T011, T012
**Acceptance**:
- [ ] `run(prompt, source, *, cache_dir=None, mcp_clients=None) -> PipelineResult` is the only public symbol
- [ ] Builds an `ArtifactCache` from `cache_dir` (or the env default)
- [ ] Loads real `McpClients` from `.mcp.json` when `mcp_clients is None`
- [ ] Chain: `source`-picked generate → texture → cleanup → variants → quality → import_ue, each checked against cache before running
- [ ] On success: returns `PipelineResult(desktop_path, mobile_path, stages_executed, cache_hits)` assembled from the `import_ue` sidecar + per-stage cache hit/miss record
- [ ] On any stage `PipelineError`: re-raises unchanged (orchestrator does NOT wrap); downstream stages are NOT invoked
- [ ] Stage ordering is asserted by an in-module `_STAGE_ORDER` tuple that BDD and unit tests can import to avoid hard-coding the sequence twice
- [ ] Passes `mypy --strict`

### T014: Implement `variants/` path helpers + cross-reference guard

**File(s)**: `src/nmg_game_dev/variants/__init__.py`
**Type**: Modify (replaces the #1 stub)
**Depends**: T002, T004
**Acceptance**:
- [ ] `desktop_path(consumer_content_root: Path, prompt: Prompt) -> Path` returns `<root>/Content/<Category>/<Name>/Desktop/`
- [ ] `mobile_path(consumer_content_root: Path, prompt: Prompt) -> Path` returns `<root>/Content/<Category>/<Name>/Mobile/`
- [ ] `assert_no_cross_reference(artifact: StageArtifact) -> None` scans the artifact's sidecar and blob metadata for paths containing the opposite variant folder; raises `PipelineError("variants.cross_reference", message, remediation, stage="variants")` on violation
- [ ] Passes `mypy --strict`

### T015: Implement `quality/` budget + manifest checks

**File(s)**: `src/nmg_game_dev/quality/__init__.py`
**Type**: Modify (replaces the #1 stub)
**Depends**: T004
**Acceptance**:
- [ ] `class MobileBudget(BaseModel)` with `poly_budget: int`, `texture_byte_budget: int`
- [ ] `class BudgetReport(BaseModel)` with `variant`, `poly_count`, `texture_bytes`, `poly_budget`, `texture_budget`, `passed: bool`, `reasons: list[str]`
- [ ] `def check_mobile_budget(artifact: StageArtifact, budget: MobileBudget) -> BudgetReport` — deterministic; reads variant metadata from the artifact sidecar
- [ ] `class ManifestReport(BaseModel)` with `passed: bool`, `reasons: list[str]`
- [ ] `def check_manifest(artifact: StageArtifact) -> ManifestReport` — validates the sidecar's manifest-prep fields are present and well-typed
- [ ] Pure functions — no MCP, no filesystem writes
- [ ] Passes `mypy --strict`

---

## Phase 4: Testing — unit + BDD + e2e scaffold

**Every acceptance criterion MUST have a Gherkin test** (per `steering/tech.md` § BDD Testing).

### T016: Unit tests for types, cache, variants, quality

**File(s)**:
- `tests/unit/pipeline/test_prompt.py`
- `tests/unit/pipeline/test_result.py`
- `tests/unit/pipeline/test_errors.py`
- `tests/unit/pipeline/test_cache.py`
- `tests/unit/variants/test_paths.py`
- `tests/unit/quality/test_budget.py`
- `tests/unit/quality/test_manifest.py`

**Type**: Create
**Depends**: T002, T003, T004, T006, T014, T015
**Acceptance**:
- [ ] `Prompt` validation covers: valid inputs, invalid category/name regex, description length bounds, trimming, `stable_hash` determinism across processes
- [ ] `PipelineResult` round-trips through `model_dump_json` / `model_validate_json`
- [ ] `PipelineError` exposes all four fields
- [ ] `ArtifactCache` covers: miss, hit, atomic-write-then-rename, corrupted-sidecar → treat as miss, env-var default root
- [ ] `variants` path helpers return correct Desktop/Mobile paths for standard + hero tiers; `assert_no_cross_reference` raises on cross-reference
- [ ] `quality` checks: pass path, mobile_budget_exceeded (with exact `remediation` string), manifest_malformed
- [ ] `pytest --cov=src/nmg_game_dev` ≥ 80% line coverage for the covered modules

### T017: Unit tests for stage modules (with fake MCP clients)

**File(s)**:
- `tests/unit/pipeline/stages/test_generate.py`
- `tests/unit/pipeline/stages/test_texture.py`
- `tests/unit/pipeline/stages/test_cleanup.py`
- `tests/unit/pipeline/stages/test_variants.py`
- `tests/unit/pipeline/stages/test_quality.py`
- `tests/unit/pipeline/stages/test_import_ue.py`
- `tests/unit/pipeline/test_run.py`
- `tests/conftest.py` (adds `fake_mcp_clients` fixture)

**Type**: Create
**Depends**: T007, T008, T009, T010, T011, T012, T013
**Acceptance**:
- [ ] Each stage module has at least one happy-path test and at least one error-translation test (MCP unreachable, stage-specific failure)
- [ ] `test_texture.py` asserts the placeholder `PipelineError("texture.not_implemented", …)` is raised exactly as specified in T008
- [ ] `test_run.py` covers: full chain happy path, source routing, cache-hit short-circuit, error re-raise without wrapping, `_STAGE_ORDER` contract
- [ ] No test invokes a real MCP — `fake_mcp_clients` fixture provides scripted `BlenderMcp`/`UnrealMcp`/`MeshyMcp` fakes
- [ ] `gate-python-unit` passes

### T018: BDD feature files for AC1–AC4

**File(s)**:
- `tests/bdd/features/pipeline_blender_first.feature`
- `tests/bdd/features/pipeline_meshy_supplement.feature`
- `tests/bdd/features/pipeline_idempotency.feature`
- `tests/bdd/features/pipeline_quality_halt.feature`
- `specs/feature-pipeline-composition-core-variant-aware-stage-runner/feature.gherkin` (aggregated view of all scenarios)

**Type**: Create
**Depends**: T013
**Acceptance**:
- [ ] Each AC in `requirements.md` maps 1:1 to a scenario
- [ ] Gherkin is syntactically valid (pytest-bdd parses without error)
- [ ] Every scenario uses concrete fixture data (no "foo" / "bar")
- [ ] `feature.gherkin` in the spec directory is the aggregated documentation view; the per-test-case splits under `tests/bdd/features/` are what pytest-bdd executes

### T019: BDD step definitions

**File(s)**:
- `tests/bdd/steps/pipeline_steps.py`
- `tests/bdd/conftest.py`

**Type**: Create
**Depends**: T018
**Acceptance**:
- [ ] All `Given`/`When`/`Then` steps across the four feature files have definitions
- [ ] Fixtures include: `fake_mcp_clients`, `fixture_prompt`, `tmp_cache_dir`, and `priming_partial_run` (for AC3 — sets up a run that failed at variants)
- [ ] `gate-python-bdd` (`pytest tests/bdd/`) passes
- [ ] A test-fixture texture stage substitutes for `stages.texture.texture` via the DI seam on `pipeline.run(...)` — does NOT rely on #5 having landed

### T020: E2E scaffold gated behind `--runslow`

**File(s)**:
- `tests/e2e/test_pipeline_e2e.py`
- `tests/e2e/conftest.py` (adds `--runslow` option + skip marker)
- `tests/e2e/fixtures/fixture_prompt.json`

**Type**: Create
**Depends**: T013
**Acceptance**:
- [ ] `pytest -m slow` or `pytest --runslow` runs at least one end-to-end scenario against real Blender + UE + Meshy MCPs
- [ ] Default `pytest tests/` skips the e2e suite — it is "Should" per FR10, not Must
- [ ] Scaffold is present even if the e2e scenario is marked `@pytest.mark.xfail` pending a runnable fixture UE project (this issue ships the scaffold; wiring a fixture UE project is out of scope)

---

## Dependency Graph

```
T001 (pyproject.toml)
  │
  ├─▶ T002 (Prompt)  ──┐
  │                    ├─▶ T005 (Stage Protocol) ──┐
  │   T004 (errors) ───┘                           │
  │   │                                            │
  │   ├─▶ T014 (variants) ──────┐                  │
  │   └─▶ T015 (quality)  ──────┤                  │
  │                             │                  │
  ├─▶ T003 (PipelineResult)     │                  │
  │                             │                  │
  │                             │   T006 (cache) ──┘
  │                             │     │
  │                             │     ▼
  │              T007, T008, T009, T010 (uses T014), T011 (uses T015), T012
  │                             │     │       │        │        │       │
  │                             └─────┴───────┴────────┴────────┴───────┴───▶ T013 (run)
  │                                                                             │
  │                                     ┌───────────────────────────────────────┤
  │                                     ▼                                       ▼
  └─▶ T016 (unit — types/cache/variants/quality)              T017 (unit — stages + run)
                                                                                │
                                                                                ▼
                                                                    T018 (BDD features)
                                                                                │
                                                                                ▼
                                                                    T019 (BDD steps)
                                                                                │
                                                                                ▼
                                                                    T020 (e2e scaffold)
```

**Critical path**: T001 → T002 → T005 → T013 → T019 (unblocks `gate-python-bdd`).

---

## Verification gates applicable to this feature

Per `steering/tech.md` § Verification Gates (diff conditions evaluated at `$nmg-sdlc:verify-code` time):

- `gate-python-lint` — all tasks touch `**/*.py`
- `gate-python-types` — all tasks touch `**/*.py`
- `gate-python-unit` — T016, T017 add `tests/unit/**`
- `gate-python-bdd` — T018, T019 add `tests/bdd/**`

Gates that do NOT apply (and why):

- `gate-blender-headless` — no Blender add-on code under `plugins/nmg-game-dev-blender-addon/**` is touched
- `gate-ue-automation` — no UE C++ code under `plugins/nmg-game-dev-ue-plugin/Source/**` is touched
- `gate-skill-schema`, `gate-mcp-schema` — no SKILL.md or `mcp-servers/**` added here
- `gate-shellcheck` — no `**/*.sh` touched
- `gate-markdown-lint` — only spec/markdown inside `specs/` (consumed by SDLC tooling, not shipped docs)
- `gate-ship-smoke` — no `skills/build-*/` or `skills/ship/**` or UE plugin runtime touched

---

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #4 | 2026-04-23 | Initial feature spec |

---

## Validation Checklist

Before moving to IMPLEMENT phase:

- [x] Each task has single responsibility
- [x] Dependencies are correctly mapped
- [x] Tasks can be completed independently (given dependencies)
- [x] Acceptance criteria are verifiable
- [x] File paths reference actual project structure (per `steering/structure.md`)
- [x] Test tasks are included for each layer (unit per module, BDD per AC, e2e scaffold)
- [x] No circular dependencies
- [x] Tasks are in logical execution order
