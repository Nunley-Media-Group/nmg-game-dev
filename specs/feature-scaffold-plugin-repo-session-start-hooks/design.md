# Design: Scaffold plugin + repo + session-start hooks

**Issues**: #1
**Date**: 2026-04-22
**Status**: Draft
**Author**: Rich Nunley

---

## Overview

This foundational issue assembles the `nmg-game-dev` repo into a valid Claude Code plugin whose consumer-facing deliverables (launcher scripts, `.mcp.json`, consumer SessionStart template, plugin manifest) are wired to function identically whether the plugin is later installed at user scope (`~/.claude/plugins/nmg-game-dev/`) or at project scope inside a consumer game repo.

The work splits into three physical deliverable groups:

1. **Plugin identity + SDLC versioning surface** — `.claude-plugin/plugin.json`, `VERSION`, `CHANGELOG.md`, `CLAUDE.md`, `pyproject.toml`, and the empty `src/nmg_game_dev/` submodule stubs. These give every downstream issue a place to land without re-debating layout.
2. **Session-start launcher contract** — `scripts/start-blender-mcp.sh` and `scripts/start-unreal-mcp.sh`, two idempotent, nohup-detached shell scripts that honor `steering/tech.md` § Session-start contract's six invariants. Shipped as consumer deliverables; invoked manually inside this repo for smoke-testing against the bundled dogfood `.uproject`.
3. **Consumer-install templates + MCP config** — `templates/consumer/.claude/settings.json` (copied into each consumer by `onboard-consumer`) and `.mcp.json` (dual-purpose: lives at this repo's root for contributor testing AND is the canonical source `onboard-consumer` copies into consumer repos).

The key architectural decision already locked in by requirements (AC11): **install-scope invariance**. Nothing this issue ships may encode a specific install scope. Path resolution is either relative, env-var-overridden, or through a documented default a consumer can override without editing the artifact.

---

## Architecture

### File-level component map

The "layers" for this scaffolding feature are groups of files, not code modules. Reference `steering/structure.md` § Project Layout for the canonical directory list.

```
nmg-game-dev/
├── .claude-plugin/
│   └── plugin.json                 ← Plugin identity + capability declarations (AC1, FR1)
│
├── .mcp.json                       ← MCP server config — dual-purpose (AC8, FR10)
│
├── templates/
│   └── consumer/
│       ├── .claude/
│       │   └── settings.json       ← SessionStart hook registration for CONSUMERS (AC5b, FR2)
│       └── README.md               ← Documents that onboard-consumer owns this template
│
├── scripts/
│   ├── start-blender-mcp.sh        ← Idempotent Blender launcher (AC3-5, FR3)
│   └── start-unreal-mcp.sh         ← Idempotent UE Editor launcher (AC3-5, FR4)
│
├── pyproject.toml                  ← Python package + dev deps (AC6, FR5)
├── src/nmg_game_dev/
│   ├── __init__.py                 ← Top-level package marker (AC6, FR6)
│   ├── pipeline/__init__.py        ← Empty submodule stub
│   ├── variants/__init__.py        ← Empty submodule stub
│   ├── quality/__init__.py         ← Empty submodule stub
│   └── ship/__init__.py            ← Empty submodule stub
│
├── VERSION                         ← "0.1.0\n" (AC7, FR7)
├── CHANGELOG.md                    ← [Unreleased] section (AC7, FR8)
├── CLAUDE.md                       ← Entry-point pointer (AC9, FR9)
│
├── fixtures/
│   └── dogfood.uproject            ← Minimal UE 5.7 project for contributor smoke-test (FR12)
│                                     THIS-REPO-ONLY — MUST NOT ship to consumers
│
├── plugins/
│   ├── nmg-game-dev-blender-addon/.gitkeep    ← (content: issue #2)
│   └── nmg-game-dev-ue-plugin/.gitkeep         ← (content: issue #3)
│
├── skills/.gitkeep                 ← (content: later v1 issues)
├── commands/.gitkeep
├── agents/.gitkeep
├── mcp-servers/.gitkeep
├── tests/
│   ├── unit/.gitkeep
│   ├── bdd/
│   │   ├── features/               ← feature.gherkin lands here via symlink or copy
│   │   └── steps/.gitkeep
│   ├── blender/.gitkeep
│   └── e2e/fixtures/.gitkeep
├── docs/
│   ├── onboarding/.gitkeep
│   ├── skills/.gitkeep
│   ├── mcp/.gitkeep
│   ├── contributing/.gitkeep
│   └── decisions/.gitkeep
└── specs/                          ← already seeded — DO NOT regenerate
    └── feature-scaffold-plugin-repo-session-start-hooks/
```

**Not in this issue** (explicit defer):
- `plugins/nmg-game-dev-blender-addon/**` beyond `.gitkeep` → issue #2
- `plugins/nmg-game-dev-ue-plugin/**` beyond `.gitkeep` → issue #3
- Any real skill / command / agent content

### Data flow — launcher invocation (the two contexts)

Two invocation paths. The scripts are identical; only the trigger differs.

#### Context 1 — consumer game project, SessionStart hook fires

```
Developer opens consumer game repo in Claude Code
        │
        ▼
Claude Code reads consumer's .claude/settings.json
        │  (populated by onboard-consumer from templates/consumer/.claude/settings.json)
        ▼
SessionStart hooks fire:
  • scripts/start-blender-mcp.sh   (consumer's scripts/, copied by onboard-consumer)
  • scripts/start-unreal-mcp.sh
        │
        ▼
Each script:
  1. Probes port (9876 / 8088). If LISTEN → exit 0 (idempotent).
  2. Resolves tool path (env var → documented default).
     Missing → exit 1 with remediation.
  3. nohup <tool> … & disown  ← detaches; script exits in ≤ 2s
  4. Log to /tmp/<tool>-mcp.log
```

#### Context 2 — contributor working inside nmg-game-dev, manual invocation

```
Contributor:  bash scripts/start-blender-mcp.sh
                                    OR
              bash scripts/start-unreal-mcp.sh
        │
        ▼
Same script path as Context 1 — probe, resolve, detach, log.
The difference: no .claude/settings.json in this repo registers these as hooks.
The dogfood fixtures/dogfood.uproject is what start-unreal-mcp.sh opens here
(by default, overridable via UE_PROJECT env var — see CLI contract below).
```

### Component responsibilities

| Artifact | Does | Does NOT do |
|----------|------|-------------|
| `.claude-plugin/plugin.json` | Declare plugin identity (name, version, description, authors) + capability surface that Claude Code reads at install | Encode paths to the host machine, list this-repo-only directories, ship secrets |
| `scripts/start-blender-mcp.sh` | Detect existing listener, resolve Blender path, launch in background with MCP addon enabled, log | Block the shell, write to stdout (detached process logs to `/tmp/…`), manage add-on installation (the add-on arrives in issue #2 — this script only *enables* the installed add-on) |
| `scripts/start-unreal-mcp.sh` | Detect existing listener, resolve UE root, open the target `.uproject`, detach | Install the UE plugin (issue #3), manage project configuration, block on UE editor initialization |
| `templates/consumer/.claude/settings.json` | Declare SessionStart hook entries with relative paths into the consumer's `scripts/` | Contain this-repo-specific paths, reference the dogfood fixture |
| `.mcp.json` | Register pinned MCP servers by name + version + transport | Encode credentials, reference this-repo-specific paths, pin to `latest` or `main` |
| `pyproject.toml` | Package metadata (`nmg_game_dev`), pinned dev deps (ruff, mypy, pytest, pytest-bdd), console-scripts entry if any | Declare runtime deps that don't exist yet (empty submodules don't need them); pin to a future Python version not supported by Blender 4.2 LTS |
| `src/nmg_game_dev/**/__init__.py` | Mark package boundaries so later issues can add modules without layout churn | Contain any real logic (deliberately empty) |
| `VERSION` | Be the single source of truth for the project's semver | Track anything else |
| `CHANGELOG.md` | Give `/open-pr` an `[Unreleased]` section to append entries under | Carry content from before v0.1.0 |
| `CLAUDE.md` | Point a new Claude session at steering docs + `/draft-issue` SDLC entry | Repeat content from steering (pointer-only) |
| `fixtures/dogfood.uproject` | Give `start-unreal-mcp.sh` a valid UE target when invoked inside this repo | Ship anywhere outside this repo; contain any real game content |

---

## Artifact specifications

### 1. `.claude-plugin/plugin.json`

Claude Code plugin manifest. Versioning tracks `VERSION` (see `steering/tech.md` § Versioning).

```jsonc
{
  "$schema": "https://schemas.claude.com/plugin-manifest.schema.json",
  "name": "nmg-game-dev",
  "version": "0.1.0",
  "description": "Blender-first, Unreal-shipped content pipeline for NMG games — skills, MCP servers, Blender add-on, UE plugin, build/sign/ship",
  "authors": [{ "name": "Nunley Media Group" }],
  "capabilities": {
    "skills": "skills/",
    "commands": "commands/",
    "agents": "agents/"
  },
  "requires": {
    "claudeCode": ">=current"
  }
}
```

**Design notes**:
- `"capabilities"` paths are relative to the plugin root and resolve correctly for both user-scope and project-scope installs.
- `$schema` field is opportunistic — if Claude Code doesn't publish that schema URL, drop the field; implementation task verifies.
- `authors` is a single-entry array; future contributors appended.
- No skills/commands/agents ship in this issue — the capability directories exist with `.gitkeep`s so the manifest resolves.

### 2. `templates/consumer/.claude/settings.json`

Consumer-only template. Inert in this repo (lives under `templates/consumer/`, not `.claude/`).

```jsonc
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "*",
        "hooks": [
          { "type": "command", "command": "bash scripts/start-blender-mcp.sh" },
          { "type": "command", "command": "bash scripts/start-unreal-mcp.sh" }
        ]
      }
    ]
  }
}
```

Accompanied by `templates/consumer/README.md` documenting:
- The file is a template consumed by `onboard-consumer` (future v1 issue), not by `nmg-game-dev` itself.
- Target path in consumer: `<consumer>/.claude/settings.json` (merged with existing settings if present).
- Why the hooks live here not in this repo's root: see requirements § "Scope of session-start hooks — consumer-game-only".

**Design notes**:
- The SessionStart hook schema follows Claude Code's published format. If Claude Code renames/restructures the hook config before implementation, adjust at implementation time — the shape is Claude Code's contract, not this issue's to define.
- Paths are relative to the consumer's project root (`scripts/start-*-mcp.sh`). This relies on `onboard-consumer` having copied the scripts into the consumer's `scripts/` first — documented in the README.

### 3. `scripts/start-blender-mcp.sh`

**CLI contract** (consumer-agnostic):

| Env var | Default | Purpose |
|---------|---------|---------|
| `BLENDER_MCP_PORT` | `9876` | TCP port Blender MCP will listen on |
| `BLENDER_BIN` | (none) | Direct path to `blender` executable |
| `BLENDER_APP` | `/Applications/Blender.app` (macOS) | Path to a `Blender.app` bundle — `Contents/MacOS/Blender` derived |
| `BLENDER_MCP_ADDON` | (none) | Override add-on module id if auto-discovery fails |

**Resolution order**:
1. If `BLENDER_BIN` is set and executable → use it.
2. Else if `BLENDER_APP` is set → derive `$BLENDER_APP/Contents/MacOS/Blender`.
3. Else fall back to `/Applications/Blender.app/Contents/MacOS/Blender` (macOS default).
4. Else fail with remediation message.

**Add-on discovery candidates** (try in order, enable first one installed):
- `bl_ext.user_default.blender_mcp` (Blender 4.2+ Extensions system, snake_case)
- `bl_ext.user_default.blender-mcp` (Extensions system, kebab-case)
- `blender_mcp` (legacy folder name under `~/Library/Application Support/Blender/<ver>/scripts/addons/`)
- `blender-mcp` (legacy folder name, kebab-case)

(If `BLENDER_MCP_ADDON` is set, skip discovery and enable it verbatim.)

**Script skeleton** (concrete bash, shellcheck-clean, `set -euo pipefail`):

```bash
#!/usr/bin/env bash
set -euo pipefail

readonly PORT="${BLENDER_MCP_PORT:-9876}"
readonly LOG="/tmp/blender-mcp.log"

# 1. Idempotency — already listening → exit 0.
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "start-blender-mcp: port $PORT already LISTEN — skipping launch" >&2
  exit 0
fi

# 2. Resolve Blender binary.
resolve_blender() {
  if [[ -n "${BLENDER_BIN:-}" && -x "$BLENDER_BIN" ]]; then
    echo "$BLENDER_BIN"; return
  fi
  local app="${BLENDER_APP:-/Applications/Blender.app}"
  local bin="$app/Contents/MacOS/Blender"
  if [[ -x "$bin" ]]; then
    echo "$bin"; return
  fi
  echo "start-blender-mcp: Blender not found. Set BLENDER_BIN or BLENDER_APP (tried: $bin)" >&2
  exit 1
}
readonly BLENDER
BLENDER="$(resolve_blender)"

# 3. Build Python bootstrap that discovers, enables the addon, and starts the MCP server.
readonly BOOTSTRAP_PY
BOOTSTRAP_PY="$(cat <<'PYEOF'
import bpy, addon_utils, os, sys

candidates = os.environ.get("BLENDER_MCP_ADDON_OVERRIDE", "").split(",") or []
candidates += [
    "bl_ext.user_default.blender_mcp",
    "bl_ext.user_default.blender-mcp",
    "blender_mcp",
    "blender-mcp",
]
candidates = [c for c in candidates if c]

enabled = None
for name in candidates:
    try:
        addon_utils.enable(name, default_set=True, persistent=True)
        enabled = name
        break
    except Exception:
        continue

if not enabled:
    sys.stderr.write(f"blender_mcp: no addon found among {candidates}\n")
    sys.exit(1)

# Deferred — start the socket server once UI is ready. The addon exposes
# a start-server operator / function; call it here.
import bpy
def _start():
    try:
        bpy.ops.blender_mcp.start_server()  # addon-exposed operator; fallback if different
    except Exception as e:
        sys.stderr.write(f"blender_mcp: failed to start server: {e}\n")
    return None

bpy.app.timers.register(_start, first_interval=1.0)
PYEOF
)"

# 4. Detach.
BLENDER_MCP_ADDON_OVERRIDE="${BLENDER_MCP_ADDON:-}" \
nohup "$BLENDER" --python-expr "$BOOTSTRAP_PY" >"$LOG" 2>&1 &
disown
echo "start-blender-mcp: launched Blender (port $PORT, log $LOG, pid $!)"
exit 0
```

**Design notes**:
- The exact `bpy.ops.blender_mcp.start_server()` invocation depends on the add-on's API — implementation task will align with whichever add-on issue #2 delivers. For this issue, a commented fallback is documented; if the add-on exposes a different entry point, the implementation task updates the bootstrap.
- Using `nohup … & disown` rather than `setsid` — macOS default behavior, matches `steering/tech.md`.
- Uses `lsof` for port check (present on macOS + every Linux dev machine); skips `ss` to keep the macOS default path clean.
- All logs to `/tmp/blender-mcp.log` per `steering/tech.md` § Session-start contract invariant 5.

### 4. `scripts/start-unreal-mcp.sh`

**CLI contract**:

| Env var | Default | Purpose |
|---------|---------|---------|
| `UE_MCP_PORT` | `8088` | TCP port the UE plugin's MCP bridge binds |
| `UE_ROOT` | `/Users/Shared/Epic Games/UE_5.7` | UE install root |
| `UE_PROJECT` | `fixtures/dogfood.uproject` (inside nmg-game-dev) / `$PWD/*.uproject` (in a consumer) | Target `.uproject` file |

**Resolution order** for `UE_PROJECT` default:
1. If `UE_PROJECT` is set → use it verbatim.
2. Else if a single `*.uproject` file exists in `$PWD` → use it.
3. Else if `$PWD/fixtures/dogfood.uproject` exists (nmg-game-dev contributor mode) → use it.
4. Else fail with remediation: "Set UE_PROJECT, or run from a consumer project containing exactly one .uproject file".

**Script skeleton**:

```bash
#!/usr/bin/env bash
set -euo pipefail

readonly PORT="${UE_MCP_PORT:-8088}"
readonly LOG="/tmp/unreal-mcp.log"
readonly UE_ROOT="${UE_ROOT:-/Users/Shared/Epic Games/UE_5.7}"
readonly UE_EDITOR="$UE_ROOT/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor"

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "start-unreal-mcp: port $PORT already LISTEN — skipping launch" >&2
  exit 0
fi

if [[ ! -x "$UE_EDITOR" ]]; then
  echo "start-unreal-mcp: UnrealEditor not found at $UE_EDITOR — set UE_ROOT" >&2
  exit 1
fi

resolve_uproject() {
  if [[ -n "${UE_PROJECT:-}" ]]; then echo "$UE_PROJECT"; return; fi
  local found
  mapfile -t found < <(find "$PWD" -maxdepth 2 -name '*.uproject' -print -quit)
  if (( ${#found[@]} == 1 )); then echo "${found[0]}"; return; fi
  if [[ -f "$PWD/fixtures/dogfood.uproject" ]]; then
    echo "$PWD/fixtures/dogfood.uproject"; return
  fi
  echo "start-unreal-mcp: no .uproject resolved — set UE_PROJECT" >&2
  exit 1
}
readonly PROJECT
PROJECT="$(resolve_uproject)"

nohup "$UE_EDITOR" "$PROJECT" -log >"$LOG" 2>&1 &
disown
echo "start-unreal-mcp: launched UE Editor (project $PROJECT, port $PORT, log $LOG, pid $!)"
exit 0
```

**Design notes**:
- Port binding is the UE plugin's responsibility, not this script's. The script's job is to open UE with the right project; the plugin does the binding. This issue does NOT implement the plugin (issue #3); the port-bind side of the contract is validated later.
- If the consumer's `.uproject` does not have the nmg-game-dev UE plugin enabled (e.g., before issue #3 lands, or if `onboard-consumer` has not yet been run), UE will boot without the MCP bridge. The script still exits 0 — that's correct behavior; the MCP registration in `.mcp.json` is what surfaces the missing bridge as a connection error in Claude, not this launcher.
- `UE_EDITOR` path follows UE 5.7 Apple Silicon layout. Linux / Windows parity is out of scope per requirements § Non-Functional.

### 5. `.mcp.json`

Single file, dual-purpose (contributor testing + copied by `onboard-consumer` into consumers).

```jsonc
{
  "mcpServers": {
    "blender": {
      "command": "uvx",
      "args": ["blender-mcp@<pinned-version>"],
      "description": "Blender MCP — ahujasid/blender-mcp"
    },
    "unreal": {
      "command": "uvx",
      "args": ["vibeue-mcp@<pinned-version>"],
      "description": "VibeUE UE MCP HTTP bridge client"
    },
    "meshy": {
      "command": "uvx",
      "args": ["meshy-mcp@<pinned-version>"],
      "env": { "MESHY_API_KEY": "${MESHY_API_KEY}" },
      "description": "Meshy.io MCP — supplementary 3D generation"
    }
  }
}
```

**Design notes**:
- `<pinned-version>` placeholders are resolved during implementation by looking up the latest tagged release of each package. The **hard requirement** is "pinned, not `latest`/`main`". The implementation task logs which versions it picked in its PR description so the pinning history is traceable.
- Using `uvx` (part of `uv`) for Python-hosted MCPs because `uv` is already in the dev-deps stack; no node.js runtime assumed.
- VibeUE's concrete npm / PyPI / git identifier is verified at implementation time. If VibeUE distributes only as source (git repo), use `uvx --from git+<url>@<tag>` form. Implementation task documents the choice.
- `env` passes `MESHY_API_KEY` from the dev's shell into the MCP process; never written to the file.
- NO consumer-specific paths (no `${HOME}`, no `/Users/…`); `onboard-consumer` copies this file verbatim.

### 6. `pyproject.toml`

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "nmg-game-dev"
version = "0.1.0"
description = "Blender-first, Unreal-shipped content pipeline for NMG games"
readme = "CLAUDE.md"
requires-python = ">=3.11"
authors = [{ name = "Nunley Media Group" }]
license = { text = "Proprietary" }

[project.optional-dependencies]
dev = [
  "pytest>=8",
  "pytest-bdd>=7",
  "ruff>=0.4",
  "mypy>=1.10",
]

[tool.hatch.build.targets.wheel]
packages = ["src/nmg_game_dev"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B"]

[tool.mypy]
python_version = "3.11"
strict = true
```

**Design notes**:
- `version = "0.1.0"` matches `VERSION` per `steering/tech.md` § Versioning's mapping table (`/open-pr` keeps them in sync).
- `requires-python = ">=3.11"` matches Blender 4.2 LTS bundled Python.
- Dev deps pinned with `>=` lower bounds, not exact pins — exact pins belong in a lockfile (`uv.lock`), which is a later-issue concern. Issue #1 just needs the deps declared; `gate-python-lint` and `gate-python-types` will exercise them once skills / real code land.
- No runtime deps under `[project]` — the empty submodule stubs don't import anything yet.
- `hatchling` chosen as the build backend (simple, stable, PyPI-friendly when we publish).

### 7. `src/nmg_game_dev/**/__init__.py`

Five empty files (one per module). Example top-level:

```python
"""nmg-game-dev — Blender-first, Unreal-shipped content pipeline for NMG games."""
from __future__ import annotations

__version__ = "0.1.0"
```

Each submodule (`pipeline/`, `variants/`, `quality/`, `ship/`) is a single-line `__init__.py`:

```python
"""<module-name> — stub; implemented in a later v1 issue."""
from __future__ import annotations
```

**Design notes**:
- Each stub gets a one-line module docstring so ruff's D-rules pass if enabled later. Keeps issue #1's scope tight.

### 8. `VERSION`, `CHANGELOG.md`, `CLAUDE.md`

**`VERSION`** — literally `0.1.0\n`. One line, trailing newline.

**`CHANGELOG.md`**:

```markdown
# Changelog

All notable changes to `nmg-game-dev` are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to semver per `steering/tech.md` § Versioning.

## [Unreleased]

### Added
- Initial scaffolding: plugin manifest, directory layout, session-start launcher scripts, MCP config, Python package, consumer SessionStart template. (#1)
```

**`CLAUDE.md`**:

```markdown
# nmg-game-dev

Blender-first, Unreal-shipped content pipeline for NMG games. Distributed as a Claude Code plugin, a Blender add-on, and a UE plugin. Installed at user or project scope — outcome identical per `specs/feature-scaffold-plugin-repo-session-start-hooks/requirements.md` AC11.

## Where to start

- **Product direction**: `steering/product.md`
- **Technical standards + gates**: `steering/tech.md`
- **Code organization**: `steering/structure.md`
- **Start a new unit of work**: `/draft-issue` (nmg-sdlc entry point)

## What this file is

A pointer to steering. Don't duplicate content from steering docs here.
```

### 9. `fixtures/dogfood.uproject`

Minimal UE 5.7 `.uproject` JSON. Engine version pinned to 5.7; no plugins enabled yet (issue #3 adds the nmg-game-dev UE plugin reference).

```json
{
  "FileVersion": 3,
  "EngineAssociation": "5.7",
  "Category": "",
  "Description": "nmg-game-dev dogfood fixture — contributor smoke-test target for start-unreal-mcp.sh. NOT SHIPPED TO CONSUMERS.",
  "Modules": [],
  "Plugins": []
}
```

Accompanied by `fixtures/README.md` noting the `NOT SHIPPED TO CONSUMERS` constraint (AC10 leak prevention).

**Design notes**:
- No `Source/` directory — keeps the `.uproject` a pure content project.
- No pre-baked assets; `UnrealEditor` opens against this file, logs to `/tmp/unreal-mcp.log`, and sits idle. That proves the launcher works.

---

## Alternatives Considered

| Option | Description | Pros | Cons | Decision |
|--------|-------------|------|------|----------|
| **A: Ship `.claude/settings.json` at repo root with SessionStart hooks enabled** | Wire Blender/UE to auto-launch every time a contributor opens this repo in Claude Code | Dogfoods the consumer path end-to-end on every contributor session | Slow session start (~2s delay); boots tools contributors often don't need (e.g., when only editing Python); user explicitly said hooks should NOT fire in this repo | **Rejected** — requirements § "Scope of session-start hooks — consumer-game-only" |
| **B (Selected): Consumer-only template at `templates/consumer/.claude/settings.json` + manual-invoke scripts in this repo** | Scripts ship as deliverables; settings.json template exists for `onboard-consumer` to copy | Aligns with user direction; contributors opt into launching Blender/UE; consumer outcome unchanged | Requires documentation so contributors know to manually run the scripts when testing the full pipeline | **Selected** |
| **C: Separate `.mcp.json` for this repo vs. `templates/consumer/.mcp.json`** | One for contributor testing, one for consumer onboarding | Clean separation of concerns | Duplicates pinned versions; drift risk; no meaningful difference in the actual server config | **Rejected** — requirements § ".mcp.json is dual-purpose" |
| **D: Pin MCP servers at the bleeding edge (`latest` / `main`)** | Always pick up the newest MCP features | Features without manual bumps | User explicitly requires pinning (AC8); floating refs break reproducibility | **Rejected** — requirements AC8 |
| **E: Use `tree-sitter` / `ripgrep`-based add-on discovery instead of `addon_utils.enable` candidates list** | Scan Blender's addon directory directly, pick the first `blender_mcp*` match | Handles unknown future names | Fragile — Blender's Extensions system already exposes a canonical list; we'd be reinventing | **Rejected** — candidates list is explicit and diff-reviewable |
| **F: Hard-code dogfood `.uproject` path in `start-unreal-mcp.sh`** | Simplify the script | Shorter script | Breaks consumer use (AC10 leak); `UE_PROJECT` env + auto-detect cleanly handles both contexts | **Rejected** |
| **G: Use `uv tool install` instead of `uvx` for MCP servers** | Keep a persistent install | Faster repeat invocations | `uvx` is the canonical pattern for one-shot tool invocation; MCP hosts restart processes anyway | **Rejected** — `uvx` matches the MCP-server lifecycle |

---

## Security Considerations

- [x] **Authentication**: Launcher scripts forward `MESHY_API_KEY` from the environment via `.mcp.json`'s `env` block. Never logged. Not written to any file this issue ships.
- [x] **Authorization**: N/A — no user-facing auth surface in the scaffolding.
- [x] **Input Validation**: Env-var resolution in the launchers fails closed (non-zero exit) with a remediation hint — never silent fallback to unexpected paths.
- [x] **Data Sanitization**: Log paths in `/tmp/*-mcp.log` tee both stdout and stderr — if a consumer later redacts secrets in their MCP logs, that's their policy; `nmg-game-dev` doesn't introduce new secret-logging surfaces.
- [x] **Sensitive Data**: `.mcp.json` must not contain API keys inline — only `${MESHY_API_KEY}`-style env references per the `env` block pattern. `gate-shellcheck` catches any `echo "$API_KEY"` inside shell scripts. Credentials never committed, never shipped in a consumer's cooked game binary (`steering/tech.md` § Security).

---

## Performance Considerations

- [x] **Launcher cold path**: `lsof` port probe + env resolution + `nohup … & disown` — target ≤ 2 s return-to-shell. `lsof -nP -iTCP:<port> -sTCP:LISTEN` is typically < 100 ms on macOS; everything else is fast-path.
- [x] **Launcher idempotent path**: port already `LISTEN` → exit 0 in ≤ 100 ms (one `lsof` call only).
- [x] **No caching added**: the scaffolding introduces no cache. Generation / asset caches are later-issue concerns.
- [x] **No database**: N/A.
- [x] **No per-frame runtime cost**: This issue ships no UE runtime module. Runtime perf budget from `steering/tech.md` § Performance (runtime) is not exercised here — validated when issue #3 ships.

---

## Testing Strategy

| Layer | Type | Coverage |
|-------|------|----------|
| Launcher scripts | BDD (pytest-bdd orchestrating bash) + shellcheck (`gate-shellcheck`) | AC3–AC5: detach, idempotency, remediation on missing binary |
| `.claude-plugin/plugin.json` | Schema check in pytest (`json.load` + required-key assertions; optional `claude plugin validate` if exposed by Claude Code CLI) | AC1 |
| Directory layout | pytest asserting `Path(...).is_dir()` for each directory in `steering/structure.md` | AC2 |
| `.mcp.json` | pytest asserting required keys + no `latest` / `main` version strings | AC8 |
| `templates/consumer/.claude/settings.json` | pytest asserting SessionStart entries + absence of repo-root `.claude/settings.json` | AC5b |
| `pyproject.toml` + `src/nmg_game_dev/` | `pip install -e .[dev]` in CI; `python -c "import nmg_game_dev"`; `ruff check .`; `pytest` | AC6 |
| `VERSION` / `CHANGELOG.md` / `CLAUDE.md` | pytest string / structural assertions | AC7, AC9 |
| Leak-prevention (AC10) | `grep`-based pytest scanning consumer-facing artifacts for banned substrings: absolute user paths, dogfood fixture refs outside `fixtures/`, this-repo-only module imports | AC10 |
| Install-scope invariance (AC11) | Documented manual-test procedure in `docs/onboarding/` (full automation blocked on `onboard-consumer` — a later v1 issue) + a pytest guard that grep-scans the consumer-facing artifacts for any reference to `.claude/plugins/` vs. `~/.claude/plugins/` hard-codes | AC11 |

Feature file: `tests/bdd/features/scaffold-plugin-repo-session-start-hooks.feature` (delivered in Phase 3 tasks, referenced from `specs/feature-scaffold-plugin-repo-session-start-hooks/feature.gherkin`).

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Blender MCP add-on API (operator name / discovery path) changes between versions | Medium | Medium | Multi-candidate discovery list; `BLENDER_MCP_ADDON` env override for manual pinning; implementation task verifies against the actual add-on that issue #2 will deliver |
| VibeUE package identifier differs from expected (e.g., not yet on PyPI) | Medium | Low | Implementation task: check VibeUE's canonical distribution channel (git tag, npm, PyPI) before pinning in `.mcp.json`; fall back to `uvx --from git+…` syntax if needed |
| `claude plugin validate` CLI surface not published in current Claude Code releases | Low | Low | AC1 pass criterion is "validation passes with no errors" — if no CLI command exists, fall back to a schema assertion pytest (see Testing Strategy). Implementation task picks the currently-working surface. |
| SessionStart hook schema in `templates/consumer/.claude/settings.json` evolves before `onboard-consumer` lands | Low | Medium | Keep the template minimal (just SessionStart with two commands). `onboard-consumer` (future issue) re-derives the template if Claude Code's schema changes, rather than forking on a stale version. |
| Contributors forget the scripts are manual-only here and expect auto-launch | Low | Low | `CLAUDE.md` + `templates/consumer/README.md` both explain the scope. Session-start contract is documented in `steering/tech.md`. |
| Dogfood `.uproject` leaks into a consumer during `onboard-consumer` | Low | High | AC10 pytest scan; `fixtures/README.md` warning; `onboard-consumer` (future issue) must whitelist what it copies — `fixtures/` is explicitly excluded |
| macOS-only paths (`/Applications/Blender.app`, `/Users/Shared/Epic Games/UE_5.7`) break a future Linux/Windows port | Low | Low | Out of scope per requirements § Non-Functional. Tracked as a future issue when the first non-macOS consumer appears. |

---

## Open Questions

- [ ] Final pinned versions for `blender-mcp`, `vibeue-mcp`, `meshy-mcp` in `.mcp.json` — resolved at implementation time (T-wire-mcp-config). The spec's hard requirement is "pinned to a specific released version/tag; never `latest`/`main`".
- [ ] Exact Blender MCP add-on entry-point function name (`bpy.ops.blender_mcp.start_server` is a placeholder) — reconciled when issue #2 ships the add-on.
- [ ] Whether `onboard-consumer` (future v1 issue) will merge into an existing consumer `.claude/settings.json` or refuse to overwrite — not this issue's decision, flagged here so the `templates/consumer/README.md` can cross-reference.

---

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #1 | 2026-04-22 | Initial feature spec |

---

## Validation Checklist

Before moving to TASKS phase:

- [x] Architecture follows existing project patterns (per `steering/structure.md` § Project Layout)
- [x] All interface changes documented with schemas (launcher CLI contract, plugin.json shape, .mcp.json shape, settings.json template shape, pyproject shape)
- [x] Database/storage changes planned — N/A (noted explicitly)
- [x] State management approach — N/A (noted explicitly)
- [x] UI components — N/A (noted explicitly)
- [x] Security considerations addressed (env-var-only secret forwarding, no inline credentials, fail-closed resolution)
- [x] Performance impact analyzed (cold path ≤ 2 s, idempotent path ≤ 100 ms)
- [x] Testing strategy defined (per-artifact coverage + leak-prevention grep + install-scope-invariance guard)
- [x] Alternatives considered and documented (7 options, rationales recorded)
- [x] Risks identified with mitigations (7 risks)
