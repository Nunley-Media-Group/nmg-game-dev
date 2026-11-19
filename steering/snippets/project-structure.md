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
│   │   ├── blender_manifest.toml  # Blender extension manifest
│   │   ├── operators/             # bpy operators (cleanup, bake, variants)
│   │   ├── panels/                # UI panels
│   │   ├── contract_core/         # Contract validation and re-import check (headless-safe cores)
│   │   ├── bake_core/             # Authored materials → contract texture sets
│   │   ├── variants_core/         # Cleanup, Mobile variant, Desktop/Mobile .glb export and sidecars
│   │   ├── terrain_core/          # Terrain grid checks, Mobile derivation, chunked .glb export
│   │   ├── rig_core/              # Humanoid rig, landmarks, animation library import
│   │   ├── reduce_core/           # Reduce a generated asset to its Desktop budget
│   │   ├── finalize_core/         # Finalize steps run in background Blender; content hash and load-back
│   │   ├── mcp_server/            # The Blender-side MCP server module
│   │   └── utils/
│   └── nmg-game-dev-godot-addon/
│       └── addons/nmg_game_dev/   # GDScript runtime add-on, copied into game/addons/ by /onboard-consumer
│           ├── plugin.cfg         # Add-on manifest (version = VERSION)
│           ├── plugin.gd          # EditorPlugin: registers the NmgAssets and NmgLaunch autoloads
│           ├── nmg_assets.gd      # NmgAssets.resolve_variant_path: Desktop/Mobile routing
│           ├── nmg_launch.gd      # NmgLaunch: launch options (cmdline / web hash), autoplay signal, test saves, --nmg-shot
│           ├── nmg_variant_scene.gd       # NmgVariantScene: instances a split scene's variant (@tool preview)
│           ├── nmg_mission_definition.gd  # NmgMissionDefinition resource class
│           ├── terrain/           # nmg_terrain.gdshader (four-layer splat)
│           └── tests/             # Headless test runner (run_tests.gd) + test_*.gd; not installed
├── skills/                        # Claude Code skills shipped to consumers
│   ├── model-asset/               # Freeform Blender modeling loop
│   ├── finalize-asset/            # Validate → bake → variants → export → re-import → load back → Godot import
│   ├── design/                    # Design docs → backlog → Godot scaffolds (.tscn / .tres / .gd)
│   ├── ship/                      # Godot export, sign, notarize, package
│   ├── onboard-consumer/          # Installs hooks, Blender add-on, Godot project + add-on, asset contract
│   ├── generate-audio/            # One-take ElevenLabs SFX/music/speech generation → import_audio
│   └── convert-to-godot/          # Migrates an existing consumer from an older engine project
├── hooks/                         # Plugin PreToolUse hooks: model_asset_reminder.py, generate_audio_guard.py (hooks.json)
├── mcp-servers/                   # NMG-authored MCP servers
│   ├── finalize/                  # finalize MCP: finalize_asset, run_finalize_step, get_finalize_job, import_audio, game_screenshot
│   │   ├── pyproject.toml
│   │   ├── tools.json
│   │   └── src/finalize_mcp/
│   ├── meshy/                     # Optional Meshy generation and retexturing
│   └── texture-gen/               # Local texture backends exposed as MCP tools
├── scripts/                       # Bash + Python tooling (session-start, CI, automation)
│   ├── start-blender-mcp.sh       # SessionStart hook — idempotent Blender launcher
│   ├── install-blender-mcp-addon.sh
│   ├── blender/                   # Headless Blender entries: contract_entry.py, finalize_entry.py, finalize_session.py
│   ├── validate-mcp-tools.py      # Runtime of gate-mcp-schema
│   ├── audit-mobile-budgets.py
│   ├── run-blender-tests.sh       # Runtime of gate-blender-headless
│   ├── run-godot-tests.sh         # Runtime of gate-godot-headless
│   ├── sign-macos.sh / notarize-macos.sh
│   └── ship-smoke.sh              # Runtime of gate-ship-smoke
├── src/
│   └── nmg_game_dev/              # Importable Python package (CLI glue, shared utils)
│       ├── __init__.py
│       ├── godot/                 # The only engine boundary: binary, headless runner, probes, project/preset writers
│       │   └── gd/                # GDScript probes run with `godot --headless -s`
│       ├── contract/              # Contract validate / re-import / render CLI, run headless in Blender
│       ├── finalize/              # `python -m nmg_game_dev.finalize` CLI over the finalize pipeline
│       ├── pipeline/              # Finalize orchestrator: steps, cache, job runner, Blender and Godot clients
│       ├── audio/                 # Saved audio → SourceArt/Audio + Godot AudioStream import
│       ├── design/                # Design backlog sync and Godot scaffold writer
│       ├── onboard/               # /onboard-consumer implementation
│       ├── convert/               # /convert-to-godot implementation
│       ├── variants/              # Desktop/Mobile variant path helpers
│       ├── quality/               # Quality gates (contract, re-import, mobile budgets)
│       └── ship/                  # Godot export + sign + notarize + package
├── tests/
│   ├── unit/                      # Pure-Python unit tests
│   ├── bdd/                       # pytest-bdd acceptance tests (.feature + steps)
│   │   ├── features/
│   │   └── steps/
│   ├── blender/                   # Runs under `blender --background --python`
│   ├── godot/                     # Fixture Godot project used by gate-godot-headless and ship-smoke
│   └── e2e/                       # Full pipeline against a fixture consumer project
├── templates/consumer/            # Files /onboard-consumer installs (SessionStart hook settings)
├── docs/
│   ├── onboarding/                # "Install and ship your first game" — consumer-facing
│   ├── skills/                    # Per-skill reference docs
│   ├── mcp/                       # MCP server / tool reference
│   ├── contributing/              # For nmg-game-dev maintainers
│   ├── asset-contract.md          # What "done" means for any generated asset
│   └── design-contract.md         # Design docs, backlog, and scaffold rules
├── specs/                         # nmg-sdlc per-issue specs (one dir per issue)
├── steering/                      # This directory — canonical conventions
├── .mcp.json                      # MCP servers (Blender, finalize, texture-gen, meshy); bundled with the plugin
├── pyproject.toml                 # Python package + dev dependencies
├── VERSION                        # Plain-text semver, managed by /sdlc-open-pr
├── CHANGELOG.md                   # Managed by /sdlc-open-pr
└── CLAUDE.md                      # Entry-point pointer document
```

There is no engine editor plugin and no engine MCP server. Godot runs only as `godot --headless`,
driven from `src/nmg_game_dev/godot/`.

### Finalize locations

| Path | Contents |
|------|----------|
| `plugins/nmg-game-dev-blender-addon/finalize_core/` | Finalize steps run in background Blender: content hash, step runner, and load-back |
| `scripts/blender/finalize_entry.py` | Headless entry for one finalize step, run as `blender --background --python` |
| `scripts/blender/finalize_session.py` | Live-session operations (content hash and load-back) sent through the Blender MCP |
| `mcp-servers/finalize/` | The `finalize` MCP server: `finalize_asset`, `run_finalize_step`, `get_finalize_job` |
| `src/nmg_game_dev/finalize/` | `python -m nmg_game_dev.finalize` CLI over the same implementation |
| `src/nmg_game_dev/pipeline/` | Finalize orchestrator: steps, cache, job runner, Blender and Godot clients |
| `src/nmg_game_dev/godot/` | Godot binary resolution, headless runner, `NMG_RESULT` parsing, `import_godot`, `import_anims`, and terrain scene writing |

### Godot locations

| Path | Contents |
|------|----------|
| `plugins/nmg-game-dev-godot-addon/` | The GDScript runtime add-on (`addons/nmg_game_dev/`) and its headless tests |
| `src/nmg_game_dev/godot/` | The engine boundary: `resolve_godot`, the headless runner, probes, `project.godot` / `export_presets.cfg` writers, and `python -m nmg_game_dev.godot` (`smoke`: the headless autoplay run `/ship` gates on; `shot`: an on-demand windowed game screenshot) |
| `src/nmg_game_dev/convert/` | `python -m nmg_game_dev.convert`, behind `/convert-to-godot` |
| `tests/godot/` | The fixture Godot project that `gate-godot-headless` imports and `ship-smoke.sh` dry-runs |

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
│ Export + re-import    │ ← .glb per variant (+ one per animation clip); headless re-import check
└───────┬───────────────┘
        ▼
┌───────────────────────┐
│ Load back (session)   │ ← baked result replaces the session's <Name> only if it is unchanged since the checkpoint
└───────┬───────────────┘
        ▼
┌───────────────────────┐
│ Godot import          │ ← godot --headless --import + GDScript probe →
│                       │   game/assets/<Category>/<Name>/{Desktop,Mobile}/; Godot generates LODs
└───────────────────────┘

Level composition (placing several assets together) happens afterwards, in Godot.
```

