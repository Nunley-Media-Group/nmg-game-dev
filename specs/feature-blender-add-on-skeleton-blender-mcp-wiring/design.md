# Design: Blender add-on skeleton + Blender MCP wiring

**Issues**: #3
**Date**: 2026-04-22
**Status**: Draft
**Author**: Rich Nunley

---

## Overview

This design delivers `plugins/nmg-game-dev-blender-addon/` as an installable Blender add-on that (1) registers cleanly on Blender 4.2 LTS and latest, (2) exposes `nmggamedev.*` operator / panel / property-group stubs following the naming contract in `steering/structure.md`, (3) coexists with the externally-pinned `ahujasid/blender-mcp` host (no second MCP server, no port binding — decision resolved below), and (4) is exercisable by a headless pytest harness wired to `gate-blender-headless`.

Three design decisions are resolved in this document and documented inline:

1. **MCP integration mechanism** — **Option (b): pipeline invokes `bpy.ops.nmggamedev.*` through the existing host's `execute_blender_code` generic Python-execution tool.** Option (a) (manifest-register) is rejected — `ahujasid/blender-mcp@1.5.6` does not expose an add-on-contribution API; making it do so would require forking the host, which is out of scope.
2. **Final addon module id** — **`nmg_game_dev_blender_addon`** (Python snake_case, legacy addon path). Extensions system (`bl_ext.user_default.nmg_game_dev_blender_addon`) is the preferred install target on Blender 4.2+, but the import-time module id is the snake_case name either way; the Extensions manifest references the same folder. The add-on does NOT need to appear in `scripts/start-blender-mcp.sh`'s discovery list — that list picks the MCP host; nmg is loaded alongside it, not in place of it.
3. **pytest entry under Blender's bundled Python** — **ensurepip + pip install into Blender's Python on first run**, then invoke pytest via `python -m pytest`. Driver lives in `tests/blender/_runner.py`; the install step is idempotent (checks `import pytest` first) so it's a no-op on subsequent runs.

No database changes. No state management beyond Blender-side property groups. No new HTTP endpoints.

---

## Architecture

### Component Diagram

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Claude Code (host process)                                               │
│   .mcp.json pins blender-mcp@1.5.6                                       │
└──────────────────────┬───────────────────────────────────────────────────┘
                       │ MCP stdio → uvx blender-mcp
                       ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ uvx blender-mcp (process A — the MCP server, ahujasid/blender-mcp)       │
│   Exposes tools: execute_blender_code, get_scene_info, ...                │
│   Bridges over TCP :9876 to Blender                                       │
└──────────────────────┬───────────────────────────────────────────────────┘
                       │ TCP :9876 (BLENDER_MCP_PORT)
                       ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ Blender process (launched by scripts/start-blender-mcp.sh)                │
│                                                                           │
│  ┌────────────────────────────┐   ┌─────────────────────────────────┐    │
│  │ ahujasid/blender-mcp addon │   │ nmg_game_dev_blender_addon      │    │
│  │ (enabled via start script) │   │ (THIS ISSUE)                    │    │
│  │  - TCP server :9876        │   │  - operators/  (stubs)          │    │
│  │  - receives Python code    │   │  - panels/     (N-panel)        │    │
│  │  - exec() in Blender ctx   │   │  - property_groups/             │    │
│  │    via bpy                 │   │  - mcp_server/ (INTEGRATION     │    │
│  │                            │   │    SEAM — not a server; tool    │    │
│  │                            │   │    manifest helper)             │    │
│  │                            │   │  - utils/                       │    │
│  └────────────┬───────────────┘   └─────────────────────────────────┘    │
│               │                                                           │
│               │ execute_blender_code("bpy.ops.nmggamedev.cleanup_desktop()")│
│               ▼                                                           │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │ bpy — shared Blender runtime: registered operators, panels, props│    │
│  └──────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────┘
```

Key properties:

- **Single MCP host.** Only `ahujasid/blender-mcp` owns a socket. The nmg add-on binds no port.
- **Shared bpy runtime.** Both add-ons live in the same Blender process; operators registered by the nmg add-on are invokable through the host's `execute_blender_code` tool.
- **Decoupled lifecycles.** Disabling either add-on leaves the other functional (AC2 invariant). The host is launched by the session-start script from #1; the nmg add-on is enabled by Blender's add-on machinery (user click or `addon_utils.enable` call).

### Data Flow — end-to-end stub invocation

```
1. Developer / pipeline code issues MCP tool call to `execute_blender_code`:
     {"code": "import bpy; bpy.ops.nmggamedev.cleanup_desktop()"}
