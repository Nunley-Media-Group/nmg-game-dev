# Tasks: Consumer onboarding — onboard-consumer skill, asset contract install, and onboarding docs

**Issue**: #7
**Date**: 2026-10-29
**Status**: Approved
**Author**: Rich Nunley

## Implementation Tasks

### T001: Onboard package foundations

**File(s)**: `src/nmg_game_dev/onboard/__init__.py`, `src/nmg_game_dev/onboard/errors.py`, `src/nmg_game_dev/onboard/paths.py`, `src/nmg_game_dev/onboard/files.py`
**Type**: Create
**Depends**: none
**Acceptance**:
- `OnboardError`, `StepResult`, `framework_root` (from `CLAUDE_PLUGIN_ROOT` or the package location), and the `fixtures` / `.mcp.json` exclusion guard behave per design (FR1, FR8, AC7)
- `sync_file` / `sync_tree` report installed, unchanged, drift, or refreshed and keep the executable bit (FR9)

### T002: Settings and agent-instruction merges

**File(s)**: `src/nmg_game_dev/onboard/settings.py`, `src/nmg_game_dev/onboard/instructions.py`
**Type**: Create
**Depends**: T001
**Acceptance**:
- SessionStart hooks from `templates/consumer/.claude/settings.json` are merged without duplicates, and unrelated keys are preserved (FR3, AC1, AC8)
- `.claude/settings.local.json` env merge sets `TEXTURE_GEN_MODELS_DIR` and `HF_HOME` (FR7, AC4)
- The marked `CLAUDE.md` / `AGENTS.md` block is added once and replaced in place (FR4, AC1, AC8)

### T003: Unreal setup

**File(s)**: `src/nmg_game_dev/onboard/unreal.py`
**Type**: Create
**Depends**: T001
**Acceptance**:
- `.uproject` merge enables `ModelContextProtocol`, `EditorToolset`, `VibeUE`, and `nmg-game-dev`, keeping other entries and fields (FR5, AC2)
- The ini merge sets `bAutoStartServer=True` and adds `ServerPortNumber=8000` only when absent (FR5, AC2)
- VibeUE is cloned at `v5.0-ue5.8`, checked against commit `bc7bc45c1e2025123778560f45c15d1f8e1be41d`, and refreshed per design (FR5, FR9, AC2, AC9)

### T004: Blender add-on link

**File(s)**: `src/nmg_game_dev/onboard/blender.py`
**Type**: Create
**Depends**: T001
**Acceptance**:
- Creates `<BLENDER_EXTENSIONS_DIR>/nmg_game_dev_blender_addon` → `plugins/nmg-game-dev-blender-addon`; a correct existing link is unchanged; a wrong target is drift and is replaced only with `--refresh` (FR6, AC3, AC8, AC9)

### T005: Texture models and volume listing

**File(s)**: `src/nmg_game_dev/onboard/textures.py`, `src/nmg_game_dev/onboard/volumes.py`
**Type**: Create
**Depends**: T001
**Acceptance**:
- Missing models are installed sequentially with the exact `mflux-save` commands and `HF_HOME`; `uv tool install mflux==0.24.0` runs only when `mflux-save` is absent; installed models are skipped (FR7, AC4, AC8)
- The platform and 60 GiB free-space checks raise `onboard.unsupported_platform` / `onboard.insufficient_disk` (AC5)
- `list_volumes` returns mount, free bytes, and `fits_models` (AC6)

### T006: Onboard runner and CLI

**File(s)**: `src/nmg_game_dev/onboard/runner.py`, `src/nmg_game_dev/onboard/__main__.py`
**Type**: Create
**Depends**: T002, T003, T004, T005
**Acceptance**:
- Preflight (uproject, models dir, platform, disk, framework sources) runs before any consumer write; failures exit 1 with `ERROR [onboard.*]` and a remediation (FR2, AC5)
- Steps run in the design order, copying the start scripts, asset contract, and UE plugin, and the report lists every step with status and remediation; drift exits 0 (FR1, FR9, AC1, AC2, AC8, AC9)
- `volumes` prints the JSON list (AC6)

### T007: Skill, references, docs, and links

**File(s)**: `skills/onboard-consumer/SKILL.md`, `skills/onboard-consumer/references/install-steps.md`, `docs/onboarding/index.md`, `docs/onboarding/first-asset.md`, `docs/onboarding/first-ship.md`, `docs/onboarding/upgrading.md`, `CLAUDE.md`, `README.md`, `templates/consumer/README.md`, `CHANGELOG.md`
**Type**: Create | Modify
**Depends**: T006
**Acceptance**:
- `SKILL.md` frontmatter has `name: onboard-consumer`, a one-line `description`, `required_mcp: []`, `required_env`, and `unattended_safe: true`; its flow covers the disk question, the autopilot path, `install`, and `--refresh` (FR10, AC6, AC11)
- `references/install-steps.md` documents every consumer write from the design table
- The docs have the AC10 content; `CLAUDE.md`, `README.md`, and `templates/consumer/README.md` link to `docs/onboarding/index.md` / the skill (FR10, AC10)
- `CHANGELOG.md` `[Unreleased]` gets a bullet for consumer onboarding ending with `(#7)`
- The registered `plugin.validate` validation passes

### T008: Unit tests for onboarding

**File(s)**: `tests/unit/onboard/__init__.py`, `tests/unit/onboard/conftest.py`, `tests/unit/onboard/test_settings.py`, `tests/unit/onboard/test_instructions.py`, `tests/unit/onboard/test_unreal.py`, `tests/unit/onboard/test_blender.py`, `tests/unit/onboard/test_textures.py`, `tests/unit/onboard/test_runner.py`, `tests/unit/onboard/test_docs_and_skill.py`
**Type**: Create
**Depends**: T006, T007
**Acceptance**:
- `conftest.py` builds a fixture consumer (`Game.uproject`, unrelated settings, `CLAUDE.md`) in a temp dir. It also puts stub `git`, `mflux-save`, and `uv` executables on `PATH` that log argv; the stub `git clone` writes `VibeUE.uplugin`, and `rev-parse HEAD` echoes a configurable sha. Host facts and `disk_usage` are injected
- Covers AC1–AC9: files and hooks installed, exclusions, no `_API_KEY` env, UE plugin/clone/uproject/ini, Blender link, model commands and skips, each prerequisite failure leaving the consumer unchanged, two framework roots giving identical trees, the second run being a no-op, and drift reported then repaired by `--refresh` with `nmg-budgets.json` untouched
- `test_docs_and_skill.py` covers AC10 and AC11 (required files, links, frontmatter)
- Passes under the `repository.tests`, `repository.lint`, and `repository.types` validations

### T009: BDD acceptance scenarios for onboarding

**File(s)**: `tests/bdd/features/onboard_consumer.feature`, `tests/bdd/test_onboard_bdd.py`
**Type**: Create
**Depends**: T008
**Acceptance**:
- `onboard_consumer.feature` contains the eleven scenarios from this spec's `feature.gherkin` (`@SCN001`–`@SCN011`), each bound with `@scenario` and implemented with the T008 fixtures
- Passes under the `repository.tests` validation

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #7 | 2026-10-29 | Initial feature tasks |
