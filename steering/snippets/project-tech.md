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
│   variants, export, re-import check, Godot import, ship    │
└───────┬───────────────────────────────────┬────────────────┘
        │                                   │
        ▼                                   ▼
┌──────────────────────┐          ┌──────────────────────────┐
│ Blender MCP          │          │ src/nmg_game_dev/godot/  │
│ (+ nmg add-on)       │          │ godot --headless only:   │
│                      │          │ --import, -s probes,     │
│                      │          │ --check-only, --export-* │
└──────┬───────────────┘          └──────┬───────────────────┘
       │                                 │
       ▼                                 ▼
┌──────────────────────┐          ┌──────────────────────────┐
│ Blender 5.2 LTS      │          │ Godot 4 (latest stable)  │
│ (GUI session +       │          │ (headless; no editor     │
│  background jobs)    │          │  bridge, no engine MCP)  │
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
│   • Godot add-on game/addons/nmg_game_dev (runtime: the    │
│     NmgAssets variant resolver, the NmgLaunch launch       │
│     options + autoplay, the NmgVariantScene variant        │
│     loader, NmgBuild + NmgVersionLabel build version,      │
│     the NmgAudio player + NmgAudioTable name table,        │
│     NmgMissionDefinition, terrain shader)                  │
│     in the Godot project under game/                       │
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
| Game engine | Godot 4 (consumer project in `game/`, `game/project.godot`) | latest stable 4.x; never pinned |
| Runtime add-on source | GDScript (`plugins/nmg-game-dev-godot-addon/addons/nmg_game_dev/`) | statically typed; Godot style guide |
| Shell scripts | bash | `set -euo pipefail`; shellcheck-clean |
| Asset authoring | Blender 5.2 through the Blender MCP (`mcp-for-blender`, published from `ahujasid/blender-mcp`), driven freeform by the agent | latest release (`uvx mcp-for-blender@latest`); never pinned |
| Engine control | `godot --headless` only (`--import`, `--check-only`, `-s <script>`, `--export-release`), driven through `src/nmg_game_dev/godot/`; GDScript probes print one `NMG_RESULT {json}` line | resolved from `GODOT_BIN`, then `godot` on `PATH`, then `/Applications/Godot.app`; no live editor bridge and no engine MCP server |
| Audio encoding | ffmpeg (music → Ogg Vorbis for Godot) | latest; resolved from `FFMPEG_BIN`, then `PATH` |
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
| `plugins/nmg-game-dev-godot-addon/addons/nmg_game_dev/plugin.cfg` | `version` | Godot add-on manifest (`[plugin]` section) |

### Path Syntax

- **JSON files**: dot-notation (e.g., `version`, `packages.mylib.version`).
- **TOML files**: dot-notation matching TOML keys (e.g., `project.version`).
- **`pyproject.toml` `project.version`**: not listed — the version is `dynamic`, and hatchling derives it from `VERSION` (`[tool.hatch.version] path = "VERSION"`). No bump rewrites it, and no lockfile records it.
- **Plain text**: `line:N` or omit Path if the whole file is the version.
- **Godot `plugin.cfg`**: the `version` key of its `[plugin]` section, a quoted string.
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
| Finalize a standard prop (validate → Godot import, both variants) | ≤ 90 s on M-series Mac | Adhoc iteration requires tight loops |
| Finalize a hero asset or character | ≤ 5 min on M-series Mac | Bakes dominate; budget is generous but bounded |
| One local AI texture (1024 px) | ≤ 30 s (klein 4B) / ≤ 100 s (Z-Image Turbo) | Measured with 4-bit weights on an M1 Max |
| `/ship desktop` cold export | ≤ 20 min | Includes Godot export + sign + notarize |
| Skill cold-start (first invocation per session) | ≤ 2 s | MCP handshake + env validation only |

### Performance (runtime — shipped Godot add-on code)

| Metric | Target | Rationale |
|--------|--------|-----------|
| Any per-frame hook added by nmg-game-dev's Godot add-on | ≤ 0.1 ms on iPhone 15-tier hardware | Shipped overhead must be near-zero |
| Memory footprint of the Godot add-on | ≤ 4 MB resident | Mobile RAM is the limiting resource |

### Security

