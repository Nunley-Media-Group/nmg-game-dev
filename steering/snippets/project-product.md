# nmg-game-dev Product Steering

This document defines the product vision, target users, and success metrics.
All feature development should align with these guidelines.

---

## Mission

**nmg-game-dev is an opinionated, Blender-first content-generation framework for Unreal Engine games used by the Nunley Media Group game team to turn creative intent into production-ready UE assets through Codex-orchestrated, free-flow ad-hoc workflows that enforce quality without sacrificing iteration speed — and it is also the delivery vehicle used to ship full games to players.**

The framework wears two hats:

- **As internal tooling** — an authoring-time pipeline that powers how NMG builds the content inside every game.
- **As a delivery platform** — the UE plugin, skill suite, and build/ship skills are what take an NMG game from repo to signed, notarized, store-ready builds on every supported platform.

It is consumed as:

1. A **Codex plugin** — skills that wrap the full game-dev loop: asset generation, level dressing, build, sign, ship.
2. A **Blender add-on** — authoring-side tooling for generation, cleanup, and optimization.
3. An **Unreal Engine plugin** — editor-side tooling for import, retarget, platform-variant handling, and runtime helpers that ship inside the consumer's game.

The headline capability: **Blender, driven by MCP and a texture-design tool (TBD in v1), produces assets at or above the quality of Meshy.io's text-to-3D output** — with Meshy kept as a supplementary fallback when its strengths are the right tool for the job. That capability is embedded in a framework that takes those assets all the way to a shipping game.

---

## Target Users

### Primary: Internal NMG game developer

| Characteristic | Implication |
|----------------|-------------|
| Works inside Codex day-to-day; prefers adhoc skills over multi-step SDLC ceremony for creative work | Expose capability as short, focused skills; keep heavyweight spec cycles optional, not required |
| Fluent in Unreal Engine + Blender, comfortable with Python; mixed comfort with MCP server authoring | Skill UX must abstract MCP plumbing; skill authors use nmg-sdlc internally when building new skills |
| Iterates on asset quality visually — reruns generation, tweaks prompts, reimports | Idempotent pipeline stages; fast cache of intermediate artifacts; re-entry at any stage |
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
| Never interact with the framework directly, only the games it ships | Anything that ends up in a shipped build (runtime UE plugin code, loaded assets) must meet player-facing quality, performance, and stability bars |
| Play on desktop (macOS/Windows) and mobile (iOS/Android) | Shipped UE plugin code must compile cleanly for every target; variant routing must never ship the wrong variant to a device |

---

## Core Value Proposition

1. **Blender-first, Meshy-capable** — the framework gets Blender to Meshy-parity (or better) for text-to-3D + texture, and still lets Meshy step in when its strengths apply (fast ideation, niche categories). No lock-in to either source.
2. **Creative freedom with quality gates** — adhoc iteration is the default path; quality (polycount, texture budgets, manifest correctness, player-facing perf) is enforced automatically, not by human review.
3. **Drop-in plugin shape** — a consumer project installs `nmg-game-dev` from a Codex plugin marketplace or this repo, installs the Blender add-on and UE plugin, and immediately has the full skill suite available. Onboarding is a first-class deliverable, not an afterthought.
4. **Codex-native orchestration** — every pipeline stage and every ship step is addressable by a skill or MCP tool. The developer's interface is chat + natural language, not a bespoke CLI.
5. **Repo to store-ready in one framework** — generate content, build per platform, sign, notarize, package. The same framework that creates the assets also delivers the game.

---

## Product Principles

| Principle | Description |
|-----------|-------------|
| Blender is the primary authoring surface | New capability lands in Blender first; Meshy is a supplement. When forced to choose, invest in Blender tooling. |
| Adhoc by default, ceremony when you need it | Short skills for 90% of creative work. Formal spec cycles for architectural changes or consumer-facing API. |
| Quality is automatic or it doesn't exist | Every asset-producing skill ends with a verification gate. No "we'll check it later." |
| Variants are first-class, not an afterthought | Desktop and Mobile are modeled from the first generation step. No retrofit pass. |
| Idempotent, resumable, cacheable | Any stage can be rerun without redoing upstream work. Generation is expensive; cache aggressively. |
| Onboarding parity with core capability | Every new consumer-facing feature ships with updated onboarding docs in the same PR. |

---

## Success Metrics

