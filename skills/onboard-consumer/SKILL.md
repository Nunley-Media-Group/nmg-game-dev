---
name: onboard-consumer
description: Onboard a game project to nmg-game-dev: start scripts, SessionStart hooks, Unreal and Blender plugins, local texture models, and the asset contract. Idempotent; re-runs report drift.
required_mcp: []
required_env: [CLAUDE_PLUGIN_ROOT?, CLAUDE_PROJECT_DIR?, TEXTURE_GEN_MODELS_DIR?, BLENDER_EXTENSIONS_DIR?, NMG_SDLC_AUTOPILOT?]
unattended_safe: true
---

# Onboard consumer

Installs everything a consumer game project needs from nmg-game-dev in one run: the start scripts and
their SessionStart hooks, the asset contract, the nmg-game-dev and VibeUE Unreal plugins, the Blender
add-on link, and the two local texture models. Every write is idempotent. A re-run reports what has
drifted from the framework and changes nothing unless it is given `--refresh`.

Use it when the developer starts a new consumer project, upgrades nmg-game-dev, or asks to set up or
repair the project. Never edit the installed copies by hand. Run this instead.

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
   Add `--uproject <file>` only when the project has more than one `.uproject`. The detailed copy,
   link, and merge rules are in `references/install-steps.md`.

3. **Relay the report.** Each step prints one line: `<status> <step>: <detail>`. Statuses are
   `installed`, `unchanged`, `drift`, and `refreshed`. Show every line. For each `drift`, the report
   gives the remediation `re-run with --refresh`. Offer to re-run with `--refresh` and do so only if
   the developer agrees.

4. **Refresh when asked.** `--refresh` restores drifted framework copies, moves VibeUE to the head
   of its `5-8` branch, and replaces a wrong Blender link. It never touches `nmg-budgets.json`. Run it only when
   the developer asks to repair the install.

5. **Point at the next step.** Once the report is clean, direct the developer to
   `docs/onboarding/index.md`, starting with `first-asset.md`.

## Failure modes and remediation

- `onboard.uproject_not_found` or `onboard.uproject_ambiguous` → pass `--uproject <file>` for the
  project's `.uproject`.
- `onboard.models_dir_missing` → choose a volume (flow step 1) and re-run with `--models-dir`.
- `onboard.insufficient_disk` → the chosen volume has less than 60 GiB free while a model is
  missing. Choose another volume. Nothing in the consumer has changed.
- `onboard.unsupported_platform` → the texture models need Apple Silicon macOS. Install the rest on
  this host by re-running with the models already present, or skip the models.
- `onboard.framework_incomplete` → the framework root is incomplete. Check `CLAUDE_PLUGIN_ROOT`
  or reinstall the plugin.
- `onboard.git_missing` → install git, then re-run.
- `onboard.model_install_failed` or `onboard.mflux_install_failed` → check disk space and network
  access. The remediation names the `mflux-save` command to re-run.
- `onboard.vibeue_clone_failed` → check network access to github.com, then re-run.

The install checks every prerequisite before it writes to the consumer. A failed preflight leaves the
consumer unchanged.
