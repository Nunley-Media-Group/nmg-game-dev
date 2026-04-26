# nmg-game-dev Code Structure Steering

This document defines code organization, naming conventions, and patterns.
All code should follow these guidelines for consistency.

---

## Project Layout

```
nmg-game-dev/
├── .codex-plugin/
│   └── plugin.json                # Codex plugin manifest (what consumers install)
├── plugins/
│   ├── nmg-game-dev-blender-addon/
│   │   ├── __init__.py            # bl_info + register/unregister
│   │   ├── operators/             # bpy operators (generate, cleanup, optimize)
│   │   ├── panels/                # UI panels
│   │   ├── mcp_server/            # The Blender-side MCP server module
│   │   └── utils/
│   └── nmg-game-dev-ue-plugin/
│       ├── nmg-game-dev.uplugin   # UE plugin manifest
│       ├── Source/
│       │   ├── NmgGameDevRuntime/ # Runtime module — ships inside consumer games
│       │   │   ├── Public/
│       │   │   ├── Private/
│       │   │   └── Tests/         # *.spec.cpp UE Automation tests
│       │   └── NmgGameDevEditor/  # Editor-only module — NOT shipped in game builds
│       │       ├── Public/
│       │       ├── Private/
│       │       └── Tests/
│       │       # Note: the Codex → editor MCP wire is owned by VibeUE
│       │       # (third-party UE plugin pinned in `.mcp.json`); nmg-game-dev does
│       │       # NOT ship its own MCP module.
│       ├── Content/               # Plugin-owned UE content (templates, defaults)
│       └── Resources/             # Plugin icon, thumbnails
├── skills/                        # Codex skills shipped to consumers
│   ├── new-character/
│   │   ├── SKILL.md               # Skill definition + frontmatter
│   │   └── references/            # Large context files loaded on demand
│   ├── new-prop/
│   ├── cleanup-asset-desktop/
│   ├── optimize-asset-for-mobile/
│   ├── retarget-animation/
│   ├── dress-level/
│   ├── generate-texture/          # Driven by the TBD texture-gen tool
│   ├── build-platform/            # $build-platform per-platform orchestrator
│   ├── sign-and-notarize/         # macOS + iOS signing
│   ├── verify-cook-manifest/      # Runtime of gate-cook-manifest-*
│   ├── audit-mobile-budgets/      # Runtime of gate-mobile-budgets
│   ├── onboard-consumer/          # Installs hooks + configs into consumer project
│   └── spec-to-assets/            # Bridge from $nmg-sdlc:write-code (nmg-sdlc) into asset skills
├── mcp-servers/                   # NMG-authored MCP servers (beyond Blender/UE plugin hosts)
│   └── texture-gen/               # Wraps whichever tool the v1 spike picks
│       ├── pyproject.toml
│       └── src/
├── scripts/                       # Bash + Python tooling (session-start, CI, automation)
│   ├── start-blender-mcp.sh       # SessionStart hook — idempotent Blender launcher
│   ├── start-unreal-mcp.sh        # SessionStart hook — idempotent UE Editor launcher
│   ├── validate-skills.py         # Runtime of gate-skill-schema
│   ├── validate-mcp-tools.py      # Runtime of gate-mcp-schema
│   ├── audit-mobile-budgets.py
│   ├── verify-cook-manifest.sh
│   ├── run-blender-tests.sh
│   ├── run-ue-tests.sh
│   ├── ship-smoke.sh              # $nmg-sdlc:verify-code's gate-ship-smoke backer
│   ├── bump-uproject-version.py
│   └── tests/                     # pytest for the scripts themselves
├── src/
│   └── nmg_game_dev/              # Importable Python package (CLI glue, shared utils)
│       ├── __init__.py
│       ├── cli.py
│       ├── pipeline/              # Pipeline stage composition (Blender → UE, Meshy → Blender → UE)
│       ├── variants/              # Desktop/Mobile variant helpers
│       ├── quality/               # Quality gate implementations
│       └── ship/                  # Build + sign + notarize + package
├── tests/
│   ├── unit/                      # Pure-Python unit tests
│   ├── bdd/                       # pytest-bdd acceptance tests (.feature + steps)
│   │   ├── features/
│   │   └── steps/
│   ├── blender/                   # Runs under `blender --background --python`
│   └── e2e/                       # Full pipeline against a fixture consumer project
│       └── fixtures/
├── docs/
│   ├── onboarding/                # "Install and ship your first game" — consumer-facing
│   ├── skills/                    # Per-skill reference docs
│   ├── mcp/                       # MCP server / tool reference
│   ├── contributing/              # For nmg-game-dev maintainers
│   └── decisions/                 # ADRs for non-obvious architectural choices
├── specs/                         # nmg-sdlc per-issue specs (one dir per issue)
├── steering/                      # This directory — canonical conventions
│   ├── product.md
│   ├── tech.md
│   └── structure.md
├── .mcp.json                      # Pinned MCP server config (Blender, Unreal, Meshy, texture-gen)
├── pyproject.toml                 # Python package + dev dependencies
├── VERSION                        # Plain-text semver, managed by $nmg-sdlc:open-pr
├── CHANGELOG.md                   # Managed by $nmg-sdlc:open-pr
└── AGENTS.md                      # Entry-point pointer document
```

