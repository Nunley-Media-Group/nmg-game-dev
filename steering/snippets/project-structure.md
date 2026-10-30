# nmg-game-dev Code Structure Steering

This document defines code organization, naming conventions, and patterns.
All code should follow these guidelines for consistency.

---

## Project Layout

```
nmg-game-dev/
├── .claude-plugin/
│   └── plugin.json                # Claude Code plugin manifest (what consumers install; version source for nmg-plugins)
├── plugins/
│   ├── nmg-game-dev-blender-addon/
│   │   ├── __init__.py            # bl_info + register/unregister
│   │   ├── operators/             # bpy operators (cleanup, bake, variants)
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
│       │       # Note: the Claude Code → editor MCP wire is owned by VibeUE
│       │       # (third-party UE plugin on Epic's native MCP); nmg-game-dev does
│       │       # NOT ship its own MCP module.
│       ├── Content/               # Plugin-owned UE content (templates, defaults)
│       └── Resources/             # Plugin icon, thumbnails
├── skills/                        # Claude Code skills shipped to consumers
│   ├── finalize-asset/            # Validate → bake → variants → export → re-import → UE import
│   │   ├── SKILL.md               # Skill definition + frontmatter
│   │   └── references/            # Large context files loaded on demand
│   ├── generate-texture/          # Local AI texture models (mflux), agent-callable
│   ├── retarget-animation/
│   ├── build-platform/            # /build-platform per-platform orchestrator
│   ├── ship/                      # Build, sign, notarize, package
│   ├── verify-cook-manifest/      # Runtime of gate-cook-manifest-*
│   ├── audit-mobile-budgets/      # Runtime of gate-mobile-budgets
│   └── onboard-consumer/          # Installs hooks, add-on, UE plugin, asset contract into a consumer
├── mcp-servers/                   # NMG-authored MCP servers (beyond Blender/UE plugin hosts)
│   └── texture-gen/               # Local texture backends exposed as MCP tools
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
│   ├── ship-smoke.sh              # /sdlc-verify-code's gate-ship-smoke backer
│   ├── bump-uproject-version.py
│   └── tests/                     # pytest for the scripts themselves
├── src/
│   └── nmg_game_dev/              # Importable Python package (CLI glue, shared utils)
│       ├── __init__.py
│       ├── cli.py
│       ├── pipeline/              # Finalize steps for an authored asset (Blender → UE)
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
│   └── asset-contract.md          # What "done" means for any generated asset
├── specs/                         # nmg-sdlc per-issue specs (one dir per issue)
├── steering/                      # This directory — canonical conventions
│   ├── product.md
│   ├── tech.md
│   └── structure.md
├── .mcp.json                      # Pinned MCP servers (Blender, Unreal); bundled with the plugin
├── pyproject.toml                 # Python package + dev dependencies
├── VERSION                        # Plain-text semver, managed by /sdlc-open-pr
├── CHANGELOG.md                   # Managed by /sdlc-open-pr
└── CLAUDE.md                      # Entry-point pointer document
```

---

## Layer Architecture

### Authoring and finalize flow

```
Developer asks for an asset in conversation
        │
        ▼
┌───────────────────────┐
│ Freeform authoring    │ ← agent drives Blender MCP; local texture models on request;
│ (interactive)         │   developer directs changes from renders
└───────┬───────────────┘
        ▼  finalize (agent tool or one command; long steps run in background Blender)
┌───────────────────────┐
│ Validate              │ ← asset contract checks (docs/asset-contract.md)
└───────┬───────────────┘
        ▼
┌───────────────────────┐
│ Bake + proof          │ ← any authored material → BC / N / ORM texture sets, proofed in Blender
└───────┬───────────────┘
        ▼
┌───────────────────────┐
│ Variants              │ ← Desktop (quality-preserved) + Mobile (within budget)
└───────┬───────────────┘
        ▼
┌───────────────────────┐
│ Export + re-import    │ ← FBX per variant; headless re-import check against the contract
└───────┬───────────────┘
        ▼
┌───────────────────────┐
│ UE import             │ ← Unreal MCP → Content/<Category>/<Name>/{Desktop,Mobile}/, ORM wired
└───────────────────────┘

Level composition (placing several assets together) happens afterwards, in Unreal.
```