| Requirement | Implementation |
|-------------|----------------|
| Authentication (to external services) | API keys via env vars; never in git |
| Credential storage | `.claude/settings.local.json` `env` (gitignored) for session-local overrides; production uses keychain / CI secrets |
| Signing identities | Read from OS keychain (macOS) or env (`ANDROID_KEYSTORE_PASSWORD`); never echoed to logs |
| Third-party tool trust | Third-party tools (Blender MCP, its add-on, Godot) track their latest releases and are never pinned; `scripts/smoke-blender-mcp.py` verifies that the latest Blender MCP and add-on work together, and `gate-godot-headless` runs the add-on tests on the latest stable Godot |
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

### GDScript (Godot add-on and probes)

- Godot's GDScript style guide: tabs, `snake_case` functions and files, `PascalCase` `class_name`.
- Static typing on every variable, parameter, and return value.
- Probes are `extends SceneTree` scripts that read a params JSON path after `--`, print exactly one
  `NMG_RESULT {json}` line, and `quit(0)`.
- Runtime code is budget-sensitive (see Runtime Performance above).
- Everything must run under `godot --headless`; nothing may assume an open editor.

### Shell

- `#!/usr/bin/env bash` shebang.
- `set -euo pipefail` at the top of every script.
- shellcheck-clean (CI enforces).
- No bashisms in scripts that must run cross-shell.

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

### Session-start contract (Blender MCP auto-launch)

Blender does not boot itself when a Claude Code session starts, and every authoring skill assumes the
Blender MCP endpoint is already reachable. nmg-game-dev owns this bootstrap and distributes it to
consumer projects via the Claude Code plugin. Godot needs no session-start launch: every Godot stage
runs `godot --headless` on demand and exits.

The framework ships one idempotent launch script, wired as a `SessionStart` hook in every consumer's
`.claude/settings.json` by the onboarding skill. The MCP servers come from the plugin's bundled
`.mcp.json`, so consumers need no separate MCP config.

| Script | Responsibility | Port |
|--------|----------------|------|
| `start-blender-mcp.sh` | Launches Blender (via `BLENDER_BIN` or `BLENDER_APP` env) with the Blender MCP add-on enabled; registers a deferred timer to start the socket server after the UI is ready. | `BLENDER_MCP_PORT` (default 9876) |

**Contract invariants** (the launch script MUST honor):

1. **Idempotent** — if the target port is already `LISTEN`, exit 0 immediately. No double-launch.
2. **Detached** — `nohup … & disown`; return to the shell (and Claude Code) in under the hook timeout.
3. **Actionable failure** — exit non-zero with a one-line remediation hint if the binary is missing.
4. **Path resolution** — prefer env-var overrides (`BLENDER_BIN`, `BLENDER_APP`), fall back to documented defaults, never hard-code the reference-project location.
5. **Logs** — stdout/stderr to `/tmp/<tool>-mcp.log`; path is documented in the skill that consumes it so failure triage is copy-paste.
6. **Add-on discovery** — the script probes multiple candidate add-on names (Extensions system `bl_ext.*` and legacy folder names) and enables the first one installed.

The onboarding skill installs this script into each consumer's `scripts/` directory, and merges the
`SessionStart` hook entry into `.claude/settings.json`. Without this auto-launch path, the adhoc
workflow is broken on every cold session.

### Texture generation interface