---

## Layer Architecture

### Pipeline Flow (authoring — invoked by a skill)

```
Developer prompt (e.g., $new-prop Weapons/Katana standard "...")
        │
        ▼
┌───────────────────────┐
│ Skill entry           │ ← resolves args, validates env, picks source (Blender-first or Meshy)
└───────┬───────────────┘
        ▼
┌───────────────────────┐
│ Generation stage      │ ← Blender MCP (primary) or Meshy MCP (supplement) → 3D mesh
└───────┬───────────────┘
        ▼
┌───────────────────────┐
│ Texture stage         │ ← texture-gen tool (TBD) → PBR channel maps
└───────┬───────────────┘
        ▼
┌───────────────────────┐
│ Cleanup stage         │ ← Blender MCP → structural cleanup, LOD chain seeding
└───────┬───────────────┘
        ▼
┌───────────────────────┐
│ Variant stage         │ ← Blender MCP → desktop (quality-preserved) + mobile (optimized) outputs
└───────┬───────────────┘
        ▼
┌───────────────────────┐
│ Quality gate          │ ← budgets check, texture resolution check, manifest prep
└───────┬───────────────┘
        ▼
┌───────────────────────┐
│ Import stage          │ ← Unreal MCP → UE asset imports into Content/Category/Name/{Desktop,Mobile}/
└───────────────────────┘
```

### Ship Flow (build + release)

```
$build-platform <platform>
        │
        ▼
┌───────────────────────┐
│ Pre-ship gates        │ ← cook manifest, mobile budgets, UE Automation tests
└───────┬───────────────┘
        ▼
┌───────────────────────┐
│ UE package stage      │ ← UAT / UBT per target
└───────┬───────────────┘
        ▼
┌───────────────────────┐
│ Sign stage            │ ← codesign (macOS/iOS), apksigner (Android), signtool (Windows)
└───────┬───────────────┘
        ▼
┌───────────────────────┐
│ Notarize stage        │ ← Apple Notary (macOS/iOS only)
└───────┬───────────────┘
        ▼
┌───────────────────────┐
│ Package artifact      │ ← .ipa / .aab / .app / .exe → release/ directory
└───────────────────────┘
```

### Layer Responsibilities

| Layer | Does | Doesn't Do |
|-------|------|------------|
| Skill entry (`skills/*/SKILL.md`) | Parse invocation, validate env, call into `src/nmg_game_dev/pipeline/` | Directly touch MCP sockets, know UE or Blender internals |
| Pipeline (`src/nmg_game_dev/pipeline/`) | Compose stages; cache intermediate artifacts; enforce ordering | Handle Codex I/O, write skill UX |
| Stage implementations | Talk to exactly one MCP or one tool | Compose multi-stage flows |
| MCP servers (Blender add-on, VibeUE editor plugin, texture-gen) | Expose tool endpoints; own tool implementation. VibeUE is third-party; nmg-game-dev does NOT author the UE-side bridge. | Know about skills or pipelines upstream |
| Quality gates (`src/nmg_game_dev/quality/`) | Deterministic checks; pass/fail reports with remediation | Generate content; rewrite inputs |
| Ship (`src/nmg_game_dev/ship/`) | Build, sign, notarize, package per platform | Touch content — by the time ship runs, content is frozen |
| UE Runtime module | Ship inside consumer games; variant-aware asset resolvers; perf-critical helpers | Anything editor-only; anything authoring |
| UE Editor module | Editor-time helpers; import pipelines | Ship inside cooked game content; bind any HTTP bridge (VibeUE owns that) |

