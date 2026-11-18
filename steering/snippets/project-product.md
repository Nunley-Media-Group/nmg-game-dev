# nmg-game-dev Product Steering

This document defines the product vision, target users, and success metrics.
All feature development should align with these guidelines.

---

## Mission

**nmg-game-dev is an opinionated, Blender-first content pipeline for Godot 4 games used by the Nunley Media Group game team to turn assets authored in Blender into production-ready Godot assets through Claude Code-orchestrated, free-flow ad-hoc workflows that enforce quality without sacrificing iteration speed — and it is also the delivery vehicle used to ship full games to players.**

The framework wears two hats:

- **As internal tooling** — an authoring-time pipeline that powers how NMG builds the content inside every game.
- **As a delivery platform** — the Godot runtime add-on, skill suite, and ship skill are what take an NMG game from repo to signed, notarized, store-ready builds on every supported platform.

It is consumed as:

1. A **Claude Code plugin** — skills, MCP servers, and tools that wrap the full game-dev loop: asset authoring, finalizing, import, build, sign, ship.
2. A **Blender add-on** — authoring-side tooling for cleanup, baking, and Desktop/Mobile variants.
3. A **Godot add-on** (`addons/nmg_game_dev`) — GDScript runtime helpers that ship inside the consumer's game: the `NmgAssets` variant resolver, the `NmgMissionDefinition` resource, and the terrain shader. Godot is the engine; every engine stage runs `godot --headless`, with no live editor bridge.

The headline capability: **the developer and Claude author an asset freeform in Blender through the Blender MCP, iterating from renders; local AI texture models supply realistic materials; and deterministic tooling makes the finished asset shippable** — validated against the asset contract (`docs/asset-contract.md`), baked, split into Desktop and Mobile variants, exported, and imported into Godot with `godot --headless`. There is no recipe library: any asset type can be attempted on day one. That capability is embedded in a framework that takes those assets all the way to a shipping game.

---

## Target Users

### Primary: Internal NMG game developer

| Characteristic | Implication |
|----------------|-------------|
| Works inside Claude Code day-to-day; prefers adhoc skills over multi-step SDLC ceremony for creative work | Expose capability as short, focused skills; keep heavyweight spec cycles optional, not required |
| Fluent in Godot + Blender, comfortable with Python and GDScript; mixed comfort with MCP server authoring | Skill UX must abstract MCP plumbing; skill authors use nmg-sdlc internally when building new skills |
| Iterates on asset quality visually — directs changes in conversation, reviews renders, reimports | Agent-callable tools for each step; idempotent finalize steps cached on asset content; re-entry at any step |
| Ships to multiple platforms (desktop + mobile) per consumer project | Variant-aware from the authoring step; never require a retrofit pass to add a mobile variant |

### Secondary: Consumer project maintainer (e.g., ghost1)

| Characteristic | Implication |
|----------------|-------------|
| Adopts nmg-game-dev as an upstream dependency; expects clean install + upgrade path | Semver discipline; CHANGELOG with BREAKING markers; onboarding doc that gets a new project productive in under an hour |
| May not touch the framework source themselves — only the skills it exposes | Stable skill surface; deprecation windows on renames; consumer-facing docs separate from internals |
| Needs the framework to take their game all the way to store-ready builds | Build / sign / notarize / package skills are first-class framework features, not per-project reinventions |

### Tertiary: End-user players (of games built on nmg-game-dev)

| Characteristic | Implication |
|----------------|-------------|
| Never interact with the framework directly, only the games it ships | Anything that ends up in a shipped build (runtime add-on code, loaded assets) must meet player-facing quality, performance, and stability bars |
| Play on desktop (macOS/Windows) and mobile (iOS/Android) | Shipped add-on code must pass `--check-only` and run on every target; variant routing must never ship the wrong variant to a device |

---

## Core Value Proposition

1. **Freeform authoring, contract-checked output** — Claude models any asset freeform in Blender, with no per-asset-type recipes; the asset contract and its tooling make every result game-ready. No paid generation service required.
2. **Creative freedom with quality gates** — adhoc iteration is the default path; quality (polycount, texture budgets, manifest correctness, player-facing perf) is enforced automatically, not by human review.
3. **Drop-in plugin shape** — a consumer project installs `nmg-game-dev` from the `nmg-plugins` marketplace, installs the Blender add-on and the Godot add-on (through `/onboard-consumer`), and immediately has the full skill suite available. Onboarding is a first-class deliverable, not an afterthought.
4. **Claude Code-native orchestration** — every pipeline stage and every ship step is addressable by a skill or MCP tool. The developer's interface is chat + natural language, not a bespoke CLI.
5. **Repo to store-ready in one framework** — generate content, build per platform, sign, notarize, package. The same framework that creates the assets also delivers the game.