2. ahujasid/blender-mcp receives the tool call over MCP stdio
3. It forwards the Python snippet to Blender over TCP :9876
4. Blender runs the snippet in the main thread via its command queue
5. `NMGGAMEDEV_OT_cleanup_desktop.execute()` runs:
     - Logs "nmggamedev.cleanup_desktop: stub invoked" (via logger, to stderr)
     - Returns {"FINISHED"}
6. Blender returns the operator result through the socket → MCP → Claude
```

For the headless test harness, Steps 1-4 collapse to "pytest under `blender --background` calls `bpy.ops.nmggamedev.cleanup_desktop()` directly".

### Layer Responsibilities (maps to `steering/structure.md` § Layer Responsibilities)

| Module | Owns | Does NOT |
|--------|------|----------|
| `operators/` | `bpy.types.Operator` subclasses with `bl_idname` / `bl_label` / `execute()` returning `{"FINISHED"}` | Compose multi-operator flows; talk to MCP |
| `panels/` | `bpy.types.Panel` subclass drawing buttons for each operator stub | Hold business logic; conditionally skip in background — registration must succeed headless |
| `property_groups/` | `bpy.types.PropertyGroup` subclasses attached to `bpy.types.Scene.nmg_game_dev` | Store runtime-only state (use Blender's session; no file I/O) |
| `mcp_server/` | **Integration seam** — `list_nmg_tools()` manifest helper; documentation of how the pipeline invokes nmg ops via the host | Run a socket; register tools with the host (no host API exists); implement operator bodies |
| `utils/` | `version_tuple()` reads `VERSION`, `log_stub_invocation(op_name)` emits structured log, `resolve_variant_path(parent, variant)` mirrors the split-variant convention | Hold operator logic |
| `__init__.py` | `bl_info`, `REGISTER_CLASSES` list, `register()` / `unregister()` — sole entry point Blender calls | Import anything that might fail at module-load time (guard risky imports in `register()`) |

---

## API / Interface Changes

### Python-level API (add-on internal)

| Symbol | Module | Purpose |
|--------|--------|---------|
| `bl_info: dict[str, Any]` | `__init__.py` | Blender add-on manifest. Version tuple via `utils.version_tuple()`. |
| `REGISTER_CLASSES: tuple[type[bpy.types.bpy_struct], ...]` | `__init__.py` | Flat registration order. Panels registered after property groups and operators to avoid draw-time attribute misses. |
| `register() -> None` | `__init__.py` | Iterates `REGISTER_CLASSES` with `bpy.utils.register_class`; attaches `Scene.nmg_game_dev` `PointerProperty`. |
| `unregister() -> None` | `__init__.py` | Reverse order; delete `Scene.nmg_game_dev`. |
| `NMGGAMEDEV_OT_cleanup_desktop` | `operators/cleanup_desktop.py` | Stub operator `nmggamedev.cleanup_desktop`. |
| `NMGGAMEDEV_OT_optimize_mobile` | `operators/optimize_mobile.py` | Stub operator `nmggamedev.optimize_mobile`. |
| `NMGGAMEDEV_OT_generate_variants` | `operators/generate_variants.py` | Stub operator `nmggamedev.generate_variants`. |
| `NMGGAMEDEV_PT_main_panel` | `panels/main_panel.py` | N-panel under category `NMG`; space_type `VIEW_3D`, region_type `UI`. |
| `NmgGameDevPipelineProps` | `property_groups/pipeline_props.py` | Minimal `variant: StringProperty`, `preset: EnumProperty`. Attached to `Scene.nmg_game_dev`. |
| `list_nmg_tools() -> list[NmgToolManifest]` | `mcp_server/manifest.py` | Enumerates registered `nmggamedev.*` operators with `{"idname", "label", "description"}` for the pipeline / docs. Read-only; no side effects. |
| `version_tuple() -> tuple[int, int, int]` | `utils/version.py` | Reads sibling `VERSION` file (walks up from `__file__`) and parses `X.Y.Z`. |
| `log_stub_invocation(op_name: str) -> None` | `utils/logging.py` | `logging.getLogger("nmg_game_dev_blender_addon").info("%s: stub invoked", op_name)` — emitted to stderr (per `steering/tech.md` § MCP server contract: stderr only). |
| `resolve_variant_path(parent: Path, variant: Literal["Desktop", "Mobile"]) -> Path` | `utils/variants.py` | Mirrors `steering/structure.md` § split-variant asset convention; pure function. |

### MCP-level API (how Claude / the pipeline reaches nmg operators)

**No new MCP tools.** Invocation uses the existing `ahujasid/blender-mcp` tool `execute_blender_code`:

```python
# From pipeline code (src/nmg_game_dev/pipeline/…)
result = mcp.blender.execute_blender_code(
    code="import bpy; return bpy.ops.nmggamedev.cleanup_desktop()"
)
```

The `mcp_server.manifest.list_nmg_tools()` helper is the **discovery surface** for pipeline code: it returns a structured list of available `nmggamedev.*` operators, consumed by docs generators and eventually by a pipeline-side thin client that wraps `execute_blender_code` calls in typed helpers. Not exposed as an MCP tool.

### File system surface

| Path | Change | Purpose |
|------|--------|---------|
| `plugins/nmg-game-dev-blender-addon/__init__.py` | Create | bl_info + register/unregister |
| `plugins/nmg-game-dev-blender-addon/operators/__init__.py` | Create | Package marker; imports the three stubs |
| `plugins/nmg-game-dev-blender-addon/operators/cleanup_desktop.py` | Create | Stub operator |
| `plugins/nmg-game-dev-blender-addon/operators/optimize_mobile.py` | Create | Stub operator |
| `plugins/nmg-game-dev-blender-addon/operators/generate_variants.py` | Create | Stub operator |
| `plugins/nmg-game-dev-blender-addon/panels/__init__.py` | Create | Package marker |
| `plugins/nmg-game-dev-blender-addon/panels/main_panel.py` | Create | `NMGGAMEDEV_PT_main_panel` |
| `plugins/nmg-game-dev-blender-addon/property_groups/__init__.py` | Create | Package marker |
| `plugins/nmg-game-dev-blender-addon/property_groups/pipeline_props.py` | Create | `NmgGameDevPipelineProps` |
| `plugins/nmg-game-dev-blender-addon/mcp_server/__init__.py` | Create | Package marker |
| `plugins/nmg-game-dev-blender-addon/mcp_server/manifest.py` | Create | `list_nmg_tools()` |
| `plugins/nmg-game-dev-blender-addon/utils/__init__.py` | Create | Package marker |
| `plugins/nmg-game-dev-blender-addon/utils/logging.py` | Create | Stub-logging helper |
| `plugins/nmg-game-dev-blender-addon/utils/variants.py` | Create | `resolve_variant_path()` |
| `plugins/nmg-game-dev-blender-addon/utils/version.py` | Create | `version_tuple()` reads `VERSION` |
| `plugins/nmg-game-dev-blender-addon/blender_manifest.toml` | Create | Blender 4.2+ Extensions manifest (opt-in install path) |
| `scripts/run-blender-tests.sh` | Create | Headless test driver backing `gate-blender-headless` |
| `tests/blender/_runner.py` | Create | `blender --background --python` driver: ensurepip → pip install pytest (idempotent) → `pytest tests/blender/` |
| `tests/blender/conftest.py` | Create | Pytest fixtures: `enabled_addon`, `blender_context` |
| `tests/blender/test_addon_registration.py` | Create | AC1, AC3, AC5, AC6 |
| `tests/blender/test_operator_stubs.py` | Create | AC4 |
| `tests/blender/test_coexistence.py` | Create | AC2 (skipped without `ahujasid/blender-mcp` installed; marked `pytest.mark.requires_host`) |

---

## Database / Storage Changes

**None.** The add-on is a Blender-runtime surface; all state lives in Blender's in-memory scene graph or transient session. No files written during `register()`.

---

## State Management

### Scene property group

```python
# property_groups/pipeline_props.py
class NmgGameDevPipelineProps(bpy.types.PropertyGroup):
    variant: bpy.props.StringProperty(
        name="Active variant",
        description="Desktop | Mobile — mirrors steering/structure.md split-variant convention",
        default="",
    )
    preset: bpy.props.EnumProperty(
        name="Active preset",
        items=(
            ("STANDARD", "Standard", "Default quality preset"),
            ("HERO", "Hero", "Character-tier preset"),
        ),
        default="STANDARD",
    )
