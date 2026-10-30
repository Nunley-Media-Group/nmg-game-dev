# Design: Consumer onboarding — onboard-consumer skill, asset contract install, and onboarding docs

**Issue**: #7
**Date**: 2026-10-29
**Status**: Approved
**Author**: Rich Nunley

## Overview

Onboarding has two layers, matching `steering/structure.md`:

1. **Skill** — `skills/onboard-consumer/SKILL.md` gathers the models disk from the developer, then runs `uv run --project "${CLAUDE_PLUGIN_ROOT}" python -m nmg_game_dev.onboard install --consumer "$CLAUDE_PROJECT_DIR" --models-dir <dir>` and relays the report.
2. **Python** — `src/nmg_game_dev/onboard/` owns every copy, link, merge, clone, model install, and drift check. Each step is a pure function of (framework root, consumer dir, options, injected runners), so it can be unit tested on temp directories.

Execution is **preflight → steps → report**. Preflight raises `OnboardError` before any write. Each step returns `StepResult(name, status ∈ {installed, unchanged, drift, refreshed}, detail, remediation)`.

## Architecture

```
python -m nmg_game_dev.onboard install --consumer C [--uproject P] [--models-dir D] [--refresh] [--json]
  framework_root = $CLAUDE_PLUGIN_ROOT or Path(__file__).resolve().parents[3]
  preflight:
    resolve uproject (P, else exactly one *.uproject in C)  → onboard.uproject_not_found | onboard.uproject_ambiguous
    resolve models dir (D, else $TEXTURE_GEN_MODELS_DIR)     → onboard.models_dir_missing
    if any model missing: Apple Silicon macOS?               → onboard.unsupported_platform
                          free bytes on D's volume ≥ 60 GiB  → onboard.insufficient_disk
    framework sources present                                → onboard.framework_incomplete
  steps (in order):
    scripts → settings_hooks → asset_contract → agent_instructions →
    ue_plugin → vibeue → uproject_plugins → mcp_autostart_ini →
    blender_addon → texture_models → texture_env
  print report (text, or JSON with --json); exit 0
```

### Modules (`src/nmg_game_dev/onboard/`)

| Module | Contents |
|--------|----------|
| `__init__.py` | Re-exports `OnboardError`, `StepResult`, `run_onboard`, `list_volumes` |
| `errors.py` | `OnboardError(PipelineError)`, `stage="onboard"` |
| `paths.py` | `framework_root(env)`, `EXCLUDED = ("fixtures", ".mcp.json")`, `assert_not_excluded(path)` used by every copy helper |
| `files.py` | `sync_file` / `sync_tree(src, dst, refresh, ignore=("Binaries","Intermediate"))` returning installed/unchanged/drift/refreshed by byte/tree comparison; preserves the executable bit |
| `settings.py` | `merge_session_hooks(settings_path, template_path)`: adds the template's `SessionStart` group only when no existing hook has an identical `command`, keeps all other keys, writes 2-space JSON; `merge_env(settings_local_path, {...})` |
| `instructions.py` | Marked block between `<!-- nmg-game-dev:begin -->` and `<!-- nmg-game-dev:end -->` referencing `docs/nmg-game-dev/asset-contract.md`; appended once, replaced in place when its content differs; creates `CLAUDE.md` if missing; touches `AGENTS.md` only if present |
| `unreal.py` | `enable_plugins(uproject, names)`; `ensure_mcp_autostart(ini_path)`; `ensure_vibeue(plugins_dir, run, refresh)` |
| `blender.py` | `link_addon(src, extensions_dir)` — creates the symlink; existing correct link → unchanged; link elsewhere or a non-link → drift (refresh replaces it) |
| `textures.py` | `TEXTURE_MODELS = (("z-image-turbo","Tongyi-MAI/Z-Image-Turbo"), ("flux2-klein-4b","black-forest-labs/FLUX.2-klein-4B"))`; `REQUIRED_FREE_BYTES = 60 * 2**30`; `MFLUX_VERSION = "0.24.0"`; `missing_models(dir)`; `install_models(dir, run, which)` |
| `volumes.py` | `list_volumes(disk_usage=shutil.disk_usage, mounts=...)` over `/` and `/Volumes/*` |
| `runner.py` | `run_onboard(consumer, framework, uproject, models_dir, refresh, env, run, which, host) -> list[StepResult]` |
| `__main__.py` | argparse with `install` / `volumes` subcommands; `OnboardError` → `ERROR [code]: …` / `Remediation: …` on stderr, exit 1 |