---

## Product Principles

| Principle | Description |
|-----------|-------------|
| Blender is the authoring surface; Godot is the composition surface | Assets are built and proofed in Blender, one at a time. Levels and multi-asset scenes are composed in Godot, never in Blender. |
| Define the target, not the method | The asset contract says what "done" means; how an asset is modeled is the agent's call. Rules must apply to every asset type, never one. |
| Adhoc by default, ceremony when you need it | Short skills for 90% of creative work. Formal spec cycles for architectural changes or consumer-facing API. |
| Quality is automatic or it doesn't exist | Every asset-producing skill ends with a verification gate. No "we'll check it later." |
| Variants are first-class, not an afterthought | Desktop and Mobile are produced in the same session that authors the asset. No retrofit pass. |
| Idempotent, resumable, cacheable | Any finalize step can be rerun without redoing upstream work; caches key on asset content. Long steps run in background Blender so MCP calls never time out. |
| Onboarding parity with core capability | Every new consumer-facing feature ships with updated onboarding docs in the same PR. |

---

## Success Metrics

| Metric | Target | Why It Matters |
|--------|--------|----------------|
| Contract compliance on first finalize | ≥ 90% of authored assets pass validation and re-import without manual fixes | The contract and tooling, not the developer, make assets shippable |
| Time from "asset approved in Blender" → Godot-imported Desktop + Mobile variants | ≤ 5 min for a hero asset; ≤ 90 s for a standard prop on an M-series Mac | Adhoc workflow is only useful if the iteration loop is fast |
| Consumer onboarding time (new NMG project to first generated asset) | ≤ 1 hour from clone to imported asset | Lock-in risk is real; make the framework easy to adopt, easy to leave |
| Skill suite coverage | 100% of ghost1's current bespoke asset workflow replaced by nmg-game-dev skills | ghost1 is the reference consumer; if nmg-game-dev can't host its pipeline, it doesn't work |
| Quality gate coverage | Every asset-producing skill has an automated verification gate | No manual QA in the happy path |

---

## Feature Prioritization

The user elected "everything in v1" — no deferral to a v2 milestone. Priorities below are ordering guidance inside v1, not deferral buckets.

### v1 — Everything

- **MCP + skill scaffolding** — the plugin shell and MCP server wiring for Blender (Blender MCP) and the finalize, texture-gen, and meshy servers. Godot is driven headless; there is no engine MCP server.
- **Asset contract + finalize pipeline** — freeform authoring in Blender, then validate → bake → Desktop/Mobile variants → export → re-import check → Godot import, each step also callable by the agent.
- **Optional Meshy source** — opt-in and paid: text, reference-image, or combined generation and retexture through the `meshy` MCP, used only when a Meshy API key is in the project's git-ignored `.env`. Its results enter the same Blender collection contract as local work.
- **Optional audio import** — sound effects and music a developer generates with the official ElevenLabs MCP server are stored as WAV under `SourceArt/Audio/` and imported into Godot (`AudioStreamWAV` for effects, Ogg Vorbis `AudioStreamOggVorbis` for music) through `import_audio`. No ElevenLabs key or API client ships with the framework.
- **Texture generation** — local AI texture models (Z-Image Turbo, FLUX.2 klein 4B via mflux) the agent calls while authoring; procedural Blender materials as the fallback; everything baked to contract texture sets and proofed in Blender.
- **Godot add-on** — runtime capability (variant routing, mission definitions, terrain shading) that ships inside the consumer's game, installed into `game/addons/nmg_game_dev/`.
- **`/convert-to-godot`** — migrates an existing consumer project to Godot in one command: it onboards the Godot project, re-finalizes every asset from its Blender source, re-imports audio, re-scaffolds the design backlog, and writes a conversion report. See `docs/skills/convert-to-godot.md`.
- **Blender add-on** — authoring-side capability (generation, cleanup, mobile optimization).
- **Quality gates** — polycount, texture budget, export-filter variant split, runtime perf bars for shipped content.
- **Build + ship skills** — per-platform builds (macOS, Windows, iOS, Android), code signing, macOS notarization, store-ready packaging. This is how NMG games get to players.
- **Onboarding + documentation** — consumer-facing docs; "install and generate your first asset in under an hour" path; "ship your first build" path.