```

Attached at `register()`:

```python
bpy.types.Scene.nmg_game_dev = bpy.props.PointerProperty(type=NmgGameDevPipelineProps)
```

Real fields grow as skills land (issue #4 onward). v1 ships these two as seed.

### State transitions

Not applicable — stubs don't mutate state. The property group exists to reserve the attachment point so downstream skills can land without re-wiring registration order.

---

## UI Components

### Main N-panel

```
┌─ NMG (N-panel category) ────────────────────┐
│  NMG Game Dev                               │
│  ─────────────────────────                  │
│  Variant: [ Desktop ▾ ]  (prop)             │
│  Preset:  [ Standard ▾ ] (prop)             │
│                                             │
│  [ Clean up for Desktop ]  (nmggamedev.cleanup_desktop)
│  [ Optimize for Mobile  ]  (nmggamedev.optimize_mobile)
│  [ Generate Variants    ]  (nmggamedev.generate_variants)
└─────────────────────────────────────────────┘
```

Panel draw code is short (≤ 30 lines). `poll()` returns True always — the panel must register in `--background` (AC5), and draw code is only called in GUI sessions.

---

## Alternatives Considered

### MCP integration mechanism

| Option | Description | Pros | Cons | Decision |
|--------|-------------|------|------|----------|
| **A: Manifest-register** | nmg add-on registers a tool manifest with `ahujasid/blender-mcp` at enable time; host advertises `nmggamedev.*` as first-class MCP tools. | Strongly-typed tool schemas; Claude auto-completion over nmg ops; no host-side Python-exec indirection. | `ahujasid/blender-mcp@1.5.6` does NOT expose an add-on contribution API — verified by its public tool surface (tools are baked into the server, not dynamically registered). Adding such an API requires forking the host, which contradicts `steering/tech.md`'s "pin MCP server versions, review each upgrade" constraint. | **Rejected — host does not support it.** |
| **B: bpy-direct via `execute_blender_code`** | Pipeline code issues `execute_blender_code("bpy.ops.nmggamedev.cleanup_desktop()")`. Host relays the Python to Blender. | Works today on the pinned host. No host-side changes. Zero new surface area. Stub-friendly — adding a new nmg operator is a pure Blender-side change. | Slightly weaker typing (pipeline code is the contract, not the MCP schema). Debug errors surface as Python tracebacks inside the `execute_blender_code` response. | **Selected.** |
| **C: Separate MCP endpoint** | Run a second MCP server in the nmg add-on on its own port. | Full control over tool schemas. | Doubles the MCP surface; contradicts Phase 1 requirement that nmg ship no second server; forces every consumer to run two socket servers. | **Explicitly ruled out — see Requirements § Out of Scope.** |

### Final addon module id

| Option | Description | Decision |
|--------|-------------|----------|
| **A: `bl_ext.user_default.nmg_game_dev_blender_addon`** | Blender 4.2+ Extensions system — full id including the repo prefix. Discovered via `addon_utils.enable("bl_ext.user_default.nmg_game_dev_blender_addon")`. | **Preferred install path on 4.2+**; requires `blender_manifest.toml`. Extensions repo is `user_default` when installed locally via `Install from Disk`. |
| **B: `nmg_game_dev_blender_addon`** | Legacy add-on path — folder under `<blender_user>/scripts/addons/` or a symlink. Discovered via `addon_utils.enable("nmg_game_dev_blender_addon")`. | **Fallback** on pre-4.2 systems (we don't support those, but the legacy path also works on 4.2+ for Install from File). |
| **C: Hyphenated variant** | `nmg-game-dev-blender-addon` | Rejected — Python module imports can't have hyphens. The directory on disk can be hyphenated if it's a symlink target, but the import-time module id must be snake_case. |

Decision: **ship with both install paths viable** — `blender_manifest.toml` enables A; `__init__.py` with `bl_info` enables B. The Python module id is `nmg_game_dev_blender_addon` in either case. Test harness and docs refer to the module id, not the Extensions prefix.

### Pytest entry under Blender's bundled Python

| Option | Description | Pros | Cons | Decision |
|--------|-------------|------|------|----------|
| **A: ensurepip + pip install into Blender's Python** | First run installs pytest; subsequent runs find it cached. | Lets us write normal pytest tests that match the project's testing style in `steering/tech.md` § Testing Standards. Install is idempotent. | Network required on first run (acceptable — CI caches Blender image). | **Selected.** |
| **B: Vendored pytest in `tests/blender/_vendor/`** | Copy pytest + deps into the repo. | No network on first run. | Vendoring pytest + pluggy + iniconfig + packaging bloats the repo; license churn on each pytest upgrade. | Rejected. |
| **C: stdlib-only unittest runner** | Rewrite tests to use `unittest`. | Zero install step. | Diverges from `steering/tech.md` testing standard (pytest / pytest-bdd). Two test styles in one repo is a readability cost. | Rejected. |

---

## Security Considerations

- [x] **Authentication**: N/A — add-on loads in-process; MCP host owns auth for external callers.
- [x] **Authorization**: N/A.
- [x] **Input Validation**: Stub operators accept no parameters in v1. `resolve_variant_path` validates `variant` is `Desktop`|`Mobile` via `Literal`; raises `ValueError` otherwise.
- [x] **Data Sanitization**: N/A — no user input crosses a trust boundary.
- [x] **Sensitive Data**: No env-var reads during `register()` except the documented `BLENDER_MCP_ADDON_OVERRIDE` (consumed by the launcher script, not the nmg add-on). No logging of env vars. No network I/O.
- [x] **Supply chain**: `blender_manifest.toml` pins minimum Blender version `4.2.0` and declares no external Python deps. No third-party wheels loaded into Blender.

---

## Performance Considerations

- [x] **Import-time budget**: Per-NFR, add-on import + register ≤ 500 ms on M-series Mac. Achieved by (a) no import-time I/O beyond reading `VERSION`, (b) no MCP discovery / socket probes at import time, (c) deferring manifest enumeration to call time in `list_nmg_tools()`.
- [x] **Background-mode load**: `register()` must not call any UI-only API (e.g., `bpy.utils.user_resource("SCRIPTS")` that implicitly inits GUI state). Panels register as classes but their `draw()` only runs in GUI mode.
- [x] **Test-harness cold run**: First-run `pip install pytest` budget — acceptable one-time cost; subsequent runs skip the install. Cold total ≤ 30 s per NFR.
- [x] **Lazy imports**: `utils/variants.py` imports `pathlib` only; `mcp_server/manifest.py` imports `bpy` at call time, not module-load time, so `manifest.py` can be imported outside Blender (useful for docs generation).

---

## Testing Strategy

| Layer | Type | Coverage | Location | Runner |
|-------|------|----------|----------|--------|
| Add-on registration | Integration (headless Blender) | AC1, AC3, AC5, AC6 | `tests/blender/test_addon_registration.py` | `scripts/run-blender-tests.sh` |
| Operator stubs | Integration (headless Blender) | AC4 | `tests/blender/test_operator_stubs.py` | Same |
| Coexistence with host | Integration (headless Blender) | AC2 | `tests/blender/test_coexistence.py` — marked `requires_host`; skipped if `ahujasid/blender-mcp` is not installed in Blender's addons path | Same |
| Test harness itself | Smoke | AC7 | `scripts/run-blender-tests.sh` exits 0 on the above | `scripts/run-blender-tests.sh` |
| Verification gate | Contract | AC8 | `/verify-code` evaluates `gate-blender-headless` | `/verify-code` |

### Fixtures

- `enabled_addon` — enables `nmg_game_dev_blender_addon` via `addon_utils.enable`; yields; unregisters on teardown.
- `blender_context` — minimal scene context (empty scene, one default object) so operators have something to act on without requiring selection.

### BDD mapping

Phase 3 (`feature.gherkin`) translates the 8 ACs into scenarios one-for-one. Step definitions land in `tests/bdd/steps/blender_addon_steps.py` **only when** the pipeline-level BDD tests start needing to drive Blender (out of scope for #3; stub scenarios in `feature.gherkin` serve as documentation for now).

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| `ahujasid/blender-mcp` upstream changes its `execute_blender_code` tool name or signature | Low | High — pipeline → nmg invocation path breaks | Pin `blender-mcp@1.5.6` exactly in `.mcp.json`; changelog-review each bump per `steering/tech.md` § Third-party MCP trust. |
| Blender 4.2 vs. latest Python diff breaks registration (e.g., `PropertyGroup` API change) | Medium | Medium | CI matrix against 4.2 LTS and latest in `scripts/run-blender-tests.sh`. |
| `pip install pytest` into Blender's Python fails in airgapped / CI environments | Medium | Medium | Cache Blender image with pytest pre-installed in CI; document manual-install fallback in `scripts/run-blender-tests.sh`'s error output. |
| Panel draw code raises in GUI mode because scene pointer property is not yet attached | Low | Low | Register panel **after** property group in `REGISTER_CLASSES`; `draw()` guards with `getattr(scene, "nmg_game_dev", None)`. |
| Module-id collision if a future nmg Blender-side package also uses `nmg_game_dev_*` | Low | Medium | Reserve the `NMGGAMEDEV_*` and `nmggamedev.*` namespace in `steering/structure.md` — already done in § Naming Conventions. |
| Extensions manifest (`blender_manifest.toml`) schema changes between Blender versions | Low | Low | Keep the manifest minimal (id, version, schema_version, blender_version_min); rev on schema bumps behind a Blender-version CI signal. |

---

## Open Questions

- [x] MCP integration mechanism — **resolved: option (b), bpy-direct via `execute_blender_code`.**
- [x] Final addon module id — **resolved: `nmg_game_dev_blender_addon`, both Extensions and legacy install paths supported.**
- [x] pytest entry under Blender bundled Python — **resolved: ensurepip + pip install into Blender's Python on first run.**
- [ ] Should the Extensions manifest be published to a public extensions repository? — Deferred per Requirements § Out of Scope.

---

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #3 | 2026-04-22 | Initial feature spec |

---

## Validation Checklist

Before moving to TASKS phase:

- [x] Architecture follows existing project patterns (per `structure.md` § Project Layout and § Naming Conventions)
- [x] All API/interface changes documented with schemas (Python-level API table; no new MCP tools)
- [x] Database/storage changes planned with migrations (none)
- [x] State management approach is clear (PropertyGroup on `Scene.nmg_game_dev`)
- [x] UI components and hierarchy defined (one N-panel)
- [x] Security considerations addressed
- [x] Performance impact analyzed
- [x] Testing strategy defined
- [x] Alternatives were considered and documented (MCP mechanism, module id, pytest entry)
- [x] Risks identified with mitigations
