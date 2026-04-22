# Tasks: Scaffold plugin + repo + session-start hooks

**Issues**: #1, #2
**Date**: 2026-04-22
**Status**: Amended
**Author**: Rich Nunley

---

## Summary

This scaffolding issue has no backend service and no UI, so the standard 5-phase template (Setup / Backend / Frontend / Integration / Testing) is collapsed to the three phases that match the design's deliverable groups.

| Phase | Tasks | Status |
|-------|-------|--------|
| Setup — plugin identity + layout + Python package | 6 | [ ] |
| Integration — launchers + MCP config + consumer templates + dogfood | 5 | [ ] |
| Testing — BDD feature + steps + unit / leak-prevention checks | 5 | [ ] |
| **Total** | **16** | |

---

## Task Format

```
### T[NNN]: [Task Title]

**File(s)**: path/to/file
**Type**: Create | Modify | Delete
**Depends**: T[NNN], T[NNN] (or None)
**Acceptance**:
- [ ] verifiable criterion
```

File paths map to the canonical layout in `steering/structure.md` § Project Layout.

---

## Phase 1: Setup — plugin identity + layout + Python package

### T001: Create top-level directory skeleton with `.gitkeep` markers

**File(s)**:
- `plugins/nmg-game-dev-blender-addon/.gitkeep`
- `plugins/nmg-game-dev-ue-plugin/.gitkeep`
- `skills/.gitkeep`
- `commands/.gitkeep`
- `agents/.gitkeep`
- `mcp-servers/.gitkeep`
- `tests/unit/.gitkeep`
- `tests/bdd/features/.gitkeep`
- `tests/bdd/steps/.gitkeep`
- `tests/blender/.gitkeep`
- `tests/e2e/fixtures/.gitkeep`
- `docs/onboarding/.gitkeep`
- `docs/skills/.gitkeep`
- `docs/mcp/.gitkeep`
- `docs/contributing/.gitkeep`
- `docs/decisions/.gitkeep`
- `scripts/` (directory only — content in Phase 2)
- `fixtures/` (directory only — content in Phase 2)
- `templates/consumer/.claude/` (directory only — content in Phase 2)

**Type**: Create
**Depends**: None
**Acceptance**:
- [ ] Every top-level directory listed in `steering/structure.md` § Project Layout exists at the repo root.
- [ ] Directories with no other content in this issue carry a `.gitkeep` so they survive `git add`.
- [ ] `specs/`, `steering/`, `.claude-plugin/` are NOT re-created (already seeded / owned by later tasks respectively).
- [ ] `ls <dir>` on every created directory returns either the `.gitkeep` or the content committed by a later task in this issue.

### T002: Write `.claude-plugin/plugin.json`

**File(s)**: `.claude-plugin/plugin.json`
**Type**: Create
**Depends**: T001
**Acceptance**:
- [ ] Valid JSON; loads without error.
- [ ] Declares `name: "nmg-game-dev"`, `version: "0.1.0"`, `description`, `authors` (array with `{name: "Nunley Media Group"}`).
- [ ] Declares `capabilities.skills = "skills/"`, `.commands = "commands/"`, `.agents = "agents/"` — all relative paths (install-scope-invariant).
- [ ] No absolute paths anywhere in the file.
- [ ] If Claude Code exposes a `claude plugin validate` command, it exits 0. Otherwise `python -c "import json; json.load(open('.claude-plugin/plugin.json'))"` exits 0 AND required-key pytest (T015a) passes.

**Notes**: Use the shape from design.md § Artifact specifications #1. Drop the `$schema` field if Claude Code doesn't publish that URL — implementation task verifies.

### T003: Seed `VERSION` and `CHANGELOG.md`

**File(s)**: `VERSION`, `CHANGELOG.md`
**Type**: Create
**Depends**: T001
**Acceptance**:
- [ ] `VERSION` contains exactly `0.1.0\n` (one line, trailing newline).
- [ ] `CHANGELOG.md` has an `## [Unreleased]` heading and an `### Added` subsection referencing `#1`.
- [ ] No content from a pre-`0.1.0` state.