### Won't Have (Now)

- Console-specific tooling paths (PlayStation / Xbox / Switch) — not a v1 target.
- Runtime (play-time) asset generation — generation is authoring-time; what ships is pre-baked.
- Any cloud-hosted or paid generation service other than the optional Meshy source — generation is local by default: Blender plus local models. nmg-game-dev ships no ElevenLabs integration; a developer may run the official ElevenLabs MCP server themselves, and nmg-game-dev imports the audio it saves.
- A per-asset-type recipe library — the agent authors freeform; the contract defines the target.
- Composing levels or multi-asset scenes in Blender — that happens in Godot.
- A bespoke launcher / storefront — we ship to Apple / Google / (direct download for desktop), not our own distribution.

---

## Key User Journeys

### Journey 1: Internal dev authors an asset

```
1. Developer and Claude author an asset freeform in Blender, in a session in the consumer project, through the Blender MCP; local texture models supply materials when the developer asks for them
2. The developer directs changes from renders until the asset is finished
3. Claude finalizes the collection: validate against the asset contract → bake → Desktop/Mobile variants → export → re-import check → load back into the session → headless Godot import
4. Developer sees both variants under game/assets/Props/Crate/{Desktop,Mobile}/; any failed check stops the run with a remediation
```

### Journey 2: Internal dev composes a level

```
1. Developer authors several assets (a race car, a track, grandstands); each is finalized as its own deliverable
2. `/design` scaffolds the region's `.tscn`; Claude places the finalized assets in it, and the developer reviews it in Godot
```

### Journey 3: Consumer adopts nmg-game-dev in a new project

```
1. Install the plugin from the nmg-plugins marketplace; run `/onboard-consumer` in the consumer project
2. Onboarding creates `game/project.godot`, installs the Godot add-on, export presets, the Blender add-on, the Blender session-start hook, and the asset contract; offers the optional local texture models; asks for no API keys
3. The first finalized asset reaches Godot as Desktop + Mobile variants
4. Consumer's first commit includes only their new content — no framework bootstrap noise
```

### Journey 4: Ship a build to players

```
1. Developer invokes `/ship mobile` (or desktop, web, or all)
2. nmg-game-dev runs the script, test, and budget gates, then Godot export per preset → code signing → notarization (macOS)
3. Output is a store-ready artifact: .ipa / .aab / .app / .exe, or a web folder
4. Quality gates block the ship if any fail; failures surface the remediation prompt, not a raw log
```

---

## Brand Voice

| Attribute | Do | Don't |
|-----------|-----|-------|
| Opinionated | "Assets are authored in Blender and composed in Godot." | "Use whichever tool you like." |
| Honest about quality | "Character anatomy is still weak — tracked in #N." | "The framework produces production-ready assets across all categories." |
| Workflow-first | Lead docs with a flow, not an API reference. | Lead docs with a module graph. |

---

## Privacy Commitment

| Data | Usage | Shared |
|------|-------|--------|
| Developer conversation (asset notes and direction) | Used by Claude in the session and by local texture models | Only with Anthropic as part of the Claude Code session; texture models run locally |
| Generated assets | Written locally to the consumer project | Not shared by the framework |
| API keys + signing credentials | Read from env; never logged; never committed; never shipped inside a game binary | Never |
| Telemetry / player data (if a shipped game collects any) | Out of scope for the framework; consumer projects own their own privacy policy | N/A at framework level |

---

## Decision log

Track major product pivots here as they happen.

<!--
### 2026-04-22 — v1 includes everything; no v2 milestone seeded
Why: user directive during /onboard-project. Scope is broad but the framework is
small enough that splitting v1/v2 would fragment work rather than focus it.

### 2026-04-22 — nmg-sdlc used for nmg-game-dev itself
Why: this is a library, not a game. SDLC ceremony is appropriate for building the
framework; the adhoc-first workflow is what the framework SHIPS to consumers,
not how it's built.
-->

---

## References

- Technical spec: `steering/tech.md`
- Code structure: `steering/structure.md`