### Ship Flow (build + release)

```
/build-platform <platform>
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
| Skill entry (`skills/*/SKILL.md`) | Parse invocation, validate env, call into `src/nmg_game_dev/pipeline/` | Directly touch MCP sockets, know UE or Blender internals, encode per-asset-type modeling recipes |
| Pipeline (`src/nmg_game_dev/pipeline/`) | Compose finalize steps; cache on asset content; run long steps in background Blender; enforce ordering | Generate assets from prompts, handle Claude Code I/O, write skill UX |
| Stage implementations | Talk to exactly one MCP or one tool | Compose multi-stage flows |
| MCP servers (Blender add-on, VibeUE on Epic's native Unreal MCP, texture-gen) | Expose tool endpoints; own tool implementation. VibeUE is third-party; nmg-game-dev does NOT author the UE-side bridge. | Know about skills or pipelines upstream |
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
| Skill directory | `kebab-case` | `skills/finalize-asset/` |
| Skill file | `SKILL.md` (uppercase) | `skills/finalize-asset/SKILL.md` |
| Frontmatter `name` | matches directory | `name: finalize-asset` |

### UE Asset naming (for plugin-owned content)

| Asset type | Prefix | Example |
|---|---|---|
| Blueprint | `BP_` | `BP_NmgAssetResolver` |
| Master material | `M_` | `M_NmgDefault` |
| Material instance | `MI_` | `MI_NmgDefault_Dark` |
| Texture | `T_<Name>_<Part>_<BC\|N\|ORM>` (per `docs/asset-contract.md`) | `T_NmgLogo_Body_BC` |

Plugin-owned assets live under `plugins/nmg-game-dev-ue-plugin/Content/`. Consumer projects own their own `Content/` and follow the same variant convention described below.

---

## The split-variant asset convention (applies to consumer projects)

**This rule is inherited from ghost1 and made canonical by nmg-game-dev.**

Desktop and mobile use **separate physical asset variants**, not scaled versions of one asset. This is the single most important structural rule the framework enforces in consumer projects.

- `Content/<Category>/<Name>/Desktop/` — full-quality variant (macOS, Windows). Blender structural cleanup only; no decimation, no texture reduction, no bone reduction.
- `Content/<Category>/<Name>/Mobile/` — fully optimized variant (iOS, Android). Decimated or rebuilt at lower detail, LOD chain, texture bake-down, bone reduction. Satisfies the budget in `docs/asset-contract.md`.
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
description: <one-line description used by Claude Code's skill picker>
required_mcp: [blender, unreal, texture-gen?]
required_env: [UE_ROOT?, BLENDER_APP?]
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
| Texture backend called directly instead of through the backend registry | Locks the framework to one model; skips allowlist, hardware, and seamless checks | Go through the texture backend interface (see tech steering) |
| A per-asset-type modeling recipe or skill | Coverage becomes recipe-authoring work; the agent already models freeform | Put rules that apply to every asset in `docs/asset-contract.md`; leave modeling to the agent |
| Composing multi-asset scenes in Blender for export | Assets overlap at the origin and layout gets baked into exports | Export each asset on its own; compose levels in Unreal |
| Long Blender work (bakes, variants) run directly through an MCP call | MCP call times out; the session hangs | Run it as a background Blender job and load results back |
| Session-start hook that blocks the shell | Claude Code session never reaches prompt | Scripts must detach with `nohup … & disown` and return in well under the hook timeout |
| Importing Blender add-on modules from pytest without headless mode | Crashes on CI / non-GUI hosts | Always invoke via `blender --background --python` or use the test harness in `tests/blender/` |
| New consumer-facing capability without matching docs update | Drift between what the framework does and what users believe it does | Onboarding + skill-reference doc updates are part of the same PR as the capability |

---

## References

- `CLAUDE.md` — project overview (added when scaffolding lands).
- `steering/product.md` — product direction.
- `steering/tech.md` — technical standards, verification gates, session-start contract.