Local texture backends (#7) share one interface, used by the agent while authoring and by tests. Z-Image Turbo and FLUX.2 klein 4B are the only texture models; the registry is closed to others.

```
Inputs:  prompt: str, backend: "z-image-turbo" | "flux2-klein-4b" | "both", resolution: int, seeds: list[int] | None
Outputs: seamless albedo PNG paths (+ comparison sheet for "both"); derived normal / roughness / metallic / AO on request;
         written to SourceArt/Textures/Generated/<name>/ (override NMG_GAME_DEV_TEXTURE_DIR)
Entry:   python -m nmg_game_dev.texture generate (blocking) or the texture-gen MCP tools generate_textures + get_texture_job (start + poll)
Errors:  TextureGenError with .code and .remediation
```

The same models also generate 2D game art (#253): icons, UI art, and paintings. Art takes are not tiled and get no maps.

```
Inputs:  kind: "icon" | "ui" | "painting", name: str, prompt: str, seeds: list[int] | None, backend (one model, not "both"),
         aspect: "1:1" (icon, ui) | "16:9" | "3:2" | "1:1" (painting), resolution: int; SourceArt/Art/style.json adds the project style
Outputs: raw takes SourceArt/Art/raw/<kind>/<Name>-<seed>.png + <Name>.json manifest + contact sheet;
         finishing writes game/assets/UI/{Icons,Panels,Paintings}/<Name>.png
Entry:   python -m nmg_game_dev.texture art / art-finish, or the texture-gen MCP tools generate_art (start; poll get_texture_job) + finish_art
Errors:  TextureGenError with .code and .remediation (texture.*, art.*)
```

Whatever the agent authors, the bake step (#67) turns it into the contract's texture sets, proofed in Blender before export.

### Ship flow

`/ship <target>` (`python -m nmg_game_dev.ship <target> --project game/project.godot`) exports the
consumer's Godot project through the presets in `game/export_presets.cfg`, which `/onboard-consumer`
writes. Targets are `macos`, `ios`, `android`, `windows`, `web`, and the groups `desktop`, `mobile`,
and `all`.

1. Gates: `godot --headless --import` first (a fresh clone has no `.godot/` class cache; any
   `ERROR:` line fails with `ship.import_failed`), then `--check-only` on every `.gd`,
   `game/tests/run_tests.gd` when it exists, and the mobile budget gate for `ios`, `android`, and
   `web`.
2. Export: `godot --headless --path game --export-release "<preset>" <out>` per platform. The iOS,
   Android, and Web presets exclude every `assets/*/Desktop/*` folder; the macOS and Windows presets
   exclude every `assets/*/Mobile/*` folder.
3. macOS is signed and notarized by `scripts/sign-macos.sh` and `scripts/notarize-macos.sh`. Windows
   exports locally on the same host, with no remote build machine. The web target uses the
   Compatibility renderer with threads off and warns when `index.pck` is over 38 MB.
4. Artifacts land under `release/<platform>/` (`.app`, `.ipa`, `.aab`, `.exe`, and a web folder),
   listed with SHA-256 in `release/RELEASE-NOTES.md`. `--dry-run` prints every command with a
   `DRY-RUN:` prefix and runs no export.

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
| Godot runtime add-on | GDScript test runner under `godot --headless` | `plugins/nmg-game-dev-godot-addon/addons/nmg_game_dev/tests/test_*.gd` |
| Blender add-on | pytest + Blender headless | `tests/blender/` invoked via `blender --background --python` |
| End-to-end pipeline | pytest-bdd driving actual MCPs on fixture projects | `tests/e2e/` |
| Designer-facing acceptance | Gherkin `.feature` files used as manual QA scripts | `specs/<issue>/feature.gherkin` |

### Gherkin Feature Files

```gherkin
# tests/bdd/features/finalize.feature
Feature: Finalize an authored asset
  As an NMG game developer
  I want a finished Blender asset turned into Desktop and Mobile variants in Godot
  So that I can iterate on content without leaving Claude Code

  Scenario: Standard prop authored in Blender
    Given the Blender MCP is running
    And a collection "Crate" that satisfies the asset contract
    When I finalize "Crate" in category "Props"
    Then both Desktop and Mobile variants exist under game/assets/Props/Crate/
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
| Godot add-on | GDScript runner, headless Godot | `plugins/nmg-game-dev-godot-addon/addons/nmg_game_dev/tests/` | `scripts/run-godot-tests.sh` |
| E2E pipeline | pytest-bdd | `tests/e2e/` | `pytest tests/e2e/ --runslow` |

### Test Pyramid

```
        /\
       /  \  E2E pipeline (pytest-bdd driving real MCPs)
      /----\
     /      \ BDD acceptance (pytest-bdd + Blender headless + Godot headless)
    /--------\
   /          \ Component tests (per-MCP, per-skill)
  /            \
 /--------------\
/                \ Unit tests (Python logic, GDScript add-on tests)
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
| `gate-godot-headless` | `plugins/nmg-game-dev-godot-addon/**`, `src/nmg_game_dev/godot/**`, `tests/godot/**`, `scripts/run-godot-tests.sh` | `scripts/run-godot-tests.sh`: imports the `tests/godot/fixture/` project with the add-on (`--import`, no `ERROR:` lines), runs the add-on's `tests/run_tests.gd` (requiring the variant-routing tests to pass), checks `probe_asset.gd` on the fixture `Crate.glb` against `expected-probe.json`, runs `--check-only` on every `src/nmg_game_dev/godot/gd/*.gd`, checks `probe_anims.gd` on the fixture rig and its `animation_library` clips (one authored after frame 0) and `probe_terrain.gd` on a fixture terrain scene against `expected-anims.json` and `expected-terrain.json`, and smoke-runs the terrain meshes and audio probes. Every Godot run is bounded by `GODOT_GATE_TIMEOUT` (default 300 s) | Godot 4 via `GODOT_BIN` or `godot` on `PATH`; otherwise the script downloads the latest stable release, checked against its `SHA512-SUMS.txt`, into the git-ignored `.cache/godot/` and reuses it. The gate forwards only `GODOT_BIN` |
| `gate-mcp-schema` | `mcp-servers/**`, `scripts/validate-mcp-tools.py` | `uv run python scripts/validate-mcp-tools.py` | — |
| `gate-shellcheck` | `scripts/**.sh` | `shellcheck -S style` on every `scripts/**.sh` (through `find -exec`) | shellcheck |
| `gate-ship-smoke` | `skills/ship/**`, `src/nmg_game_dev/ship/**`, `scripts/sign-macos.sh`, `scripts/notarize-macos.sh`, `scripts/ship-smoke.sh`, `src/nmg_game_dev/godot/presets.py`, `tests/godot/**` | `scripts/ship-smoke.sh`: a dry-run `/ship all` of `tests/godot/fixture/project.godot` with placeholder credentials; no Godot export runs | — |
| `plugin.validate` | `.claude-plugin/**`, `.mcp.json`, `skills/**`, `agents/**`, `commands/**`, `hooks/**`, `templates/consumer/**` | `claude plugin validate .` | — |
| `plugin.session-smoke` | the same paths as `plugin.validate` | extension `project.plugin-session-smoke`: loads this checkout with `--plugin-dir` and checks that its MCP servers connect | Herdr |

### Not gated yet

- **E2E pipeline** (`uv run pytest tests/e2e --runslow`). It drives live Blender and texture MCPs and
  a real Godot binary. Run it by hand before a release.

Specs name these validation ids in their tasks. Do not cite the gates above as passing evidence unless the verification artifact recorded them.

---

## Environment Variables

### Required (per capability)

| Variable | When needed |
|----------|-------------|
| `GODOT_BIN` | Override if Godot 4 is not `godot` on `PATH` or at `/Applications/Godot.app` |
| `FFMPEG_BIN` | Override if ffmpeg is not on `PATH` (music imports encode Ogg Vorbis) |
| `BLENDER_MCP_PORT` | Override the Blender MCP endpoint port (default 9876) |
| `BLENDER_BIN` / `BLENDER_APP` | Override if Blender isn't at the default install path |
| `TEXTURE_GEN_MODELS_DIR` / `HF_HOME` | Local texture model weights location (optional texture models) |
| `NOTARIZATION_KEYCHAIN_PROFILE` (preferred), or `NOTARIZATION_APPLE_ID` / `_APP_SPECIFIC_PASSWORD` / `_TEAM_ID` | macOS signing and notarization (`/ship macos`) |
| `IOS_PROVISIONING_PROFILE` / `IOS_TEAM_ID` | iOS exports (`/ship ios`) |
| `ANDROID_KEYSTORE` / `ANDROID_KEYSTORE_PASSWORD` (`ANDROID_KEYSTORE_ALIAS` optional, default `upload`) | Android exports (`/ship android`) |

Windows and web exports run locally and need no extra variables.

### Optional

| Variable | Purpose |
|----------|---------|
| `NMG_GAME_DEV_CACHE_DIR` | Override the finalize cache root (`by-key/`, `runs/`, and `jobs/` live under it) |
| `NMG_GAME_DEV_TEXTURE_DIR` | Override the generated-texture root (default `SourceArt/Textures/Generated`) |
| `TEXTURE_GEN_BLENDER_RESERVE_GB` | RAM kept free for Blender when checking whether a texture model fits (default 8) |
| `NMG_GODOT_TIMEOUT_S` | Seconds any headless Godot run may take before it is stopped (default 900; `/ship` exports allow 3600) |
| `NMG_GAME_DEV_LOG_LEVEL` | `debug` / `info` / `warn` / `error` |

---

## References

- `CLAUDE.md` for project overview.
- `steering/snippets/project-product.md` for product direction.
- `steering/snippets/project-structure.md` for code organization.
