# nmg-game-dev Technical Steering

This document defines the technology stack, constraints, and integration standards.
All technical decisions should align with these guidelines. Section names below are
load-bearing — nmg-sdlc matches on them literally.

---

## Architecture Overview

```
Developer in Claude Code
        │
        │  natural language; the agent authors freeform
        ▼
┌────────────────────────────────────────────────────────────┐
│ nmg-game-dev Claude Code plugin                            │
│   skills/ + agent tools: texture gen, validate, bake,      │
│   variants, export, re-import check, UE import, ship       │
└───────┬───────────────────────────────────┬────────────────┘
        │                                   │
        ▼                                   ▼
┌──────────────────────┐          ┌──────────────────────────┐
│ Blender MCP          │          │ Unreal MCP               │
│ (+ nmg add-on)       │          │ Epic native MCP (5.8)    │
│                      │          │ + VibeUE expansion       │
└──────┬───────────────┘          └──────┬───────────────────┘
       │                                 │
       ▼                                 ▼
┌──────────────────────┐          ┌──────────────────────────┐
│ Blender 5.2 LTS      │          │ UE 5.8                   │
│ (GUI session +       │          │ (editor + runtime;       │
│  background jobs)    │          │  level composition)      │
└──────┬───────────────┘          └──────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────┐
│ Local texture models (mflux, 4-bit)      │
│ Z-Image Turbo, FLUX.2 klein 4B;          │
│ procedural Blender materials as fallback │
└──────────────────────────────────────────┘

        Consumer project (e.g., ghost1)
        │
        ▼
┌────────────────────────────────────────────────────────────┐
│ Installed artifacts from nmg-game-dev                      │
│   • Claude Code plugin (skills + MCP configs)              │
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
| Distribution | Claude Code plugin from the `nmg-plugins` marketplace (what nmg-game-dev SHIPS) | targets current Claude Code |
| Host tooling | Python | 3.11+ (matches Blender bundled python) |
| Authoring surface | Blender | 5.2 LTS (latest LTS) |
| Game engine | Unreal Engine | 5.8 (Apple Silicon native) |
| UE plugin source | C++ (+ Blueprints for composition) | Epic coding standard |
| Shell scripts | bash | `set -euo pipefail`; shellcheck-clean |
| Asset authoring | Blender 5.2 through the Blender MCP (`mcp-for-blender`, published from `ahujasid/blender-mcp`), driven freeform by the agent | latest release (`uvx mcp-for-blender@latest`); never pinned |
| UE control | Epic's native Unreal MCP server on UE 5.8 (`127.0.0.1:8000/mcp`, `ModelContextProtocol` + `EditorToolset`), expanded by the VibeUE plugin | VibeUE latest (`scripts/install-vibeue.sh`); never pinned; NMG does NOT author its own UE-side bridge |
| Texture generation | Local models via mflux (Z-Image Turbo, FLUX.2 klein 4B, 4-bit) | optional install; procedural Blender materials as fallback |

### External Services

| Service | Purpose | Notes |
|---------|---------|-------|
| Apple Notary Service | macOS notarization of shipped builds | Team ID + app-specific password |
| Apple Developer | iOS provisioning | `.mobileprovision` via env |
| Google Play | Android AAB upload | Keystore + password via env |
| GitHub | Source + issue + PR automation | `gh` CLI |
| CodeRabbit | Automated PR review and merge gating | GitHub App `coderabbitai`; required status context `CodeRabbit` |

### Automated Review

nmg-sdlc's automated PR review handling reads this section to decide which PR
review threads it may address. Treat threads whose author satisfies either
predicate below as in-scope; all other threads, including human reviewers, are
out of scope and left unresolved for human follow-up.

| Predicate | Default | Description |
|-----------|---------|-------------|
| `bots` | `false` | When `true`, any thread whose first comment has `author.__typename == "Bot"` is eligible |
| `logins` | `["coderabbitai"]` | Explicit GitHub login allow-list for automated reviewers; CodeRabbit posts as `coderabbitai` |

Modify the defaults above to change automated-review eligibility without a skill
or script change. If this section is missing or malformed,
nmg-sdlc fails closed and treats every review thread as
out of scope.

---

## Versioning

The `VERSION` file (plain text semver at project root) is the **single source of truth** for the project's current version. Stack-specific files are kept in sync via the mapping table below.

| File | Path | Notes |
|------|------|-------|
| `VERSION` | (entire file) | Plain semver, one line |
| `.claude-plugin/plugin.json` | `version` | Claude Code plugin manifest |
| `plugins/nmg-game-dev-blender-addon/blender_manifest.toml` | `version` | Blender extension manifest |
| `plugins/nmg-game-dev-ue-plugin/nmg-game-dev.uplugin` | `VersionName` | UE plugin manifest |

### Path Syntax

- **JSON files**: dot-notation (e.g., `version`, `packages.mylib.version`).
- **TOML files**: dot-notation matching TOML keys (e.g., `project.version`).
- **`pyproject.toml` `project.version`**: not listed — the version is `dynamic`, and hatchling derives it from `VERSION` (`[tool.hatch.version] path = "VERSION"`). No bump rewrites it, and no lockfile records it.
- **Plain text**: `line:N` or omit Path if the whole file is the version.
- **Blender add-on `bl_info.version`**: not listed — `__init__.py` derives it from `VERSION` at import time via `utils.version.version_tuple()`, so it never needs rewriting.

### Version Bump Classification

`/sdlc-open-pr` and the `sdlc-runner.mjs` deterministic bump postcondition read this table.

| Label | Bump Type | Description |
|-------|-----------|-------------|
| `bug` | patch | Bug fix — backwards-compatible |
| `enhancement` | minor | New feature — backwards-compatible |
| `feature` | minor | New feature — backwards-compatible |
| `docs` | patch | Documentation-only change |

**Default**: if no label matches, bump type is **minor**.

**Major bumps are manual-only** — `/sdlc-open-pr #N --major`. Unattended runs never apply a major bump.

