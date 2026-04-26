# Requirements: Blender add-on skeleton + Blender MCP wiring

**Issues**: #3
**Date**: 2026-04-22
**Status**: Draft
**Author**: Rich Nunley

---

## User Story

**As an** internal NMG game developer (per `steering/product.md` — primary persona)
**I want** the `nmg-game-dev-blender-addon` shipped with `bl_info`, a register/unregister pair, operator/panel/property-group stubs that follow the naming contract, a defined seat for nmg-side Blender MCP wiring, and a headless test harness that proves it loads
**So that** every downstream Blender-facing skill (`cleanup-asset-desktop`, `optimize-asset-for-mobile`, `new-prop`, `new-character`, `generate-variants`) has a single registered place to land its operators and be invoked by the Blender MCP running in the same Blender process.

---

## Background

Issue #1 (`feature-scaffold-plugin-repo-session-start-hooks`) shipped the outside of the Blender add-on: `plugins/nmg-game-dev-blender-addon/.gitkeep`, `scripts/start-blender-mcp.sh` that enables the external `ahujasid/blender-mcp` host, and the `.mcp.json` entry pinning `blender-mcp@1.5.6`. #1's Out-of-Scope explicitly deferred the add-on's actual content to this issue.

This issue delivers the add-on itself — nmg's OWN Blender add-on with operators, panels, property groups, and the nmg-side Blender MCP integration seat. It is a **separate add-on** from `ahujasid/blender-mcp` and is enabled alongside it, not in place of it. `steering/structure.md` § Project Layout already declares the directory layout (`operators/`, `panels/`, `mcp_server/`, `utils/`) and naming conventions (`nmggamedev.verb_noun`, `NMGGAMEDEV_PT_*`, `NmgGameDev*Props`); this issue realizes those declarations as installable code.

### Relationship to the external Blender MCP host

`ahujasid/blender-mcp` is the **sole** MCP host for Blender-side capabilities. It binds the socket, receives tool calls from Codex, and executes Python inside Blender. **nmg-game-dev does not ship its own Blender MCP server** — it does not fork, vendor, or parallel `ahujasid/blender-mcp`, and it does not bind any port. The nmg add-on contributes `bpy` operators registered in the same Blender process; the host invokes them via Python execution (`bpy.ops.nmggamedev.<verb>_<noun>(...)`). The two add-ons coexist in the same Blender instance and remain independently enable-able.

### Scope of the nmg-side MCP integration seam

