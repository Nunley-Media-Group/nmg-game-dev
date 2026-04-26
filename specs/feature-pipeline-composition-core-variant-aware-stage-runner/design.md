# Design: Pipeline composition core — variant-aware stage runner

**Issues**: #4
**Date**: 2026-04-23
**Status**: Draft
**Author**: Rich Nunley

---

## Overview

The pipeline core is a pure-Python composition layer inside `src/nmg_game_dev/` that accepts a typed `Prompt`, walks a fixed ordered stage chain (generate → texture → cleanup → variants → quality → import), and returns the Desktop + Mobile output paths. Every stage is implemented as a `Protocol`-typed callable that receives an immutable `StageContext` and returns a typed `StageArtifact`; stages never know about each other, and each talks to exactly one MCP or one tool. The runner between them handles three cross-cutting concerns: **cache lookup** (content-addressed by `(stage, prompt hash, upstream artifact hash)`), **source routing** (Blender-first vs. Meshy-supplement picks which generator module runs, not which downstream stages run), and **error translation** (any stage-level failure surfaces as a single `PipelineError` with `.code/.message/.remediation`).

The key design decision is the **stage-as-Protocol pattern**: each stage is defined as a `typing.Protocol` in `pipeline/stages/_base.py`, so downstream stages and tests can swap implementations without inheritance. This matters most for the texture stage — #5's concrete implementation will land as a new module that satisfies the `TextureStage` Protocol, with zero edits to `pipeline/__init__.py` or any other stage. It also matters for tests, which pass fake MCP clients into the stage callables rather than monkey-patching module globals.

Cache is content-addressed and append-only in v1: keys are SHA-256 of `(stage name, stable prompt hash, incoming artifact hashes)` and values are either blob paths (for mesh/texture artifacts) or small JSON sidecars (for variant metadata and quality results). The cache lives at `${NMG_GAME_DEV_CACHE_DIR:-~/.cache/nmg-game-dev}` by default, with a per-project override (`pipeline.run(..., cache_dir=Path)`) for consumer projects that want reproducibility tied to their repo. No eviction in v1 — that's a post-v1 refinement (see `requirements.md` § Out of Scope).

---

## Architecture

### Component Diagram

Reference `steering/structure.md` § Pipeline Flow for the product-level layer architecture. The design below maps that flow to concrete Python modules.

```
┌────────────────────────────────────────────────────────────────────┐
│  Skill entry (future: skills/new-prop/SKILL.md, etc.)              │
│    - parses invocation, validates env, builds Prompt               │
└─────────────────────────────────┬──────────────────────────────────┘
                                  │ calls into
                                  ▼
┌────────────────────────────────────────────────────────────────────┐
│  src/nmg_game_dev/pipeline/__init__.py                             │
│    run(prompt: Prompt, source: Source, *, cache_dir=None)          │
│      → PipelineResult                                              │
└────┬─────────┬────────────┬──────────┬──────────┬────────┬─────────┘
     │         │            │          │          │        │
     ▼         ▼            ▼          ▼          ▼        ▼
┌────────┐ ┌────────┐ ┌──────────┐ ┌─────────┐ ┌────────┐ ┌──────────┐
│generate│ │texture │ │ cleanup  │ │variants │ │quality │ │import_ue │
│  .py   │ │  .py   │ │   .py    │ │   .py   │ │  .py   │ │   .py    │
│        │ │(abstr.)│ │          │ │         │ │        │ │          │
│Blender │ │  #5    │ │ Blender  │ │ Blender │ │ local  │ │VibeUE UE │
│ MCP ─┐ │ │  lands │ │   MCP    │ │   MCP   │ │(no MCP)│ │   MCP    │
│      │ │ │  here  │ │          │ │         │ │        │ │          │
│ Meshy│ │ │        │ │          │ │         │ │        │ │          │
│ MCP ─┘ │ │        │ │          │ │         │ │        │ │          │
└────┬───┘ └────┬───┘ └────┬─────┘ └────┬────┘ └────┬───┘ └────┬─────┘
     │          │          │            │           │          │
     ▼          ▼          ▼            ▼           ▼          ▼
 ┌──────────────────────────────────────────────────────────────────┐
 │  src/nmg_game_dev/pipeline/cache.py                              │
 │    Content-addressed lookup + store between every stage          │
 └──────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
 ┌──────────────────────────────────────────────────────────────────┐
 │  src/nmg_game_dev/variants/  + src/nmg_game_dev/quality/         │
 │    Called by variants.py and quality.py stages respectively.     │
 │    Pure-logic modules — no MCP calls.                            │
 └──────────────────────────────────────────────────────────────────┘
```