**Notes**: `/open-pr` will append to `[Unreleased]` on every subsequent PR. Format per `steering/tech.md` § Versioning + Keep-a-Changelog 1.1.0.

### T004: Write `CLAUDE.md` entry-point pointer doc

**File(s)**: `CLAUDE.md`
**Type**: Create
**Depends**: T001
**Acceptance**:
- [ ] Opens with a one-paragraph project summary aligned with `steering/product.md` § Mission.
- [ ] Links to `steering/product.md`, `steering/tech.md`, `steering/structure.md`.
- [ ] Mentions `/draft-issue` as the SDLC entry point.
- [ ] Does NOT duplicate content from steering docs (pointer-only).
- [ ] Explicitly notes install-scope invariance (AC11) so contributors understand the consumer-vs-this-repo distinction.

### T005: Write `pyproject.toml`

**File(s)**: `pyproject.toml`
**Type**: Create
**Depends**: T001
**Acceptance**:
- [ ] `[project]` block: `name = "nmg-game-dev"`, `version = "0.1.0"`, `description`, `readme = "CLAUDE.md"`, `requires-python = ">=3.11"`, `authors = [{ name = "Nunley Media Group" }]`, `license = { text = "Proprietary" }`.
- [ ] `[project.optional-dependencies].dev` includes `pytest>=8`, `pytest-bdd>=7`, `ruff>=0.4`, `mypy>=1.10`.
- [ ] `[build-system]` uses `hatchling`.
- [ ] `[tool.hatch.build.targets.wheel] packages = ["src/nmg_game_dev"]`.
- [ ] `[tool.ruff]` line-length 100, target-version py311, basic lint selects.
- [ ] `[tool.mypy]` strict mode, python_version 3.11.
- [ ] `pip install -e .[dev]` in a fresh venv succeeds (exit 0).
- [ ] `ruff check .` on the empty scaffold exits 0.

### T006: Create `src/nmg_game_dev/` package + submodule stubs

**File(s)**:
- `src/nmg_game_dev/__init__.py`
- `src/nmg_game_dev/pipeline/__init__.py`
- `src/nmg_game_dev/variants/__init__.py`
- `src/nmg_game_dev/quality/__init__.py`
- `src/nmg_game_dev/ship/__init__.py`

**Type**: Create
**Depends**: T005
**Acceptance**:
- [ ] Top-level `__init__.py` declares `__version__ = "0.1.0"` and has a one-line module docstring.
- [ ] Each submodule `__init__.py` has a one-line docstring and `from __future__ import annotations`.
- [ ] `python -c "import nmg_game_dev; import nmg_game_dev.pipeline; import nmg_game_dev.variants; import nmg_game_dev.quality; import nmg_game_dev.ship"` exits 0.
- [ ] `ruff check src/` exits 0.
- [ ] `mypy src/` exits 0.

---

## Phase 2: Integration — launchers + MCP config + consumer templates + dogfood

### T007: Write `scripts/start-blender-mcp.sh`

**File(s)**: `scripts/start-blender-mcp.sh`
**Type**: Create
**Depends**: T001
**Acceptance**:
- [ ] Shebang `#!/usr/bin/env bash` + `set -euo pipefail` at top.
- [ ] Executable bit set (`chmod +x`).
- [ ] Idempotent: when `BLENDER_MCP_PORT` (default 9876) is already `LISTEN`, exits 0 in ≤ 100 ms without invoking Blender.
- [ ] Resolves Blender via `BLENDER_BIN` → `BLENDER_APP/Contents/MacOS/Blender` → `/Applications/Blender.app/Contents/MacOS/Blender` default.
- [ ] When no Blender path resolves, exits 1 with a one-line remediation referencing `BLENDER_BIN`/`BLENDER_APP`.
- [ ] Uses `nohup … & disown` to detach; returns control in ≤ 2 s on cold launch.
- [ ] Stdout + stderr tee to `/tmp/blender-mcp.log`.
- [ ] Add-on discovery passes 4 candidates in order: `bl_ext.user_default.blender_mcp`, `bl_ext.user_default.blender-mcp`, `blender_mcp`, `blender-mcp`. Honors `BLENDER_MCP_ADDON` env override.
- [ ] `shellcheck -S style scripts/start-blender-mcp.sh` exits 0.

