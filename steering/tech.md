# nmg-game-dev Technical Steering

This document defines the technology stack, constraints, and integration standards.
All technical decisions should align with these guidelines. Section names below are
load-bearing — nmg-sdlc matches on them literally.

---

## Architecture Overview

```
Developer in Claude Code
        │
        │  slash commands / natural language
        ▼
┌────────────────────────────────────────────────────────────┐
│ nmg-game-dev Claude Code plugin                            │
│   skills/ (asset gen, optimization, build, ship, verify)   │
│   commands/ (ad-hoc shortcuts)                             │
│   agents/ (specialized review / verification agents)       │
└───────┬─────────────────────────┬────────────────┬─────────┘
        │                         │                │
        ▼                         ▼                ▼
┌──────────────┐          ┌──────────────┐   ┌──────────────┐
│ Blender MCP  │          │ Unreal MCP   │   │ Meshy MCP    │
│ (+ add-on)   │          │ (+ plugin)   │   │ (supplement) │
└──────┬───────┘          └──────┬───────┘   └──────┬───────┘
       │                         │                  │
       ▼                         ▼                  ▼
┌──────────────┐          ┌──────────────┐   ┌──────────────┐
│ Blender 4.x  │          │ UE 5.x       │   │ Meshy.io API │
│ (headless    │          │ (editor +    │   │              │
│  + GUI)      │          │  runtime)    │   │              │
└──────┬───────┘          └──────────────┘   └──────────────┘
       │
       ▼
┌──────────────────────────────────────────┐
│ Texture Design Tool (TBD — v1 spike)     │
│ Candidates: ComfyUI + SD/SDXL + ControlNet, │
│ Substance, Dream Textures, custom diffusion │
└──────────────────────────────────────────┘

        Consumer project (e.g., ghost1)
        │
        ▼
┌────────────────────────────────────────────────────────────┐
│ Installed artifacts from nmg-game-dev                      │
│   • Claude Code plugin (skills + commands + MCP configs)   │
│   • Blender add-on (authoring tools)                       │
│   • UE plugin (editor tools + runtime module shipped in    │
│     the consumer's game binary)                            │
└────────────────────────────────────────────────────────────┘
```

---

## Technology Stack

| Layer | Technology | Version |
|-------|------------|---------|
| Orchestration | nmg-sdlc (Claude Code plugin, used to BUILD nmg-game-dev) | latest |
| Distribution | Claude Code plugin (what nmg-game-dev SHIPS) | targets current Claude Code |
| Host tooling | Python | 3.11+ (matches Blender bundled python) |
| Authoring surface | Blender | 4.x LTS (oldest supported 4.2 LTS) |
| Game engine | Unreal Engine | 5.7 (Apple Silicon native) |
| UE plugin source | C++ (+ Blueprints for composition) | Epic coding standard |
| Shell scripts | bash | `set -euo pipefail`; shellcheck-clean |
| 3D generation (supplement) | Meshy.io | via MCP |
| 3D + asset control (primary) | Blender MCP (`ahujasid/blender-mcp`) | pinned per `.mcp.json` |
| UE control | VibeUE in-editor plugin (binds 127.0.0.1:8088/mcp inside UE) | pinned per `.mcp.json`; NMG does NOT author its own UE-side bridge |
| Texture generation | **TBD — v1 spike** | picked during v1; pluggable interface |

### External Services

| Service | Purpose | Notes |
|---------|---------|-------|
| Meshy.io | 3D asset generation (supplement) | Rate-limited; cache aggressively; `MESHY_API_KEY` |
| Apple Notary Service | macOS notarization of shipped builds | Team ID + app-specific password |
| Apple Developer | iOS provisioning | `.mobileprovision` via env |
| Google Play | Android AAB upload | Keystore + password via env |
| GitHub | Source + issue + PR automation | `gh` CLI |
| (TBD) Texture-gen hosted service | If the v1 spike picks a hosted tool | Credential model decided at spike |

---

## Versioning

The `VERSION` file (plain text semver at project root) is the **single source of truth** for the project's current version. Stack-specific files are kept in sync via the mapping table below.

| File | Path | Notes |
|------|------|-------|
| `VERSION` | (entire file) | Plain semver, one line |
| `.claude-plugin/plugin.json` | `version` | Claude Code plugin manifest |
| `plugins/nmg-game-dev-blender-addon/__init__.py` | `bl_info.version` | Blender add-on tuple (major, minor, patch) |
| `plugins/nmg-game-dev-ue-plugin/nmg-game-dev.uplugin` | `VersionName` | UE plugin manifest |
| `pyproject.toml` | `project.version` | Python tooling package |

### Path Syntax

