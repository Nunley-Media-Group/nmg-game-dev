# Design: UE plugin skeleton — Runtime + Editor modules

**Issues**: #2
**Date**: 2026-04-22
**Status**: Draft
**Author**: Rich Nunley

---

## Overview

This design fills the empty `plugins/nmg-game-dev-ue-plugin/` directory shipped by `#1` with a UE 5.7 plugin in two modules whose responsibilities mirror `steering/structure.md` § Layer Responsibilities exactly: `NmgGameDevRuntime` ships in cooked games and hosts `UNmgAssetResolver`; `NmgGameDevEditor` adds editor-only authoring hooks (a deliberate placeholder skeleton in this issue, with the actual hook implementations landing in subsequent asset-pipeline issues).

The single load-bearing architectural choice is **strict module visibility**: the runtime module's `Build.cs` lists only `Core`, `CoreUObject`, and `Engine`. It does NOT depend on `UnrealEd`, `Slate`, `EditorSubsystem`, or anything else editor-only. This is enforced by AC3 (cook test): if a runtime header `#include`s an editor-only type, UBT fails the cook of the dogfood fixture.

The Claude → editor MCP wire is owned end-to-end by VibeUE (a separate, third-party UE plugin pinned in `.mcp.json` from `#1`). Nothing in this design binds an HTTP port, registers an HTTP route, or reads `UE_MCP_PORT`. See requirements § "MCP scope correction" for why this changed during review.

The variant resolver is a single `static UFUNCTION` on a `UBlueprintFunctionLibrary` subclass. The function reads platform context from `UGameplayStatics::GetPlatformName()` (works at runtime, mockable in tests) rather than from `#if PLATFORM_*` macros (compile-time, unmockable). Fail-closed behavior matches AC5 — invalid input returns the input unchanged plus a `LogNmgGameDev` warning; never crashes, never returns `FSoftObjectPath()`.

---

## Architecture

### Component Diagram

Reference `steering/structure.md` § Project Layout. Concrete file map for this issue:

```
plugins/nmg-game-dev-ue-plugin/
├── nmg-game-dev.uplugin                           ← FR1, AC1, AC8
└── Source/
    ├── NmgGameDevRuntime/                         ← FR2-FR5 (ships in cooked games)
    │   ├── NmgGameDevRuntime.Build.cs
    │   ├── Public/
    │   │   ├── NmgGameDevLog.h                    ← LogNmgGameDev declaration (FR9)
    │   │   └── NmgAssetResolver.h                 ← FR3 (UCLASS + ResolveVariantPath)
    │   ├── Private/
    │   │   ├── NmgGameDevLog.cpp                  ← LogNmgGameDev definition
    │   │   ├── NmgGameDevRuntimeModule.cpp        ← FR4 (FNmgGameDevRuntimeModule)
    │   │   └── NmgAssetResolver.cpp               ← ResolveVariantPath impl + warning path
    │   └── Tests/
    │       └── NmgAssetResolver.spec.cpp          ← FR5 (UE Automation Spec)
    └── NmgGameDevEditor/                          ← FR6 (editor-only)
        ├── NmgGameDevEditor.Build.cs
        └── Private/
            └── NmgGameDevEditorModule.cpp         ← FNmgGameDevEditorModule placeholder

fixtures/
└── dogfood.uproject                               ← FR7 (in-place edit — Plugins array)

scripts/
└── run-ue-tests.sh                                ← FR8 (gate-ue-automation runtime)

tests/
└── ue-automation/
    └── .gitkeep                                   ← results.xml is generated; ensure dir exists
```

### Module dependency graph

```
NmgGameDevRuntime (Type=Runtime, LoadingPhase=Default)
    └── deps: Core, CoreUObject, Engine
        (No editor-only deps. AssetResolver uses UGameplayStatics::GetPlatformName,
         which lives in Engine; no need for IPluginManager / Projects in this issue.)

NmgGameDevEditor (Type=Editor, LoadingPhase=Default)
    └── deps: Core, CoreUObject, Engine, UnrealEd (Private), NmgGameDevRuntime
        (Depends on Runtime so future editor hooks can call into AssetResolver during
         authoring; depending the OTHER way would silently force editor symbols into
         cooked builds. UnrealEd is Private — no public Editor headers consume it in
         this issue's skeleton.)
```