`run`, `which`, `host` (platform/machine), and `disk_usage` are injected. Production code uses `subprocess.run`, `shutil.which`, `platform`, and `shutil.disk_usage`.

## API / Interface Changes

| Interface | Input | Output / Error | Behavior |
|-----------|-------|----------------|----------|
| `python -m nmg_game_dev.onboard install` | `--consumer`, `--uproject`, `--models-dir`, `--refresh`, `--json` | Exit 0 with step report (drift included); exit 1 with `ERROR [onboard.*]` | FR1, FR2, FR9 |
| `python -m nmg_game_dev.onboard volumes` | none | JSON `[{"mount": str, "free_bytes": int, "fits_models": bool}]` | FR1, AC6 |
| VibeUE clone | missing `Plugins/VibeUE` | `git clone --depth 1 --branch v5.0-ue5.8 https://github.com/kevinpbuckley/VibeUE.git <C>/Plugins/VibeUE` | Present: `git -C … rev-parse HEAD` must equal `bc7bc45c1e2025123778560f45c15d1f8e1be41d`, else drift. Present without `.git`: drift. Refresh: `git -C … fetch --depth 1 origin tag v5.0-ue5.8` then `git -C … checkout --force bc7bc45c…`, or clone again if it isn't a git checkout |
| Model install | each missing `<D>/<id>-q4` | `mflux-save --model <id> --quantize 4 --path <D>/<id>-q4` with env `HF_HOME=<D>/hf-cache`, run sequentially | Non-zero exit → `OnboardError onboard.model_install_failed` naming the model; when `mflux-save` is missing, first `uv tool install mflux==0.24.0` (failure → `onboard.mflux_install_failed`) |

## Data / Storage Changes

Consumer writes (all relative to the consumer root):

| Path | Owner | Drift-checked |
|------|-------|---------------|
| `scripts/start-blender-mcp.sh`, `scripts/start-unreal-mcp.sh` | framework | yes |
| `.claude/settings.json` (SessionStart group) | merged | no (merge only) |
| `.claude/settings.local.json` `env.TEXTURE_GEN_MODELS_DIR`, `env.HF_HOME` | merged | no (set to the resolved values) |
| `docs/nmg-game-dev/asset-contract.md` | framework | yes |
| `CLAUDE.md` / `AGENTS.md` marked block | framework block | block replaced in place |
| `Plugins/nmg-game-dev/` | framework | yes (tree, excluding `Binaries/`, `Intermediate/`) |
| `Plugins/VibeUE/` | pinned clone | yes (HEAD commit) |
| `<name>.uproject` `Plugins[]` | merged | no |
| `Config/DefaultEditorPerProjectUserSettings.ini` | merged | no |
| `nmg-budgets.json` | consumer | never read, written, or reported |

`.uproject` merge: parse JSON; for each of `ModelContextProtocol`, `EditorToolset`, `VibeUE`, `nmg-game-dev`, set `Enabled: true` on an existing entry or append `{"Name": n, "Enabled": true}`; write back with tab indentation; leave every other field unchanged.

Ini merge: line-based. Add the section if absent; set `bAutoStartServer=True`; add `ServerPortNumber=8000` only when no `ServerPortNumber=` line exists in that section; keep every other line and section.

Blender link: `<BLENDER_EXTENSIONS_DIR>/nmg_game_dev_blender_addon` → `<framework>/plugins/nmg-game-dev-blender-addon` (the id from `blender_manifest.toml`). The directory is created if missing.

## State and UI Behavior

The skill flow:

1. Unless `NMG_SDLC_AUTOPILOT=1`, run `volumes`, then ask with `AskUserQuestion` which qualifying volume should hold the texture models, recommending the one with the most free space. The models dir is `<mount>/nmg-texture-models`. Under autopilot, use `TEXTURE_GEN_MODELS_DIR`; if it's unset, the install's `onboard.models_dir_missing` remediation is shown.
2. Run `install`.
3. Relay installed / unchanged / drift lines; for drift, offer re-running with `--refresh`.

Report lines are `<status> <step>: <detail>`, with a `Remediation:` line for drift.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Python package with a thin skill | Selected | Testable on temp dirs; matches the `ship` package layout from #6 |
| All logic as SKILL.md instructions | Rejected | Not deterministic or testable; idempotency would depend on the agent |
| Optional texture models | Rejected | Interview decision: models are required and installed on a chosen disk |
| Leave VibeUE/Epic plugin setup to #68 | Rejected | Interview decision: consumer Unreal setup moves to #7 |
| Overwrite drifted files on every run | Rejected | A plain re-run reports drift; `--refresh` is the explicit repair |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #7 | 2026-10-29 | Initial feature design |
