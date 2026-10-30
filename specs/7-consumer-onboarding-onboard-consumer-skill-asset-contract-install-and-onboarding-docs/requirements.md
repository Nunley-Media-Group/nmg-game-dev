# Requirements: Consumer onboarding — onboard-consumer skill, asset contract install, and onboarding docs

**Issue**: #7
**Date**: 2026-10-29
**Status**: Approved
**Author**: Rich Nunley

## User Story

**As an** NMG game developer starting or upgrading a consumer game project (e.g., ghost1)
**I want** one idempotent `onboard-consumer` skill and a short set of onboarding docs
**So that** my project gets the start scripts, SessionStart hooks, Unreal and Blender plugins, local texture models, and the asset contract in one run, and later re-runs tell me what has drifted

## Background

nmg-game-dev is a Claude Code plugin; its Blender and Unreal MCP servers ship in the plugin's bundled `.mcp.json`, so consumers need no MCP config of their own. The source artifacts onboarding places already exist:

- `scripts/start-blender-mcp.sh` and `scripts/start-unreal-mcp.sh`
- `templates/consumer/.claude/settings.json` (SessionStart hooks)
- `plugins/nmg-game-dev-ue-plugin/` and `plugins/nmg-game-dev-blender-addon/`
- `docs/asset-contract.md`

`skills/` has no onboarding skill and `docs/onboarding/` is empty.

Unreal setup is two layers on UE 5.8. Epic's Unreal MCP plugin (`ModelContextProtocol`) and `EditorToolset` provide the native MCP server, which auto-starts via `UModelContextProtocolSettings.bAutoStartServer`. VibeUE (`kevinpbuckley/VibeUE`, tag `v5.0-ue5.8`) registers its tools on that server.

Local texture generation uses two mflux models saved with 4-bit quantization: `z-image-turbo` (`Tongyi-MAI/Z-Image-Turbo`) and `flux2-klein-4b` (`black-forest-labs/FLUX.2-klein-4B`). Onboarding installs both on a disk the developer chooses.

## Acceptance Criteria

### AC1: Fresh onboarding installs the framework files

**Given** a consumer directory with one `.uproject`, an existing `.claude/settings.json` holding unrelated settings, and an existing `CLAUDE.md`
**When** `python -m nmg_game_dev.onboard install --consumer <dir> --models-dir <dir>` runs
**Then** `scripts/start-blender-mcp.sh` and `scripts/start-unreal-mcp.sh` are copied into `<consumer>/scripts/` and are executable
**And** the template's SessionStart hook group is merged into `.claude/settings.json`, and the unrelated settings are unchanged
**And** `docs/asset-contract.md` is installed at `<consumer>/docs/nmg-game-dev/asset-contract.md`, and `CLAUDE.md` (and `AGENTS.md` when present) gains one marked block that references it
**And** no `.mcp.json` is written, nothing from `fixtures/` (including `dogfood.uproject`) is written, and no settings file gains an environment variable whose name ends in `_API_KEY`

### AC2: Unreal plugins are installed and enabled

**Given** the same consumer and a `git` executable on `PATH`
**When** onboarding runs
**Then** the nmg-game-dev UE plugin is copied to `<consumer>/Plugins/nmg-game-dev/` (without `Binaries/` or `Intermediate/`)
**And** VibeUE is cloned with `git clone --depth 1 --branch v5.0-ue5.8 https://github.com/kevinpbuckley/VibeUE.git <consumer>/Plugins/VibeUE`
**And** the `.uproject` `Plugins` list has `ModelContextProtocol`, `EditorToolset`, `VibeUE`, and `nmg-game-dev` enabled, and its other entries and fields are kept
**And** `Config/DefaultEditorPerProjectUserSettings.ini` has `bAutoStartServer=True` under `[/Script/ModelContextProtocolEngine.ModelContextProtocolSettings]`, and `ServerPortNumber=8000` unless a port is already set there

### AC3: The Blender add-on is linked into Blender's extensions

**Given** `BLENDER_EXTENSIONS_DIR` points at a Blender `extensions/user_default` directory
**When** onboarding runs
**Then** `<BLENDER_EXTENSIONS_DIR>/nmg_game_dev_blender_addon` is a symlink to the framework's `plugins/nmg-game-dev-blender-addon`

### AC4: Local texture models are installed on the chosen disk

**Given** `--models-dir <dir>` on a volume with at least 60 GiB free, on an Apple Silicon Mac
**When** onboarding runs
**Then** `mflux-save --model z-image-turbo --quantize 4 --path <dir>/z-image-turbo-q4` and `mflux-save --model flux2-klein-4b --quantize 4 --path <dir>/flux2-klein-4b-q4` run one after the other, with `HF_HOME=<dir>/hf-cache`
**And** `mflux==0.24.0` is installed with `uv tool install` first if `mflux-save` is not on `PATH`
**And** `.claude/settings.local.json` `env` has `TEXTURE_GEN_MODELS_DIR=<dir>` and `HF_HOME=<dir>/hf-cache`
**And** a model whose `<dir>/<id>-q4` directory already exists is not saved again

### AC5: Texture prerequisites fail before anything changes

**Given** no `--models-dir` and no `TEXTURE_GEN_MODELS_DIR`, or a models dir whose volume has less than 60 GiB free while a model is missing, or a host that is not Apple Silicon macOS
**When** onboarding runs
**Then** it exits 1 with code `onboard.models_dir_missing`, `onboard.insufficient_disk`, or `onboard.unsupported_platform` and a remediation
**And** no file in the consumer directory has been created or changed