**Breaking changes use minor bumps.** Communicate with `**BREAKING CHANGE:**` prefix in CHANGELOG entries and a `### Migration Notes` sub-section.

Pre-1.0: breaking changes are allowed inside minor bumps without a major gate. The framework is pre-release until the first consumer project (ghost1) is fully migrated to nmg-game-dev.

---

## Technical Constraints

### Performance (authoring)

| Metric | Target | Rationale |
|--------|--------|-----------|
| Finalize a standard prop (validate → UE import, both variants) | ≤ 90 s on M-series Mac | Adhoc iteration requires tight loops |
| Finalize a hero asset or character | ≤ 5 min on M-series Mac | Bakes dominate; budget is generous but bounded |
| One local AI texture (1024 px) | ≤ 30 s (klein 4B) / ≤ 100 s (Z-Image Turbo) | Measured with 4-bit weights on an M1 Max |
| `/build-platform desktop` cold build | ≤ 20 min | Includes UE cook + sign + notarize |
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
| Credential storage | `.claude/settings.local.json` `env` (gitignored) for session-local overrides; production uses keychain / CI secrets |
| Signing identities | Read from OS keychain (macOS) or env (`ANDROID_KEYSTORE_PASSWORD`); never echoed to logs |
| Third-party MCP trust | Third-party tools (Blender MCP, its add-on, VibeUE) track their latest releases and are never pinned; `scripts/smoke-blender-mcp.py` and `scripts/smoke-unreal-mcp.py` verify that the latest versions work together |
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
- Onboarding docs lead with a flow, not an API reference.

---

## API / Interface Standards

### Skill contract

Every consumer-facing skill MUST:

1. Have a one-line `description` that fits in the Claude Code skills list.
2. Declare its required MCP servers in its frontmatter.
3. Fail fast with an actionable error if a required env var or MCP is missing.
4. Be idempotent — safe to rerun on partial failure.
5. Respect unattended runs (`NMG_SDLC_AUTOPILOT=1`: no prompts; fall back to documented defaults).

### MCP server contract

Every nmg-game-dev-authored MCP server MUST:

1. Expose tools with stable names — changes go through the deprecation window.
2. Return structured errors (`error.code`, `error.message`, `error.remediation`).
3. Log to stderr only — stdout is the MCP channel.
4. Handle cancellation / timeout gracefully (clean up partial state).

### Session-start contract (Blender MCP + Unreal MCP auto-launch)

Neither Blender nor Unreal Editor boot themselves when a Claude Code session starts, and every downstream skill assumes their MCP endpoints are already reachable. nmg-game-dev owns this bootstrap and distributes it to consumer projects via the Claude Code plugin.

The framework ships two idempotent launch scripts, wired as `SessionStart` hooks in every consumer's `.claude/settings.json` by the onboarding skill. The MCP servers come from the plugin's bundled `.mcp.json`, so consumers need no separate MCP config.

| Script | Responsibility | Port |
|--------|----------------|------|
| `start-blender-mcp.sh` | Launches Blender (via `BLENDER_BIN` or `BLENDER_APP` env) with the Blender MCP add-on enabled; registers a deferred timer to start the socket server after the UI is ready. | `BLENDER_MCP_PORT` (default 9876) |
| `start-unreal-mcp.sh` | Launches UE Editor with the consumer's `.uproject`; Epic's native Unreal MCP server auto-starts and **VibeUE** (installed by `onboard-consumer`) registers its tools on it. nmg-game-dev's UE plugin contributes Runtime helpers + Editor authoring hooks but does NOT bind any port. | `UE_MCP_PORT` (default 8000) |

