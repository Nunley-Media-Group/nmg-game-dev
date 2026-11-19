# design

`design` reads the game's design docs under `docs/design/` into a backlog, then scaffolds the regions,
missions, and systems as Godot files. The `/design` skill and the `python -m nmg_game_dev.design` CLI run
the same code. The file format and the rules are in `docs/design-contract.md`, which onboarding
installs into the project as `docs/nmg-game-dev/design-contract.md`.

## Flow

```
python -m nmg_game_dev.design sync [--project DIR]
python -m nmg_game_dev.design scaffold [--project DIR]

1. sync: parse every docs/design/**/*.md, check it, and report every error (exit 1, no write)
2. sync: merge with the previous backlog, write docs/design/backlog.json atomically, print one line per entry
3. scaffold: for each region, mission, and system that is not orphaned, write its Godot file
   (.tscn, .tres, or .gd) unless it already exists, then print one line per item
4. scaffold: write the backlog once, with the items' new statuses
```

The skill runs `sync`, then `scaffold`, and relays each line as printed. It stops after a failed
sync. Scaffold writes text files directly into `game/`; it never starts Godot.

## Commands

| Command | Flag | Meaning |
|---------|------|---------|
| `sync` | `--project DIR` | Project root. Default: `CLAUDE_PROJECT_DIR` when set, else the working directory. |
| `scaffold` | `--project DIR` | Same as for `sync`. |

Asset entries (`character`, `vehicle`, `prop`, `environment`) are not scaffolded. Finalize builds them.

## Report lines

Sync prints one entry line per backlog entry, with the status after the merge:

```text
<status> <type> <asset_name>: <source>
```

Scaffold prints one line per item:

```text
created <type> <asset_name>: <file path>
unchanged <type> <asset_name>: <file path>
skipped <type> <asset_name>: <source>
error design.scaffold_failed <asset_name>: <error>
error design.unknown_reference <asset_name>: <message>
```

`created` and `unchanged` both set the item to `scaffolded`. `skipped` is printed for an `orphaned`
entry, which keeps its status. A failed item keeps its status.

Sync prints an error line per problem and writes nothing when there is any:

```text
error <code> <source>: <field> — <message>
```

## Exit codes

| Command | Exit | Meaning |
|---------|------|---------|
| `sync` | 0 | Backlog written. |
| `sync` | 1 | A file has an error, or `docs/design/` is missing. The backlog is unchanged. |
| `scaffold` | 0 | Every item was created, unchanged, or skipped. |
| `scaffold` | 1 | At least one `design.scaffold_failed` or `design.unknown_reference`, and the other items still ran; or `design.godot_project_missing`. |

## Scaffolded files

| Type | File | Contents |
|------|------|----------|
| `region` | `game/levels/<Name>/<Name>.tscn` | `Marker3D` `PlayerSpawn`, `DirectionalLight3D`, `WorldEnvironment`, and a 200 m ground plane, or an `NmgVariantScene` that loads the platform's variant of the finalized terrain scene the region's `terrain` names |
| `mission` | `game/missions/<Name>.tres` | An `NmgMissionDefinition` resource with `mission_name`, `act`, `region`, `depends_on`, and `design_doc_path` |
| `system` | `game/systems/<Name>/<snake_name>.gd` | A component script, `class_name <Name>Component` / `extends Node` |

`NmgMissionDefinition` is a `Resource` class from the `addons/nmg_game_dev` add-on that
`/onboard-consumer` installs. Its fields are filled from the entry.

## Failure codes

| Code | Meaning | Remediation |
|------|---------|-------------|
| `design.dir_missing` | `docs/design/` does not exist. | Run `/onboard-consumer`, or create the folder and add the design docs. |
| `design.frontmatter_missing` | A file has no leading `---` frontmatter block. | Add the block, then rerun sync. |
| `design.frontmatter_invalid` | The frontmatter is not valid YAML. | Fix the YAML, then rerun sync. |
| `design.unknown_type` | `type` is not a listed type. | Use one of the seven types, then rerun sync. |
| `design.missing_field` | A required field is absent. | Add the field the line names, then rerun sync. |
| `design.invalid_field` | A value breaks its rule. | Correct the value the line names, then rerun sync. |
| `design.duplicate_name` | Two entries derive the same asset name. | Rename one `name`, then rerun sync. |
| `design.invalid_name` | `name` yields no valid asset name. | Use words that form a PascalCase name starting with a letter, then rerun sync. |
| `design.unknown_reference` | `depends_on` or `region` names no entry. | Fix the name, or add the design file, then rerun sync. |
| `design.scaffold_failed` | Writing one item's file failed. | Fix the error on the line, then rerun scaffold. Items already created report `unchanged`. |
| `design.godot_project_missing` | `game/project.godot` does not exist (exit 1). | Run `/onboard-consumer`, then rerun scaffold. |
| `design.backlog_update_failed` | Warning from finalize, not from sync or scaffold. | See `docs/mcp/finalize.md`. |

## Notes

- Scaffold never overwrites an existing file. Rerunning it after a partial failure is safe.
- Scaffold writes the backlog once, after all items, with the new statuses.
- Sync rewrites a byte-identical backlog when the design files have not changed.