### Stage Chain (source-routed)

| # | Stage | Module | MCP target | Blender source | Meshy source |
|---|-------|--------|------------|----------------|--------------|
| 1 | generate | `stages/generate.py` | Blender *or* Meshy | → Blender MCP | → Meshy MCP |
| 2 | texture | `stages/texture.py` (abstract; #5 impl) | texture-gen tool (TBD) | → run | → run |
| 3 | cleanup | `stages/cleanup.py` | Blender | → run | → run |
| 4 | variants | `stages/variants.py` | Blender | → run | → run |
| 5 | quality | `stages/quality.py` | none (local) | → run | → run |
| 6 | import_ue | `stages/import_ue.py` | VibeUE UE MCP | → run | → run |

Stages 2–6 are identical across sources; only stage 1 branches on `source`. This is the core product rule from `steering/product.md` ("Blender is the primary authoring surface … Meshy is a supplement") translated into one branch point.

### Data Flow

```
1. Skill builds Prompt(category, name, tier, description) and calls pipeline.run(prompt, source)
2. Runner computes the initial cache key from the Prompt and picks the generate stage based on source
3. For each stage in order:
     a. Compute cache key = sha256(stage_name, prompt_hash, upstream_artifact_hash)
     b. Cache hit → load StageArtifact from cache, add stage to result.cache_hits
     c. Cache miss → call the stage callable with StageContext(prompt, upstream_artifact, cache_dir, mcp_clients)
        → on success: store StageArtifact in cache, add stage to result.stages_executed
        → on failure: translate any exception to PipelineError(code, message, remediation); raise; DO NOT import to UE
4. After the import_ue stage succeeds, return PipelineResult(desktop_path, mobile_path, stages_executed, cache_hits)
```

### Failure & resume flow

```
Run 1:
  generate HIT cache? no  → run  → store
  texture  HIT cache? no  → run  → store
  cleanup  HIT cache? no  → run  → store
  variants HIT cache? no  → run  → FAIL  → raise PipelineError, no further stages

Run 2 (same prompt):
  generate HIT cache? yes → serve from cache (no MCP call)
  texture  HIT cache? yes → serve from cache
  cleanup  HIT cache? yes → serve from cache
  variants HIT cache? no  → run  → store  (resumes here)
  quality  HIT cache? no  → run  → store
  import   HIT cache? no  → run  → store
  → PipelineResult returned, cache_hits=[generate, texture, cleanup], stages_executed=[variants, quality, import_ue]
```

This satisfies AC3 deterministically: cache keys are stable across runs as long as the `Prompt` and upstream artifact hashes are unchanged. The AC4 halt is a natural consequence of step 3c — the runner never proceeds past a failed stage.

---

## API / Interface Changes

### New public entrypoint — `src/nmg_game_dev/pipeline/__init__.py`

```python
from __future__ import annotations

from pathlib import Path
from typing import Literal

from .prompt import Prompt
from .result import PipelineResult

Source = Literal["blender", "meshy"]


def run(
    prompt: Prompt,
    source: Source,
    *,
    cache_dir: Path | None = None,
    mcp_clients: McpClients | None = None,
) -> PipelineResult:
    """Compose generate → texture → cleanup → variants → quality → import_ue.

    Raises:
        PipelineError: when any stage fails. .code/.message/.remediation carry
            the failure detail; no UE import is attempted.
    """
```

The two keyword-only arguments are the seams that tests use to substitute fakes:

- `cache_dir` — override the content-addressed cache root; defaults to `${NMG_GAME_DEV_CACHE_DIR:-~/.cache/nmg-game-dev}`.
- `mcp_clients` — DI container with pre-configured `BlenderMcp`, `UnrealMcp`, `MeshyMcp` clients; defaults to loading real clients from `.mcp.json`.

### Typed models — `src/nmg_game_dev/pipeline/prompt.py` and `result.py`

Open question resolution: **use pydantic v2**. Skills will pass user-provided strings into `Prompt(...)`; validation belongs at the boundary, not in every caller. Pydantic adds one runtime dep but it's already transitively present through several MCP client SDKs.

```python
# prompt.py
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Tier = Literal["standard", "hero"]


class Prompt(BaseModel):
    model_config = {"frozen": True}  # immutable — required for stable hashing

    category: str = Field(pattern=r"^[A-Z][A-Za-z0-9]*$")
    name: str = Field(pattern=r"^[A-Z][A-Za-z0-9]*$")
    tier: Tier
    description: str = Field(min_length=1, max_length=512)

    @field_validator("description")
    @classmethod
    def _trim(cls, v: str) -> str:
        return v.strip()

    def stable_hash(self) -> str:
        """SHA-256 over a canonical JSON projection — stable across processes."""
```

```python
# result.py
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel


class PipelineResult(BaseModel):
    desktop_path: Path
    mobile_path: Path
    stages_executed: list[str]
    cache_hits: list[str]
```

### Stage Protocol — `src/nmg_game_dev/pipeline/stages/_base.py`

Open question resolution: **stages are `Protocol` callables, not classes**. Free functions satisfy the Protocol, and tests can pass lambdas or `functools.partial` without inheriting a base class. This also lets #5's texture implementation register as a plain function.

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..prompt import Prompt


@dataclass(frozen=True)
class StageContext:
    prompt: Prompt
    upstream_artifact: StageArtifact | None  # None for generate (first stage)
    cache_dir: Path
    mcp_clients: McpClients


@dataclass(frozen=True)
class StageArtifact:
    stage: str
    blob_path: Path           # primary produced file
    sidecar: dict[str, object] | None  # metadata (e.g., variant budget summary)

    def content_hash(self) -> str:
        """Hash over blob contents + sidecar JSON. Feeds the next stage's cache key."""


class Stage(Protocol):
    def __call__(self, ctx: StageContext) -> StageArtifact: ...
```

### Error contract — `src/nmg_game_dev/pipeline/errors.py`

Matches the MCP-server error contract in `steering/tech.md` § API / Interface Standards.

```python
from __future__ import annotations


class PipelineError(Exception):
    """Raised when any stage fails. Always caught at skill boundaries."""

    def __init__(self, code: str, message: str, remediation: str, stage: str) -> None:
        super().__init__(message)
        self.code = code              # stable enum string, e.g., "quality.mobile_budget_exceeded"
        self.message = message        # human-readable
        self.remediation = remediation  # copy-pasteable next action
        self.stage = stage            # which stage raised — for observability
```

The `.code` field uses a `<stage>.<condition>` namespaced-string convention so future additions don't collide and skills can switch on it.

### Cache API — `src/nmg_game_dev/pipeline/cache.py`

```python
from __future__ import annotations

from pathlib import Path

from .stages._base import StageArtifact


class ArtifactCache:
    def __init__(self, root: Path) -> None: ...

    def key(self, stage: str, prompt_hash: str, upstream_hash: str | None) -> str:
        """SHA-256 hex of the canonical (stage, prompt_hash, upstream_hash) tuple."""

    def get(self, key: str) -> StageArtifact | None:
        """Return the cached artifact, or None on miss. Lazy blob copy on read."""

    def put(self, key: str, artifact: StageArtifact) -> None:
        """Store blob + JSON sidecar atomically (write-then-rename)."""
```

Layout on disk:

```
${NMG_GAME_DEV_CACHE_DIR}/
  by-key/
    {first-2-hex}/
      {full-sha256}/
        blob.<ext>         # the produced artifact (mesh/texture/etc.)
        sidecar.json       # {stage, produced_at, upstream_key, ...metadata}
  tmp/                      # atomic-write staging
```

### Variants module — `src/nmg_game_dev/variants/__init__.py`

```python
def desktop_path(consumer_content_root: Path, prompt: Prompt) -> Path:
    """<root>/Content/<Category>/<Name>/Desktop/"""

def mobile_path(consumer_content_root: Path, prompt: Prompt) -> Path:
    """<root>/Content/<Category>/<Name>/Mobile/"""

def assert_no_cross_reference(artifact: StageArtifact) -> None:
    """Raise PipelineError('variants.cross_reference', ...) if the artifact
       references assets from the opposite variant folder."""
```

### Quality module — `src/nmg_game_dev/quality/__init__.py`

```python
class BudgetReport(BaseModel):
    variant: Literal["desktop", "mobile"]
    poly_count: int
    texture_bytes: int
    poly_budget: int | None
    texture_budget: int | None
    passed: bool
    reasons: list[str]  # empty when passed


def check_mobile_budget(artifact: StageArtifact, budget: MobileBudget) -> BudgetReport: ...
def check_manifest(artifact: StageArtifact) -> ManifestReport: ...
```

The quality stage composes these two checks and raises `PipelineError("quality.mobile_budget_exceeded", ...)` or `PipelineError("quality.manifest_malformed", ...)` on failure.

---

## Database / Storage Changes

No database. The only persistent storage is the on-disk artifact cache described under Cache API above.

---

## State Management

Not applicable — this is a pure-logic composition layer with no UI state. State lives in the cache (across runs) and the `StageContext`/`StageArtifact` chain (within a run).

---

## UI Components

Not applicable — backend/tooling code. Consumer-facing surface is the Python API; skills (future issues) render UI-equivalent prompts in Codex.

---

## Alternatives Considered

| Option | Description | Pros | Cons | Decision |
|--------|-------------|------|------|----------|
| **A: Class-based stages** | Each stage is a subclass of `BaseStage` with `run()` method. | Familiar OO pattern; easy to store per-stage config. | Forces inheritance on #5's texture impl; makes test fakes verbose; fights `mypy --strict` on covariant return types. | Rejected — Protocol is lighter and satisfies `mypy --strict` cleanly. |
| **B: `Stage` as `Protocol` callable** | Each stage is a function matching the `Stage` Protocol. | Pure functions; trivial to fake in tests; #5 lands as a single module. | No built-in per-stage config slot (must live on `StageContext`). | **Selected** — matches "Stages talk to exactly one MCP" in `steering/structure.md`. |
| **C: dataclass `Prompt`** | Plain `@dataclass(frozen=True)` with no validation. | Zero new deps. | Validation pushed into every skill caller; regex + length checks duplicated. | Rejected — skills are the entry point for user-provided strings; validation belongs there. |
| **D: pydantic v2 `Prompt`** | `BaseModel` with field validators. | Boundary validation; stable JSON projection for hashing; already transitively installed. | One explicit dep line in `pyproject.toml`. | **Selected** — open-question #1 resolved here. |
| **E: Per-project cache only** | Default cache to `{project_root}/.nmg-game-dev-cache/`. | Reproducibility tied to the repo. | Every clone rebuilds the cache from scratch; breaks the `NMG_GAME_DEV_CACHE_DIR` default in `steering/tech.md`. | Rejected. |
| **F: Per-user cache with per-project override** | Default to `~/.cache/nmg-game-dev`; allow `pipeline.run(..., cache_dir=project_path)` for consumers that want reproducibility. | Honors steering default; gives consumers an escape hatch. | Slightly more surface area on the public entrypoint. | **Selected** — open-question #2 resolved here. |
| **G: Parallel stage execution** | Run stages 2–5 concurrently when independent. | Potentially faster. | Stages 2–5 are pairwise-dependent (cleanup reads texture output, variants reads cleanup output); parallelism requires restructuring into a DAG. Out of scope per requirements.md. | Rejected for v1. |

---

## Security Considerations

- [x] **Authentication**: No credentials handled here. MCP clients (injected via `mcp_clients`) carry whatever auth `.mcp.json` configured (e.g., `MESHY_API_KEY` from env).
- [x] **Authorization**: N/A — single-user tool, no multi-tenant concerns.
- [x] **Input Validation**: `Prompt` pydantic model validates `category`/`name` against a strict regex and `description` length at construction time. Invalid prompts raise `pydantic.ValidationError` before any MCP call.
- [x] **Data Sanitization**: Cache paths derived only from SHA-256 hex digests — no user-controlled path components. Prevents directory traversal via crafted prompts.
- [x] **Sensitive Data**: Error `.message` and `.remediation` strings never include env-var values or MCP-client internals. Stage code reads env only through pre-injected clients.

---

## Performance Considerations

- [x] **Caching**: Content-addressed, append-only per this design. Cache hits skip MCP calls entirely — the AC3 idempotent re-run never re-invokes upstream MCPs.
- [x] **Pagination**: N/A (no list APIs).
- [x] **Lazy Loading**: `ArtifactCache.get()` returns a `StageArtifact` whose `blob_path` points directly at the cache-resident blob — no copy until a downstream stage reads it. This keeps the cached-resume path in AC3 under the 200 ms non-MCP overhead budget.
- [x] **Indexing**: N/A — cache lookup is O(1) hash-table via filesystem `{first-2-hex}/{full-sha}` sharding.

---

## Testing Strategy

| Layer | Type | Framework | Coverage |
|-------|------|-----------|----------|
| `pipeline.run()` control flow | Unit | pytest | Stage ordering, source routing, cache-hit/miss branches, error translation |
| Each stage module | Unit | pytest | Stage logic with fake MCP clients; every `PipelineError` raise path |
| `ArtifactCache` | Unit | pytest | Atomic write, cache hit/miss, corrupted-entry handling |
| `Prompt` model | Unit | pytest | Validation regex, description trim, `stable_hash` determinism |
| `variants/` path helpers | Unit | pytest | Desktop/Mobile path correctness; cross-reference guard |
| `quality/` gates | Unit | pytest | Budget pass/fail with exact remediation strings |
| AC1 (Blender-first e2e) | BDD | pytest-bdd | `tests/bdd/features/pipeline_blender_first.feature` |
| AC2 (Meshy-supplement e2e) | BDD | pytest-bdd | `tests/bdd/features/pipeline_meshy_supplement.feature` |
| AC3 (idempotent re-entry) | BDD | pytest-bdd | `tests/bdd/features/pipeline_idempotency.feature` |
| AC4 (quality-gate halt) | BDD | pytest-bdd | `tests/bdd/features/pipeline_quality_halt.feature` |
| Full-stack e2e (optional) | pytest-bdd | `tests/e2e/` | Gated behind `pytest --runslow`; exercises real Blender + UE + Meshy |

Gates that apply per `steering/tech.md` § Verification Gates:

- `gate-python-lint` — ruff clean
- `gate-python-types` — mypy --strict clean
- `gate-python-unit` — `pytest tests/unit/`
- `gate-python-bdd` — `pytest tests/bdd/`
- `gate-blender-headless`, `gate-ue-automation` — do NOT apply (no Blender add-on code, no UE C++ code touched)

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| #5's texture impl doesn't fit the `Stage` Protocol | Low | Medium | Open question #3 resolved in this design — Protocol shape is fixed and documented here; #5 has a stable contract to target. |
| Cache grows unbounded and fills the user's disk | Medium | Low | Documented explicitly as out-of-scope in `requirements.md`; `NMG_GAME_DEV_CACHE_DIR` can point at an ephemeral volume; user can `rm -rf` the cache root at any time without corrupting state. |
| Stage ordering is subtly wrong for Meshy-supplement | Medium | Medium | AC2 BDD scenario asserts the exact call order; design table "Stage Chain (source-routed)" makes it reviewable at spec time, not just runtime. |
| MCP client availability breaks during a partial run | High | Low | Each stage translates connection failures into `PipelineError("mcp.{server}.unreachable", ...)` with a remediation pointing at `scripts/start-blender-mcp.sh` / `start-unreal-mcp.sh`. |
| Pydantic version mismatch with an MCP SDK | Low | Medium | Pin `pydantic>=2,<3` in `pyproject.toml`. Fail early on install rather than at runtime. |
| `Path` comparisons across platforms (macOS vs. Windows consumers) | Medium | Medium | Use `pathlib.Path` everywhere; never concatenate with `/`; test on macOS + Linux in CI (Windows is out of scope for v1 authoring). |

---

## Open Questions

All three open questions from `requirements.md` are resolved in this design:

- ✅ Prompt model → pydantic v2 (Alternative D above)
- ✅ Cache scope → per-user default with per-project override (Alternative F above)
- ✅ Stage signatures → `Protocol`-typed callables (Alternative B above)

No residual questions block Phase 3.

---

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #4 | 2026-04-23 | Initial feature spec |

---

## Validation Checklist

Before moving to TASKS phase:

- [x] Architecture follows existing project patterns (per `structure.md` § Pipeline Flow, § Layer Responsibilities)
- [x] All API/interface changes documented with schemas (public `run()`, `Stage` Protocol, `StageContext`/`StageArtifact`, `PipelineError`, `ArtifactCache`)
- [x] Database/storage changes planned — only on-disk cache, layout documented
- [x] State management approach is clear — stateless composition layer, cache is the only persistence
- [x] UI components — N/A (tooling code)
- [x] Security considerations addressed
- [x] Performance impact analyzed (cache-hit path ≤ 200 ms overhead target)
- [x] Testing strategy defined (unit + BDD per AC + optional e2e)
- [x] Alternatives were considered and documented (7 alternatives, 3 selections, 4 rejections)
- [x] Risks identified with mitigations (6 rows)