- **JSON files**: dot-notation (e.g., `version`, `packages.mylib.version`).
- **TOML files**: dot-notation matching TOML keys (e.g., `project.version`).
- **Plain text**: `line:N` or omit Path if the whole file is the version.
- **Python `bl_info` tuple**: special-cased — `/open-pr` rewrites the tuple literal.

### Version Bump Classification

`/open-pr` and the `sdlc-runner.mjs` deterministic bump postcondition read this table.

| Label | Bump Type | Description |
|-------|-----------|-------------|
| `bug` | patch | Bug fix — backwards-compatible |
| `enhancement` | minor | New feature — backwards-compatible |
| `feature` | minor | New feature — backwards-compatible |
| `docs` | patch | Documentation-only change |

**Default**: if no label matches, bump type is **minor**.

**Major bumps are manual-only** — `/open-pr #N --major`. Unattended runs never apply a major bump.

**Breaking changes use minor bumps.** Communicate with `**BREAKING CHANGE:**` prefix in CHANGELOG entries and a `### Migration Notes` sub-section.

Pre-1.0: breaking changes are allowed inside minor bumps without a major gate. The framework is pre-release until the first consumer project (ghost1) is fully migrated to nmg-game-dev.

---

## Technical Constraints

### Performance (authoring)

| Metric | Target | Rationale |
|--------|--------|-----------|
| `/new-prop` end-to-end (standard tier) | ≤ 90 s on M-series Mac | Adhoc iteration requires tight loops |
| `/new-character` end-to-end (hero) | ≤ 5 min on M-series Mac | Characters are the slowest asset; budget is generous but bounded |
| `/ship desktop` cold build | ≤ 20 min | Includes UE cook + sign + notarize |
| Skill cold-start (first invocation per session) | ≤ 2 s | MCP handshake + env validation only |

### Performance (runtime — shipped UE plugin code)

| Metric | Target | Rationale |
|--------|--------|-----------|
| Any per-frame hook added by nmg-game-dev's UE runtime module | ≤ 0.1 ms on iPhone 15-tier hardware | Shipped overhead must be near-zero |
| Memory footprint of UE runtime module | ≤ 4 MB resident | Mobile RAM is the limiting resource |

### Security

| Requirement | Implementation |
|-------------|----------------|
| Authentication (to external services) | API keys via env vars; never in git |
| Credential storage | `.claude/secrets.json` (gitignored) for session-local overrides; production uses keychain / CI secrets |
| Signing identities | Read from OS keychain (macOS) or env (`ANDROID_KEYSTORE_PASSWORD`); never echoed to logs |
| Third-party MCP trust | Pin MCP server versions in `.mcp.json`; review each upgrade |
| Supply chain | `pyproject.toml` pins exact versions for build-critical deps; `uv.lock` / `requirements.lock` committed |

---

## Coding Standards

### Python (primary tooling language)

- PEP 8.
- Type hints required on all public functions.
- `from __future__ import annotations` at file top.
- Ruff for lint + format (configured in `pyproject.toml`).
- Prefer `pathlib.Path` over `os.path`.
- Blender add-on code runs inside Blender's bundled Python — no dependencies that require compiled wheels unless they're already in Blender's env. Validate in CI against Blender 4.2 LTS and latest.

### C++ (UE plugin)

- Epic's coding standard.
- UHT/UBT rejects violations — don't fight them.
- One module per feature domain; no circular dependencies.
- Editor-only code lives in a separate `*Editor` module.
- Runtime code is budget-sensitive (see Runtime Performance above).

### Shell

- `#!/usr/bin/env bash` shebang.
- `set -euo pipefail` at the top of every script.
- shellcheck-clean (CI enforces).
- No bashisms in scripts that must run cross-shell.

### Blueprints (UE)

- Node comments for any non-obvious flow.
- Pure functions preferred for logic.
- No hidden casts across module boundaries.

### Markdown (docs)

- CommonMark.
- `markdownlint` CI gate with project config.
- Onboarding docs lead with a flow, not an API reference.

---

## API / Interface Standards

### Skill contract

Every consumer-facing skill MUST:

1. Have a one-line `description` that fits in the Claude skills list.
2. Declare its required MCP servers in its frontmatter.
3. Fail fast with an actionable error if a required env var or MCP is missing.
4. Be idempotent — safe to rerun on partial failure.
5. Respect `.claude/unattended-mode` (no prompts when present; fall back to documented defaults).

### MCP server contract

Every nmg-game-dev-authored MCP server MUST:

1. Expose tools with stable names — changes go through the deprecation window.
2. Return structured errors (`error.code`, `error.message`, `error.remediation`).
3. Log to stderr only — stdout is the MCP channel.
4. Handle cancellation / timeout gracefully (clean up partial state).

### Session-start contract (Blender MCP + Unreal MCP auto-launch)

