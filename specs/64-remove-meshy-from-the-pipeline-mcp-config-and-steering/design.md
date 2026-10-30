# Design: Remove Meshy from the pipeline and MCP config

**Issue**: #64
**Date**: 2026-10-29
**Status**: Approved
**Author**: Rich Nunley

## Overview

This is a subtractive change plus one new guard at the top of `pipeline.run`. `_STAGE_ORDER` and the stage list are unchanged. `generate_blender` becomes the default `generate` stage, and `stage_overrides` still works.

## Code changes

| Path | Change |
|------|--------|
| `src/nmg_game_dev/pipeline/__init__.py` | `Source = Literal["blender"]`; `_SUPPORTED_SOURCES: tuple[str, ...] = ("blender",)`; drop the `generate_meshy` import; `generate_fn = overrides.get("generate", generate_blender)`; remove Meshy wording from the module and `run` docstrings |
| `src/nmg_game_dev/pipeline/stages/_base.py` | Delete `MeshyMcp`; remove `McpClients.meshy` and its docstring lines |
| `src/nmg_game_dev/pipeline/stages/_mcp.py` | `Server = Literal["blender", "unreal"]`; drop the `"meshy"` remediation entry |
| `src/nmg_game_dev/pipeline/stages/generate.py` | Delete `generate_meshy`; the docstring describes Blender generation only |
| `.mcp.json` | Delete only the `meshy` object (and the comma before it) |

The guard runs first in `run`, before the `mcp_clients is None` check:

```python
if source not in _SUPPORTED_SOURCES:
    raise PipelineError(
        code="pipeline.unsupported_source",
        message=f"Unsupported pipeline source {source!r}",
        remediation='Use source="blender"; Blender is the only supported generation source.',
        stage="pipeline",
    )
```

Callers that pass `"meshy"` now fail type-checking and are also rejected at runtime. Tests that exercise the runtime path use `cast(Any, "meshy")`.

## Test changes

| Path | Change |
|------|--------|
| `tests/_scaffold_contract.py` | `REQUIRED_SERVERS = ("blender", "unreal")` |
| `tests/unit/test_scaffold_guards.py` | Replace `test_mcp_json_meshy_has_env` with `test_mcp_json_has_no_meshy` (no `meshy` key; no `MESHY_API_KEY` or `meshy-mcp-server` in the text). Add `test_steering_snippets_do_not_offer_meshy`, parametrized over `steering/snippets/*.md` and the AC5 strings |
| `tests/conftest.py` | Delete `FakeMeshyMcp`, `fake_meshy`, and `fake_mcp_clients_no_meshy`; `fake_mcp_clients` builds `McpClients(blender=..., unreal=...)` |
| `tests/unit/pipeline/test_run.py` | Replace `test_meshy_source_routing` with `test_unsupported_source_rejected`: `"meshy"` and `"other"` raise `pipeline.unsupported_source` with stage `pipeline` and `"blender"` in the remediation, the fakes record zero calls, and the cache dir stays empty |
| `tests/unit/pipeline/test_no_meshy.py` | New. AC3: no `meshy` in `dataclasses.fields(McpClients)` (or annotations, if it isn't a dataclass), `hasattr` checks for `MeshyMcp` and `generate_meshy` are false, `typing.get_args(Server) == ("blender", "unreal")`, and `typing.get_args(Source) == ("blender",)` |
| `tests/unit/pipeline/stages/test_generate.py` | Delete `TestGenerateMeshy` and the `generate_meshy` import |
| `tests/unit/pipeline/stages/test_cleanup.py`, `tests/unit/pipeline/stages/test_quality.py` | Remove the `fake_meshy` parameters and assertions, keeping each test's Blender and UE assertions |
| `tests/bdd/features/pipeline_meshy_supplement.feature` | Delete |
| `tests/bdd/features/pipeline_unsupported_source.feature` | New scenario: `pipeline.run` with source `"meshy"` raises `pipeline.unsupported_source` and calls no MCP fake |
| `tests/bdd/features/pipeline_blender_first.feature`, `pipeline_idempotency.feature`, `pipeline_quality_halt.feature` | Background step text becomes `the MCP clients are scripted fakes with no real Blender or UE processes` |
| `tests/bdd/test_pipeline_bdd.py` | Remove the Meshy scenario, `_FakeMeshy`, and the Meshy given, when, and then steps; rename the background step; add the unsupported-source scenario and steps |
| `tests/bdd/conftest.py` | Remove the `FakeMeshyMcp` import and `bdd_fake_meshy` |
| `tests/bdd/features/scaffold-plugin-repo-session-start-hooks.feature`, `tests/bdd/steps/test_scaffold.py` | The AC8 step becomes `it declares two pinned MCP server entries: `blender` (ahujasid/blender-mcp) and `unreal` (VibeUE)` |
| `tests/e2e/test_pipeline_e2e.py`, `tests/e2e/conftest.py` | Delete `test_meshy_supplement_e2e`; docstrings and the `--runslow` help mention only Blender and UE |

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Keep `Source` as `Literal["blender"]` with a runtime guard | Selected | The issue requires the explicit `pipeline.unsupported_source` error, and the type keeps callers honest |
| Drop the `source` parameter | Rejected | It would break the public signature that #69 will reshape anyway |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #64 | 2026-10-29 | Initial feature design |
