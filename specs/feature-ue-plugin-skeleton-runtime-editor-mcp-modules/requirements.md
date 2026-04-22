# Requirements: UE plugin skeleton — Runtime + Editor modules

**Issues**: #2
**Date**: 2026-04-22
**Status**: Draft
**Author**: Rich Nunley

---

## User Story

**As an** internal NMG game developer (per `steering/product.md` — primary persona)
**I want** the `nmg-game-dev` UE plugin skeleton in place — a valid `.uplugin` manifest, two buildable C++ modules (Runtime that ships in cooked games + Editor that doesn't), an enabled fixture project, and a Blueprint-callable variant resolver
**So that** every downstream skill that drives Unreal Editor (asset import, level dressing, build, ship) has a defined place to land its editor-side code, and every shipped consumer game has a runtime helper it can call to resolve Desktop/Mobile asset variants without each consumer re-inventing the convention.

---

## Background

Issue `#1` (`feature-scaffold-plugin-repo-session-start-hooks`) shipped the *outside* of the UE plugin: the plugin directory's `.gitkeep`, the dogfood `.uproject` fixture, the `start-unreal-mcp.sh` launcher script, and the `.mcp.json` `unreal` entry pinned to VibeUE. `#1`'s Out-of-Scope list explicitly defers "UE plugin sources beyond the plugin manifest stub needed to boot the MCP bridge on session-start" — that deferred work is this issue's scope, *minus* the MCP bridge module (see "MCP scope correction" below).

This issue fills the plugin: the `.uplugin` manifest, two C++ modules, the AssetResolver runtime helper, the enable-flag in the dogfood fixture, and the test runner that backs `gate-ue-automation`.

### MCP scope correction (revision during requirements review)

The original issue body and `#1`'s spec assumed `NmgGameDevMCP` would be a third module that binds an HTTP bridge on `UE_MCP_PORT`. Investigation during this spec's review (`https://github.com/kevinpbuckley/VibeUE`) showed that `VibeUE` — already pinned in `.mcp.json` from `#1` — IS itself the in-editor UE plugin that binds `127.0.0.1:8088/mcp`. Its bridge is closed (no plugin-extension API), and writing a competing `NmgGameDevMCP` would either collide on the port or duplicate the entire ~950-method service surface VibeUE already provides.

**Resolution**: drop `NmgGameDevMCP` from this issue entirely. The Claude → editor wire is owned by VibeUE end-to-end. NMG's contribution to the editor is the `NmgGameDevEditor` module (authoring hooks for future asset-pipeline skills) and the `NmgGameDevRuntime` module (helpers that ship in cooked games).

Concretely:
- The dogfood `.uproject`'s `Plugins` array enables `nmg-game-dev`. Contributors who want to smoke-test the VibeUE round-trip clone VibeUE manually into `fixtures/Plugins/VibeUE/` (not part of this issue's deliverables — VibeUE is a third-party plugin pulled per its own install instructions).
- `#1` AC3 ("VibeUE MCP client can connect to the bridge") is no longer closed by this issue. It will be closed by `#7` (`onboard-consumer`) ensuring VibeUE is installed in consumer `.uproject`s — that's a separate spec amendment, tracked outside this issue.
- The `UE_MCP_PORT` env var documented in `steering/tech.md` § Session-start contract is now consumed by VibeUE's Project Settings, not by anything we own. No code in this issue reads `UE_MCP_PORT`.

### What "Runtime" and "Editor" mean here

`NmgGameDevRuntime` is a C++ module of `Type=Runtime`. UBT cooks it into the consumer's shipped game binary; it executes at gameplay time on the player's device (Mac, Win64, Linux, iOS, Android). Its public API is what consumer games call from gameplay code — `UNmgAssetResolver::ResolveVariantPath` is the only entry in this issue. Subject to `steering/tech.md` § Performance (runtime — shipped UE plugin code) budgets: ≤ 0.1 ms per-frame and ≤ 4 MB resident on iPhone 15-tier hardware.

`NmgGameDevEditor` is a C++ module of `Type=Editor`. UBT loads it only inside Unreal Editor and strips it from cooked game builds. It depends on `UnrealEd` + `NmgGameDevRuntime`. In this issue it's a deliberate placeholder skeleton — empty `StartupModule`/`ShutdownModule` plus a `LogNmgGameDev` `Initialized` line. Future asset-pipeline skills (Blender→UE import, retarget, level-dressing) hook in here; landing the skeleton now means those skills don't have to litigate module structure when they arrive.

