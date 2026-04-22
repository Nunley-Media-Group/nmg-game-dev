# Requirements: Scaffold plugin + repo + session-start hooks

**Issues**: #1, #2
**Date**: 2026-04-22
**Status**: Amended
**Author**: Rich Nunley

---

## User Story

**As an** internal NMG game developer (per `steering/product.md` — primary persona)
**I want** a fresh clone of `nmg-game-dev` to self-assemble into a working Claude Code plugin whose two session-start launcher scripts are ready for consumer projects to adopt, and whose Python/MCP scaffolding is in place
**So that** every downstream v1 issue (#2–#7) can assume the plugin shell, directory layout, Python package, and shipped launcher scripts are already wired.

---

## Background

`nmg-game-dev` is distributed as a Claude Code plugin, a Blender add-on, and a UE plugin (see `steering/product.md` § Mission). Before any of the asset-generation, quality-gate, build, or ship skills can land, the repo needs a valid plugin manifest, the canonical directory layout from `steering/structure.md`, a Python tooling package, and the two idempotent launcher scripts defined in `steering/tech.md` § Session-start contract.

### Scope of session-start hooks — consumer-game-only

The session-start hooks this issue delivers are for **consumer game projects** (e.g., ghost1 or any future NMG game repo that adopts `nmg-game-dev`). They are NOT wired to auto-run on this plugin repo's own session start. Inside `nmg-game-dev`, contributors launch Blender / UE manually when they need to test a pipeline feature; this repo is a library, not a game.

Concretely:
- `scripts/start-blender-mcp.sh` and `scripts/start-unreal-mcp.sh` ship as executable deliverables under `scripts/`.
- The `.claude/settings.json` artifact that registers them as `SessionStart` hooks ships as a **consumer template** at `templates/consumer/.claude/settings.json`. It is never loaded by Claude Code in this repo — it exists so `onboard-consumer` (a later v1 issue) can copy it into downstream projects.
- There is no `.claude/settings.json` at this repo's root registering SessionStart hooks.

### UE MCP — VibeUE in-editor plugin

`steering/tech.md` § Technology Stack pins UE control on **VibeUE** (an in-editor UE plugin):
- `.mcp.json` pins VibeUE as the `unreal` entry.
- `start-unreal-mcp.sh` launches UE Editor against the consumer's `.uproject`. Once VibeUE is enabled in that project (installed by `onboard-consumer`, future v1 issue), VibeUE itself binds the HTTP bridge on `UE_MCP_PORT` (default 8088) at editor startup. Claude connects through the `mcp-remote` transport to VibeUE's `/mcp` endpoint.
- For this foundational issue, neither the nmg-game-dev UE plugin nor VibeUE is built or installed. The launcher still ships; the port-bind side of the contract is validated when VibeUE is enabled in a consumer `.uproject`.

> *Updated 2026-04-22 per #2 review*: an earlier draft of this section described an `NmgGameDevMCP` editor-only module that nmg-game-dev would ship to bind the HTTP bridge. Investigation against `https://github.com/kevinpbuckley/VibeUE` showed VibeUE owns the editor MCP wire end-to-end (closed bridge, no plugin-extension API). Building a competing module would either collide on the port or duplicate VibeUE's ~950-method service surface, so #2 dropped `NmgGameDevMCP` and now ships only Runtime + Editor modules. References below to "the nmg-game-dev UE plugin binding the bridge" were incorrect and are corrected in line.

### `.mcp.json` is dual-purpose

Unlike the SessionStart hooks, the MCP server configuration is needed in **both** places:

1. **In this repo** — contributors testing pipeline features need Blender MCP, VibeUE (UE), and Meshy MCP servers registered with Claude Code so that slash commands and pipeline stages under development can actually talk to the tools. `.mcp.json` lives at this repo's root.
2. **In every consumer game project** — `onboard-consumer` (future v1 issue) treats this repo's root `.mcp.json` as the canonical source and copies / adapts it into the consumer. There is NO separate `templates/consumer/.mcp.json`; one file is the single source of truth, reused at onboarding time.

The contrast with SessionStart is deliberate: MCP *configuration* is the same in both contexts (same servers, same pinned versions), so one file serves both. SessionStart *triggers* differ (manual here, auto there), so the settings.json is consumer-template-only.

### End goal: this plugin is installed into other Claude Code projects to create games

Every deliverable in this issue must hold up under the lens "a consumer game project runs `claude plugin add nmg-game-dev` (or the marketplace equivalent) + `onboard-consumer`, and the deliverable lands correctly in that consumer."

#### Install-level invariance (user-level vs. project-level)

The plugin itself may be installed either at the **user level** (`~/.claude/plugins/nmg-game-dev/`, shared across every project that user opens) or at the **project level** (inside a specific consumer repo's plugin directory). The outcome for the consumer must be identical in both cases — the same skills, commands, and agents must be available; the same consumer-side artifacts (launcher scripts, `.mcp.json`, `SessionStart` hooks) must land.

This works because the two concerns are decoupled:
- **Plugin-level install** (Claude Code's responsibility): wires up `skills/`, `commands/`, `agents/` from this repo's `.claude-plugin/plugin.json`. Unaffected by install scope.
- **Consumer project-level setup** (`onboard-consumer`'s responsibility): copies `scripts/`, `.mcp.json`, and the `SessionStart` entries into the specific consumer repo the developer is onboarding. Runs per-project regardless of where the plugin itself lives.

Practical requirement: no artifact shipped in this issue may assume a specific install scope. The launcher scripts must resolve paths via env vars / documented defaults (not via the plugin's own install location); `plugin.json` must not encode project-specific paths; `.mcp.json` must carry only server configuration, never this-repo-specific paths.

#### Artifact-to-consumer distribution trace

The table below traces each artifact from where it lives in this repo to where and how it reaches a consumer game project:

| This-repo artifact | Distribution channel | Lands in consumer as |
|--------------------|----------------------|----------------------|
| `.claude-plugin/plugin.json`, `skills/`, `commands/`, `agents/` | Claude Code plugin install (`claude plugin add nmg-game-dev`) at either user scope (`~/.claude/plugins/`) or project scope | Registered plugin; skills/commands/agents available in the consumer's Claude session — outcome identical for both install scopes |
| `scripts/start-blender-mcp.sh`, `scripts/start-unreal-mcp.sh` | Copied by `onboard-consumer` (v1 issue) into the consumer's `scripts/` | Executable launchers invoked by the consumer's `SessionStart` hooks |
| `templates/consumer/.claude/settings.json` | Copied by `onboard-consumer` into the consumer's `.claude/settings.json` (merging if one already exists) | Registers `SessionStart` hooks that run the two launchers at consumer session start |
| `.mcp.json` (root) | Copied by `onboard-consumer` into the consumer's repo root | Consumer's MCP server configuration |
| `src/nmg_game_dev/` Python package | Published / installed (`pip install nmg-game-dev` or equivalent — mechanism resolved in `onboard-consumer`) | Importable from the consumer's Python environment; skills call into its pipeline / variants / quality / ship modules |
| `plugins/nmg-game-dev-blender-addon/` (later issue) | Installed into the consumer's Blender user-extensions directory by `onboard-consumer` | Blender add-on enabled in the dev's Blender instance |
| `plugins/nmg-game-dev-ue-plugin/` (issue #3) | Installed into the consumer's `.uproject`'s `Plugins/` directory by `onboard-consumer` | UE plugin enabled in the consumer's game project |

What this means for this issue's scope:
- Nothing we ship here can assume it lives inside `nmg-game-dev` forever. Every path we hard-code must either be relative (works in any repo) or env-var-resolved with a documented default (adapts per consumer).
- `.claude-plugin/plugin.json`'s identity fields (`name`, `version`, `description`, `authors`) are what consumers see in their plugin list — get them right.
- The dogfood `.uproject` fixture is a **this-repo-only** artifact used for contributor smoke-testing; it must never leak into a consumer via `onboard-consumer`.

This is explicitly a foundational issue (`foundational` label); blocks `#2, #3, #4, #5, #6, #7`. Its only job is to put the skeleton in place — no asset skills, no UE plugin source beyond a boot stub, no Blender add-on implementation.

---

## Acceptance Criteria

**IMPORTANT: Each criterion becomes a Gherkin BDD test scenario.**

### AC1: Plugin manifest is valid

**Given** `.claude-plugin/plugin.json` exists at the repo root
**When** the plugin manifest is validated against Claude Code's schema (e.g., `claude plugin validate` or equivalent)
**Then** validation passes with no errors
**And** the manifest declares `name`, `version`, `description`, `authors`, and capability fields

### AC2: Directory layout matches steering/structure.md

**Given** the layout declared in `steering/structure.md` § Project Layout
**When** `ls` probes the repo root and each declared top-level directory
**Then** every top-level directory listed in `structure.md` exists (empty directories carry a `.gitkeep`)
**And** the Python package `src/nmg_game_dev/` is importable with submodule stubs for `pipeline/`, `variants/`, `quality/`, `ship/`

### AC3: Launcher scripts ship and detach Blender / UE when invoked manually

**Given** a developer, working inside the `nmg-game-dev` repo, runs `scripts/start-blender-mcp.sh` (or `scripts/start-unreal-mcp.sh`) directly from the shell
**And** `BLENDER_BIN` (or `BLENDER_APP`) resolves to an installed Blender binary
**And** `UE_ROOT` resolves to an installed Unreal Engine 5.7 install (default `/Users/Shared/Epic Games/UE_5.7`)
**When** the script is invoked
**Then** `start-blender-mcp.sh` detaches Blender with the MCP add-on enabled on `BLENDER_MCP_PORT` (default 9876) and returns control to the shell in under ~2 s
**And** `start-unreal-mcp.sh` detaches UE Editor opened against the target `.uproject` (VibeUE binds `UE_MCP_PORT`, default 8088, inside UE — the launcher does not bind any port itself) and returns control to the shell in under ~2 s
**And** neither script blocks the shell on Blender / UE boot

### AC4: Launcher scripts are idempotent

**Given** Blender (or UE) is already listening on its MCP port
**When** the corresponding `start-*-mcp.sh` script is re-run
**Then** the script exits 0 without double-launching the tool
**And** no duplicate process appears in the process table

### AC5: Launcher scripts fail with actionable remediation

**Given** `BLENDER_BIN`/`BLENDER_APP` does not resolve to an installed Blender (or `UE_ROOT` points at a missing UE install)
**When** the corresponding launcher runs
**Then** the script exits non-zero
**And** emits a one-line remediation hint naming the env var to set and the default path it checked

### AC5b: `.claude/settings.json` SessionStart template is shipped for consumers

**Given** `templates/consumer/.claude/settings.json` exists in this repo
**When** a reader inspects it
**Then** it declares two `SessionStart` hook entries that invoke `scripts/start-blender-mcp.sh` and `scripts/start-unreal-mcp.sh`
**And** no `.claude/settings.json` at the repo root registers those hooks (the template is inert inside this repo)
**And** a comment or sibling `README.md` under `templates/consumer/` documents that `onboard-consumer` (future v1 issue) copies this template into downstream projects

### AC6: Python package bootstraps

**Given** `pyproject.toml` declares the `nmg_game_dev` package, dev deps (`pytest`, `pytest-bdd`, `ruff`, `mypy`), and console scripts
**When** `pip install -e .[dev]` (or `uv sync`) runs in a fresh venv
**Then** the install succeeds
**And** `python -c "import nmg_game_dev"` exits 0
**And** `ruff check .` and `pytest` both exit 0 against the empty scaffold

### AC7: Version seed and changelog present

**Given** the repo
**When** a developer reads `VERSION` and `CHANGELOG.md`
**Then** `VERSION` contains exactly `0.1.0` (plus trailing newline)
**And** `CHANGELOG.md` has an `[Unreleased]` section that `/open-pr` can append to

### AC8: MCP server config pinned (Blender + VibeUE + Meshy), dual-purpose

**Given** `.mcp.json` at this repo's root
**When** Claude Code loads the workspace (either this repo for contributor testing, or a consumer project where `onboard-consumer` has copied this file)
**Then** the file declares three pinned MCP server entries:
  - `blender` → `ahujasid/blender-mcp` pinned
  - `unreal` → the VibeUE MCP server pinned (concrete package identifier + version resolved in design)
  - `meshy` → the Meshy MCP server pinned
**And** every server entry carries a pinned version (no floating `latest` or `main`)
**And** the file works identically whether loaded inside nmg-game-dev (for pipeline testing) or inside a consumer game project (onboarded by `onboard-consumer`) — no this-repo-only paths, no consumer-only hard-codes

### AC9: Entry-point pointer doc present

**Given** `CLAUDE.md` at the repo root
**When** a new contributor (or a Claude session) opens the repo
**Then** `CLAUDE.md` points at `steering/product.md`, `steering/tech.md`, `steering/structure.md`, and the `/draft-issue` SDLC entry point

### AC10: Nothing this-repo-specific leaks into consumer-facing deliverables

**Given** the artifacts designated as consumer-facing: `.claude-plugin/plugin.json`, `scripts/start-*-mcp.sh`, `templates/consumer/.claude/settings.json`, `.mcp.json`, `pyproject.toml`'s declared package metadata
**When** a reviewer greps these artifacts for repo-specific absolute paths, hard-coded user names, this-repo-only fixture references, or credentials
**Then** no hit is returned
**And** every path resolution in the launcher scripts uses either env-var overrides (`BLENDER_BIN`, `BLENDER_APP`, `UE_ROOT`) or documented defaults that a consumer can override without editing the script

### AC11: Install-scope invariance

**Given** the plugin is installed at either user scope (`~/.claude/plugins/nmg-game-dev/`) or project scope, and `onboard-consumer` has been run against a consumer game project
**When** a developer opens the consumer project in Claude Code
**Then** the consumer-side outcome is identical regardless of the plugin's install scope — same skills available, same `scripts/` present, same `.mcp.json` content, same `.claude/settings.json` `SessionStart` entries
**And** no artifact this issue ships encodes or depends on a specific install scope

### Generated Gherkin Preview

```gherkin
Feature: Scaffold plugin + repo + session-start hooks
  As an internal NMG game developer
  I want a fresh clone of nmg-game-dev to self-assemble into a working Claude Code plugin
  So that every downstream v1 issue can assume the scaffolding is in place

  Scenario: Plugin manifest is valid
    Given .claude-plugin/plugin.json exists at the repo root
    When the plugin manifest is validated
    Then validation passes with no errors

  Scenario: Directory layout matches structure.md
    Given the layout declared in steering/structure.md
    When ls probes the repo root
    Then every declared top-level directory exists

  Scenario: Launchers detach Blender and UE when invoked manually
    Given BLENDER_BIN and UE_ROOT resolve to installed tools
    When scripts/start-blender-mcp.sh and scripts/start-unreal-mcp.sh are invoked
    Then Blender ends up listening on 9876 and UE Editor on 8088, with both scripts returning quickly

  Scenario: Launchers are idempotent
    Given the target port is already LISTEN
    When the launcher re-runs
    Then it exits 0 without double-launching

  Scenario: Launchers fail with remediation
    Given BLENDER_BIN points at a missing binary
    When start-blender-mcp.sh runs
    Then the script exits non-zero with a one-line remediation hint

  Scenario: Consumer template ships under templates/consumer/
    Given templates/consumer/.claude/settings.json exists
    Then it declares two SessionStart hook entries invoking the launcher scripts
    And no .claude/settings.json at the repo root registers those hooks

  # ... AC6–AC9 become scenarios in feature.gherkin
```

---

## Functional Requirements

| ID | Requirement | Priority | Notes |
|----|-------------|----------|-------|
| FR1 | `.claude-plugin/plugin.json` — plugin manifest with `name`, `version`, `description`, `authors`, capability declarations | Must | Versioning table in `steering/tech.md` requires this file to track with `VERSION` |
| FR2 | `templates/consumer/.claude/settings.json` — consumer-targeted template declaring the two `SessionStart` hooks, plus a sibling `README.md` documenting that `onboard-consumer` is responsible for installing it into downstream projects. NO `.claude/settings.json` at this repo's root. | Must | Per user direction: this repo does not auto-run the hooks; they target consumer games |
| FR3 | `scripts/start-blender-mcp.sh` — port-probed, nohup-detached Blender launcher with multi-candidate add-on discovery | Must | Per `steering/tech.md` § Session-start contract invariants 1–6; invoked manually in this repo, as a SessionStart hook in consumer repos |
| FR4 | `scripts/start-unreal-mcp.sh` — port-probed, nohup-detached UE Editor launcher that opens the target `.uproject` | Must | In a consumer, targets the consumer's `.uproject`. In this repo, targets the dogfood fixture per FR12. |
| FR5 | `pyproject.toml` — declares `nmg_game_dev` package, dev deps (`pytest`, `pytest-bdd`, `ruff`, `mypy`), console scripts | Must | `gate-python-lint` and `gate-python-types` require these tools |
| FR6 | `src/nmg_game_dev/__init__.py` + empty submodule stubs (`pipeline/`, `variants/`, `quality/`, `ship/`) | Must | Each stub is `__init__.py` only; no implementation in this issue |
| FR7 | `VERSION` seeded at `0.1.0` | Must | Single source of truth per `steering/tech.md` § Versioning |
| FR8 | `CHANGELOG.md` seeded with `[Unreleased]` section | Must | `/open-pr` requires this shape |
| FR9 | `CLAUDE.md` — entry-point pointer doc (mirrors ghost1's shape) | Must | Points at steering docs + SDLC entry |
| FR10 | `.mcp.json` at repo root — pinned MCP server config: `blender` (`ahujasid/blender-mcp`), `unreal` (VibeUE), `meshy`. Dual-purpose: used here for contributor testing AND copied by `onboard-consumer` into consumer projects. No consumer-only template variant. | Must | VibeUE chosen as the concrete UE MCP; exact package identifier + pinned version resolved in design |
| FR11 | Top-level directories from `steering/structure.md` exist (with `.gitkeep` where otherwise empty) | Must | `specs/.gitkeep`, `steering/` already seeded — do NOT regenerate per issue body |
| FR12 | Dogfood UE `.uproject` fixture used when `start-unreal-mcp.sh` is invoked from inside this repo | Should | Minimal blank UE 5.7 project; gives the launcher a valid target so contributors can smoke-test without a consumer. VibeUE's port-bind is not validated here — that arrives when VibeUE is enabled in a consumer `.uproject` (via `onboard-consumer`). *(Updated 2026-04-22: previously said "NmgGameDevMCP bridge port-bind" validated by #2/#3; corrected per #2 review — VibeUE owns the bind, not us.)* |

---

## Non-Functional Requirements

| Aspect | Requirement |
|--------|-------------|
| **Performance** | Each `SessionStart` hook must return control to the shell well under the hook timeout (idempotent fast-path: < 1 s when port is already bound; cold launch: detached, so script itself exits immediately even while Blender/UE boots) |
| **Security** | Launcher scripts MUST NOT log signing credentials, API keys, or other env secrets (`steering/tech.md` § Security). Shellcheck-clean under `gate-shellcheck`. |
| **Platform** | macOS Apple Silicon primary; scripts must work with `BLENDER_APP` (macOS `.app` bundle) as well as `BLENDER_BIN` (direct binary). UE path defaults to `/Users/Shared/Epic Games/UE_5.7`. Windows/Linux parity is NOT a requirement for this issue. |
| **Reliability** | Launchers are idempotent: repeated invocation when the port is already listening MUST exit 0 without double-launching. Stdout/stderr tee to `/tmp/<tool>-mcp.log`. |
| **Accessibility** | N/A (no UI surface in this issue) |

---

## Data Requirements

No persistent data model is introduced. Configuration artifacts only:

| File | Purpose |
|------|---------|
| `.claude-plugin/plugin.json` | Plugin identity + version |
| `.claude/settings.json` | SessionStart hook registration (template for consumers) |
| `.mcp.json` | Pinned MCP server versions |
| `VERSION`, `CHANGELOG.md` | Versioning state |
| `pyproject.toml` | Python package metadata |

---

## Dependencies

### Internal Dependencies
- [x] `steering/product.md`, `steering/tech.md`, `steering/structure.md` — already seeded by `/onboard-project`.

### External Dependencies
- [ ] Blender 4.x LTS installed on the dev machine (runtime dependency for AC3; not installed by this issue).
- [ ] Unreal Engine 5.7 installed (runtime dependency for AC3).
- [ ] Python 3.11+ (for `pyproject.toml` install).

### Blocked By
- None. This issue unblocks #2–#7.

---

## Out of Scope

Explicitly NOT included in this issue (tracked as other v1 issues per issue #1's own "Out of scope" list):

- UE plugin sources (`.uplugin`, modules, helpers). All UE plugin content lands in #2. *(Updated 2026-04-22: previously said "beyond the plugin manifest stub needed to boot the MCP bridge on session-start" — the bridge is owned by VibeUE, not nmg-game-dev, so no stub is needed in this issue and #2 ships only Runtime + Editor modules.)*
- Blender add-on implementation — only the `__init__.py` / `bl_info` shim needed for `start-blender-mcp.sh` to discover and enable an add-on name.
- Any skills under `skills/` beyond schema-stubbed `SKILL.md` placeholders.
- Texture-gen tool integration (v1 spike, separately).
- Re-seeding `specs/.gitkeep` or `steering/*.md` — already present.
- Implementation of any quality gate, pipeline stage, or ship step.
- Windows / Linux session-start hook parity.

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Time from `git clone` to first successful Claude session with Blender + UE listening | ≤ 2 min | Manual wall-clock on M-series Mac |
| Session-start hook cold script runtime | ≤ 2 s script return (tools launch in background) | `time scripts/start-blender-mcp.sh` |
| Idempotent re-run on bound port | ≤ 100 ms | `time scripts/start-blender-mcp.sh` when already listening |
| Downstream v1 issues (#2–#7) start-issue blocked reason | Zero cite "scaffolding missing" after this lands | Issue comments |

---

## Open Questions

- [x] Does the dogfood `.uproject` fixture ship in this issue, or is it deferred to the UE-plugin issue (#3)? **Resolved**: minimal blank UE 5.7 project ships here so `start-unreal-mcp.sh` has a valid target for smoke-testing; issue #3 later enables the nmg-game-dev UE plugin inside it.
- [x] Does `.claude/settings.json` ship as a live settings file or as a consumer-only template? **Resolved (user direction)**: ships ONLY as a consumer template at `templates/consumer/.claude/settings.json`. This repo does NOT auto-run the session-start hooks; contributors launch Blender / UE manually when testing.
- [x] What is the concrete UE MCP server pinned in `.mcp.json`? **Resolved (user direction)**: VibeUE (the VibeUE-style HTTP-bridge pattern referenced in `steering/tech.md`). Exact package identifier + pinned version resolved in design.
- [ ] Add-on name discovery candidates for `start-blender-mcp.sh` — which names to probe? **Proposed**: `bl_ext.user_default.blender_mcp`, `bl_ext.user_default.blender-mcp`, `blender_mcp`, `blender-mcp`. Finalized in design.

---

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #1 | 2026-04-22 | Initial feature spec |
| #2 | 2026-04-22 | Cleanup: drop NmgGameDevMCP framing — VibeUE owns the editor MCP bridge end-to-end (no nmg-game-dev module binds the port) |

---

## Validation Checklist

Before moving to PLAN phase:

- [x] User story follows "As a / I want / So that" format
- [x] All acceptance criteria use Given/When/Then format
- [x] No implementation details in requirements (implementation deferred to design.md)
- [x] All criteria are testable and unambiguous
- [x] Success metrics are measurable
- [x] Edge cases (idempotent re-run, missing binary) are specified
- [x] Dependencies identified (Blender / UE / Python runtime; no upstream specs)
- [x] Out of scope defined
- [x] Open questions documented with proposed resolutions