Neither Blender nor Unreal Editor boot themselves when a Claude session starts, and every downstream skill assumes their MCP endpoints are already reachable. nmg-game-dev owns this bootstrap and distributes it to consumer projects via the Claude Code plugin.

The framework ships two idempotent launch scripts, wired as `SessionStart` hooks in every consumer's `.claude/settings.json` by the onboarding skill:

| Script | Responsibility | Port |
|--------|----------------|------|
| `start-blender-mcp.sh` | Launches Blender (via `BLENDER_BIN` or `BLENDER_APP` env) with the Blender MCP add-on enabled; registers a deferred timer to start the socket server after the UI is ready. | `BLENDER_MCP_PORT` (default 9876) |
| `start-unreal-mcp.sh` | Launches UE Editor with the consumer's `.uproject`; **VibeUE** (the in-editor plugin pinned in `.mcp.json`, installed by `onboard-consumer`) binds the MCP HTTP bridge on startup. nmg-game-dev's UE plugin contributes Runtime helpers + Editor authoring hooks but does NOT bind any port. | `UE_MCP_PORT` (default 8088) — read by VibeUE's Project Settings |

**Contract invariants** (every launch script MUST honor):

1. **Idempotent** — if the target port is already `LISTEN`, exit 0 immediately. No double-launch.
2. **Detached** — `nohup … & disown`; return to the shell (and Claude Code) in under the hook timeout.
3. **Actionable failure** — exit non-zero with a one-line remediation hint if the binary or project file is missing.
4. **Path resolution** — prefer env-var overrides (`BLENDER_BIN`, `UE_ROOT`, `BLENDER_APP`), fall back to documented defaults, never hard-code the reference-project location.
5. **Logs** — stdout/stderr to `/tmp/<tool>-mcp.log`; path is documented in the skill that consumes it so failure triage is copy-paste.
6. **Plugin/addon discovery** — the Blender script probes multiple candidate addon names (Extensions system `bl_ext.*` and legacy folder names) and enables the first one installed. The UE script relies on the nmg-game-dev UE plugin being enabled in the consumer's `.uproject`.

The onboarding skill (one of the v1 deliverables) installs these scripts into each consumer's `scripts/` directory and injects the `SessionStart` hook entries into `.claude/settings.json`. Without this auto-launch path, the adhoc workflow is broken on every cold session.

### Texture-gen tool interface (TBD contract)

Until the v1 spike picks a tool, any integration MUST conform to:

```
Inputs:  prompt: str, resolution: int, style_refs: list[Path], seed: int | None
Outputs: base_color: Path, normal: Path, roughness: Path, metallic: Path, ao: Path | None
Errors:  TextureGenError with .remediation field
```

This contract lets the spike swap implementations without cascading changes.

---

## Testing Standards

### BDD Testing (Required for nmg-sdlc — building nmg-game-dev itself)

**Every acceptance criterion MUST have a Gherkin test.**

| Layer | Framework | Location |
|-------|-----------|----------|
| Python tooling | pytest-bdd | `tests/bdd/` with `.feature` files alongside step defs |
| UE runtime module | UE Automation Framework | `plugins/nmg-game-dev-ue-plugin/Source/**/Tests/*.spec.cpp` |
| Blender add-on | pytest + Blender headless | `tests/blender/` invoked via `blender --background --python` |
| End-to-end pipeline | pytest-bdd driving actual MCPs on fixture projects | `tests/e2e/` |
| Designer-facing acceptance | Gherkin `.feature` files used as manual QA scripts | `specs/<issue>/feature.gherkin` |

### Gherkin Feature Files

```gherkin
# tests/bdd/features/new_prop.feature
Feature: Generate a new prop Blender-first
  As an NMG game developer
  I want to run /new-prop and get both desktop and mobile variants
  So that I can iterate on content without leaving Claude

  Scenario: Standard-tier prop, Blender-first
    Given the Blender MCP is running
    And the texture-gen tool is configured
    When I run /new-prop Weapons/Crate standard "wooden supply crate"
    Then both Desktop and Mobile variants exist under Content/Weapons/Crate/
    And the mobile variant passes gate-mobile-budgets
    And the desktop variant is unbudgeted
```

### Step Definitions

```
# tests/bdd/steps/ — pytest-bdd style
@given("the Blender MCP is running")
def _(blender_mcp):
    assert blender_mcp.ping()
```

### Unit Tests