The Runtime → Editor arrow is one-way. Nothing in `NmgGameDevRuntime` may `#include` from `NmgGameDevEditor`. The cook test in AC3 fails if this is violated.

### Data flow — `UNmgAssetResolver::ResolveVariantPath`

```
1. Gameplay code constructs FSoftObjectPath ParentPath:
       /Game/Weapons/Katana/Katana
   (no Desktop/ or Mobile/ subfolder — the "parent path" convention)
2. Code calls UNmgAssetResolver::ResolveVariantPath(ParentPath)
3. Resolver inspects UGameplayStatics::GetPlatformName():
   - "Windows", "Mac", "Linux"     → variant = "Desktop"
   - "IOS", "Android"               → variant = "Mobile"
   - anything else (e.g., dedicated server, unknown future platform)
                                    → variant = "Desktop" + warning
4. Resolver constructs sibling-folder path:
       /Game/Weapons/Katana/Desktop/Katana   (or Mobile)
5. Validates the constructed path looks well-formed (has at least three slashes,
   does not already contain "/Desktop/" or "/Mobile/", asset-name segment matches
   the parent folder name).
6. On failure: logs "LogNmgGameDev: Warning: ResolveVariantPath: input '<path>'
   does not match parent-path convention; returning unchanged." and returns input.
7. On success: returns the variant path.
```

The validation in step 5 is what closes AC5: malformed input never silently produces an empty or wrong path that would null an asset reference at gameplay time.

### Data flow — module load + Initialized log

```
1. UE Editor launches against fixtures/dogfood.uproject (via start-unreal-mcp.sh).
2. UBT reports loaded modules; FModuleManager invokes each StartupModule in
   LoadingPhase order.
3. NmgGameDevRuntime::StartupModule:
   - Registers LogNmgGameDev category (DEFINE_LOG_CATEGORY in NmgGameDevLog.cpp).
   - Reads VersionName from the .uplugin descriptor cached at module init.
   - Emits one LogNmgGameDev: Display line.
4. NmgGameDevEditor::StartupModule:
   - Reads VersionName same way.
   - Emits one LogNmgGameDev: Display line.
5. (No third module. VibeUE — separately enabled in the consumer .uproject — handles
   the MCP HTTP bridge in its own process space.)
```

---

## API / Interface Changes

### `nmg-game-dev.uplugin` schema (UE 5.7)

```jsonc
{
  "FileVersion": 3,
  "Version": 1,
  "VersionName": "0.1.0",                        // tracked to repo-root VERSION (steering/tech.md § Versioning)
  "FriendlyName": "nmg-game-dev",
  "Description": "NMG game development pipeline — Runtime helpers (variant resolver) and Editor authoring hooks. The Claude-to-editor MCP wire is provided by VibeUE separately.",
  "Category": "NMG",
  "CreatedBy": "Nunley Media Group",
  "CreatedByURL": "https://github.com/Nunley-Media-Group/nmg-game-dev",
  "DocsURL": "",
  "MarketplaceURL": "",
  "SupportURL": "https://github.com/Nunley-Media-Group/nmg-game-dev/issues",
  "EngineVersion": "5.7.0",
  "CanContainContent": true,                     // for plugins/nmg-game-dev-ue-plugin/Content/ (templates/defaults; future)
  "IsBetaVersion": true,
  "Installed": false,
  "Modules": [
    {
      "Name": "NmgGameDevRuntime",
      "Type": "Runtime",
      "LoadingPhase": "Default",
      "PlatformAllowList": ["Mac", "Win64", "Linux", "IOS", "Android"]
    },
    {
      "Name": "NmgGameDevEditor",
      "Type": "Editor",
      "LoadingPhase": "Default",
      "PlatformAllowList": ["Mac", "Win64", "Linux"]
    }
  ]
}
```

**Why `PlatformAllowList` (not the legacy `WhitelistPlatforms`)**: UE 5.0 renamed the field. Both names are accepted by 5.7's parser, but `PlatformAllowList` is the documented forward path. Closes the related Open Question.

**Why no top-level `PlatformAllowList`**: per-module whitelists are stricter than a plugin-level one — if both are present, UBT requires intersection. Per-module avoids the trap where a top-level whitelist accidentally includes a platform a sub-module can't actually compile against.

### `UNmgAssetResolver` C++ surface

