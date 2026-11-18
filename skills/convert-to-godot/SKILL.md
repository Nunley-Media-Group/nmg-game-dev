---
name: convert-to-godot
description: Convert an Unreal-based consumer project to Godot 4 in one command: onboard game/, re-finalize every asset from its Blender source, import the audio, re-scaffold the design backlog, swap the Unreal hooks, and delete the Unreal files only after everything converts.
required_mcp: []
required_env: [CLAUDE_PLUGIN_ROOT?, CLAUDE_PROJECT_DIR?, GODOT_BIN?, BLENDER_APP?, BLENDER_BIN?, FFMPEG_BIN?, TEXTURE_GEN_MODELS_DIR, BLENDER_EXTENSIONS_DIR?]
unattended_safe: false
---

# Convert to Godot

Migrates a consumer project that was set up for Unreal Engine to the Godot 4 pipeline. It onboards
the Godot project in `game/` (as `/onboard-consumer` does), re-finalizes every asset that has a
`Content/<Category>/<Name>/Mobile/nmg-asset.json` from its Blender source into
`game/assets/<Category>/<Name>/{Desktop,Mobile}/`, imports every WAV under `SourceArt/Audio/`,
re-scaffolds every backlog entry that was scaffolded, replaces the Unreal SessionStart hooks and
`UE_*` settings, and writes `godot-conversion-report.md`. Only when every item converts does it
delete `Content/`, `Source/`, `Config/`, `Plugins/`, the `.uproject`, and
`scripts/start-unreal-mcp.sh`, through `git rm`. A partial run keeps every Unreal file and resumes
where it stopped.

Use it once per consumer project, when the developer asks to move the project from Unreal to Godot.
The full reference is `docs/skills/convert-to-godot.md`.

## Flow

1. **Check the tree.** The project must be a git repository with a clean working tree and a
   `.uproject` at its root. Godot 4 (`GODOT_BIN`, `godot` on PATH, or `/Applications/Godot.app`)
   and Blender (`BLENDER_BIN` or `BLENDER_APP`) must be installed, and ffmpeg (`FFMPEG_BIN` or PATH)
   when the project has music. Onboarding needs `TEXTURE_GEN_MODELS_DIR`.

2. **Dry run and confirm.** Run
   `uv run --project "${CLAUDE_PLUGIN_ROOT}" python -m nmg_game_dev.convert --project "$CLAUDE_PROJECT_DIR" --dry-run`.
   It prints one `PLAN convert <item>` line per asset, audio file, and scaffold, and one
   `PLAN delete <path>` line per Unreal path, and writes nothing. Show the plan and ask the developer
   with `AskUserQuestion` whether to convert. The conversion deletes the Unreal files once every item
   succeeds, so never run it without that confirmation.

3. **Convert.** Run the same command without `--dry-run`. Relay each line as it prints:
   `converted <item>`, `failed <item> [<code>]: <message>`, and `deleted <path>`. Finalizing every
   asset in Blender takes a while; let it run.

4. **Relay the report.** Read `godot-conversion-report.md` and summarize its four sections:
   Converted, Failed (item, code, remediation), Manual port (C++ under `Source/`, `.umap` levels,
   and `.uasset` files finalize did not produce), and Deletions. The manual-port items are for the
   developer to rebuild in Godot; the conversion never ports them.

5. **On failure, fix and rerun.** Exit 1 with failed items means no Unreal file was deleted. Apply
   each failure's remediation, then rerun the same command. The rerun skips the items recorded in
   `game/.nmg-convert.json` and retries only the rest, so the clean-tree check does not apply to it.

6. **Commit.** Once the run exits 0, the deletions are staged. Ask the developer to review
   `git status` and commit the conversion.

## Failure modes and remediation

- `convert.not_unreal` → there is no `.uproject` at the project root. Run from the Unreal project
  root or pass `--project`. Nothing was written.
- `convert.dirty_worktree` → commit or stash the uncommitted changes, then rerun. Nothing was written.
- `godot.not_found` → install Godot 4 or set `GODOT_BIN`. Nothing was written.
- `finalize.blender_not_found` → install Blender or set `BLENDER_APP`. Nothing was written.
- `convert.source_missing` → the asset has no `SourceArt/**/<Name>.blend`. Add its Blender source,
  then rerun.
- `convert.source_ambiguous` → several `SourceArt/**/<Name>.blend` files match (names are compared
  case-insensitively). Keep exactly one, then rerun.
- `convert.sidecar_invalid` → restore the asset's `Mobile/nmg-asset.json` from git, then rerun.
- `audio.ffmpeg_not_found` → install ffmpeg or set `FFMPEG_BIN`, then rerun to import the music.
- `onboard.*` → follow the onboarding remediation (see `/onboard-consumer`), then rerun.
- Any finalize, audio, or `design.*` code → follow the remediation in the report row, then rerun.
- `convert.delete_failed` → resolve the git error, then rerun to finish the deletions.
- `convert.state_invalid` → delete `game/.nmg-convert.json` and restart from a clean tree.

## Test fixtures

- `tests/convert_fakes.py` (`make_unreal_consumer`), exercised by `tests/unit/convert/`.