### AC6: The skill asks which disk to use

**Given** mounted volumes
**When** `python -m nmg_game_dev.onboard volumes` runs
**Then** it prints a JSON list of volumes with mount point, free bytes, and whether each has at least 60 GiB free
**And** `skills/onboard-consumer/SKILL.md` tells the agent to present the qualifying volumes with `AskUserQuestion` and to pass `<chosen volume>/nmg-texture-models` as `--models-dir`, using `TEXTURE_GEN_MODELS_DIR` without asking when `NMG_SDLC_AUTOPILOT=1`

### AC7: Install scope does not change the result

**Given** two copies of the framework root in different directories (one standing in for a user-scope plugin cache, one for a project-scope install)
**When** each onboards an identical fresh consumer
**Then** the two consumer trees are identical apart from the Blender symlink target, and no flag selects the scope
**And** the framework root comes from `CLAUDE_PLUGIN_ROOT` when set, otherwise from the package location

### AC8: Re-running is idempotent

**Given** a consumer that onboarding has already completed
**When** onboarding runs again without `--refresh`
**Then** there are no duplicate hook groups, `.uproject` plugin entries, ini keys, or `CLAUDE.md` blocks
**And** the Blender symlink is left intact, no `git clone` runs, and no `mflux-save` runs
**And** it exits 0

### AC9: Drift is reported and `--refresh` repairs it

**Given** an onboarded consumer whose `scripts/start-blender-mcp.sh`, installed asset contract, or `Plugins/nmg-game-dev/` differs from the framework, or whose `Plugins/VibeUE` HEAD is not the pinned commit, and which has a project-root `nmg-budgets.json`
**When** onboarding runs without `--refresh`
**Then** each differing item is listed as drift with the remediation `re-run with --refresh`, its content is unchanged, and the command exits 0
**And** `nmg-budgets.json` is neither reported nor changed
**When** onboarding runs with `--refresh`
**Then** the framework-owned copies are restored, VibeUE is checked out at the pinned commit, and `nmg-budgets.json` is unchanged

### AC10: Onboarding docs exist and are linked

**Given** the repository
**When** `docs/onboarding/` is read
**Then** `index.md` links to `first-asset.md`, `first-ship.md`, and `upgrading.md`
**And** `first-asset.md` covers prompting for an asset, the review loop, what the contract enforces, texture sources, budget overrides (`nmg-budgets.json`), and import into `Content/<Category>/<Name>/{Desktop,Mobile}/`
**And** `first-ship.md` walks through the `ship` skill on a fixture project, `upgrading.md` covers reviewing breaking changes, re-registering the plugin, and re-running onboarding with `--refresh`, and `CLAUDE.md` and `README.md` link to `docs/onboarding/index.md`

### AC11: The onboard-consumer skill is the entry point

**Given** the plugin checkout
**When** `skills/onboard-consumer/SKILL.md` is loaded
**Then** its frontmatter has `name: onboard-consumer`, a one-line `description`, `required_mcp: []`, `required_env`, and `unattended_safe: true`
**And** its flow runs `python -m nmg_game_dev.onboard install`, and the detailed copy/link/merge rules are in `skills/onboard-consumer/references/install-steps.md`

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | `python -m nmg_game_dev.onboard install --consumer DIR [--uproject P] [--models-dir D] [--refresh]` and `python -m nmg_game_dev.onboard volumes` | Must |
| FR2 | Preflight (uproject resolution, texture prerequisites, framework sources) completes before any consumer write | Must |
| FR3 | Copy the start scripts; merge the SessionStart hook template into `.claude/settings.json` idempotently, preserving other settings | Must |
| FR4 | Install the asset contract and a marked reference block in `CLAUDE.md` / `AGENTS.md`; never touch `nmg-budgets.json` | Must |
| FR5 | Copy the nmg-game-dev UE plugin, clone VibeUE at the pinned tag, enable the four plugins in the `.uproject`, and set MCP auto-start in `DefaultEditorPerProjectUserSettings.ini` | Must |
| FR6 | Symlink the Blender add-on into `BLENDER_EXTENSIONS_DIR` (default `~/Library/Application Support/Blender/5.2/extensions/user_default`) | Must |
| FR7 | Install both texture models with `mflux-save --quantize 4` on the chosen disk and record `TEXTURE_GEN_MODELS_DIR` / `HF_HOME` in `.claude/settings.local.json` | Must |
| FR8 | An explicit exclusion list keeps `fixtures/` and `.mcp.json` out of every consumer write | Must |
| FR9 | Detect drift of framework-owned copies and the VibeUE pin; `--refresh` restores them | Must |
| FR10 | `skills/onboard-consumer/SKILL.md` + `references/install-steps.md`; `docs/onboarding/{index,first-asset,first-ship,upgrading}.md`; links from `CLAUDE.md`, `README.md`, and `templates/consumer/README.md` | Must |
| FR11 | Tests onboard a fixture consumer twice, covering exclusion, merge, drift, scope, and prerequisite cases with stub `git`, `mflux-save`, and `uv` | Must |

## Out of Scope

- Changing the plugin's `.mcp.json` Unreal endpoint or `scripts/start-unreal-mcp.sh` defaults (#68)
- Texture generation, the backend registry, allowlist checks, and seamless post-processing (#65)
- Contract validation, variants, bake, and finalize behavior (#30, #33, #67, #69)
- Recipe or per-asset-type skills; hosted generation services

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #7 | 2026-10-29 | Initial feature spec |
