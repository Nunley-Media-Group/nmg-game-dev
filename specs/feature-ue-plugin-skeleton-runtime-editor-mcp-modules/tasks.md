# Tasks: UE plugin skeleton — Runtime + Editor modules

**Issues**: #2
**Date**: 2026-04-22
**Status**: Planning
**Author**: Rich Nunley

---

## Summary

| Phase | Tasks | Status |
|-------|-------|--------|
| Setup | 3 | [x] |
| Backend (Runtime module) | 5 | [x] |
| Backend (Editor module) | 2 | [x] |
| Integration | 2 | [x] |
| Testing | 3 | [x] |
| **Total** | **15 tasks** | Completed 2026-04-22 (verify-code) |

(No Frontend phase — this issue ships no UI.)

---

## Phase 1: Setup

### T001: Author the `.uplugin` manifest

**File(s)**: `plugins/nmg-game-dev-ue-plugin/nmg-game-dev.uplugin`
**Type**: Create
**Depends**: None
**Acceptance**:
- [ ] File matches the schema in `design.md` § `.uplugin` schema (UE 5.7) verbatim
- [ ] `VersionName` field equals the current value of repo-root `VERSION` (`0.2.0` at issue-land time — bumped from `0.1.0` when `#1`'s `/open-pr` landed)
- [ ] `EngineVersion` is `"5.7.0"`
- [ ] Two `Modules` entries: `NmgGameDevRuntime` (`Type=Runtime`, `LoadingPhase=Default`) and `NmgGameDevEditor` (`Type=Editor`, `LoadingPhase=Default`)
- [ ] `PlatformAllowList` per module matches AC8 (Runtime: Mac/Win64/Linux/IOS/Android; Editor: Mac/Win64/Linux)
- [ ] No top-level `PlatformAllowList`
- [ ] `jq -e .` parses the file without error

**Notes**: This is the first artifact UBT touches; if it's malformed, every other task fails. Validate with `jq` before moving on.

### T002: Declare `LogNmgGameDev` log channel

**File(s)**:
- `plugins/nmg-game-dev-ue-plugin/Source/NmgGameDevRuntime/Public/NmgGameDevLog.h`
- `plugins/nmg-game-dev-ue-plugin/Source/NmgGameDevRuntime/Private/NmgGameDevLog.cpp`

**Type**: Create
**Depends**: None
**Acceptance**:
- [ ] Header uses `DECLARE_LOG_CATEGORY_EXTERN(LogNmgGameDev, Log, All)` with the runtime module's `*_API` export macro on the category
- [ ] Source uses `DEFINE_LOG_CATEGORY(LogNmgGameDev)`
- [ ] Header is `#pragma once` and includes only `CoreMinimal.h`
- [ ] Both files compile cleanly when included from any other source in either module (no transitive include surprises)

**Notes**: Runtime owns the channel so the Editor module gets it transitively without depending on editor-only headers. Per FR9.

### T003: Bootstrap `tests/ue-automation/` output directory

**File(s)**: `tests/ue-automation/.gitkeep`
**Type**: Create
**Depends**: None
**Acceptance**:
- [ ] Directory exists in git so `scripts/run-ue-tests.sh -ReportExportPath` has a write target on a fresh clone
- [ ] `.gitkeep` is the only file in the directory at land time

---

## Phase 2: Backend — Runtime module

### T004: Author `NmgGameDevRuntime.Build.cs`

**File(s)**: `plugins/nmg-game-dev-ue-plugin/Source/NmgGameDevRuntime/NmgGameDevRuntime.Build.cs`
**Type**: Create
**Depends**: T001, T002
**Acceptance**:
- [ ] `PublicDependencyModuleNames` lists exactly `Core`, `CoreUObject`, `Engine` — nothing else
- [ ] `PrivateDependencyModuleNames` is empty (or absent)
- [ ] Module type follows `ModuleRules` standard pattern; `PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs`
- [ ] No editor-only modules (`UnrealEd`, `Slate`, `EditorSubsystem`, `EditorStyle`, `HTTPServer`) appear anywhere in the file
- [ ] UBT regenerates project files (`-projectfiles`) without complaining about this module

**Notes**: This is the cook boundary. Adding an editor dep here breaks AC3 (cook isolation). Per FR2.

### T005: Implement `FNmgGameDevRuntimeModule`

**File(s)**: `plugins/nmg-game-dev-ue-plugin/Source/NmgGameDevRuntime/Private/NmgGameDevRuntimeModule.cpp`
**Type**: Create
**Depends**: T002, T004
**Acceptance**:
- [ ] Implements `IModuleInterface` with `StartupModule()` and `ShutdownModule()` overrides
- [ ] `IMPLEMENT_MODULE(FNmgGameDevRuntimeModule, NmgGameDevRuntime)` macro present
- [ ] `StartupModule` reads `VersionName` from `IPluginManager::Get().FindPlugin(TEXT("nmg-game-dev"))->GetDescriptor().VersionName`
- [ ] Emits exactly one log line: `UE_LOG(LogNmgGameDev, Display, TEXT("NmgGameDevRuntime Initialized v%s"), *VersionName)` using the format from `design.md` § Initialized log message format
- [ ] `ShutdownModule` emits a one-line shutdown notice on the same channel
- [ ] No `check()` or `ensure()` on the descriptor lookup — defensive fallback to `TEXT("unknown")` if `FindPlugin` returns null

**Notes**: `IPluginManager` lives in the `Projects` module; if T004's `Core/CoreUObject/Engine` triplet is insufficient, T004 needs `Projects` added to its dependency list (the design table lists Runtime deps as `Core/CoreUObject/Engine`; Projects is the smallest possible extra). Resolve this at first compile.

### T006: Author `UNmgAssetResolver` header

**File(s)**: `plugins/nmg-game-dev-ue-plugin/Source/NmgGameDevRuntime/Public/NmgAssetResolver.h`
**Type**: Create
**Depends**: T004
**Acceptance**:
- [ ] Header matches the C++ surface in `design.md` § `UNmgAssetResolver` C++ surface verbatim
- [ ] Class derives from `UBlueprintFunctionLibrary` (NOT `UObject` directly, NOT `BlueprintType`)
- [ ] `ResolveVariantPath` is `static`, `UFUNCTION(BlueprintPure, Category = "nmg-game-dev|Variants", meta = (DisplayName = "Resolve Variant Path"))`
- [ ] Returns `FSoftObjectPath`, takes `const FSoftObjectPath&`
- [ ] Uses `NMGGAMEDEVRUNTIME_API` export macro on the class
- [ ] `*.generated.h` include is the LAST include in the file
- [ ] Doc comment in header matches AC4/AC5 promise (variant routing + fail-closed on malformed input)

**Notes**: Per FR3. The `BlueprintFunctionLibrary` shape is load-bearing — see Alternative D in design.

### T007: Implement `UNmgAssetResolver::ResolveVariantPath`

**File(s)**: `plugins/nmg-game-dev-ue-plugin/Source/NmgGameDevRuntime/Private/NmgAssetResolver.cpp`
**Type**: Create
**Depends**: T002, T006
**Acceptance**:
- [ ] Implementation follows the 7-step data flow in `design.md` § Data flow — `ResolveVariantPath`
- [ ] Platform branch reads `UGameplayStatics::GetPlatformName()` (NOT `#if PLATFORM_*`)
- [ ] `Windows` / `Mac` / `Linux` → `Desktop` variant
- [ ] `IOS` / `Android` → `Mobile` variant
- [ ] Unknown platform string → `Desktop` variant + `LogNmgGameDev: Warning`
- [ ] Validation per step 5: input rejected if it already contains `/Desktop/` or `/Mobile/`, or has fewer than 3 path segments, or the asset-name segment doesn't match the parent folder name
- [ ] On rejection: emit `LogNmgGameDev: Warning: ResolveVariantPath: input '<path>' does not match parent-path convention; returning unchanged.` and return the input unchanged
- [ ] Function never `check()`s, never crashes, never returns an empty `FSoftObjectPath`
- [ ] No editor-only includes (`#include "Editor.h"`, `#include "UnrealEd.h"`, etc.)

**Notes**: Per FR3 + AC4 + AC5. The validation is what closes AC5 — keep it strict; gameplay-time silent nulls are the failure mode this is designed to prevent.

### T008: Author `NmgAssetResolver.spec.cpp` UE Automation Spec

**File(s)**: `plugins/nmg-game-dev-ue-plugin/Source/NmgGameDevRuntime/Tests/NmgAssetResolver.spec.cpp`
**Type**: Create
**Depends**: T007
**Acceptance**:
- [ ] Uses `BEGIN_DEFINE_SPEC` / `END_DEFINE_SPEC` pattern with test prefix `NmgGameDev.Runtime.AssetResolver`
- [ ] `It("resolves Desktop variant on Windows", ...)` covers AC4 desktop branch (mocks `GetPlatformName` or asserts host-platform behavior on a desktop CI host)
- [ ] `It("resolves Mobile variant on IOS", ...)` covers AC4 mobile branch
- [ ] `It("returns input unchanged on path with /Desktop/ already present", ...)` covers AC5
- [ ] `It("returns input unchanged on path with /Mobile/ already present", ...)` covers AC5
- [ ] `It("returns input unchanged on too-short path", ...)` covers AC5
- [ ] `It("emits a single LogNmgGameDev warning per malformed input", ...)` covers AC5 (uses `AddExpectedError` to validate the warning fires)
- [ ] Tests pass when `Automation RunTests NmgGameDev.Runtime.AssetResolver` is invoked headlessly via `scripts/run-ue-tests.sh`
- [ ] `Tests/` directory exists with the `.spec.cpp` as its only source file at land time

**Notes**: Per FR5. Mocking `GetPlatformName` cleanly is hard in UE Automation — pragmatic compromise is to assert the desktop branch on the host CI machine + cover the mobile branch by passing a path that already mentions a platform context, or by relying on a thin platform-resolver indirection if needed. Implementation can pick either; the test names above describe coverage, not implementation strategy.

---

## Phase 3: Backend — Editor module

### T009: Author `NmgGameDevEditor.Build.cs`

**File(s)**: `plugins/nmg-game-dev-ue-plugin/Source/NmgGameDevEditor/NmgGameDevEditor.Build.cs`
**Type**: Create
**Depends**: T001, T004
**Acceptance**:
- [ ] `PublicDependencyModuleNames` lists `Core`, `CoreUObject`, `Engine`, `NmgGameDevRuntime`
- [ ] `PrivateDependencyModuleNames` lists `UnrealEd`
- [ ] No public dep on `UnrealEd` (per Alternative E rejection in design)
- [ ] `PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs`
- [ ] UBT regenerates project files without complaining about this module

**Notes**: Per FR6. The Runtime → Editor edge is established here.

### T010: Implement `FNmgGameDevEditorModule`

**File(s)**: `plugins/nmg-game-dev-ue-plugin/Source/NmgGameDevEditor/Private/NmgGameDevEditorModule.cpp`
**Type**: Create
**Depends**: T002, T005, T009
**Acceptance**:
- [ ] Implements `IModuleInterface` with `StartupModule()` and `ShutdownModule()` overrides
- [ ] `IMPLEMENT_MODULE(FNmgGameDevEditorModule, NmgGameDevEditor)` macro present
- [ ] `StartupModule` reads `VersionName` (same lookup pattern as T005)
- [ ] Emits exactly one log line matching the format `LogNmgGameDev: Display: NmgGameDevEditor Initialized v<VersionName>`
- [ ] `ShutdownModule` emits a one-line shutdown notice
- [ ] Module body is otherwise empty — no asset-pipeline hooks, no menu entries, no Slate widgets in this issue (those land in subsequent asset-skill issues)

**Notes**: Per FR6. Deliberate skeleton. Resist the temptation to scaffold "future" hook structures — they'll need rewriting when the actual hook semantics arrive.

---

## Phase 4: Integration

### T011: Enable plugin in `fixtures/dogfood.uproject`

**File(s)**: `fixtures/dogfood.uproject`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- [ ] The same file (no rename, no relocation) — `git mv` not used
- [ ] `Plugins` array gets one new entry: `{ "Name": "nmg-game-dev", "Enabled": true }`
- [ ] No other fields modified
- [ ] `find fixtures/ -name '*.uproject'` returns exactly one file
- [ ] `jq '.Plugins[] | select(.Name == "nmg-game-dev")' fixtures/dogfood.uproject` returns the entry
- [ ] `jq -e .` still parses the whole file

**Notes**: Per FR7 + AC7. In-place edit. If UE 5.7 also requires a `Modules` entry pointing at a `.Target.cs` for content-only projects (per the design's open question), add that here as a separate sub-edit and document it in the PR description.

### T012: Author `scripts/run-ue-tests.sh`

**File(s)**: `scripts/run-ue-tests.sh`
**Type**: Create
**Depends**: T003, T008, T011
**Acceptance**:
- [ ] Script header: `#!/usr/bin/env bash` + `set -euo pipefail` (per `steering/tech.md` § Coding Standards Shell)
- [ ] Resolves `UE_ROOT` via env-var override; defaults to `/Users/Shared/Epic Games/UE_5.7`; exits non-zero with a one-line remediation hint if the path doesn't exist
- [ ] Locates `UnrealEditor-Cmd` under `${UE_ROOT}/Engine/Binaries/<Platform>/`
- [ ] Invokes: `UnrealEditor-Cmd <project> -ExecCmds="Automation RunTests NmgGameDev.+; Quit" -unattended -nopause -nullrhi -ReportOutputPath=tests/ue-automation -ReportExportPath=tests/ue-automation/results.xml`
- [ ] `<project>` is the absolute path to `fixtures/dogfood.uproject`
- [ ] Exit code: 0 if every NmgGameDev test passes, non-zero with the failing test name printed to stderr otherwise
- [ ] Writes a JUnit-format report at `tests/ue-automation/results.xml`
- [ ] `shellcheck -S style scripts/run-ue-tests.sh` exits 0
- [ ] Script `chmod +x` (executable bit committed)

**Notes**: Per FR8 + AC6. Backs `gate-ue-automation`. The exit-code translation may need parsing UE's automation summary line if the editor itself returns 0 even when individual tests fail; document any post-process step inline.

---

## Phase 5: BDD Testing (Required)

**Every acceptance criterion MUST have a Gherkin test.**

### T013: Author `feature.gherkin`

**File(s)**: `specs/feature-ue-plugin-skeleton-runtime-editor-mcp-modules/feature.gherkin`
**Type**: Create
**Depends**: T001, T005, T007, T010, T011, T012
**Acceptance**:
- [ ] Every AC from `requirements.md` (AC1–AC8) has a corresponding `Scenario:` block
- [ ] Uses Given/When/Then format
- [ ] Includes the malformed-input scenario from AC5 explicitly
- [ ] Feature title and user story stanza match the requirements user story
- [ ] Valid Gherkin syntax (parses with `pytest-bdd`'s parser if exercised)
- [ ] No scenario references `NmgGameDevMCP`, `/health`, `UE_MCP_PORT`, or any HTTP route — those were removed during requirements review

### T014: Mirror `feature.gherkin` into `tests/bdd/features/`

**File(s)**: `tests/bdd/features/ue_plugin_skeleton.feature`
**Type**: Create
**Depends**: T013
**Acceptance**:
- [ ] File is a copy of `specs/feature-.../feature.gherkin` (or a symlink, per `steering/tech.md` § BDD Testing — design notes "feature.gherkin lands here via symlink or copy")
- [ ] `pytest-bdd` discovers the feature file when run with `pytest tests/bdd/`
- [ ] Step definitions are NOT implemented in this issue — empty stubs are acceptable; the file's purpose here is to make the gate-ue-automation contract reachable from `gate-python-bdd`'s discovery

**Notes**: Step definitions for the integration scenarios (cook isolation, module load) require driving UE from pytest, which is out of scope for this issue's BDD step layer. Stubs let CI surface "not implemented" rather than "no such file." Per `steering/tech.md` § Test Pyramid.

### T015: Verify `gate-ue-automation` end-to-end against the spec tests

**File(s)**: (verification — no file changes)
**Type**: Verify
**Depends**: T008, T012
**Acceptance**:
- [ ] `scripts/run-ue-tests.sh` exits 0 against the spec tests from T008
- [ ] `tests/ue-automation/results.xml` exists and is valid JUnit XML (`xmllint --noout` passes)
- [ ] The JUnit report contains test cases for every `It(...)` in T008's spec
- [ ] Re-running the script after a deliberate edit that breaks one assertion in T008 surfaces a non-zero exit code AND prints the failing test name to stderr (sanity check that failure path works)

**Notes**: This is the smoke test that validates the whole stack works together. If T008's tests pass headless via this script, AC6 is satisfied. Run after T012 lands.

---

## Dependency Graph

```
T001 (.uplugin) ──┬──▶ T004 (Runtime Build.cs) ──┬──▶ T005 (Runtime module) ──┬──▶ T010 (Editor module)
                  │                              │                            │
                  │                              ├──▶ T006 (Resolver header) ─┴──▶ T007 (Resolver impl) ──▶ T008 (Spec tests)
                  │                              │
                  └──▶ T009 (Editor Build.cs) ───┴──▶ T010 (Editor module)
                  │
                  └──▶ T011 (dogfood Plugins array)

T002 (LogNmgGameDev) ──▶ T005, T007, T010    (log channel consumed by every module + resolver)

T003 (tests/ue-automation/.gitkeep) ──▶ T012 (run-ue-tests.sh)

T011 ──▶ T012 (test runner needs the dogfood fixture to enable our plugin)
T008, T011, T012 ──▶ T013 (feature.gherkin) ──▶ T014 (mirror into tests/bdd/features)
T008, T012 ──▶ T015 (verify gate-ue-automation end-to-end)
```

Critical path: `T001 → T004 → T005 → T010 → T011 → T012 → T015`.

---

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #2 | 2026-04-22 | Initial feature spec (revised during requirements review to drop NmgGameDevMCP module — task list reflects two-module scope) |

---

## Validation Checklist

Before moving to IMPLEMENT phase:

- [x] Each task has single responsibility
- [x] Dependencies are correctly mapped
- [x] Tasks can be completed independently (given dependencies)
- [x] Acceptance criteria are verifiable (every AC item is a command or artifact check)
- [x] File paths reference actual project structure (per `steering/structure.md`)
- [x] Test tasks are included for each layer (T008 unit-spec; T013 BDD; T015 end-to-end smoke)
- [x] No circular dependencies (graph above is a DAG)
- [x] Tasks are in logical execution order (`.uplugin` → modules → fixture wiring → test runner → BDD → verify)
- [x] No tasks reference `NmgGameDevMCP`, `/health`, `UE_MCP_PORT`, or any HTTP code (revised scope honored)