**Notes**: Bootstrap Python invocation (`bpy.ops.blender_mcp.start_server`) is a placeholder — may need adjustment when issue #2's add-on lands and its API is finalized. Document as a comment inside the script pointing at the design spec's open question.

### T008: Write `scripts/start-unreal-mcp.sh`

**File(s)**: `scripts/start-unreal-mcp.sh`
**Type**: Create
**Depends**: T001
**Acceptance**:
- [ ] Shebang + `set -euo pipefail` + executable bit.
- [ ] Idempotent: `UE_MCP_PORT` (default 8088, the port **VibeUE** binds inside UE) already `LISTEN` → exit 0 in ≤ 100 ms.
- [ ] Resolves UE editor via `UE_ROOT` (default `/Users/Shared/Epic Games/UE_5.7`) + fixed relative path `Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor`.
- [ ] Missing editor → exits 1 with remediation mentioning `UE_ROOT`.
- [ ] `UE_PROJECT` resolution: env → single `*.uproject` in `$PWD` → `$PWD/fixtures/dogfood.uproject` → fail with remediation.
- [ ] `nohup … & disown`; returns in ≤ 2 s.
- [ ] Logs to `/tmp/unreal-mcp.log`.
- [ ] `shellcheck -S style scripts/start-unreal-mcp.sh` exits 0.

### T009: Write root `.mcp.json` with pinned MCP servers

**File(s)**: `.mcp.json`
**Type**: Create
**Depends**: T001
**Acceptance**:
- [ ] Declares `mcpServers.blender`, `.unreal`, `.meshy`.
- [ ] Each server entry has a **pinned** version — no `latest`, no `main`, no `HEAD`, no floating tag. Verify by grep: `grep -E '(latest|main|HEAD)' .mcp.json` returns no hits.
- [ ] `blender` → ahujasid/blender-mcp at a specific released version (implementer resolves by inspecting the canonical distribution channel at implementation time).
- [ ] `unreal` → VibeUE at a specific released version (resolver checks PyPI / npm / git tag; records the chosen channel in the PR description).
- [ ] `meshy` → Meshy MCP at a specific released version; carries `env: { "MESHY_API_KEY": "${MESHY_API_KEY}" }`.
- [ ] No consumer-only or this-repo-only paths.
- [ ] `python -c "import json; json.load(open('.mcp.json'))"` exits 0.

**Notes**: Implementation task records the three pinned versions in the PR description for traceability. Pins are revisited in a future maintenance issue when Dependabot-equivalent tooling lands.

### T010: Create `templates/consumer/.claude/settings.json` + README

**File(s)**:
- `templates/consumer/.claude/settings.json`
- `templates/consumer/README.md`

**Type**: Create
**Depends**: T001, T007, T008
**Acceptance**:
- [ ] `templates/consumer/.claude/settings.json` declares a `hooks.SessionStart` entry with two `{ type: "command", command: "bash scripts/<launcher>.sh" }` entries referencing `start-blender-mcp.sh` and `start-unreal-mcp.sh` — both paths relative to the consumer's repo root.
- [ ] NO `.claude/settings.json` exists at this repo's root. Verify with `test ! -f .claude/settings.json`.
- [ ] `templates/consumer/README.md` explains: (a) this directory is a consumer-onboarding template, (b) `onboard-consumer` (future v1 issue) copies it into downstream projects, (c) why it lives here and not at repo root (link to `requirements.md` § "Scope of session-start hooks — consumer-game-only").
- [ ] Valid JSON (loads without error).

### T011: Create `fixtures/dogfood.uproject` + README