```cpp
// plugins/nmg-game-dev-ue-plugin/Source/NmgGameDevRuntime/Public/NmgAssetResolver.h
#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "NmgAssetResolver.generated.h"

UCLASS()
class NMGGAMEDEVRUNTIME_API UNmgAssetResolver : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()

public:
    /**
     * Resolve a parent asset path (no variant subfolder) to its platform-appropriate
     * Desktop/ or Mobile/ variant. See steering/structure.md § split-variant convention.
     *
     * On malformed input, logs a LogNmgGameDev warning and returns the input unchanged
     * (never crashes, never returns an empty path).
     */
    UFUNCTION(BlueprintPure, Category = "nmg-game-dev|Variants",
              meta = (DisplayName = "Resolve Variant Path"))
    static FSoftObjectPath ResolveVariantPath(const FSoftObjectPath& ParentPath);
};
```

**Why `UBlueprintFunctionLibrary`** instead of the requirements' `UCLASS(BlueprintType)`:
- The function is a stateless static lookup. `BlueprintFunctionLibrary` is the UE-canonical container for that shape; `BlueprintType` would imply the class is also instantiable / pluggable as a variable, which is wrong.
- Closes the related Open Question. The requirements text used `UCLASS(BlueprintType)` as a colloquial reference; the design correctly picks the function-library shape.

**Why `BlueprintPure`**: no observable side effects (the warning log is a diagnostic, not state mutation in BP terms). Pure means BP graphs can place the node anywhere without execution-pin wiring. Closes the related Open Question.

---

## Database / Storage Changes

None. No persistent state. Build artifacts (compiled module binaries, automation reports) are filesystem-only and not part of any data model.

---

## State Management

UE module lifecycle only — no application state introduced.

| Event | Module | Action |
|-------|--------|--------|
| `StartupModule` | Runtime | Register `LogNmgGameDev` category; emit `Initialized v<VersionName>` line |
| `StartupModule` | Editor | Emit `Initialized v<VersionName>` line; reserve hook slots (no-ops in this issue) |
| `ShutdownModule` | Editor | Emit one line; no real teardown |
| `ShutdownModule` | Runtime | Emit one line; no real teardown |

### Initialized log message format

```
LogNmgGameDev: Display: NmgGameDevRuntime Initialized v0.1.0
LogNmgGameDev: Display: NmgGameDevEditor  Initialized v0.1.0
```

Format: `LogNmgGameDev: <Verbosity>: <ModuleName> Initialized v<VersionName>` — fixed-format so AC2's grep is `grep -E 'LogNmgGameDev: Display: Nmg.+ Initialized'` and produces exactly two matches. Closes the related Open Question.

---

## UI Components

None. This issue ships no Slate UI, no Blueprint asset, no editor menu entry. The runtime resolver is a function library; the editor module is a placeholder.

---

## Alternatives Considered

| Option | Description | Pros | Cons | Decision |
|--------|-------------|------|------|----------|
| **A: Single `Editor` module containing the placeholder hooks** (no separate Runtime module) | Combine into one module of `Type=Editor` | One fewer `Build.cs`; one fewer `StartupModule` | `UNmgAssetResolver` is a runtime helper that consumer games must be able to call from cooked code. An editor-only module would not cook; we MUST have a Runtime module for the resolver. | Rejected — fundamental misfit |
| **B: Add `NmgGameDevMCP` as a third module that binds an HTTP bridge on `UE_MCP_PORT`** (the original issue body) | Three modules; ours owns the editor MCP wire | Self-contained — no external plugin dependency | VibeUE (pinned in `.mcp.json` from `#1`) IS the in-editor plugin that binds 127.0.0.1:8088/mcp. Its bridge is closed (no extension API). Building our own bridge would either collide on the port or duplicate VibeUE's ~950-method service surface. | Rejected — discovered during requirements review; see requirements § "MCP scope correction" |
| **C: Use `#if PLATFORM_*` for variant selection in `ResolveVariantPath`** | Compile-time platform branching | Zero runtime overhead | Cannot be unit-tested across platforms (compile-time fixed); cannot mock; AC5 (malformed input warning) is hard to test if branch is compile-time | Rejected — `UGameplayStatics::GetPlatformName()` is the testable path |
| **D: `UCLASS(BlueprintType)` with instance methods (per requirements text)** | An instantiable resolver class | Allows future per-instance config | The function is stateless; instance overhead is gratuitous; BP authors would have to construct an object before calling; `BlueprintFunctionLibrary` is UE's canonical pattern for this exact shape | Rejected — `BlueprintFunctionLibrary` chosen |
| **E: Make `UnrealEd` a Public dep of `NmgGameDevEditor`** | Re-export `UnrealEd` to anything depending on Editor | Future modules that depend on Editor get UnrealEd transitively | Nothing depends on Editor in this issue; Public deps inflate include graphs and build times for no benefit. Future asset-pipeline issues can promote it to Public if a real consumer emerges. | Rejected — `Private` chosen |

