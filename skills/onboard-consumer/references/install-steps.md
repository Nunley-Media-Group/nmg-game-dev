# Install steps: every consumer write

`python -m nmg_game_dev.onboard install` runs preflight, then these steps in order. Paths are relative
to the consumer root unless marked otherwise. `<game>` is the Godot project folder, `game` unless
`--game-dir` names another. Every step is idempotent. "Drift-checked" means a re-run compares the
item with the framework copy, reports `drift` when it differs, and leaves it unchanged unless
`--refresh` is given.

## Preflight (no consumer writes)

| Check | Failure code |
|-------|--------------|
| `--game-dir` is a relative folder inside the consumer | `onboard.game_dir_invalid` |
| `--models-dir`, or `TEXTURE_GEN_MODELS_DIR` | `onboard.models_dir_missing` |
| Framework sources present (Blender start script, asset contract, design contract, hook template, Godot add-on `plugin.cfg`, Blender manifest) | `onboard.framework_incomplete` |
| `git` on PATH | `onboard.git_missing` |
| `git-lfs` on PATH | `onboard.git_lfs_missing` |
| When any model is missing: Apple Silicon macOS | `onboard.unsupported_platform` |
| When any model is missing: at least 60 GiB free on the models volume | `onboard.insufficient_disk` |

## Steps