**File(s)**:
- `fixtures/dogfood.uproject`
- `fixtures/README.md`

**Type**: Create
**Depends**: T001
**Acceptance**:
- [ ] `fixtures/dogfood.uproject` is valid UE 5.7 project JSON: `FileVersion: 3`, `EngineAssociation: "5.7"`, `Modules: []`, `Plugins: []`, description referencing this issue's scope.
- [ ] `fixtures/README.md` warns in the first line that the fixture is **this-repo-only — MUST NOT ship to consumers**. References AC10.
- [ ] `start-unreal-mcp.sh` when invoked from the repo root (and no other `.uproject` present) resolves to this file via its `UE_PROJECT` fallback chain.

---

## Phase 3: Testing — BDD feature + steps + unit / leak-prevention checks

### T012: Author `specs/feature-scaffold-plugin-repo-session-start-hooks/feature.gherkin`

**File(s)**: `specs/feature-scaffold-plugin-repo-session-start-hooks/feature.gherkin`
**Type**: Create
**Depends**: (None — written during Phase 3 of `/write-spec`; task declared here for `/write-code` / `/verify-code` traceability)
**Acceptance**:
- [ ] Contains exactly one `Scenario` per acceptance criterion (AC1–AC11) — 11 scenarios minimum, plus the optional AC5b scenario → 12 total.
- [ ] Feature heading matches the spec title.
- [ ] Given/When/Then wording matches the AC verbatim where practical.
- [ ] Valid Gherkin syntax (loads without error via `gherkin` parser).

### T013: Mirror the feature file under `tests/bdd/features/`

**File(s)**: `tests/bdd/features/scaffold-plugin-repo-session-start-hooks.feature`
**Type**: Create
**Depends**: T012
**Acceptance**:
- [ ] Content matches `specs/.../feature.gherkin` (copy or symlink; copy preferred so pytest-bdd discovery works cross-platform).
- [ ] File is picked up by `pytest tests/bdd/` at collection time.

### T014: Implement pytest-bdd step definitions

**File(s)**: `tests/bdd/steps/test_scaffold.py` (pytest-bdd scenario+steps in one module; one step per Given/When/Then in the feature)
**Type**: Create
**Depends**: T002, T003, T004, T005, T006, T007, T008, T009, T010, T011, T013
**Acceptance**:
- [ ] Every scenario in `tests/bdd/features/scaffold-plugin-repo-session-start-hooks.feature` has at least one bound step (no unbound step warnings at collection).
- [ ] Steps that invoke `scripts/start-*-mcp.sh` mock the actual Blender/UE launch (patch `subprocess.Popen` or use a `fake_blender_bin` fixture) — BDD tests MUST NOT require Blender/UE installed on CI.
- [ ] Idempotency test uses a tiny Python socket server bound to the target port to simulate "already LISTEN", then asserts the script exits 0 in ≤ 1 s.
- [ ] Remediation test unsets `BLENDER_BIN`/`BLENDER_APP`, points them at a non-existent path, and asserts non-zero exit + hint on stderr.
- [ ] `pytest tests/bdd/` exits 0 from a fresh venv with dev deps installed.

### T015: Add scaffold-guard unit tests

