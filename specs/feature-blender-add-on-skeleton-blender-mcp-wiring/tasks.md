# Tasks: Blender add-on skeleton + Blender MCP wiring

**Issues**: #3
**Date**: 2026-04-22
**Status**: Planning
**Author**: Rich Nunley

---

## Summary

| Phase | Tasks | Status |
|-------|-------|--------|
| Setup | 3 | [ ] |
| Backend (add-on runtime) | 6 | [ ] |
| Frontend (Blender UI) | 2 | [ ] |
| Integration | 2 | [ ] |
| Testing | 4 | [ ] |
| **Total** | **17** | |

Per `steering/structure.md`, "Frontend" here means Blender-hosted UI (N-panel). "Backend" means the Python module surface loaded into Blender's process.

---

## Task Format

```
### T[NNN]: [Task Title]
**File(s)**: absolute repo-rooted path(s)
**Type**: Create | Modify
**Depends**: T[NNN], T[NNN] or None
**Acceptance**: verifiable checklist
**Notes**: implementation hints
```

---

## Phase 1: Setup

### T001: Create utils package with `version_tuple()` helper

**File(s)**:
- `plugins/nmg-game-dev-blender-addon/utils/__init__.py` (create, empty package marker)
- `plugins/nmg-game-dev-blender-addon/utils/version.py` (create)

**Type**: Create
**Depends**: None
**Acceptance**:
- [ ] `version_tuple() -> tuple[int, int, int]` reads `VERSION` by walking up from `__file__` until found, parses `X.Y.Z`, returns `(X, Y, Z)`.
- [ ] Raises a clear `RuntimeError` with an actionable message if `VERSION` is missing or malformed.
- [ ] No import of `bpy` (so the helper is unit-testable outside Blender).
- [ ] `from __future__ import annotations` at top; type hints on every function (per `steering/tech.md` § Coding Standards — Python).

**Notes**: Walk-up search pattern so the add-on can live under `plugins/...` at repo root OR installed under a Blender user-scripts path where `VERSION` isn't a sibling. When not found, default to returning `(0, 0, 0)` is tempting but wrong — fail loudly so `$nmg-sdlc:open-pr`'s version-rewrite never silently resolves to zeros.

### T002: Create utils logging + variants helpers

**File(s)**:
- `plugins/nmg-game-dev-blender-addon/utils/logging.py` (create)
- `plugins/nmg-game-dev-blender-addon/utils/variants.py` (create)

**Type**: Create
**Depends**: T001
**Acceptance**:
- [ ] `log_stub_invocation(op_name: str) -> None` uses `logging.getLogger("nmg_game_dev_blender_addon")` and logs at INFO with message `%s: stub invoked`.
- [ ] Logger is configured to write to stderr only (module-level handler attached idempotently — calling `log_stub_invocation` twice must not double-attach handlers).
- [ ] `resolve_variant_path(parent: Path, variant: Literal["Desktop", "Mobile"]) -> Path` returns `parent / variant` and raises `ValueError` on any other variant string.
- [ ] No `bpy` import in either module.

**Notes**: stderr-only satisfies `steering/tech.md` § MCP server contract invariant 3 ("Log to stderr only — stdout is the MCP channel"), even though this add-on isn't a server — the same process hosts `ahujasid/blender-mcp`'s stdout stream.

### T003: Create Blender Extensions manifest

**File(s)**: `plugins/nmg-game-dev-blender-addon/blender_manifest.toml` (create)