| Type | Framework | Location | Run Command |
|------|-----------|----------|-------------|
| Python unit | pytest | `tests/unit/` | `pytest tests/unit/` |
| Python BDD | pytest-bdd | `tests/bdd/` | `pytest tests/bdd/` |
| Blender add-on | pytest in headless Blender | `tests/blender/` | `scripts/run-blender-tests.sh` |
| UE runtime | UE Automation | `plugins/nmg-game-dev-ue-plugin/Source/**/Tests/` | `scripts/run-ue-tests.sh` |
| E2E pipeline | pytest-bdd | `tests/e2e/` | `pytest tests/e2e/ --runslow` |

### Test Pyramid

```
        /\
       /  \  E2E pipeline (pytest-bdd driving real MCPs)
      /----\
     /      \ BDD acceptance (pytest-bdd + Blender headless + UE Automation)
    /--------\
   /          \ Component tests (per-MCP, per-skill)
  /            \
 /--------------\
/                \ Unit tests (Python logic, UE C++ utilities)
 \________________/
```

---

## Verification Gates

`/verify-code` enforces these. Each declares when it applies.

| Gate | Condition | Action | Pass Criteria |
|------|-----------|--------|---------------|
| `gate-python-lint` | Diff touches `**/*.py` | `ruff check . && ruff format --check .` | Exit code 0 |
| `gate-python-types` | Diff touches `**/*.py` | `mypy src/ tests/` | Exit code 0 |
| `gate-python-unit` | Diff touches `src/**/*.py` or `tests/unit/**` | `pytest tests/unit/` | Exit code 0 |
| `gate-python-bdd` | Diff touches `src/**/*.py` or `tests/bdd/**` | `pytest tests/bdd/` | Exit code 0 |
| `gate-blender-headless` | Diff touches `plugins/nmg-game-dev-blender-addon/**` or `tests/blender/**` | `scripts/run-blender-tests.sh` | Exit code 0 |
| `gate-ue-automation` | Diff touches `plugins/nmg-game-dev-ue-plugin/Source/**/*.cpp` or `*.h` | `scripts/run-ue-tests.sh` | Exit code 0 |
| `gate-skill-schema` | Diff touches `skills/**/SKILL.md` | `scripts/validate-skills.py` | Exit code 0 AND every SKILL.md parses |
| `gate-mcp-schema` | Diff touches `mcp-servers/**` | `scripts/validate-mcp-tools.py` | Exit code 0 |
| `gate-shellcheck` | Diff touches `**/*.sh` | `shellcheck -S style scripts/*.sh` | Exit code 0 |
| `gate-markdown-lint` | Diff touches `**/*.md` | `markdownlint docs/ steering/ *.md` | Exit code 0 |
| `gate-ship-smoke` | Diff touches `skills/build-*/` or `skills/ship/**` or UE plugin runtime | `scripts/ship-smoke.sh` | Exit code 0 — dry run of `/ship` on fixture project succeeds |

Skipping a gate that applies requires an explicit `verify-skip: <gate-name>` note in the spec's `tasks.md` with a justification. `/verify-code` surfaces skipped gates in the PR body.

### Condition Evaluation Rules

- `Always` — gate always applies.
- `{path} directory exists` — `test -d {path}`.
- `{glob} files exist in {path}` — glob probe.
- `Diff touches {glob}` — `git diff --name-only` intersects the glob.

### Pass Criteria Evaluation Rules

- `Exit code 0` — the Action command exits 0.
- `{file} file generated` — named file exists post-command.
- `output contains "{text}"` — stdout/stderr contains the text.
- Compound criteria use `AND`.

---

## Environment Variables

### Required (per capability)

| Variable | When needed |
|----------|-------------|
| `MESHY_API_KEY` | Any Meshy-sourced generation |
| `UE_ROOT` | Override if UE 5.7 isn't at the default Epic Games path |
| `BLENDER_BIN` | Override if Blender isn't on `$PATH` |
| `TEXTURE_GEN_*` | TBD — defined when the v1 spike picks the tool |
| `NOTARIZATION_APPLE_ID` / `_APP_SPECIFIC_PASSWORD` / `_TEAM_ID` | macOS notarization (`/ship macos` / `/ship ios`) |
| `IOS_PROVISIONING_PROFILE` | iOS builds |
| `ANDROID_HOME` / `ANDROID_KEYSTORE` / `ANDROID_KEYSTORE_PASSWORD` | Android builds |
| `WINDOWS_BUILD_HOST` / `_USER` / `_SSH_KEY` / `WINDOWS_REMOTE_PROJECT_PATH` | Windows remote builds |

### Optional

| Variable | Purpose |
|----------|---------|
| `NMG_GAME_DEV_CACHE_DIR` | Override the generation cache location |
| `NMG_GAME_DEV_LOG_LEVEL` | `debug` / `info` / `warn` / `error` |

---

## References

- `CLAUDE.md` for project overview (added when scaffolding lands).
- `steering/product.md` for product direction.
- `steering/structure.md` for code organization.
