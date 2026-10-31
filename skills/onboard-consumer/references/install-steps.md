# Install steps: every consumer write

`python -m nmg_game_dev.onboard install` runs preflight, then these steps in order. Paths are relative
to the consumer root unless marked otherwise. Every step is idempotent. "Drift-checked" means a
re-run compares the file with the framework copy, reports `drift` when it differs, and leaves it
unchanged unless `--refresh` is given.

## Preflight (no consumer writes)

| Check | Failure code |
|-------|--------------|
| One `.uproject` at the root, or `--uproject` names one | `onboard.uproject_not_found`, `onboard.uproject_ambiguous` |
| `--models-dir`, or `TEXTURE_GEN_MODELS_DIR` | `onboard.models_dir_missing` |
| Framework sources present (start scripts, asset contract, design contract, hook template, UE plugin, Blender manifest) | `onboard.framework_incomplete` |
| `git` on PATH | `onboard.git_missing` |
| When any model is missing: Apple Silicon macOS | `onboard.unsupported_platform` |
| When any model is missing: at least 60 GiB free on the models volume | `onboard.insufficient_disk` |

## Steps

| Step | Consumer path | Action | Drift-checked |
|------|---------------|--------|---------------|
| `scripts/start-blender-mcp.sh` | `scripts/start-blender-mcp.sh` | Copy the framework script; keep the executable bit | Yes |
| `scripts/start-unreal-mcp.sh` | `scripts/start-unreal-mcp.sh` | Copy the framework script; keep the executable bit | Yes |
| `settings_hooks` | `.claude/settings.json` | Append each SessionStart hook whose `command` is not already present. Other keys are kept. | No (merge only) |
| `asset_contract` | `docs/nmg-game-dev/asset-contract.md` | Copy `docs/asset-contract.md` | Yes |
| `design_contract` | `docs/nmg-game-dev/design-contract.md` | Copy `docs/design-contract.md` | Yes |
| `design_dir` | `docs/design/` | Create the directory when absent. An existing directory is reported as is; its contents are never listed or changed. | No (directory only) |
| `agent_instructions:CLAUDE.md` | `CLAUDE.md` | Add the marked block once, or replace it in place. Creates the file if missing. | Block replaced in place |
| `agent_instructions:AGENTS.md` | `AGENTS.md` | Same as CLAUDE.md, only when the file already exists | Block replaced in place |
| `ue_plugin` | `Plugins/nmg-game-dev/` | Copy the UE plugin tree without `Binaries/` and `Intermediate/` | Yes (tree) |
| `vibeue` | `Plugins/VibeUE/` | `git clone --depth 1 --branch 5-8 https://github.com/kevinpbuckley/VibeUE.git Plugins/VibeUE` (VibeUE's UE 5.8 branch), then check HEAD equals the head of branch `5-8` on origin (`git ls-remote`) | Yes (HEAD) |
| `uproject_plugins` | `<name>.uproject` | Enable `ModelContextProtocol`, `EditorToolset`, `VibeUE`, and `nmg-game-dev` in `Plugins`. Other entries and fields are kept. Tab indentation. | No (merge only) |
| `mcp_autostart_ini` | `Config/DefaultEditorPerProjectUserSettings.ini` | Under `[/Script/ModelContextProtocolEngine.ModelContextProtocolSettings]`, set `bAutoStartServer=True`. Add `ServerPortNumber=8000` only when no port line exists. Other lines are kept. | No (merge only) |
| `blender_addon` | `$BLENDER_EXTENSIONS_DIR/nmg_game_dev_blender_addon` (outside the consumer) | Symlink to `<framework>/plugins/nmg-game-dev-blender-addon`. Default extensions dir: `~/Library/Application Support/Blender/5.2/extensions/user_default`. | Yes (link target) |
| `texture_models` | `<models dir>/z-image-turbo-q4`, `<models dir>/flux2-klein-4b-q4` (outside the consumer) | For each missing model, run `mflux-save --model <id> --quantize 4 --path <models dir>/<id>-q4` with `HF_HOME=<models dir>/hf-cache`, one after the other. Runs `uv tool install mflux==0.24.0` first only when `mflux-save` is not on PATH. | Skipped when present |
| `texture_env` | `.claude/settings.local.json` `env` | Set `TEXTURE_GEN_MODELS_DIR=<models dir>` and `HF_HOME=<models dir>/hf-cache`. Other keys are kept. | No (set to the resolved values) |
| `gitignore_env` | `.gitignore` | Append a `.env` line, creating `.gitignore` when missing. An existing `.env` or `/.env` line counts as present, so a rerun adds nothing. | Skipped when present |

## Never written

- `.mcp.json`: the plugin's root `.mcp.json` ships the MCP servers. Consumers get no MCP config from onboarding.
- `fixtures/` (including `dogfood.uproject`): the framework's fixtures never reach a consumer.
- `.env`: onboarding never asks for, creates, or writes the project `.env`. The optional Meshy key (`MESHY_API_KEY=`) is the developer's to add; `gitignore_env` only keeps that file out of git.
- `docs/design/` contents: the design docs are the consumer's. Onboarding creates the directory and nothing inside it.
- `nmg-budgets.json`: the consumer owns it. Onboarding never reads, writes, or reports it.
- Any settings value whose name ends in `_API_KEY`.
- `SourceArt/Textures/Generated/`: generated textures are created by the texture commands, not by onboarding.

## Drift and `--refresh`

A re-run without `--refresh` reports each differing framework-owned item as `drift` with the
remediation `re-run with --refresh`, and exits 0. With `--refresh`, the framework copy is restored,
VibeUE is moved to the head of its `5-8` branch on origin (or cloned again if it is not a git
checkout), and a wrong Blender link is replaced. VibeUE's drift is measured against that branch
head, so a checkout that is already at the head is `unchanged`. If `git ls-remote` cannot reach
origin, the `5-8` head is not checked: the checkout is left as is and reported `unchanged`.