The split exists because shipping editor code in player builds is forbidden — `UnrealEd`/`Slate`/`EditorSubsystem` symbols would bloat the binary and probably fail platform certification. UBT's cook process verifies the boundary: AC3 fails the cook if a runtime header `#include`s an editor-only type.

### Versioning relationship to `VERSION`

Per `steering/tech.md` § Versioning, the plugin's `VersionName` field tracks the repo-root `VERSION` file (single source of truth). At the time this issue lands, `VERSION` reads `0.1.0` from `#1`; the `.uplugin`'s `VersionName` MUST be set to that exact value. Future bumps via `/open-pr` propagate to both files in the same commit.

### Module-naming and visibility decisions deferred to design

The names `NmgGameDevRuntime`, `NmgGameDevEditor` are load-bearing in `steering/structure.md` and stay fixed. What the design phase resolves: exact `LoadingPhase` per module; whether `NmgGameDevEditor` lists `UnrealEd` in `PrivateDependencyModuleNames` vs `PublicDependencyModuleNames`; and the exact `Initialized` log message format so AC2's grep is unambiguous.

This issue **blocks** `#6` (ship skills — needs a buildable UE plugin to package) and `#7` (`onboard-consumer` — needs something to install into consumer `.uproject`s).

---

## Acceptance Criteria

**IMPORTANT: Each criterion becomes a Gherkin BDD test scenario.**

### AC1: Plugin manifest is valid

**Given** `plugins/nmg-game-dev-ue-plugin/nmg-game-dev.uplugin` exists at the path declared in `steering/structure.md`
**When** UnrealBuildTool parses the manifest during a project regenerate (`-projectfiles`)
**Then** UBT exits 0 with no manifest-parse errors
**And** the manifest declares `FriendlyName`, `Version` (numeric), `VersionName` (string, equal to the repo-root `VERSION` value `0.1.0`), `EngineVersion: "5.7.0"`, two `Modules` entries (`NmgGameDevRuntime`, `NmgGameDevEditor`), and the platform whitelist documented in design
**And** every `Modules` entry declares `Type` (`Runtime` for the first; `Editor` for the second) and `LoadingPhase`

### AC2: Plugin loads in a UE 5.7 project — both modules report loaded