**File(s)**: `tests/unit/test_scaffold_guards.py`
**Type**: Create
**Depends**: T002, T003, T004, T005, T009, T010, T011
**Acceptance**:
- [ ] **T015a — plugin.json schema**: loads `.claude-plugin/plugin.json` as JSON; asserts required keys (`name`, `version`, `description`, `authors`, `capabilities`). (Supports AC1.)
- [ ] **T015b — directory layout**: asserts every directory in `steering/structure.md` § Project Layout exists at repo root. (Supports AC2.)
- [ ] **T015c — .mcp.json pinning**: asserts no `latest`/`main`/`HEAD` substrings; asserts all three servers declared. (Supports AC8.)
- [ ] **T015d — no-leak grep**: scans `.claude-plugin/plugin.json`, `scripts/start-*-mcp.sh`, `templates/consumer/.claude/settings.json`, `.mcp.json`, and `pyproject.toml` for banned substrings: absolute `/Users/<name>/` paths (except documented defaults), `fixtures/dogfood.uproject` references, `.claude/plugins/` or `~/.claude/plugins/` hard-codes. (Supports AC10, AC11.)
- [ ] **T015e — no repo-root SessionStart wiring**: asserts `.claude/settings.json` does NOT exist at repo root. (Supports AC5b.)
- [ ] **T015f — version triangulation**: asserts `VERSION`, `.claude-plugin/plugin.json`'s `version`, and `pyproject.toml`'s `project.version` all equal `0.1.0`. (Supports AC7 + `steering/tech.md` versioning-mapping.)
- [ ] **T015g — CHANGELOG shape**: asserts `CHANGELOG.md` contains `## [Unreleased]`. (Supports AC7.)
- [ ] **T015h — CLAUDE.md pointers**: asserts `CLAUDE.md` references `steering/product.md`, `steering/tech.md`, `steering/structure.md`, and `/draft-issue`. (Supports AC9.)
- [ ] `pytest tests/unit/` exits 0.

### T016: Verify project-wide gates pass on the scaffolding

**File(s)**: (no new files — verification task)
**Type**: Verify
**Depends**: T001–T015
**Acceptance**:
- [ ] `gate-python-lint` (`ruff check . && ruff format --check .`) exits 0.
- [ ] `gate-python-types` (`mypy src/ tests/`) exits 0.
- [ ] `gate-python-unit` (`pytest tests/unit/`) exits 0.
- [ ] `gate-python-bdd` (`pytest tests/bdd/`) exits 0.
- [ ] `gate-shellcheck` (`shellcheck -S style scripts/*.sh`) exits 0.
- [ ] `gate-markdown-lint` (`markdownlint docs/ steering/ *.md`) exits 0 — note: `specs/` is excluded per `steering/tech.md` pattern. If markdownlint surfaces formatting nits in `CHANGELOG.md` or `CLAUDE.md`, fix inline.
- [ ] Gates that don't apply in this issue (e.g., `gate-ue-automation`, `gate-blender-headless`, `gate-ship-smoke`) are skipped cleanly — document any skip reasons in the verify-code output per `steering/tech.md` `verify-skip` convention.

---

## Dependency Graph

```
T001 ─┬─▶ T002 ──▶ T015a
      ├─▶ T003 ──▶ T015f, T015g
      ├─▶ T004 ──▶ T015h
      ├─▶ T005 ──▶ T006 ──▶ T014
      │             │
      │             └──▶ T015f
      ├─▶ T007 ──┬──▶ T010 ──▶ T015d, T015e
      │           │
      ├─▶ T008 ──┘
      ├─▶ T009 ──▶ T015c
      └─▶ T011

T012 (no code deps — written during /write-spec) ──▶ T013 ──▶ T014

T001..T015 ──▶ T016 (final gate check)
```

**Critical path**: T001 → T005 → T006 → T014 → T016 (5 serial steps; everything else parallelizable).

---

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #1 | 2026-04-22 | Initial feature spec |
| #2 | 2026-04-22 | Cleanup: T008 idempotency note clarified — UE_MCP_PORT is bound by VibeUE, not by anything nmg-game-dev ships |

---

## Validation Checklist

Before moving to IMPLEMENT phase:

- [x] Each task has a single responsibility.
- [x] Dependencies mapped (graph above).
- [x] Tasks completable independently given their dependencies.
- [x] Acceptance criteria verifiable (shell commands, grep checks, pytest assertions).
- [x] File paths match `steering/structure.md` § Project Layout — plus the two additions this issue introduces (`templates/consumer/`, `fixtures/`) which are explicitly called out in design.md.
- [x] Test tasks cover every AC (T014 + T015 + T016).
- [x] No circular dependencies.
- [x] Logical execution order (Setup → Integration → Testing).