---

## Security Considerations

- [x] **Authentication / authorization**: N/A — this issue exposes no network surface.
- [x] **Input Validation**: `ResolveVariantPath` validates path well-formedness in step 5 of its data flow; malformed input returns unchanged + warning, never crashes.
- [x] **Sensitive Data**: No env vars, API keys, or project paths leak into log lines. The `Initialized` log line emits only the module name + version.

---

## Performance Considerations

- [x] **Per-frame cost**: `UNmgAssetResolver::ResolveVariantPath` is called at asset-load time, never per-frame. Cost is one platform-name lookup + one string concatenation. Well below the 0.1 ms per-frame budget (the budget doesn't even apply because the function isn't on the frame path).
- [x] **Memory footprint (runtime)**: One UCLASS reflection registration (`UNmgAssetResolver` — function library, no instance state) + one log category. Far below the 4 MB resident budget.
- [x] **Startup cost**: Two `StartupModule` calls; one log-category registration; one descriptor read per module for `VersionName`. Sub-millisecond cumulative; well inside UE's editor-init budget.

---

## Testing Strategy

| Layer | Type | Coverage |
|-------|------|----------|
| `UNmgAssetResolver` | UE Automation Spec (`*.spec.cpp`) | AC4 (Desktop/Mobile routing per `GetPlatformName` mock), AC5 (malformed input fail-closed). Tests live in `Source/NmgGameDevRuntime/Tests/` per `steering/structure.md`. |
| `.uplugin` parse | Build-time (UBT) | AC1 — exercised by the project regenerate step in `scripts/run-ue-tests.sh` (regenerate is a precondition; failure aborts the test run with the UBT error) |
| Module load | Integration (Gherkin) | AC2 — script greps the editor log after a smoke-launch for the two `Initialized` lines |
| Cook isolation | Integration (Gherkin) | AC3 — Development cook of the dogfood fixture; `find` over the cooked output for module binaries; failure on Editor presence or Runtime absence |
| Test runner | Smoke (Gherkin) | AC6 — invoke `scripts/run-ue-tests.sh`; assert exit 0 + JUnit report present |
| Dogfood fixture | Diff verification (Gherkin) | AC7 — `git diff` shows `fixtures/dogfood.uproject` Plugins array updated; `find fixtures/ -name '*.uproject'` returns exactly one file |
| Platform whitelist | Manifest read (Gherkin) | AC8 — `jq` over the `.uplugin` JSON; assert each module's `PlatformAllowList` matches the spec |

The Gherkin scenarios live in `specs/feature-ue-plugin-skeleton-runtime-editor-mcp-modules/feature.gherkin` and (per `steering/tech.md` § BDD Testing) are pytest-bdd executable in `tests/bdd/features/ue_plugin_skeleton.feature` once step definitions land.

### `scripts/run-ue-tests.sh` shape

```bash
#!/usr/bin/env bash
set -euo pipefail

# Resolves UE_ROOT (default /Users/Shared/Epic Games/UE_5.7), then runs the editor
# in -nullrhi headless mode against fixtures/dogfood.uproject with the automation
# command line:
#
#   UnrealEditor-Cmd <project> -ExecCmds="Automation RunTests NmgGameDev.+; Quit" \
#       -unattended -nopause -nullrhi -ReportOutputPath=tests/ue-automation \
#       -ReportExportPath=tests/ue-automation/results.xml
#
# Exit code: 0 if every NmgGameDev.* test passes, non-zero otherwise.
# JUnit-format report at tests/ue-automation/results.xml (UE writes JUnit when
# the path ends in .xml; closes the JUnit-output Open Question).
```

