# convert-to-godot

`/convert-to-godot` migrates a consumer project that was built on Unreal Engine to the Godot 4
pipeline in one command. The skill and the `python -m nmg_game_dev.convert` CLI run the same code.
It re-creates what the pipeline made from your sources, lists what it cannot convert, and deletes the
Unreal files only after every item converted.

## Command

```
python -m nmg_game_dev.convert [--project DIR] [--dry-run] [--json]
```

| Flag | Meaning |
|------|---------|
| `--project DIR` | Consumer root. Default: `CLAUDE_PROJECT_DIR` when set, else the working directory. |
| `--dry-run` | Print the plan (`PLAN convert <item>`, `PLAN delete <path>`) and write nothing. |
| `--json` | Also print the result as JSON: converted, failed, manual port, deletions, deleted. |

Exit codes: `0` every item converted (or the dry run planned it), `1` a guard or item failure, `2` an
argument error.

## What it converts

| Item | Found as | Converted to |
|------|----------|--------------|
| `asset:<Category>/<Name>` | every `Content/<Category>/<Name>/Mobile/nmg-asset.json`; the asset class is its `class` | a full finalize of the single `SourceArt/**/<Name>.blend` (names compared case-insensitively), collection `<Name>`, into `game/assets/<Category>/<Name>/{Desktop,Mobile}/` |
| `audio:SFX/<Name>` | `SourceArt/Audio/SFX/<Name>.wav` | `game/assets/Audio/<Name>.wav`, imported as `AudioStreamWAV` |
| `audio:Music/<Name>` | `SourceArt/Audio/Music/<Name>.wav` | `game/assets/Audio/<Name>.ogg` (ffmpeg), imported as a looping `AudioStreamOggVorbis` |
| `scaffold:<type>/<Name>` | backlog entries of type region, mission, or system with status `scaffolded` | the Godot files `/design` scaffolds: `game/levels/`, `game/missions/`, `game/systems/` |

It also onboards the project first (see `skills/onboard-consumer/SKILL.md`), removes every
SessionStart hook whose command runs `start-unreal-mcp.sh` (and any hook group left empty) and every
`env` key starting with `UE_` from `.claude/settings.json`, and keeps every other setting.

## What it leaves for you

The report's Manual port section lists what the conversion cannot rebuild:

- every file under `Source/` (C++ game code),
- every `Content/**/*.umap` (levels),
- every `Content/**/*.uasset` outside a finalized `Content/<Category>/<Name>/` folder.

Port these to Godot by hand. Blueprints, levels, and C++ are out of scope.

## Flow

1. **Guards, before any write.** `convert.not_unreal` when the root has no `*.uproject`. Unless a
   conversion is being resumed, `convert.dirty_worktree` when `git status --porcelain` prints
   anything.
2. **Preflight.** `godot.not_found` or `finalize.blender_not_found` when either tool is missing.
3. **Dry run** stops here, after printing the plan.
4. **Convert.** Onboard, then each item that is not done yet. A failure is recorded with its error
   code and remediation, and the other items still run. Each success is written to
   `game/.nmg-convert.json` (`{"version": 1, "done": [...]}`) at once.
5. **Hooks and settings** are replaced in `.claude/settings.json`.
6. **Report.** `godot-conversion-report.md` at the project root has four sections: Converted,
   Failed (item, code, remediation), Manual port (path, reason), and Deletions.
7. **Deletions, only when nothing failed.** `git rm -r -q --ignore-unmatch -- Content Source Config
   Plugins <name>.uproject scripts/start-unreal-mcp.sh` (those that exist), then any untracked
   remainder of those paths and the state file are removed. The deletions are staged for you to
   review and commit.

## Resuming

When any item fails, nothing is deleted, the Deletions section reads `kept: N items failed`, and the
command exits 1. Fix each failure using its remediation and run the command again. The rerun reads
`game/.nmg-convert.json`, skips the clean-tree check, and converts only the items that are not done.

## Error codes

| Code | Meaning | Remediation |
|------|---------|-------------|
| `convert.not_unreal` | No `.uproject` at the project root | Run from the Unreal project root or pass `--project` |
| `convert.dirty_worktree` | Uncommitted changes, or not a git repository | Commit or stash, then rerun |
| `convert.source_missing` | No `SourceArt/**/<Name>.blend` for the asset | Add the Blender source, then rerun |
| `convert.source_ambiguous` | Several sources match the asset's name | Keep exactly one, then rerun |
| `convert.sidecar_invalid` | The asset's `Mobile/nmg-asset.json` is unreadable | Restore it from git, then rerun |
| `convert.backlog_invalid` | `docs/design/backlog.json` is unreadable | Run `/design sync`, then rerun |
| `convert.scaffold_not_run` | The scaffold produced no line for an entry | Run `/design sync`, then rerun |
| `convert.item_failed` | An unexpected error in one item | Fix the cause in the message, then rerun |
| `convert.delete_failed` | `git rm` failed | Resolve the git error, then rerun |
| `convert.state_invalid` | `game/.nmg-convert.json` is unreadable | Delete it and restart from a clean tree |

Finalize (`validate.*`, `import_godot.*`, …), audio (`audio.*`), onboarding (`onboard.*`), and
scaffold (`design.*`) failures keep their own codes and remediations in the report.