---

## Naming Conventions

### Python

| Element | Convention | Example |
|---------|------------|---------|
| Modules / files | `snake_case.py` | `pipeline/variant_split.py` |
| Classes | `PascalCase` | `VariantRouter`, `QualityGate` |
| Functions / methods | `snake_case` | `run_pipeline`, `apply_budget_gate` |
| Constants | `UPPER_SNAKE_CASE` | `DEFAULT_MOBILE_BUDGET` |
| Type aliases | `PascalCase` | `VariantKind = Literal["desktop", "mobile"]` |
| Private helpers | `_leading_underscore` | `_resolve_blender_bin()` |

### Blender add-on

| Element | Convention | Example |
|---------|------------|---------|
| Operator `bl_idname` | `nmggamedev.verb_noun` | `nmggamedev.cleanup_desktop` |
| Panel `bl_idname` | `NMGGAMEDEV_PT_panel_name` | `NMGGAMEDEV_PT_main_panel` |
| Property group classes | `NmgGameDev<Name>Props` | `NmgGameDevPipelineProps` |

### UE C++

| Element | Convention | Example |
|---------|------------|---------|
| Module directory | `PascalCase` under `Source/` | `NmgGameDevRuntime` |
| Runtime class | `FName`/`UName`/`AName`/`SName` per UE convention | `UNmgAssetResolver`, `FNmgVariantContext` |
| Editor class | Prefix with `FNmg<Editor>` | `FNmgImportPipeline` |
| Public header | `NmgGameDev/Public/*.h` | `Public/NmgAssetResolver.h` |
| Test spec | `*.spec.cpp` in `Tests/` | `Tests/NmgAssetResolver.spec.cpp` |

### Skills

| Element | Convention | Example |
|---------|------------|---------|
| Skill directory | `kebab-case` | `skills/new-character/` |
| Skill file | `SKILL.md` (uppercase) | `skills/new-character/SKILL.md` |
| Frontmatter `name` | matches directory | `name: new-character` |

### UE Asset naming (for plugin-owned content)

| Asset type | Prefix | Example |
|---|---|---|
| Blueprint | `BP_` | `BP_NmgAssetResolver` |
| Master material | `M_` | `M_NmgDefault` |
| Material instance | `MI_` | `MI_NmgDefault_Dark` |
| Texture | `T_<Name>_<Type>` | `T_NmgLogo_BaseColor` |

Plugin-owned assets live under `plugins/nmg-game-dev-ue-plugin/Content/`. Consumer projects own their own `Content/` and follow the same variant convention described below.

---

## The split-variant asset convention (applies to consumer projects)

**This rule is inherited from ghost1 and made canonical by nmg-game-dev.**

Desktop and mobile use **separate physical asset variants**, not scaled versions of one asset. This is the single most important structural rule the framework enforces in consumer projects.

- `Content/<Category>/<Name>/Desktop/` — full-quality variant (macOS, Windows). Blender structural cleanup only; no decimation, no texture reduction, no bone reduction.
- `Content/<Category>/<Name>/Mobile/` — fully optimized variant (iOS, Android). Decimation, LOD chain, texture bake-down, bone reduction. Satisfies the budget JSON.
- Both variants have **identical logical names** (e.g., `SK_Guard`, `M_Guard`). Only the subfolder differs.
- Asset Manager cook rules (per-platform INIs) include/exclude per target. Desktop packages never contain `Mobile/`; mobile packages never contain `Desktop/`. `gate-cook-manifest-*` is the hard gate.
- `Content/Shared/` is platform-agnostic — ships on every platform.

### Why split instead of LODs

A single asset with aggressive LODs would still ship the full source mesh in every cooked package. Splitting keeps mobile downloads small, lets the desktop variant retain hero detail, and makes the boundary auditable via cook manifests rather than runtime LOD selection.