**Contract invariants** (every launch script MUST honor):

1. **Idempotent** — if the target port is already `LISTEN`, exit 0 immediately. No double-launch.
2. **Detached** — `nohup … & disown`; return to the shell (and Claude Code) in under the hook timeout.
3. **Actionable failure** — exit non-zero with a one-line remediation hint if the binary or project file is missing.
4. **Path resolution** — prefer env-var overrides (`BLENDER_BIN`, `UE_ROOT`, `BLENDER_APP`), fall back to documented defaults, never hard-code the reference-project location.
5. **Logs** — stdout/stderr to `/tmp/<tool>-mcp.log`; path is documented in the skill that consumes it so failure triage is copy-paste.
6. **Plugin/addon discovery** — the Blender script probes multiple candidate addon names (Extensions system `bl_ext.*` and legacy folder names) and enables the first one installed. The UE script relies on the nmg-game-dev UE plugin being enabled in the consumer's `.uproject`.

The onboarding skill (one of the v1 deliverables) installs these scripts into each consumer's `scripts/` directory, and merges the `SessionStart` hook entries into `.claude/settings.json`. Without this auto-launch path, the adhoc workflow is broken on every cold session.

### Texture generation interface

Local texture backends (#7) share one interface, used by the agent while authoring and by tests. Z-Image Turbo and FLUX.2 klein 4B are the only texture models; the registry is closed to others.

```
Inputs:  prompt: str, backend: "z-image-turbo" | "flux2-klein-4b" | "both", resolution: int, seeds: list[int] | None
Outputs: seamless albedo PNG paths (+ comparison sheet for "both"); derived normal / roughness / metallic / AO on request;
         written to SourceArt/Textures/Generated/<name>/ (override NMG_GAME_DEV_TEXTURE_DIR)
Entry:   python -m nmg_game_dev.texture generate (blocking) or the texture-gen MCP tools generate_textures + get_texture_job (start + poll)
Errors:  TextureGenError with .code and .remediation
```

Whatever the agent authors, the bake step (#67) turns it into the contract's texture sets, proofed in Blender before export.

### Long-running Blender work

MCP calls time out (180 s for the Blender MCP), so bakes, variant generation, and full finalize runs never run inside one. The job runner starts detached as `python -m nmg_game_dev.finalize run-job <job_dir>`. It checkpoints the open session's scene with `save_as_mainfile(copy=True)`, runs each Blender step in its own `blender --background` process against that checkpoint, and writes progress the agent can poll. The `finalize` MCP tools (`finalize_asset`, `run_finalize_step`, and `get_finalize_job`) and the CLI (`python -m nmg_game_dev.finalize`) share that one implementation. Each MCP tool returns a job id at once, or the finished result when the job completes within `wait_seconds` (at most 150).

Load-back rule: after the Blender steps pass, the baked `<Name>` and `<Name>_Mobile` collections replace the session's copies only when the session's `<Name>` is unchanged since the checkpoint. Otherwise nothing is replaced, the run reports `finalize.session_changed` with the result `.blend` path, and `loaded_back` is false. A crashed background step fails with `finalize.job_crashed` and leaves the session unchanged.

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
# tests/bdd/features/finalize.feature
Feature: Finalize an authored asset
  As an NMG game developer
  I want a finished Blender asset turned into Desktop and Mobile variants in Unreal
  So that I can iterate on content without leaving Claude Code

  Scenario: Standard prop authored in Blender
    Given the Blender MCP is running
    And a collection "Crate" that satisfies the asset contract
    When I finalize "Crate" in category "Props"
    Then both Desktop and Mobile variants exist under Content/Props/Crate/
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

`steering/manifest.json` registers every gate, and `/sdlc-verify-code` runs only what it registers. This table mirrors those registrations. Every gate is required: when its condition matches the change, verification cannot pass until the gate passes, and no spec note can skip it.

| Validation id | Applies when the change touches | Runs | Host prerequisite |
|---------------|---------------------------------|------|-------------------|
| `repository.tests` | anything | `uv run pytest tests/unit tests/bdd -q` | — |
| `repository.lint` | anything | `uv run ruff check .` | — |
| `repository.format` | anything | `uv run ruff format --check .` | — |
| `repository.types` | anything | `uv run mypy src tests` | — |
| `gate-blender-headless` | `plugins/nmg-game-dev-blender-addon/**`, `tests/blender/**`, `scripts/blender/**`, `scripts/run-blender-tests.sh` | `scripts/run-blender-tests.sh` (headless Blender pytest) | Blender 5.2. When it is not at `/Applications/Blender.app`, export `BLENDER_APP` (or `BLENDER_BIN`) in `~/.zshenv`; the gate forwards only those two variables |
| `gate-ue-compile` | `plugins/nmg-game-dev-ue-plugin/Source/**`, `plugins/nmg-game-dev-ue-plugin/*.uplugin`, `fixtures/Source/**`, `fixtures/dogfood.uproject` | extension `project.ue-compile`: the engine `Build.sh DogfoodEditor Mac Development` for `fixtures/dogfood.uproject`, which compiles the UE plugin and its automation specs | UE 5.8 (`UE_ROOT` overrides the default path); VibeUE in `fixtures/Plugins/` from `scripts/install-vibeue.sh`; no Live Coding session open on the dogfood project |
| `gate-mcp-schema` | `mcp-servers/**`, `scripts/validate-mcp-tools.py` | `uv run python scripts/validate-mcp-tools.py` | — |
| `gate-shellcheck` | `scripts/**.sh` | `shellcheck -S style` on every `scripts/**.sh` (through `find -exec`) | shellcheck |
| `gate-ship-smoke` | `skills/ship/**`, `src/nmg_game_dev/ship/**`, `scripts/build-*.sh`, `scripts/sign-macos.sh`, `scripts/notarize-macos.sh`, `scripts/verify-cook-manifest.sh`, `scripts/ship-smoke.sh` | `scripts/ship-smoke.sh`: a dry-run ship of the fixture with placeholder credentials; no UE build | — |
| `plugin.validate` | `.claude-plugin/**`, `.mcp.json`, `skills/**`, `agents/**`, `commands/**`, `hooks/**`, `templates/consumer/**` | `claude plugin validate .` | — |
| `plugin.session-smoke` | the same paths as `plugin.validate` | extension `project.plugin-session-smoke`: loads this checkout with `--plugin-dir` and checks that its MCP servers connect | Herdr |

### Not gated yet

- **UE Automation** (`scripts/run-ue-tests.sh`). It writes its reports into tracked files under `tests/ue-automation/`, so running it dirties the tree in the middle of verification. `gate-ue-compile` compiles the specs but does not run them. Register `gate-ue-automation` once the reports move to an ignored path.
- **E2E pipeline** (`uv run pytest tests/e2e --runslow`). It drives live Blender, Unreal and texture MCPs. Run it by hand before a release.

Specs name these validation ids in their tasks. Do not cite the gates above as passing evidence unless the verification artifact recorded them.

---

## Environment Variables

### Required (per capability)

| Variable | When needed |
|----------|-------------|
| `UE_ROOT` | Override if UE 5.8 isn't at the default install path |
| `UE_PROJECT` | Override the `.uproject` that `start-unreal-mcp.sh` opens |
| `UE_MCP_PORT` / `BLENDER_MCP_PORT` | Override the MCP endpoint ports (defaults 8000 and 9876) |
| `BLENDER_BIN` / `BLENDER_APP` | Override if Blender isn't at the default install path |
| `TEXTURE_GEN_MODELS_DIR` / `HF_HOME` | Local texture model weights location (optional texture models) |
| `NOTARIZATION_KEYCHAIN_PROFILE` (preferred), or `NOTARIZATION_APPLE_ID` / `_APP_SPECIFIC_PASSWORD` / `_TEAM_ID` | macOS notarization (`/build-platform macos` / `/build-platform ios`) |
| `IOS_PROVISIONING_PROFILE` | iOS builds |
| `ANDROID_HOME` / `ANDROID_KEYSTORE` / `ANDROID_KEYSTORE_PASSWORD` | Android builds |
| `WINDOWS_BUILD_HOST` / `_USER` / `_SSH_KEY` / `WINDOWS_REMOTE_PROJECT_PATH` | Windows remote builds |

### Optional

| Variable | Purpose |
|----------|---------|
| `NMG_GAME_DEV_CACHE_DIR` | Override the finalize cache root (`by-key/`, `runs/`, and `jobs/` live under it) |
| `NMG_GAME_DEV_TEXTURE_DIR` | Override the generated-texture root (default `SourceArt/Textures/Generated`) |
| `TEXTURE_GEN_BLENDER_RESERVE_GB` | RAM kept free for Blender when checking whether a texture model fits (default 8) |
| `NMG_GAME_DEV_LOG_LEVEL` | `debug` / `info` / `warn` / `error` |

---

## References

- `CLAUDE.md` for project overview (added when scaffolding lands).
- `steering/product.md` for product direction.
- `steering/structure.md` for code organization.