| Metric | Target | Why It Matters |
|--------|--------|----------------|
| Asset quality — Blender-first vs. Meshy (subjective A/B by internal dev team) | ≥ parity on 80% of paired generations; strictly better on 20% | Validates the "Blender should learn how to be Meshy.io" thesis |
| Time from prompt → UE-imported asset (desktop variant) | ≤ 5 min on M-series Mac for a hero character; ≤ 90 s for a standard prop | Adhoc workflow is only useful if the iteration loop is fast |
| Consumer onboarding time (new NMG project to first generated asset) | ≤ 1 hour from clone to imported asset | Lock-in risk is real; make the framework easy to adopt, easy to leave |
| Skill suite coverage | 100% of ghost1's current bespoke asset workflow replaced by nmg-game-dev skills | ghost1 is the reference consumer; if nmg-game-dev can't host its pipeline, it doesn't work |
| Quality gate coverage | Every asset-producing skill has an automated verification gate | No manual QA in the happy path |

---

## Feature Prioritization

The user elected "everything in v1" — no deferral to a v2 milestone. Priorities below are ordering guidance inside v1, not deferral buckets.

### v1 — Everything

- **MCP + skill scaffolding** — the plugin shell, MCP server wiring for Blender, Unreal, Meshy, and the texture-gen tool.
- **Blender → UE pipeline** — authoring in Blender, import into UE via the UE plugin, with desktop/mobile variant support.
- **Meshy → Blender → UE pipeline** — supplementary ingestion path for when Meshy is the right starting point.
- **Texture generation (Blender-first)** — research spike to pick the texture-design tool; integration; quality gate to match Meshy output.
- **Unreal Engine plugin** — editor-side capability (import, retarget, level dressing, variant routing) AND runtime capability that ships inside the consumer's game binary.
- **Blender add-on** — authoring-side capability (generation, cleanup, mobile optimization).
- **Quality gates** — polycount, texture budget, cook-manifest equivalents, runtime perf bars for shipped content.
- **Build + ship skills** — per-platform builds (macOS, Windows, iOS, Android), code signing, macOS notarization, store-ready packaging. This is how NMG games get to players.
- **Onboarding + documentation** — consumer-facing docs; "install and generate your first asset in under an hour" path; "ship your first build" path.

### Won't Have (Now)

- Console-specific tooling paths (PlayStation / Xbox / Switch) — not a v1 target.
- Runtime (play-time) asset generation — generation is authoring-time; what ships is pre-baked.
- Any cloud-hosted generation service of our own — we orchestrate existing tools, we don't host new ones.
- A bespoke launcher / storefront — we ship to Apple / Google / (direct download for desktop), not our own distribution.

---

## Key User Journeys

### Journey 1: Internal dev generates a prop, Blender-first

```
1. Developer invokes `$new-prop Weapons/Katana standard "Tachi-style katana, weathered"`
2. nmg-game-dev orchestrates: texture-gen tool → Blender MCP (mesh + materials) → quality gate → Blender MCP (desktop + mobile variants) → UE MCP (import)
3. Developer sees both variants under Content/Weapons/Katana/{Desktop,Mobile}/ in the consumer project
4. If quality gate fails, skill surfaces the failure and the iteration prompt
```

### Journey 2: Internal dev uses Meshy because the category benefits from it

```
1. Developer invokes `$new-character Guards/Patrol "Futuristic patrol guard, light armor" --source meshy`
2. nmg-game-dev routes: Meshy MCP (generation) → Blender MCP (cleanup + mobile optimize) → UE MCP (import)
3. Same variant output, same quality gates
```

### Journey 3: Consumer adopts nmg-game-dev in a new project

```
1. Clone the consumer project; run the nmg-game-dev onboarding skill
2. Skill installs the Codex plugin, Blender add-on, UE plugin; prompts for API keys
3. First `$new-prop` or `$new-character` invocation works end-to-end
4. Consumer's first commit includes only their new content — no framework bootstrap noise
```

### Journey 4: Ship a build to players

```
1. Developer invokes `$build-platform mobile` (or desktop, or all)
2. nmg-game-dev drives UE packaging → code signing → notarization (macOS) → cook-manifest verification per platform
3. Output is a store-ready artifact: .ipa / .aab / .app / .exe
4. Quality gates block the ship if any fail; failures surface the remediation prompt, not a raw log
```

---

## Brand Voice

| Attribute | Do | Don't |
|-----------|-----|-------|
| Opinionated | "Blender is the primary authoring surface." | "Some people prefer Meshy." |
| Honest about quality | "Texture gen quality is currently below Meshy on metallic materials — tracked in #N." | "The framework produces production-ready assets across all categories." |
| Workflow-first | Lead docs with a flow, not an API reference. | Lead docs with a module graph. |

---

## Privacy Commitment

| Data | Usage | Shared |
|------|-------|--------|
| Developer prompts (asset descriptions) | Passed to Meshy / texture-gen tool when those tools are invoked | With the respective third-party provider per their ToS |
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