The add-on ships an `mcp_server/` module, as declared in `steering/structure.md` § Project Layout. The directory name is historical — despite the name, **this module is NOT a separate MCP server**. It is the Blender-side integration seam: the tool manifest + invocation helpers that make nmg operators discoverable and invokable through `ahujasid/blender-mcp`. v1 scaffolding means the seam is present and loaded; concrete tool wiring for cleanup / optimize / variant split lands with the skill-specific issues (#4 and onward).

The remaining open design question — resolved in `design.md` — is the **mechanism** by which ahujasid/blender-mcp reaches nmg operators: (a) the nmg add-on registers a manifest the host discovers at load time and advertises as first-class tools, or (b) the pipeline core invokes nmg operators via `bpy.ops` through the host's generic Python-execution tool. Both options use the existing host; neither introduces a second MCP server. Option (b) is strictly simpler (no host-side changes); option (a) is only viable if `ahujasid/blender-mcp` actually exposes an extension API.

---

## Acceptance Criteria

**IMPORTANT: Each criterion becomes a Gherkin BDD test scenario.**

### AC1: Add-on installs and enables cleanly on Blender 4.2 LTS and latest

**Given** a Blender 4.2 LTS install (the oldest supported version per `steering/tech.md` § Technology Stack) or Blender latest stable
**And** `plugins/nmg-game-dev-blender-addon/` is installed via either the Extensions system (`bl_ext.user_default.nmg_game_dev_blender_addon`) or the legacy add-on path
**When** `addon_utils.enable(<final-module-id>, default_set=True, persistent=True)` runs
**Then** the call returns without raising
**And** every operator, panel, and property group declared in the add-on's registration list is registered with Blender
**And** `unregister()` followed by `register()` succeeds with no leaked classes (idempotent re-register)

### AC2: Add-on coexists with ahujasid/blender-mcp at runtime and binds no port

**Given** `scripts/start-blender-mcp.sh` (from #1) has enabled `ahujasid/blender-mcp` and its socket server is listening on `BLENDER_MCP_PORT` (default 9876)
**When** the nmg add-on is also enabled (either manually or via the add-on's own install flow)
**Then** both add-ons load without raising, registration conflict, or duplicate-class errors
**And** the nmg add-on binds no additional TCP port (`lsof -nP -iTCP -sTCP:LISTEN` on `BLENDER_MCP_PORT + 1` and any other port attributed to Blender shows only the host's port)
**And** the `ahujasid/blender-mcp` host can invoke any nmg operator through the integration mechanism chosen in `design.md` (manifest-register or bpy-direct via the host's Python-execution tool)
**And** disabling either add-on leaves the other functional

### AC3: Operators follow the naming contract

**Given** the nmg add-on is loaded
**When** registered classes are inspected via `bpy.types`
**Then** every nmg operator's `bl_idname` begins with `nmggamedev.` (per `steering/structure.md` § Naming Conventions — Blender add-on)
**And** every panel's `bl_idname` begins with `NMGGAMEDEV_PT_`
**And** every property group class name begins with `NmgGameDev` and ends with `Props`

### AC4: Operator stubs for cleanup, optimize, and generate-variants exist and are callable

**Given** the nmg add-on is loaded in a Blender instance with a minimally valid scene context
**When** each of `nmggamedev.cleanup_desktop`, `nmggamedev.optimize_mobile`, and `nmggamedev.generate_variants` is invoked via `bpy.ops`
**Then** the call returns `{'FINISHED'}` for the stub implementation
**And** the stub emits a structured log line (`logger.info("nmggamedev.<op>: stub invoked")`) so downstream skills observing the MCP host can confirm the endpoint is wired
**And** no operator mutates scene data in the stub phase — stubs are no-ops beyond logging

### AC5: Main 3D-viewport side panel is discoverable

**Given** the nmg add-on is loaded in a GUI session of Blender
**When** the user opens the 3D viewport's N-panel
**Then** a panel whose `bl_idname` begins with `NMGGAMEDEV_PT_` is visible under a category labelled `NMG`
**And** the panel registers successfully in `--background` mode (even though it is not drawn)

### AC6: Version tuple in `bl_info` matches `VERSION`

**Given** the repo's `VERSION` file contains `X.Y.Z` (per `steering/tech.md` § Versioning)
**When** `plugins/nmg-game-dev-blender-addon/__init__.py` is imported
**Then** `bl_info["version"]` equals the tuple `(X, Y, Z)`
**And** `$nmg-sdlc:open-pr`'s `bl_info.version` rewrite target (per the Versioning mapping table) resolves to this exact literal

### AC7: Headless test harness works via run-blender-tests.sh

**Given** `tests/blender/` contains at least one pytest test that imports the add-on and exercises every operator stub
**And** `scripts/run-blender-tests.sh` exists and is executable
**When** `scripts/run-blender-tests.sh` is invoked from the repo root
**Then** Blender launches in `--background` mode, resolves via `BLENDER_BIN` or the documented default
**And** the nmg add-on loads and every operator stub test passes
**And** the script exits 0

### AC8: `gate-blender-headless` passes on the touched paths

**Given** a diff that touches `plugins/nmg-game-dev-blender-addon/**` or `tests/blender/**`
**When** `$nmg-sdlc:verify-code` evaluates `gate-blender-headless` (per `steering/tech.md` § Verification Gates)
**Then** the gate runs `scripts/run-blender-tests.sh` and exits 0

### Generated Gherkin Preview

```gherkin
Feature: Blender add-on skeleton and MCP wiring
  As an internal NMG game developer
  I want the nmg-game-dev-blender-addon installed with stub operators, panels, and an MCP integration seat
  So that downstream skills can land real implementations on a stable, tested foundation

  Scenario: Add-on installs and enables cleanly on Blender 4.2 LTS
    Given a Blender 4.2 LTS install with the nmg add-on installed
    When addon_utils.enable runs for the nmg add-on
    Then the call returns without raising
    And every declared operator, panel, and property group is registered
    And unregister followed by register succeeds with no leaked classes

  Scenario: Add-on coexists with ahujasid/blender-mcp
    Given start-blender-mcp.sh has enabled ahujasid/blender-mcp
    When the nmg add-on is also enabled
    Then both add-ons load without conflict
    And nmg operators are invokable through the MCP host integration

  Scenario: Operators follow the naming contract
    Given the nmg add-on is loaded
    When registered classes are inspected
    Then every nmg bl_idname begins with nmggamedev.
    And every panel bl_idname begins with NMGGAMEDEV_PT_
    And every property group class name begins with NmgGameDev and ends with Props

  Scenario: Operator stubs are callable and return FINISHED
    Given the nmg add-on is loaded
    When nmggamedev.cleanup_desktop, .optimize_mobile, and .generate_variants are invoked
    Then each returns FINISHED
    And each emits a structured log line indicating stub invocation

  Scenario: 3D viewport side panel is discoverable under the NMG category
    Given the nmg add-on is loaded in a GUI Blender session
    When the 3D viewport N-panel is opened
    Then an NMGGAMEDEV_PT_ panel is visible under category NMG

  Scenario: bl_info version matches VERSION
    Given VERSION contains X.Y.Z
    When __init__.py is imported
    Then bl_info["version"] equals (X, Y, Z)

  Scenario: Headless test harness runs the add-on end-to-end
    Given tests/blender/ contains operator-stub tests
    When scripts/run-blender-tests.sh is invoked from the repo root
    Then Blender launches in --background mode
    And the nmg add-on loads and the tests pass
    And the script exits 0

  Scenario: gate-blender-headless passes on touched paths
    Given a diff touching plugins/nmg-game-dev-blender-addon/** or tests/blender/**
    When $nmg-sdlc:verify-code evaluates gate-blender-headless
    Then scripts/run-blender-tests.sh runs and exits 0
```

---

## Functional Requirements

| ID | Requirement | Priority | Notes |
|----|-------------|----------|-------|
| FR1 | `plugins/nmg-game-dev-blender-addon/__init__.py` defines `bl_info` (name, author, version, blender, category, description, doc_url), a `REGISTER_CLASSES` list, and `register()` / `unregister()` functions that iterate it. | Must | Final module id chosen in `design.md`. Version tuple derived from `VERSION`. |
| FR2 | `operators/` package with stubs for `nmggamedev.cleanup_desktop`, `nmggamedev.optimize_mobile`, `nmggamedev.generate_variants` — each returning `{'FINISHED'}` with a structured log line, no scene mutation. | Must | Class names follow `NMGGAMEDEV_OT_<verb>_<noun>` per `steering/structure.md`. |
| FR3 | `panels/` package with one `NMGGAMEDEV_PT_main_panel` registered in the 3D viewport N-panel under category `NMG`. | Must | Panel draws placeholders for the stub operators. |
| FR4 | `mcp_server/` package — Blender-side integration seam into the existing `ahujasid/blender-mcp` host. **NOT a separate MCP server, no port binding.** v1 scaffolding: the module loads cleanly, exposes a tool-manifest helper (`list_nmg_tools()`) that enumerates registered `nmggamedev.*` operators with their descriptions, and documents how the pipeline core / host will invoke them. Mechanism (manifest-register vs. bpy-direct) resolved in `design.md`. | Must | Directory name is historical per `steering/structure.md`; requirements narrow the scope to "integration seam, not server". |
| FR5 | `utils/` package — shared helpers: `resolve_variant_path(parent, variant)`, `log_stub_invocation(op_name)`, `version_tuple()` reading `VERSION`. | Must | Referenced by operators and by the test harness. |
| FR6 | Property groups (e.g., `NmgGameDevPipelineProps`) scaffolded — at minimum a `StringProperty` for the active variant and an `EnumProperty` for the active preset. | Should | Enables downstream skills to persist UI state; real fields grow as skills land. |
| FR7 | `scripts/run-blender-tests.sh` — resolves Blender via `BLENDER_BIN` / `BLENDER_APP` in the same order as `start-blender-mcp.sh`; invokes `blender --background --python <pytest-runner>.py` against `tests/blender/`; exits with the test result. | Must | Backs `gate-blender-headless` per `steering/tech.md` § Verification Gates. |
| FR8 | `tests/blender/` — at least one smoke test that enables the add-on, exercises every operator stub, confirms the panel class is registered, and asserts the naming contract (AC3) holds for every registered class. | Must | Uses pytest under Blender's bundled Python. |
| FR9 | The add-on's `bl_info["version"]` tuple is kept in sync with `VERSION` per the mapping table in `steering/tech.md` § Versioning. | Must | `$nmg-sdlc:open-pr` rewrites the tuple literal; FR1 must produce a literal the rewriter can parse. |
| FR10 | Every operator stub's `bl_options` is a conservative default (`{"REGISTER", "UNDO"}`) and they accept a valid context without assuming any selection. | Should | Prevents crashes when invoked via MCP without prior UI interaction. |
| FR11 | Add-on loads in `--background` mode without attempting to draw UI; panel `poll()` (if any) guards for headless context. | Must | Required for AC7 and AC8. |

---

## Non-Functional Requirements

| Aspect | Requirement |
|--------|-------------|
| **Performance** | Add-on import + register completes in ≤ 500 ms on M-series Mac so `scripts/start-blender-mcp.sh` hook stays inside its idempotent / detached budget (per `steering/tech.md` § Session-start contract). Test harness (AC7) completes in ≤ 30 s cold. |
| **Security** | No network access during `register()`. No file writes outside Blender's user config under `register()`. No env var reads beyond `BLENDER_MCP_ADDON_OVERRIDE` (consumed at enable time) and anything `utils/` explicitly documents. |
| **Accessibility** | N/A — add-on UI is Blender-hosted; standard Blender N-panel accessibility applies. |
| **Reliability** | `unregister()` is idempotent; re-enable after disable must succeed. No class leaks on hot reload. Add-on must not crash Blender if the external `ahujasid/blender-mcp` is not present. |
| **Platforms** | macOS (primary dev), Windows, Linux — whatever Blender 4.2 LTS and latest support. Python 3.11+ to match Blender bundled Python (`steering/tech.md` § Technology Stack). |

---

## UI/UX Requirements

| Element | Requirement |
|---------|-------------|
| **Interaction** | 3D viewport N-panel; panel category `NMG`; one button per stub operator, labelled with the operator `bl_label`. No modal dialogs in v1 scaffolding. |
| **Typography** | Blender defaults — no custom fonts. |
| **Contrast** | Blender defaults — theme-driven. |
| **Loading States** | Not applicable; stub operators return synchronously. |
| **Error States** | Operator errors surface via Blender's `self.report({'ERROR'}, ...)` — stubs never error in v1. |
| **Empty States** | Panel shows all three stub operator buttons even with no object selected. |

---

## Data Requirements

### Input Data

| Field | Type | Validation | Required |
|-------|------|------------|----------|
| `BLENDER_BIN` | env var — path | Executable if set | No (falls back to `BLENDER_APP` then `/Applications/Blender.app/Contents/MacOS/Blender`) |
| `BLENDER_MCP_ADDON_OVERRIDE` | env var — comma-separated addon ids | Each token is a valid addon module id | No (falls back to the documented discovery list in `scripts/start-blender-mcp.sh`) |

### Output Data

| Field | Type | Description |
|-------|------|-------------|
| Structured stub log | stderr (Blender-hosted) | `nmggamedev.<op>: stub invoked` — consumed by MCP host logs and test-harness assertions |
| `scripts/run-blender-tests.sh` exit code | int | 0 on pass, non-zero on fail — consumed by `gate-blender-headless` |

---

## Dependencies

### Internal Dependencies

- [x] #1 `feature-scaffold-plugin-repo-session-start-hooks` — ships `plugins/nmg-game-dev-blender-addon/` directory, `scripts/start-blender-mcp.sh`, `.mcp.json` `blender` entry, `VERSION`. **Already merged** (commits 76a1479, 83d5d52, f295656).
- [x] `steering/structure.md` § Project Layout — declares the directory layout and naming conventions.
- [x] `steering/tech.md` § Session-start contract — defines port, log path, and launcher invariants.
- [x] `steering/tech.md` § Verification Gates — declares `gate-blender-headless` (backs AC8).

### External Dependencies

- [x] `ahujasid/blender-mcp` (PyPI `blender-mcp@1.5.6`, pinned in `.mcp.json`) — MCP host; must be enabled alongside the nmg add-on for AC2.
- [x] Blender 4.2 LTS (oldest supported) through Blender latest — runtime target.
- [x] Blender bundled Python 3.11+ — no compiled-wheel dependencies.

### Blocks

- [ ] #4 — pipeline composition core (needs nmg-side Blender tool endpoints to call into, per the design outcome of FR4).
- [ ] #7 — `onboard-consumer` (needs a real installable add-on to ship into consumer Blender instances).

---

## Out of Scope

This spec is a skeleton; real implementation lands in follow-on issues.

- Concrete operator bodies for cleanup, optimize, and variant-split — stubs only in v1; real logic in #4 and beyond.
- Texture-gen integration — owned by the TBD texture-gen tool spike, not this add-on.
- UE-side anything — issue #2 owns the UE plugin.
- The external `ahujasid/blender-mcp` host's lifecycle — managed by `scripts/start-blender-mcp.sh` (already shipped by #1).
- A second (nmg-authored) MCP server for Blender — explicitly ruled out; nmg-game-dev uses the existing `ahujasid/blender-mcp` host only.
- Blender Extensions-system repository publishing — the add-on is installable locally; public repository submission is a future release concern.
- Full N-panel UX (tabs, collapsible sections, preset pickers) — v1 ships one panel with three buttons.
- Property-group schemas beyond the minimal two-field stub (FR6) — real fields grow with the skills that consume them.
- Persistent caching, background tasks, or modal operator progress reporting — not needed for stubs.

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| `addon_utils.enable()` succeeds on Blender 4.2 LTS and latest | 100% | AC1 test matrix |
| Operators satisfy the naming contract | 100% of registered classes | AC3 assertion in `tests/blender/` |
| `scripts/run-blender-tests.sh` cold run | ≤ 30 s | Measured in CI |
| `gate-blender-headless` passes on touched paths | 100% | AC8 |
| Downstream skill unblock | Issues #4 and #7 can start without further add-on work | Absence of follow-up issues labelled "blender-addon-prereq" |

---

## Open Questions

- [ ] **MCP integration mechanism (resolved in `design.md`).** Decision space is narrowed to two options — both use the existing `ahujasid/blender-mcp` host; **a second MCP server is explicitly out of scope**: (a) the add-on registers a tool manifest with the host at load time so the host advertises `nmggamedev.*` endpoints as first-class MCP tools, or (b) the pipeline core invokes nmg operators via `bpy.ops` through the host's generic Python-execution tool. `design.md` picks one with rationale and verifies (a) is actually reachable in the pinned `blender-mcp@1.5.6` API before committing to it; falls back to (b) otherwise.
- [ ] **Final addon module id.** `bl_ext.user_default.nmg_game_dev_blender_addon` (Extensions system) vs. legacy `nmg_game_dev_blender_addon` vs. hyphenated variants. `design.md` picks one and the discovery list in `scripts/start-blender-mcp.sh` does not need to carry it (the nmg add-on is loaded alongside, not in place of, the external MCP host).
- [ ] **pytest entry under Blender bundled Python.** Does the repo install `pytest` into Blender's Python via `ensurepip` + `pip install`, bundle it as a vendored dep, or drive tests via a minimal custom runner that doesn't require pytest? Resolved in `design.md` and reflected in FR7.

---

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #3 | 2026-04-22 | Initial feature spec |

---

## Validation Checklist

Before moving to PLAN phase:

- [x] User story follows "As a / I want / So that" format
- [x] All acceptance criteria use Given/When/Then format
- [x] No implementation details in requirements (the MCP integration shape is deliberately deferred to `design.md`)
- [x] All criteria are testable and unambiguous
- [x] Success metrics are measurable
- [x] Edge cases and error states are specified (idempotent re-register, background mode, missing external add-on)
- [x] Dependencies are identified
- [x] Out of scope is defined
- [x] Open questions are documented