| Step | Consumer path | Action | Drift-checked |
|------|---------------|--------|---------------|
| `scripts/start-blender-mcp.sh` | `scripts/start-blender-mcp.sh` | Copy the framework script; keep the executable bit | Yes |
| `settings_hooks` | `.claude/settings.json` | Append each template SessionStart hook whose `command` is not already present. The template has only the Blender hook. Other keys are kept. | No (merge only) |
| `asset_contract` | `docs/nmg-game-dev/asset-contract.md` | Copy `docs/asset-contract.md` | Yes |
| `design_contract` | `docs/nmg-game-dev/design-contract.md` | Copy `docs/design-contract.md` | Yes |
| `design_dir` | `docs/design/` | Create the directory when absent. An existing directory is reported as is; its contents are never listed or changed. | No (directory only) |
| `agent_instructions:CLAUDE.md` | `CLAUDE.md` | Add the marked block once, or replace it in place. Creates the file if missing. | Block replaced in place |
| `agent_instructions:AGENTS.md` | `AGENTS.md` | Same as CLAUDE.md, only when the file already exists | Block replaced in place |
| `godot_project` | `<game>/project.godot` | Create it when missing with `config_version=5`, `[application] config/name` (the consumer folder name), `[rendering] renderer/rendering_method.mobile="gl_compatibility"` and `renderer/rendering_method.web="gl_compatibility"`, `[editor_plugins] enabled=PackedStringArray("res://addons/nmg_game_dev/plugin.cfg")`, and `[autoload]` holding `NmgAssets="*res://addons/nmg_game_dev/nmg_assets.gd"` and `NmgLaunch="*res://addons/nmg_game_dev/nmg_launch.gd"` (the launch options, autoplay, and screenshot autoload, #251). On an existing file, each missing key is added (`refreshed`); every other line is kept. | Yes (the renderer, editor plugin, and both autoload keys) |
| `godot_addon` | `<game>/addons/nmg_game_dev/` | Copy `<framework>/plugins/nmg-game-dev-godot-addon/addons/nmg_game_dev` without its `tests/` folder | Yes (tree) |
| `export_presets` | `<game>/export_presets.cfg` | Write the macOS, iOS, Android, Windows Desktop, and Web presets when missing, named after `config/name`. Desktop presets exclude `assets/*/Mobile/*`; mobile and web presets exclude `assets/*/Desktop/*`. | Yes (whole file) |
| `godot_binary` | none | Look for Godot 4: `GODOT_BIN`, then `godot` on PATH, then `/Applications/Godot.app`. `unchanged` "found at <path>", or `skipped` with "Install Godot 4 or set GODOT_BIN". | No (report only) |
| `ffmpeg_binary` | none | Look for ffmpeg: `FFMPEG_BIN`, then PATH. `unchanged` "found at <path>", or `skipped` with "Install ffmpeg or set FFMPEG_BIN (needed to import music)". | No (report only) |
| `blender_addon` | `$BLENDER_EXTENSIONS_DIR/nmg_game_dev_blender_addon` (outside the consumer) | Symlink to `<framework>/plugins/nmg-game-dev-blender-addon`. Default extensions dir: `~/Library/Application Support/Blender/5.2/extensions/user_default`. | Yes (link target) |
| `texture_models` | `<models dir>/z-image-turbo-q4`, `<models dir>/flux2-klein-4b-q4` (outside the consumer) | For each missing model, run `mflux-save --model <id> --quantize 4 --path <models dir>/<id>-q4` with `HF_HOME=<models dir>/hf-cache`, one after the other. Runs `uv tool install mflux==0.24.0` first only when `mflux-save` is not on PATH. | Skipped when present |
| `texture_env` | `.claude/settings.local.json` `env` | Set `TEXTURE_GEN_MODELS_DIR=<models dir>` and `HF_HOME=<models dir>/hf-cache`. Other keys are kept. | No (set to the resolved values) |
| `gitignore_env` | `.gitignore` | Append `.env`, `game/.godot/` (Godot's import cache, following `--game-dir`), and `.nmg/` (the per-asset finalize records and their log copies), creating `.gitignore` when missing. A line with or without a leading `/` counts as present, so a rerun adds nothing. | Skipped when present |
| `gitattributes_lfs` | `.gitattributes` | Add the marked `# nmg-game-dev:begin` … `# nmg-game-dev:end` block, which tracks the binary asset patterns in Git LFS (`.blend`, `.glb`, `.fbx`, `.obj`, `.abc`, `.usd`, `.usdz`, textures, audio, and video). Creates the file when missing. Lines outside the block are kept byte-for-byte. | Yes (managed block) |
| `git_lfs_hooks` | `.git/hooks/pre-push` (the repository's hooks directory) | When the consumer is a git work tree and no `pre-push` hook mentions `git lfs`, run `git lfs install --local`. Outside a git work tree the step is `skipped` with the detail `not a git repository`. A non-zero exit raises `onboard.git_lfs_hooks_failed`. | No (installs once) |

## Never written

- Git history and the index: onboarding never runs `git add --renormalize .` or `git lfs migrate`. Files already committed as full blobs stay blobs until you convert them yourself; [docs/onboarding/index.md](../../../docs/onboarding/index.md) gives the commands.
- `.mcp.json`: the plugin's root `.mcp.json` ships the MCP servers. Consumers get no MCP config from onboarding.
- `fixtures/`: the framework's fixtures never reach a consumer.
- `.env`: onboarding never asks for, creates, or writes the project `.env`. The optional Meshy key (`MESHY_API_KEY=`) is the developer's to add; `gitignore_env` only keeps that file out of git.
- `docs/design/` contents: the design docs are the consumer's. Onboarding creates the directory and nothing inside it.
- `nmg-budgets.json`: the consumer owns it. Onboarding never reads, writes, or reports it.
- Any settings value whose name ends in `_API_KEY`.
- `SourceArt/Textures/Generated/`: generated textures are created by the texture commands, not by onboarding.
- Godot itself and ffmpeg: onboarding only reports whether they are installed.

## Drift and `--refresh`

A re-run without `--refresh` reports each differing framework-owned item as `drift` with the
remediation `re-run with --refresh`, and exits 0. A second run on an unchanged consumer leaves every
file byte-identical. With `--refresh`, the framework copy is restored: the start script, the
contracts, the add-on files, the drifted `project.godot` keys (other keys and lines stay as they
are), and `export_presets.cfg`. A wrong Blender link is replaced.

`skipped` is not a drift. It means the step does not apply to this consumer or a tool is missing.
`git_lfs_hooks` reports `skipped` outside a git work tree, and `godot_binary` or `ffmpeg_binary`
report `skipped` when the tool is not found; the rest of the install still runs.