### Ship Flow (build + release)

```
/ship <target>
        │
        ▼
┌───────────────────────┐
│ Pre-export gates      │ ← --import, --check-only on every .gd, game/tests/run_tests.gd,
│                       │   mobile budgets
└───────┬───────────────┘
        ▼
┌───────────────────────┐
│ Godot export          │ ← godot --headless --export-release <preset> (macOS, iOS, Android,
│                       │   Windows locally, Web); presets filter Desktop/ or Mobile/
└───────┬───────────────┘
        ▼
┌───────────────────────┐
│ Sign + notarize       │ ← codesign + Apple Notary (macOS); Android keystore via env
└───────┬───────────────┘
        ▼
┌───────────────────────┐
│ Package artifact      │ ← .app / .ipa / .aab / .exe / web folder → release/ + RELEASE-NOTES.md
└───────────────────────┘
```

### Layer Responsibilities

| Layer | Does | Doesn't Do |
|-------|------|------------|
| Skill entry (`skills/*/SKILL.md`) | Parse invocation, validate env, call the finalize MCP tools or the `python -m nmg_game_dev.*` CLIs | Directly touch MCP sockets, know Godot or Blender internals, encode per-asset-type modeling recipes |
| Pipeline (`src/nmg_game_dev/pipeline/`) | Compose finalize steps; cache on asset content; run long steps in background Blender; enforce ordering | Generate assets from prompts, handle Claude Code I/O, write skill UX |
| Step implementations (`finalize_core/`, `src/nmg_game_dev/godot/`) | Run one finalize step against one tool or core | Compose multi-step flows, cache, or ordering |
| Godot boundary (`src/nmg_game_dev/godot/`) | Resolve the binary, run `godot --headless`, parse probe output, write Godot text resources | Talk to a running editor; nothing in nmg-game-dev bridges to a live Godot editor |
| MCP servers (Blender add-on, texture-gen, finalize, meshy) | Expose tool endpoints; own tool implementation. The finalize server wraps `src/nmg_game_dev/pipeline/` without adding logic. | Know about skills or pipelines upstream |
| Quality gates (`src/nmg_game_dev/quality/`) | Deterministic checks; pass/fail reports with remediation | Generate content; rewrite inputs |
| Ship (`src/nmg_game_dev/ship/`) | Export, sign, notarize, package per platform | Touch content — by the time ship runs, content is frozen |
| Godot runtime add-on (`addons/nmg_game_dev`) | Ships inside consumer games: variant resolver autoload, `NmgLaunch` autoload (launch options, autoplay signal, test save folder, screenshot flag), `NmgVariantScene` (instances a split scene's variant at run time, previews Desktop in the editor), mission resource class, terrain shader | Authoring, importing, or anything editor-only beyond registering its autoload |

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

### GDScript (Godot add-on, probes, scaffolds)

| Element | Convention | Example |
|---------|------------|---------|
| Files | `snake_case.gd` | `nmg_assets.gd`, `probe_asset.gd` |
| `class_name` | `PascalCase`, prefixed `Nmg` for add-on classes | `NmgMissionDefinition` |
| Functions / variables | `snake_case`, statically typed | `resolve_variant_path(path: String) -> String` |
| Constants | `UPPER_SNAKE_CASE` | `MOBILE_FOLDER` |
| Indentation | Tabs | — |
| Tests | `tests/test_*.gd`, methods `test_*`, run by `tests/run_tests.gd` | `test_nmg_assets.gd` |
| Autoload | `PascalCase` singleton name | `NmgAssets` |

### Skills

| Element | Convention | Example |
|---------|------------|---------|
| Skill directory | `kebab-case` | `skills/finalize-asset/` |
| Skill file | `SKILL.md` (uppercase) | `skills/finalize-asset/SKILL.md` |
| Frontmatter `name` | matches directory | `name: finalize-asset` |

### Finalized asset files (consumer projects)

| File | Pattern | Example |
|---|---|---|
| Variant mesh | `<Variant>/<Name>.glb` | `Mobile/Crate.glb` |
| Texture | `T_<Name>_<Part>_<BC\|N\|ORM>.png` (per `docs/asset-contract.md`) | `T_Crate_Body_BC.png` |
| Material variant | `M_<Name>_<Part>_<Variant>.tres` | `M_Crate_Body_Red.tres` |
| Animation clip | `Animations/A_<Name>_<Clip>.glb` | `Animations/A_Guard_Walk.glb` |
| Terrain | `<Variant>/<Name>_Chunk_<row>_<col>.glb` + `<Variant>/<Name>.tscn` | `Desktop/Valley.tscn` |

---

## The split-variant asset convention (applies to consumer projects)

**This rule is inherited from ghost1 and made canonical by nmg-game-dev.**

Desktop and mobile use **separate physical asset variants**, not scaled versions of one asset. This is the single most important structural rule the framework enforces in consumer projects.

- `game/assets/<Category>/<Name>/Desktop/` — full-quality variant (macOS, Windows). Blender structural cleanup only; no decimation, no texture reduction, no bone reduction.
- `game/assets/<Category>/<Name>/Mobile/` — fully optimized variant (iOS, Android, Web). Decimated or rebuilt at lower detail, texture bake-down, materials merged. Satisfies the budget in `docs/asset-contract.md`. Godot generates the LODs of both variants at import time.
- Both variants have **identical logical names** (e.g., `Guard.glb`, `T_Guard_Body_BC.png`). Only the subfolder differs.
- Export preset filters include/exclude per target: the iOS, Android, and Web presets exclude `assets/*/Desktop/*`, and the macOS and Windows presets exclude `assets/*/Mobile/*`. `/onboard-consumer` writes those presets into `game/export_presets.cfg`.
- Assets outside a `Desktop/` or `Mobile/` folder are platform-agnostic and ship on every platform.

### Why split instead of LODs

A single asset with aggressive LODs would still ship the full source mesh in every exported package. Splitting keeps mobile and web downloads small, lets the desktop variant retain hero detail, and makes the boundary auditable through the export filters rather than runtime LOD selection.

### Asset reference rules (consumer gameplay code)

- Gameplay code refers to a split asset by its variant-free path (`res://assets/<Category>/<Name>/<Name>.glb`) and loads it at runtime through `NmgAssets.resolve_variant_path(path)`, from the `addons/nmg_game_dev` add-on. The resolver picks `Mobile/` when the platform has the `mobile` or `web` feature tag, and `Desktop/` otherwise.
- A scene that ships on every platform places a split scene through an `NmgVariantScene` node whose `scene_path` is the variant-free path (`res://assets/<Category>/<Name>/<Name>.tscn`); it instances the variant `NmgAssets` picks when it enters the tree. `/design` writes one for each region's terrain. In the editor it shows the Desktop variant as an unowned preview that is never saved.
- Never `preload()` or hard-link a `Desktop/` or `Mobile/` path from a scene or script that ships on every platform; the export filter would leave a dangling reference.
- Never reference `Mobile/` from `Desktop/`, or vice versa. The folder boundary is the contract.

---

## File Templates

### Skill (`skills/<name>/SKILL.md`)

```markdown
---
name: <kebab-case-name>
description: <one-line description used by Claude Code's skill picker>
required_mcp: [blender, finalize, texture-gen?]
required_env: [GODOT_BIN?, BLENDER_APP?]
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

### GDScript probe (`src/nmg_game_dev/godot/gd/probe_*.gd`)

```gdscript
extends SceneTree


func _initialize() -> void:
	var args: PackedStringArray = OS.get_cmdline_user_args()
	var params: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	var result: Dictionary = {}
	# ... load resources named in params and measure them
	print("NMG_RESULT " + JSON.stringify(result))
	quit(0)
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

### GDScript

```
# 1. @tool / class_name / extends
# 2. signals, enums, constants
# 3. @export and other member variables
# 4. built-in virtual methods (_init, _ready, ...), then public, then private (_leading_underscore) methods
```

---

## Anti-Patterns to Avoid

| Anti-Pattern | Problem | Solution |
|--------------|---------|----------|
| A skill that directly opens MCP sockets | Duplicates logic the pipeline owns; breaks cancellation | Call the finalize MCP tools or `python -m nmg_game_dev.finalize` — never open Blender sockets or run Godot from a SKILL.md flow |
| A live Godot editor bridge or Godot MCP server | Pipeline stages stop being file-based and reproducible | Run Godot headless through `src/nmg_game_dev/godot/`; write Godot text resources directly |
| Desktop asset referenced from the Mobile variant (or vice versa) | Cross-variant leak into exported packages | Load through `NmgAssets.resolve_variant_path`; never hard-link across the boundary |
| Hard-coded Blender / Godot paths in any shipped script | Breaks on every consumer that didn't clone the reference project | Env vars (`BLENDER_BIN`, `GODOT_BIN`) with documented defaults; fail with an actionable message when unset |
| Texture backend called directly instead of through the backend registry | Locks the framework to one model; skips allowlist, hardware, and seamless checks | Go through the texture backend interface (see tech steering) |
| A per-asset-type modeling recipe or skill | Coverage becomes recipe-authoring work; the agent already models freeform | Put rules that apply to every asset in `docs/asset-contract.md`; leave modeling to the agent |
| Composing multi-asset scenes in Blender for export | Assets overlap at the origin and layout gets baked into exports | Export each asset on its own; compose levels in Godot |
| Long Blender work (bakes, variants) run directly through an MCP call | MCP call times out; the session hangs | Run it as a background Blender job and load results back |
| Session-start hook that blocks the shell | Claude Code session never reaches prompt | Scripts must detach with `nohup … & disown` and return in well under the hook timeout |
| Importing Blender add-on modules from pytest without headless mode | Crashes on CI / non-GUI hosts | Always invoke via `blender --background --python` or use the test harness in `tests/blender/` |
| New consumer-facing capability without matching docs update | Drift between what the framework does and what users believe it does | Onboarding + skill-reference doc updates are part of the same PR as the capability |

---

## References

- `CLAUDE.md` — project overview.
- `steering/snippets/project-product.md` — product direction.
- `steering/snippets/project-tech.md` — technical standards, verification gates, session-start contract.