**Given** the dogfood fixture `fixtures/dogfood.uproject` has the `nmg-game-dev` plugin enabled in its `Plugins` array
**When** UE Editor 5.7 launches against that `.uproject` via `scripts/start-unreal-mcp.sh` (from `#1`)
**Then** the editor reaches the main UI without a blocking modal error
**And** the Output Log contains an `Initialized` line for each of `NmgGameDevRuntime`, `NmgGameDevEditor` (one per module's `StartupModule`)
**And** `LogModuleManager` reports no failures for either module name

### AC3: Runtime module cooks; Editor module does NOT cook

**Given** a UE Development cook of `fixtures/dogfood.uproject` for a desktop target (Mac, Win64, or Linux)
**When** the cook completes successfully
**Then** the cooked output contains the platform-appropriate `NmgGameDevRuntime` binary (`.dylib` on Mac, `.dll` on Win64, `.so` on Linux)
**And** the cooked output does NOT contain any `NmgGameDevEditor` binary
**And** the cook log shows zero references to editor-only types from the runtime module (no leak from Editor → Runtime)

### AC4: `UNmgAssetResolver::ResolveVariantPath` routes Desktop and Mobile variants correctly

**Given** an asset present at `Content/<Category>/<Name>/Desktop/<Name>.uasset` AND `Content/<Category>/<Name>/Mobile/<Name>.uasset`
**And** a parent path `Content/<Category>/<Name>/<Name>` (no variant subfolder) is supplied
**When** `UNmgAssetResolver::ResolveVariantPath(ParentPath)` is called from C++ or Blueprint at runtime
**Then** on a desktop platform (`Windows`, `Mac`, or `Linux`) the returned `FSoftObjectPath` resolves to the `Desktop/` variant
**And** on a mobile platform (`IOS` or `Android`) it resolves to the `Mobile/` variant
**And** the function is callable from Blueprint (UFUNCTION `BlueprintCallable`, BlueprintPure where it makes sense, exposed under category `nmg-game-dev`)

### AC5: AssetResolver fails closed on a malformed parent path

**Given** a parent path that does not have sibling `Desktop/` and `Mobile/` folders (e.g., a path that already ends in `/Desktop/<Name>` or a non-content path)
**When** `ResolveVariantPath` is called
**Then** the function returns the input path unchanged AND emits a single `LogNmgGameDev` warning naming the offending path and the rule it violated
**And** the function never `check()`s, never crashes, and never returns an empty path that would silently null an asset reference at gameplay time

### AC6: UE Automation tests for the runtime helpers run via the dedicated test runner

**Given** the dogfood fixture `.uproject`
**And** `scripts/run-ue-tests.sh` from this issue is on disk and executable
**When** `scripts/run-ue-tests.sh` is invoked from the repo root
**Then** the script invokes UE's automation runner against the `NmgGameDev.*` test prefix in headless mode
**And** the script exits 0 if every NmgGameDev `*.spec.cpp` test passes, non-zero otherwise (with the failing test name on stderr)
**And** the run produces a JUnit-format report under `tests/ue-automation/results.xml` (or the path the script documents) so `gate-ue-automation` can consume it

### AC7: Plugin enabled in the dogfood fixture without a separate `.uproject` being created

**Given** `fixtures/dogfood.uproject` shipped by `#1` with an empty `Plugins` array
**When** this issue lands
**Then** the same `fixtures/dogfood.uproject` file (no rename, no relocation) has a `Plugins` array entry `{ "Name": "nmg-game-dev", "Enabled": true }`
**And** no second `.uproject` exists in `fixtures/`
**And** `start-unreal-mcp.sh` from `#1` (which targets the dogfood fixture inside this repo) successfully launches against the updated file

### AC8: Cookable platforms match `steering/tech.md`'s desktop+mobile target list

**Given** the `.uplugin` manifest declares supported platforms via per-module `PlatformAllowList`
**When** a reviewer compares the declaration against `steering/product.md`'s "ships to multiple platforms (desktop + mobile)" + `steering/tech.md`'s shipped-platforms table
**Then** `Mac`, `Win64`, `Linux`, `IOS`, `Android` are all listed for `NmgGameDevRuntime`
**And** `Mac`, `Win64`, `Linux` (the three UE 5.7 editor host platforms) are listed for `NmgGameDevEditor`
**And** no other platforms (e.g., HoloLens, console SDKs) appear in any whitelist

### Generated Gherkin Preview

```gherkin
Feature: UE plugin skeleton — Runtime + Editor modules
  As an internal NMG game developer
  I want a buildable UE plugin with Runtime and Editor modules
  So that downstream skills have a place to land editor code and shipped games can resolve asset variants

  Scenario: Plugin manifest is valid
    Given the .uplugin file at plugins/nmg-game-dev-ue-plugin/nmg-game-dev.uplugin
    When UBT parses the manifest
    Then no parse errors occur
    And the manifest declares VersionName "0.1.0", two modules, and platform whitelist

  Scenario: Both modules load in UE 5.7
    Given the dogfood fixture has the plugin enabled
    When UE Editor launches via start-unreal-mcp.sh
    Then NmgGameDevRuntime and NmgGameDevEditor both log Initialized

  Scenario: Runtime cooks; Editor does not
    Given a Development cook of the dogfood fixture
    When the cook completes
    Then NmgGameDevRuntime binary is in the cooked output
    And no NmgGameDevEditor binary is present

  Scenario: AssetResolver routes Desktop and Mobile variants
    Given an asset with both Desktop/ and Mobile/ variants
    When ResolveVariantPath is called on the parent path
    Then the desktop variant resolves on desktop and the mobile variant resolves on mobile

  Scenario: AssetResolver fails closed on malformed input
    Given a parent path with no sibling Desktop/Mobile folders
    When ResolveVariantPath is called
    Then the input path is returned unchanged with a LogNmgGameDev warning

  Scenario: UE Automation tests run via scripts/run-ue-tests.sh
    Given the dogfood fixture and the test runner script
    When scripts/run-ue-tests.sh is invoked
    Then NmgGameDev.* automation tests run headlessly
    And the script exits 0 on success with a JUnit report

  Scenario: Plugin enabled in the existing dogfood fixture (no second .uproject)
    Given fixtures/dogfood.uproject from #1 with an empty Plugins array
    When this issue lands
    Then the same file has the nmg-game-dev plugin enabled
    And no second .uproject is created in fixtures/

  Scenario: Cookable platforms match steering/tech.md
    Given the .uplugin platform whitelist
    Then Mac, Win64, Linux, IOS, Android are listed for NmgGameDevRuntime
    And Mac, Win64, Linux only for NmgGameDevEditor
```

---

## Functional Requirements

| ID | Requirement | Priority | Notes |
|----|-------------|----------|-------|
| FR1 | `plugins/nmg-game-dev-ue-plugin/nmg-game-dev.uplugin` — manifest declaring `FriendlyName`, `Version`, `VersionName` (tracked to `VERSION` per `steering/tech.md` § Versioning), `EngineVersion: "5.7.0"`, two `Modules` entries, and per-module platform whitelist | Must | `VersionName` MUST equal repo-root `VERSION` at the time the spec lands (`0.1.0`) |
| FR2 | `Source/NmgGameDevRuntime/NmgGameDevRuntime.Build.cs` — module build rules; `Type=Runtime`; minimum dependency surface (`Core`, `CoreUObject`, `Engine` — no editor-only deps) | Must | Per `steering/tech.md` § Coding Standards (UE C++): "Editor-only code lives in a separate `*Editor` module" |
| FR3 | `Source/NmgGameDevRuntime/Public/NmgAssetResolver.h` + `Private/NmgAssetResolver.cpp` — `UNmgAssetResolver` class exposing `ResolveVariantPath(FSoftObjectPath)` callable from Blueprint under category `nmg-game-dev` (matches the file template intent in `steering/structure.md` § File Templates) | Must | Variant-aware: Desktop on `Windows`/`Mac`/`Linux`, Mobile on `IOS`/`Android`; failure mode per AC5 |
| FR4 | `Source/NmgGameDevRuntime/Private/NmgGameDevRuntimeModule.cpp` — `FNmgGameDevRuntimeModule : IModuleInterface` with `StartupModule` / `ShutdownModule` placeholders that emit one `Initialized` log line on `LogNmgGameDev` | Must | Log channel `LogNmgGameDev` defined here so both modules share it |
| FR5 | `Source/NmgGameDevRuntime/Tests/NmgAssetResolver.spec.cpp` — UE Automation Spec covering AC4 (variant routing) and AC5 (malformed-input fail-closed) | Must | Spec-style (`BEGIN_DEFINE_SPEC` / `END_DEFINE_SPEC`); test prefix `NmgGameDev.Runtime.AssetResolver` |
| FR6 | `Source/NmgGameDevEditor/NmgGameDevEditor.Build.cs` + `Private/NmgGameDevEditorModule.cpp` — editor-only module skeleton; `Type=Editor`; `LoadingPhase=Default` (revisited in design) | Must | `StartupModule` emits `Initialized` log line; the module is intentionally empty beyond that — future asset-pipeline skills land their hooks here |
| FR7 | `fixtures/dogfood.uproject` (from `#1`) — the `Plugins` array is updated in place to enable `nmg-game-dev`. NO new `.uproject` file is created. | Must | AC7 — explicitly an in-place edit, not a new fixture |
| FR8 | `scripts/run-ue-tests.sh` — bash script (`set -euo pipefail`, shellcheck-clean per `steering/tech.md` § Coding Standards) that drives UE's automation runner against the `NmgGameDev.*` test prefix headlessly and writes a JUnit-format report | Must | Backs `gate-ue-automation` per `steering/tech.md` § Verification Gates; exit 0 on pass, non-zero with failing test name on stderr otherwise |
| FR9 | Log channel `LogNmgGameDev` declared once in `NmgGameDevRuntime` and reused by `NmgGameDevEditor` | Should | One channel for the whole plugin so triage is greppable |

---

## Non-Functional Requirements

| Aspect | Requirement |
|--------|-------------|
| **Performance (runtime)** | Per `steering/tech.md` § Performance (runtime — shipped UE plugin code): any per-frame hook the runtime module adds MUST be ≤ 0.1 ms on iPhone 15-tier hardware; runtime module resident memory ≤ 4 MB. This issue's runtime surface (`UNmgAssetResolver`) does no per-frame work — `ResolveVariantPath` is called at asset-load time only. |
| **Security** | No credentials, API keys, or env-var values appear in any log line emitted by the modules. The `Initialized` log line emits only the module name and version. |
| **Platforms** | Runtime: `Mac`, `Win64`, `Linux`, `IOS`, `Android` (desktop + mobile per `steering/product.md`; Linux included so contributors and CI on Linux are first-class). Editor: `Mac`, `Win64`, `Linux` (UE 5.7's three editor host platforms). Apple Silicon is the primary editor host; Linux editor is a supported secondary host. Console SDKs and HoloLens are out of scope. |
| **Reliability** | Module startup failures MUST NOT silently degrade — log a single `LogNmgGameDev: Error` line naming the failure and continue editor startup. |
| **Build determinism** | Module dependencies are declared in `Build.cs` only — no `#include` of editor-only headers from runtime sources. Verified by AC3 (cook test) which fails the build if any leak exists. |
| **Testability** | UE Automation Spec coverage is required for AssetResolver (FR3). Module-load behavior is exercised by the integration scenarios in `feature.gherkin` driven by the test runner script (FR8). |

---

## Data Requirements

No persistent data model. Runtime artifacts only:

| Artifact | Purpose |
|----------|---------|
| `nmg-game-dev.uplugin` | Plugin identity, version, module declarations, platform whitelist |
| `Build.cs` files (×2) | Per-module build rules consumed by UnrealBuildTool |
| `*.spec.cpp` files | UE Automation test definitions (Runtime tests only in this issue) |
| `tests/ue-automation/results.xml` (output) | JUnit report consumed by `gate-ue-automation` |

---

## Dependencies

### Internal Dependencies
- [x] `#1` — repo scaffolding, `plugins/nmg-game-dev-ue-plugin/.gitkeep` directory marker, `fixtures/dogfood.uproject` empty fixture, `start-unreal-mcp.sh` launcher, `.mcp.json` `unreal` entry pinned to VibeUE, `VERSION` file at `0.1.0`.
- [x] `steering/structure.md` — module names (`NmgGameDevRuntime`, `NmgGameDevEditor`), file template for `UNmgAssetResolver`, split-variant asset convention.
- [x] `steering/tech.md` — Versioning table (VersionName ↔ VERSION), runtime performance budgets, verification gate `gate-ue-automation`, UE C++ coding standards.

### External Dependencies
- [ ] Unreal Engine 5.7 installed on the contributor's machine (already required by `#1` for `start-unreal-mcp.sh`). Default path `/Users/Shared/Epic Games/UE_5.7`; overridden via `UE_ROOT`.
- [ ] UE 5.7 modules: `Engine`, `CoreUObject`, `UnrealEd` (for the editor module). All ship with the engine — no third-party deps.
- [ ] **VibeUE** is NOT a dependency of this issue. It's required at consumer-onboarding time (`#7`) so Claude can drive the editor, but no code in this issue depends on or interacts with VibeUE.

### Blocked By
- None at the time of writing. `#1` already merged (commit `f295656`).

### Spec amendments triggered (and applied)
- `#1`'s spec previously contained references to `NmgGameDevMCP`, `UE_MCP_PORT` (as an nmg-game-dev responsibility), and the MCP HTTP bridge — all responsibilities VibeUE owns end-to-end. **Cleaned up in this branch alongside the #2 work**: `specs/feature-scaffold-plugin-repo-session-start-hooks/{requirements,design,tasks}.md` were amended (Status `Amended`, `**Issues**: #1, #2`, Change History row added), and `steering/{tech,structure}.md` were corrected. See the commit history on this branch.

---

## Out of Scope

Explicitly NOT included in this issue:

- An NMG-owned MCP HTTP bridge (`NmgGameDevMCP` module, `/health` endpoint, `/tools/*` stubs, `UE_MCP_PORT` consumption). VibeUE owns the editor-side bridge end-to-end; see "MCP scope correction" in Background.
- Real implementations of any editor authoring hook. The editor module ships as a placeholder skeleton; the actual import / retarget / level-dressing flow lands when the asset-skill issues start.
- Variant generation or split-asset creation. `UNmgAssetResolver` consumes assets that already follow the `Content/<Category>/<Name>/{Desktop,Mobile}/` convention; producing those assets is the Blender add-on + asset skills' job.
- Per-frame runtime hooks. None of this issue's runtime code runs per-frame; the budget is reserved for future helpers.
- Console SDK support (PlayStation / Xbox / Switch) — explicitly out of scope per `steering/product.md` § Won't Have. (Linux IS in scope — see NFR Platforms.)
- Hot-reload friendliness across the modules (UE's hot reload of editor modules is fragile; no special accommodation in this skeleton).
- Plugin packaging (`UnrealEditor -run=BuildPlugin`) — `gate-ue-automation` runs against the dogfood fixture, not against a packaged `.uplugin` artifact. Packaging is a `#6` concern.
- `gate-ue-automation` runtime wiring inside `/verify-code` — this issue ships `scripts/run-ue-tests.sh`, the gate's runtime entry, but does not modify the gate's invocation surface in `nmg-sdlc`.
- Shipping VibeUE inside the `nmg-game-dev` repo. VibeUE is a third-party plugin pulled per its own install instructions; contributors who want to smoke-test the VibeUE round-trip clone it manually into `fixtures/Plugins/VibeUE/`.

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Time from `start-unreal-mcp.sh` invocation to both modules logging `Initialized` | ≤ 90 s on M-series Mac (cold UE Editor boot) | Tail the editor log; grep for two `Initialized` lines after launch |
| `scripts/run-ue-tests.sh` runtime against `NmgGameDev.*` (AssetResolver only) | ≤ 60 s on M-series Mac headless | `time scripts/run-ue-tests.sh` |
| Cooked-output binary size — `NmgGameDevRuntime` (Mac Development) | ≤ 2 MB | `du -h <CookedOutput>/.../NmgGameDevRuntime.dylib` |
| Downstream issues (`#6`, `#7`) start-issue blocked reason | Zero cite "UE plugin missing" after this lands | Issue comments |

---

## Open Questions

- [ ] **`LoadingPhase` per module.** Candidates: `Default` (most modules) vs `PostEngineInit` vs `PostConfigInit`. Both modules likely `Default`; resolved in design.
- [ ] **`UnrealEd` placement** — `PrivateDependencyModuleNames` vs `PublicDependencyModuleNames` in `NmgGameDevEditor.Build.cs`. Resolved in design (likely `Private` since no public headers consume it in this issue).
- [ ] **Platform whitelist exact field name.** UE 5.x uses `PlatformAllowList`; legacy `WhitelistPlatforms` still parses. Resolved in design against the UE 5.7 schema, with `Linux` included for editor + runtime as confirmed during requirements review.
- [ ] **Whether `BlueprintPure` is appropriate for `ResolveVariantPath`.** It's a pure lookup against the path string + a runtime platform query — no observable side effects. Pure is probably right; revisit in design if there's any caching consideration.
- [ ] **Test-runner JUnit output path.** `tests/ue-automation/results.xml` proposed; design confirms whether this path is what `gate-ue-automation` will read or if the gate prescribes a different location.
- [ ] **`Initialized` log message format.** One-line per module; format: `LogNmgGameDev: Display: <ModuleName> Initialized v<VersionName>`? Final string locked in design so AC2's grep is unambiguous.

---

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #2 | 2026-04-22 | Initial feature spec (revised during requirements review to drop NmgGameDevMCP — VibeUE owns the editor MCP bridge end-to-end) |

---

## Validation Checklist

Before moving to PLAN phase:

- [x] User story follows "As a / I want / So that" format
- [x] All acceptance criteria use Given/When/Then format
- [x] No implementation details in requirements (`Build.cs` content, exact include lists all deferred to design)
- [x] All criteria are testable and unambiguous (every AC has a verifiable command or artifact check)
- [x] Success metrics are measurable
- [x] Edge cases (malformed AssetResolver input) are specified
- [x] Dependencies identified (`#1` artifacts; UE 5.7 modules; explicit non-dependency on VibeUE)
- [x] Out of scope defined
- [x] Open questions documented with proposed resolutions
