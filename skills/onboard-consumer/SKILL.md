---
name: onboard-consumer
description: Onboard a game project to nmg-game-dev: the Godot project in game/ with the nmg_game_dev add-on and export presets, the Blender start script and hook, the Blender add-on, local texture models, and the contracts. Idempotent; re-runs report drift.
required_mcp: []
required_env: [CLAUDE_PLUGIN_ROOT?, CLAUDE_PROJECT_DIR?, TEXTURE_GEN_MODELS_DIR?, BLENDER_EXTENSIONS_DIR?, GODOT_BIN?, FFMPEG_BIN?, NMG_SDLC_AUTOPILOT?]
unattended_safe: true
---

# Onboard consumer

Installs everything a consumer game project needs from nmg-game-dev in one run: the Blender start
script and its SessionStart hook, the asset and design contracts, the Godot project in `game/`
(`game/project.godot`, the `nmg_game_dev` add-on, and `game/export_presets.cfg`), the Blender add-on
link, Git LFS tracking for binary assets, and the two local texture models. It also reports whether
Godot 4 and ffmpeg are installed. Every write is idempotent. A re-run reports what has drifted from
the framework and changes nothing unless it is given `--refresh`.

Use it when the developer starts a new consumer project, upgrades nmg-game-dev, or asks to set up or
repair the project. Never edit the installed copies by hand. Run this instead. To move a project
from the previous engine target to Godot, use `/convert-to-godot`, which runs this install itself.

## Flow

1. **Choose the texture models disk.** Unless `NMG_SDLC_AUTOPILOT=1`:
   - Run `uv run --project "${CLAUDE_PLUGIN_ROOT}" python -m nmg_game_dev.onboard volumes`.
   - Keep the volumes with `fits_models: true` (at least 60 GiB free). If none qualify, say so and stop.
   - Ask the developer with `AskUserQuestion` which qualifying volume should hold the models. Put the
     one with the most free space first and mark it recommended.
   - The models directory is `<chosen mount>/nmg-texture-models`.

   Under `NMG_SDLC_AUTOPILOT=1`, use `TEXTURE_GEN_MODELS_DIR` without asking. If it is unset, the
   install stops with `onboard.models_dir_missing`. Show that remediation and stop.

2. **Run the install.** From the consumer root:
   `uv run --project "${CLAUDE_PLUGIN_ROOT}" python -m nmg_game_dev.onboard install --consumer "$CLAUDE_PROJECT_DIR" --models-dir <models dir>`
   The Godot project lives in `game/` (`game/project.godot`). Add `--game-dir <folder>` only when the
   project keeps it somewhere else. The detailed copy, link, and merge rules are in
   `references/install-steps.md`.

3. **Relay the report.** Each step prints one line: `<status> <step>: <detail>`. Statuses are
   `installed`, `unchanged`, `drift`, `refreshed`, `conflict`, and `skipped`. Show every line. For each
   `drift`, the report gives the remediation `re-run with --refresh`. `conflict` means onboarding left
   a file of the developer's alone instead of overwriting it: for `precommit_hook`
   (`onboard.precommit_hook_conflict`) a foreign `pre-commit` hook already exists, and the report's
   remediation is the secret-scan line to add to that hook. Relay that line exactly; the developer
   adds it and re-runs. `skipped` means the step does not apply here or a tool is missing. It is not
   an error:
   - `git_lfs_hooks` and `precommit_hook` are skipped in a folder that is not a git work tree, so
     that consumer has no commit-time secret scan (`/ship` still scans before every build).
   - `godot_binary` is skipped when Godot 4 is not found (`GODOT_BIN`, then `godot` on PATH, then
     `/Applications/Godot.app`). Relay its remediation: install Godot 4 or set `GODOT_BIN`. Finalize,
     audio import, and ship need it.
   - `ffmpeg_binary` is skipped when ffmpeg is not found (`FFMPEG_BIN`, then PATH). Relay its
     remediation: install ffmpeg or set `FFMPEG_BIN`. Music import needs it.

   Offer to re-run with `--refresh` when there is drift, and do so only if the developer agrees.

4. **Refresh when asked.** `--refresh` restores drifted framework copies, the framework keys in
   `game/project.godot`, and `game/export_presets.cfg`, and replaces a wrong Blender link. It never
   touches `nmg-budgets.json` or the project's own `project.godot` keys. Run it only when the
   developer asks to repair the install.

5. **Point at the next step.** Once the report is clean, direct the developer to
   `docs/onboarding/index.md`, starting with `first-asset.md`.

## Failure modes and remediation

- `onboard.game_dir_invalid` → `--game-dir` must be a relative folder inside the consumer, such as
  `game`.
- `onboard.models_dir_missing` → choose a volume (flow step 1) and re-run with `--models-dir`.
- `onboard.insufficient_disk` → the chosen volume has less than 60 GiB free while a model is
  missing. Choose another volume. Nothing in the consumer has changed.
- `onboard.unsupported_platform` → the texture models need Apple Silicon macOS. Install the rest on
  this host by re-running with the models already present, or skip the models.
- `onboard.framework_incomplete` → the framework root is incomplete. Check `CLAUDE_PLUGIN_ROOT`
  or reinstall the plugin.
- `onboard.git_missing` → install git, then re-run.
- `onboard.git_lfs_missing` → install Git LFS (`brew install git-lfs`), then re-run. Nothing in the consumer has changed.
- `onboard.git_lfs_hooks_failed` → `git lfs install --local` refused to run, usually because the repository already has a custom `pre-push` hook. Resolve that hook, then re-run. The steps before it have already written their files.
- `onboard.precommit_hook_failed` → git could not report the repository's hooks directory
  (`git rev-parse --git-path hooks`). Fix the repository so that command works, then re-run.
- `onboard.model_install_failed` or `onboard.mflux_install_failed` → check disk space and network
  access. The remediation names the `mflux-save` command to re-run.

The install checks every prerequisite before it writes to the consumer. A failed preflight leaves the
consumer unchanged. A missing Godot or ffmpeg never fails the install.