Closes both the JUnit output path and the test-runner shape Open Questions. Linux compatibility falls out for free — the script uses `UnrealEditor-Cmd` (renamed from `UE4Editor-Cmd` in UE5; same on Mac, Win64, Linux).

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| UE 5.7 schema changes for `.uplugin` between writing this design and landing the work | Low | Medium | `EngineVersion: "5.7.0"` is pinned. UBT validates the manifest at project-regen; AC1 is exercised by `scripts/run-ue-tests.sh`. |
| Cook of the dogfood fixture takes >10 min on a slow contributor machine | Medium | Low | AC3's cook only needs to be exercised in CI / before a release; for everyday development, AC1+AC2+AC6 give signal in <2 min. |
| `UGameplayStatics::GetPlatformName()` returns an unexpected string (e.g., "TVOS", "VisionOS" if Apple ships a future target) | Low | Low | Resolver's default branch is "Desktop" + warning. Wrong-on-Apple-future is preferable to crashing-on-Apple-future. |
| AssetResolver false-negative on edge-case paths (e.g., `/Game/Foo/Bar.Bar_C` for class refs) | Medium | Medium | The convention is "soft references to *uassets* under the variant convention"; class refs are out of scope. Validation in step 5 of the data flow rejects these as malformed → input returned unchanged + warning. |
| Linux UE Editor — `UnrealEditor-Cmd` exists on Linux but the headless path is less battle-tested | Medium | Medium | `scripts/run-ue-tests.sh` explicitly uses `-nullrhi` which is the supported headless path on Linux. CI matrix should include Linux (out of scope for this issue but enabled by FR9 / NFR Platforms). |
| `VersionName` read drifts because we read from a hard-coded literal somewhere | Low | Medium | `Initialized` log reads `VersionName` from the loaded `.uplugin` descriptor, not a literal. If implementation slips and uses a literal, AC1 + AC2 grep mismatches surface it during the test runner. |
| `#1`'s spec contained stale references to `NmgGameDevMCP` | (resolved) | (resolved) | Cleaned up in this branch alongside the #2 spec work — `#1`'s `requirements.md`/`design.md`/`tasks.md` amended in place (Status `Amended`, Change History row added) and `steering/{tech,structure}.md` corrected. |

---

## Open Questions

All requirements-phase Open Questions are resolved here:

- [x] **`LoadingPhase` per module** → `Default` for both Runtime and Editor.
- [x] **`UnrealEd` placement** → `Private` dependency in `NmgGameDevEditor.Build.cs` (no public Editor headers consume it in this skeleton).
- [x] **Platform whitelist field shape** → `PlatformAllowList` per `Modules` entry; no top-level whitelist; Linux included for both modules.
- [x] **`BlueprintPure` on `ResolveVariantPath`** → yes; warning is a diagnostic, not state.
- [x] **`UCLASS` shape** → `UBlueprintFunctionLibrary` (not `UCLASS(BlueprintType)` from the issue body).
- [x] **JUnit output path** → `tests/ue-automation/results.xml` via UE's `-ReportExportPath` flag.
- [x] **`Initialized` log format** → `LogNmgGameDev: Display: <ModuleName> Initialized v<VersionName>`.

New design-phase Open Questions:

- [ ] **`fixtures/dogfood.uproject` `Modules` array** — currently empty. Does UE 5.7 require a `Modules` entry pointing at a `.Target.cs` for an empty content-only project that enables a code plugin? If yes, the implementation adds a stub `DogfoodTarget.cs`. Confirmed at first launch.

---

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #2 | 2026-04-22 | Initial feature spec (revised during requirements review to drop NmgGameDevMCP module) |

---

## Validation Checklist

Before moving to TASKS phase:

- [x] Architecture follows existing project patterns (per `steering/structure.md` — module split mirrors the project layout; file template for `UNmgAssetResolver`)
- [x] All API/interface changes documented with schemas (`.uplugin` JSON, `UNmgAssetResolver` C++)
- [x] Database/storage changes planned with migrations (N/A — no persistent state)
- [x] State management approach is clear (UE module lifecycle table)
- [x] UI components and hierarchy defined (N/A — no UI)
- [x] Security considerations addressed (no network surface; input validation in resolver; no secrets in logs)
- [x] Performance impact analyzed (per-frame, memory, startup)
- [x] Testing strategy defined (Spec tests + Gherkin scenarios + test runner script)
- [x] Alternatives were considered and documented (five alternatives in the table, including the rejected NmgGameDevMCP module path)
- [x] Risks identified with mitigations (seven risks in the table)