### Asset reference rules (consumer gameplay code)

- Gameplay code uses soft references (`TSoftObjectPtr`, `TSoftClassPtr`) for any asset that has a Desktop/Mobile split.
- A parent Blueprint one level above the variant folder uses a platform-aware resolver (`UNmgAssetResolver`, shipped by the nmg-game-dev UE runtime module) to pick the right variant at runtime.
- Never reference `Mobile/` from `Desktop/`, or vice versa. The folder boundary is the contract.

---

## File Templates

### Skill (`skills/<name>/SKILL.md`)

```markdown
---
name: <kebab-case-name>
description: <one-line description used by Codex's skill picker>
required_mcp: [blender, unreal, meshy?, texture-gen?]
required_env: [UE_ROOT?, MESHY_API_KEY?]
unattended_safe: true | false
---

# <Human-readable Title>

<One-paragraph what this skill does and when to reach for it.>

## Flow

1. ...
2. ...

## Failure modes and remediation

- <condition> → <remediation prompt>

## Test fixtures

- <path to e2e fixture this skill is validated against>
```

### Blender operator (`plugins/nmg-game-dev-blender-addon/operators/*.py`)

```python
from __future__ import annotations

import bpy


class NMGGAMEDEV_OT_cleanup_desktop(bpy.types.Operator):
    bl_idname = "nmggamedev.cleanup_desktop"
    bl_label = "Clean up for Desktop variant"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: bpy.types.Context) -> set[str]:
        # ... structural cleanup, zero quality reduction
        return {"FINISHED"}
```

### UE runtime class (`plugins/nmg-game-dev-ue-plugin/Source/NmgGameDevRuntime/Public/NmgAssetResolver.h`)

```cpp
#pragma once

#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "NmgAssetResolver.generated.h"

UCLASS(BlueprintType)
class NMGGAMEDEVRUNTIME_API UNmgAssetResolver : public UObject
{
    GENERATED_BODY()

public:
    // Returns the variant path (Desktop/ or Mobile/) appropriate for the current platform.
    UFUNCTION(BlueprintCallable, Category = "nmg-game-dev")
    static FSoftObjectPath ResolveVariantPath(const FSoftObjectPath& ParentPath);
};
```

---

## Import Order

### Python

```
# 1. Standard library
# 2. Third-party (bpy, pytest, etc.)
# 3. nmg_game_dev internal modules
# 4. Type-only imports (under `if TYPE_CHECKING:`)
```

### UE C++

```
// 1. Module's own Public headers
// 2. CoreMinimal + other engine
// 3. Same-module Private headers
// 4. Third-party
// 5. Generated .h MUST be last
```

---

## Anti-Patterns to Avoid

| Anti-Pattern | Problem | Solution |
|--------------|---------|----------|
| A skill that directly opens MCP sockets | Duplicates logic the pipeline owns; breaks cancellation | Call into `src/nmg_game_dev/pipeline/` — never speak MCP from a SKILL.md flow |
| Desktop asset referenced from the Mobile variant (or vice versa) | Cross-variant leak into cooked packages | Use `UNmgAssetResolver` parent Blueprint; never hard-link across the boundary |
| Hard-coded Blender / UE paths in any shipped script | Breaks on every consumer that didn't clone the reference project | Env vars with documented defaults; fail with an actionable message when unset |
| Texture-gen tool accessed outside the TBD contract interface | Locks the framework to one tool, prevents the spike outcome from landing cleanly | Always go through `src/nmg_game_dev/pipeline/texture.py`'s abstract interface |
| Session-start hook that blocks the shell | Codex session never reaches prompt | Scripts must detach with `nohup … & disown` and return in well under the hook timeout |
| Importing Blender add-on modules from pytest without headless mode | Crashes on CI / non-GUI hosts | Always invoke via `blender --background --python` or use the test harness in `tests/blender/` |
| New consumer-facing capability without matching docs update | Drift between what the framework does and what users believe it does | Onboarding + skill-reference doc updates are part of the same PR as the capability |

---

## References

- `AGENTS.md` — project overview (added when scaffolding lands).
- `steering/product.md` — product direction.
- `steering/tech.md` — technical standards, verification gates, session-start contract.