**Type**: Create
**Depends**: None
**Acceptance**:
- [ ] `schema_version = "1.0.0"`.
- [ ] `id = "nmg_game_dev_blender_addon"`.
- [ ] `version` mirrors `VERSION` (updated by `$nmg-sdlc:open-pr`'s version-rewrite path).
- [ ] `blender_version_min = "4.2.0"`.
- [ ] `name = "NMG Game Dev"`, `tagline` short, `maintainer` "Nunley Media Group".
- [ ] `type = "add-on"`.
- [ ] No external `wheels` or network permissions declared.

**Notes**: Minimal manifest — Blender 4.2+ Extensions require this file in addition to (not instead of) `bl_info` for the Extensions install path. Legacy install still works from `bl_info` alone.

---

## Phase 2: Backend — add-on runtime classes

### T004: Create property_groups module with `NmgGameDevPipelineProps`

**File(s)**:
- `plugins/nmg-game-dev-blender-addon/property_groups/__init__.py` (create, exports `NmgGameDevPipelineProps`)
- `plugins/nmg-game-dev-blender-addon/property_groups/pipeline_props.py` (create)

**Type**: Create
**Depends**: None
**Acceptance**:
- [ ] `NmgGameDevPipelineProps(bpy.types.PropertyGroup)` defined with `variant: StringProperty(default="")` and `preset: EnumProperty(items=(("STANDARD","Standard",...),("HERO","Hero",...)), default="STANDARD")`.
- [ ] Class name begins `NmgGameDev` and ends `Props` (AC3 contract).
- [ ] No side-effecting imports.

**Notes**: Keep fields minimal per Requirements § Out of Scope — real fields grow with downstream skills.

### T005: Create operator stub `nmggamedev.cleanup_desktop`

**File(s)**:
- `plugins/nmg-game-dev-blender-addon/operators/__init__.py` (create, exports the three operator classes)
- `plugins/nmg-game-dev-blender-addon/operators/cleanup_desktop.py` (create)

**Type**: Create
**Depends**: T002
**Acceptance**:
- [ ] Class `NMGGAMEDEV_OT_cleanup_desktop(bpy.types.Operator)` with `bl_idname = "nmggamedev.cleanup_desktop"`, `bl_label = "Clean up for Desktop variant"`, `bl_options = {"REGISTER", "UNDO"}`.
- [ ] `execute(self, context) -> set[str]` calls `log_stub_invocation("nmggamedev.cleanup_desktop")` then returns `{"FINISHED"}`.
- [ ] No scene mutation (FR2, AC4).
- [ ] Accepts valid context without assuming any selection (FR10).

**Notes**: Template in `steering/structure.md` § File Templates is the exact shape.

### T006: Create operator stub `nmggamedev.optimize_mobile`

**File(s)**: `plugins/nmg-game-dev-blender-addon/operators/optimize_mobile.py` (create)

**Type**: Create
**Depends**: T002, T005
**Acceptance**:
- [ ] Class `NMGGAMEDEV_OT_optimize_mobile` with `bl_idname = "nmggamedev.optimize_mobile"`, `bl_label = "Optimize for Mobile variant"`, `bl_options = {"REGISTER", "UNDO"}`.
- [ ] `execute()` logs stub invocation, returns `{"FINISHED"}`, no scene mutation.

**Notes**: Same shape as T005.

### T007: Create operator stub `nmggamedev.generate_variants`

**File(s)**: `plugins/nmg-game-dev-blender-addon/operators/generate_variants.py` (create)

**Type**: Create
**Depends**: T002, T005
**Acceptance**:
- [ ] Class `NMGGAMEDEV_OT_generate_variants` with `bl_idname = "nmggamedev.generate_variants"`, `bl_label = "Generate Desktop + Mobile variants"`, `bl_options = {"REGISTER", "UNDO"}`.
- [ ] `execute()` logs stub invocation, returns `{"FINISHED"}`, no scene mutation.

**Notes**: Same shape as T005.

### T008: Create `mcp_server/manifest.py` integration seam

**File(s)**:
- `plugins/nmg-game-dev-blender-addon/mcp_server/__init__.py` (create)
- `plugins/nmg-game-dev-blender-addon/mcp_server/manifest.py` (create)

**Type**: Create
**Depends**: T005, T006, T007
**Acceptance**:
- [ ] `list_nmg_tools() -> list[dict[str, str]]` returns one dict per registered `nmggamedev.*` operator with keys `idname`, `label`, `description`.
- [ ] Implementation enumerates `bpy.types` at call time and filters operators whose `bl_idname` starts with `nmggamedev.` — does NOT import operators at module load (so `manifest.py` remains importable outside Blender for docs generation).
- [ ] Module docstring explicitly states: "This module is an integration seam into `ahujasid/blender-mcp` — it is NOT a separate MCP server and binds no port."
- [ ] No socket / network / threading code anywhere in `mcp_server/`.

**Notes**: The FR4 narrowing. If a future host-side contribution API becomes available, this module is where the registration call would land; v1 only provides discovery.

### T009: Create `__init__.py` with `bl_info`, `REGISTER_CLASSES`, register/unregister

**File(s)**: `plugins/nmg-game-dev-blender-addon/__init__.py` (create)

**Type**: Create
**Depends**: T001, T003, T004, T005, T006, T007, T008, T011
**Acceptance**:
- [ ] `bl_info` dict includes `"name": "NMG Game Dev"`, `"author"`, `"version": version_tuple()`, `"blender": (4, 2, 0)`, `"category": "Pipeline"`, `"description"`, `"doc_url"`, `"support": "COMMUNITY"`.
- [ ] `REGISTER_CLASSES: tuple[type, ...]` lists classes in exactly this order: `NmgGameDevPipelineProps`, three operator classes, `NMGGAMEDEV_PT_main_panel` (property group first, panel last — prevents draw-time attribute misses).
- [ ] `register()` iterates `REGISTER_CLASSES` calling `bpy.utils.register_class`, then attaches `bpy.types.Scene.nmg_game_dev = bpy.props.PointerProperty(type=NmgGameDevPipelineProps)`.
- [ ] `unregister()` deletes `Scene.nmg_game_dev`, then unregisters classes in reverse order.
- [ ] Calling `unregister(); register()` is idempotent and raises nothing (AC1).
- [ ] No network / file I/O during `register()` beyond `version_tuple()`'s `VERSION` read (FR11, NFR Security).

**Notes**: `bl_info["version"]` MUST be a tuple literal that `$nmg-sdlc:open-pr`'s rewriter can parse. Generate the tuple via `version_tuple()` at module-import time so the bump script has a deterministic target.

---

## Phase 3: Frontend — Blender UI

### T010: N-panel registration-only skeleton

**File(s)**:
- `plugins/nmg-game-dev-blender-addon/panels/__init__.py` (create)
- `plugins/nmg-game-dev-blender-addon/panels/main_panel.py` (create)

**Type**: Create
**Depends**: T004, T005, T006, T007
**Acceptance**:
- [ ] Class `NMGGAMEDEV_PT_main_panel(bpy.types.Panel)` with `bl_idname = "NMGGAMEDEV_PT_main_panel"`, `bl_label = "NMG Game Dev"`, `bl_space_type = "VIEW_3D"`, `bl_region_type = "UI"`, `bl_category = "NMG"` (AC5).
- [ ] Class name begins `NMGGAMEDEV_PT_` (AC3 contract).
- [ ] Registers successfully in `--background` mode (AC5).

**Notes**: Per `steering/structure.md` N-panel category convention; draw code lands in T011 so registration and draw concerns are separable during review.

### T011: N-panel `draw()` — buttons for each stub + property fields

**File(s)**: `plugins/nmg-game-dev-blender-addon/panels/main_panel.py` (modify)

**Type**: Modify
**Depends**: T010
**Acceptance**:
- [ ] `draw(self, context)` renders: `variant` prop field, `preset` prop field, then three `layout.operator("nmggamedev.<op>")` buttons in the order cleanup → optimize → generate.
- [ ] Guards with `getattr(context.scene, "nmg_game_dev", None)` so the panel renders safely if the scene property isn't attached yet.
- [ ] Draw code is ≤ 30 lines.

**Notes**: `draw()` is never called in background mode; no headless-mode guards needed at draw time.

---

## Phase 4: Integration

### T012: Author `scripts/run-blender-tests.sh`

**File(s)**: `scripts/run-blender-tests.sh` (create; `chmod +x`)

**Type**: Create
**Depends**: T013 (consumed by this script)
**Acceptance**:
- [ ] Shebang `#!/usr/bin/env bash`; `set -euo pipefail` (per `steering/tech.md` § Shell).
- [ ] Blender resolution mirrors `scripts/start-blender-mcp.sh` order: `BLENDER_BIN` → `BLENDER_APP/Contents/MacOS/Blender` → `/Applications/Blender.app/Contents/MacOS/Blender`.
- [ ] Invokes `"$BLENDER" --background --python tests/blender/_runner.py -- tests/blender` from repo root.
- [ ] Non-zero exit if Blender is not found, with a one-line remediation (contract invariant 3 in `steering/tech.md` § Session-start contract).
- [ ] Exits with the underlying pytest exit code.
- [ ] shellcheck-clean (`gate-shellcheck` applies; see `steering/tech.md` § Verification Gates).

**Notes**: The `-- tests/blender` after `--python` passes argv through to `_runner.py`; Blender swallows its own args before `--`.

### T013: Pytest bootstrap driver under Blender's Python

**File(s)**: `tests/blender/_runner.py` (create)

**Type**: Create
**Depends**: None
**Acceptance**:
- [ ] Parses argv after `--` for the pytest target path (default `tests/blender`).
- [ ] `try: import pytest` — on ImportError, runs `python -m ensurepip --upgrade` then `python -m pip install --upgrade pip pytest`, both via `subprocess.run(..., check=True)`. Install step is a no-op on subsequent runs.
- [ ] After ensuring pytest is importable, calls `pytest.main([<target>, "-q"])` and calls `sys.exit(result)`.
- [ ] Uses `sys.executable` (Blender's bundled Python) for pip invocations.
- [ ] No imports that require Blender GUI (so the bootstrap runs under `--background`).

**Notes**: `ensurepip --upgrade` is idempotent; `pip install pytest` is idempotent on installed pytest (resolves to "Requirement already satisfied"). Both steps stay cheap after the first run.

---

## Phase 5: Testing

### T014: Pytest fixtures — `enabled_addon` + `blender_context`

**File(s)**: `tests/blender/conftest.py` (create)

**Type**: Create
**Depends**: T009, T013
**Acceptance**:
- [ ] `enabled_addon` fixture: session-scoped; imports `addon_utils`, calls `addon_utils.enable("nmg_game_dev_blender_addon", default_set=True, persistent=False)`; yields the enabled module id; teardown calls `addon_utils.disable`.
- [ ] `blender_context` fixture: function-scoped; ensures a minimal scene (creates a new empty scene if `bpy.data.scenes` is empty); returns `bpy.context`.
- [ ] Both fixtures document why they exist at module scope (so failures in one don't cascade).

**Notes**: Session scope on `enabled_addon` matters — repeatedly enabling/disabling an add-on across every test leaks classes and makes AC1's "unregister→register is idempotent" harder to observe.

### T015: `test_addon_registration.py` — covers AC1, AC3, AC5, AC6

**File(s)**: `tests/blender/test_addon_registration.py` (create)

**Type**: Create
**Depends**: T014
**Acceptance**:
- [ ] `test_enable_succeeds` (AC1) — `enabled_addon` fixture consumed; `addon_utils.check("nmg_game_dev_blender_addon")` returns `(True, True)`.
- [ ] `test_unregister_register_is_idempotent` (AC1) — calls `addon.unregister()` then `addon.register()` twice; no exceptions; no duplicate class registration warnings captured via `warnings.catch_warnings()`.
- [ ] `test_naming_contract_operators` (AC3) — enumerates `bpy.types` for operators with `bl_idname.startswith("nmggamedev.")`; asserts there are exactly 3 (cleanup_desktop, optimize_mobile, generate_variants).
- [ ] `test_naming_contract_panels` (AC3) — every nmg panel class name starts with `NMGGAMEDEV_PT_`.
- [ ] `test_naming_contract_property_groups` (AC3) — every nmg property group class name starts with `NmgGameDev` and ends with `Props`.
- [ ] `test_panel_registered_in_background` (AC5) — `NMGGAMEDEV_PT_main_panel` is in `bpy.types` even though `draw()` is not called in background mode.
- [ ] `test_bl_info_version_matches_VERSION` (AC6) — parses `VERSION`, asserts `bl_info["version"] == (int, int, int)` tuple matches.

**Notes**: Use `bpy.types.__dict__` iteration to enumerate registered classes; filter by `issubclass(cls, bpy.types.Operator)` etc.

### T016: `test_operator_stubs.py` — covers AC4

**File(s)**: `tests/blender/test_operator_stubs.py` (create)

**Type**: Create
**Depends**: T014
**Acceptance**:
- [ ] Parameterized over `("cleanup_desktop", "optimize_mobile", "generate_variants")`.
- [ ] Each call — `bpy.ops.nmggamedev.<op>()` — returns `{"FINISHED"}`.
- [ ] `caplog` / `capsys` capture confirms the `<op>: stub invoked` log line was emitted at INFO.
- [ ] Before/after scene-state hash (e.g., `hash(tuple(sorted(bpy.data.objects.keys())))`) is unchanged — proves no scene mutation (FR2).

**Notes**: Blender's logger setup may bypass `caplog`; if so, stub the logger handler in a fixture to capture records directly.

### T017: `test_coexistence.py` — covers AC2 (skipped when host not installed)

**File(s)**: `tests/blender/test_coexistence.py` (create)

**Type**: Create
**Depends**: T014
**Acceptance**:
- [ ] `pytestmark = pytest.mark.requires_host` — skipped when `ahujasid/blender-mcp` is not importable.
- [ ] `test_both_addons_load` — both the host and the nmg add-on enable successfully; `addon_utils.check` returns `(True, True)` for each.
- [ ] `test_no_second_port_bound` — runs `lsof -nP -iTCP -sTCP:LISTEN` via `subprocess.run`; asserts no additional TCP port is LISTEN-ing on Blender's PID beyond `BLENDER_MCP_PORT` (default 9876). Skipped on non-macOS / Linux (Windows lacks `lsof`).
- [ ] `test_disabling_one_leaves_the_other_functional` — disable host, confirm `bpy.ops.nmggamedev.cleanup_desktop()` still returns `{"FINISHED"}`; re-enable host, disable nmg, confirm host's socket still listens.
- [ ] `verify-skip` is NOT needed — `gate-blender-headless` only requires the script to exit 0; skips do not fail pytest.

**Notes**: `requires_host` is a custom mark declared in `pyproject.toml` (or `conftest.py` via `pytest_configure`). Document the skip reason in the skip message so CI logs are self-explanatory.

---

## Dependency Graph

```
T001 (utils/version) ──────────────────────────────────────────────┐
                                                                    │
T002 (utils/logging+variants) ──┬──▶ T005 ──▶ T006 ──▶ T007 ──▶ T008│
                                │                                   │
T003 (blender_manifest.toml) ───┤                                   │
                                │                                   │
T004 (property_groups) ─────────┴─────────────────────▶ T009 (__init__.py)
                                                        │
                                                        ▼
                        T010 ──▶ T011 (panel draw)      │
                                                        │
                        T013 (runner bootstrap) ───▶ T012 (run-blender-tests.sh)
                                                        │
                                                        ▼
                        T014 (conftest fixtures) ──┬──▶ T015 (addon registration tests)
                                                   ├──▶ T016 (operator stubs tests)
                                                   └──▶ T017 (coexistence tests)
```

Critical path: **T002 → T005 → T008 → T009 → T010 → T011 → T014 → T015** (test harness assertion closes AC1/AC3/AC5/AC6).

---

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #3 | 2026-04-22 | Initial feature spec |

---

## Validation Checklist

Before moving to IMPLEMENT phase:

- [x] Each task has single responsibility
- [x] Dependencies are correctly mapped
- [x] Tasks can be completed independently (given dependencies)
- [x] Acceptance criteria are verifiable
- [x] File paths reference actual project structure (per `steering/structure.md`)
- [x] Test tasks are included for each layer (unit-equivalents covered by T015–T017; smoke by T012)
- [x] No circular dependencies
- [x] Tasks are in logical execution order
