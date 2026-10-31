# design

`design` reads the game's design docs under `docs/design/` into a backlog, then scaffolds the regions,
missions, and systems in Unreal. The `/design` skill and the `python -m nmg_game_dev.design` CLI run
the same code. The file format and the rules are in `docs/design-contract.md`, which onboarding
installs into the project as `docs/nmg-game-dev/design-contract.md`.

## Flow

```
python -m nmg_game_dev.design sync [--project DIR]
python -m nmg_game_dev.design scaffold [--project DIR] [--url URL]

1. sync: parse every docs/design/**/*.md, check it, and report every error (exit 1, no write)
2. sync: merge with the previous backlog, write docs/design/backlog.json atomically, print one line per entry
3. scaffold: for each region, mission, and system that is not orphaned, create its Unreal asset
   unless it already exists, then print one line per item
4. scaffold: write the backlog once, with the items' new statuses
```

The skill runs `sync`, then `scaffold`, and relays each line as printed. It stops after a failed
sync. Scaffold reaches the Unreal MCP endpoint through `UnrealMcpClient`.

## Commands

| Command | Flag | Meaning |
|---------|------|---------|
| `sync` | `--project DIR` | Project root. Default: `CLAUDE_PROJECT_DIR` when set, else the working directory. |
| `scaffold` | `--project DIR` | Same as for `sync`. |
| `scaffold` | `--url URL` | Unreal MCP endpoint. Default: `http://127.0.0.1:$UE_MCP_PORT/mcp`, port 8000 when unset. |

Asset entries (`character`, `vehicle`, `prop`, `environment`) are not scaffolded. Finalize builds them.

## Report lines

Sync prints one entry line per backlog entry, with the status after the merge:

```text
<status> <type> <asset_name>: <source>
```

Scaffold prints one line per item:

```text
created <type> <asset_name>: <asset path>
unchanged <type> <asset_name>: <asset path>
skipped <type> <asset_name>: <source>
error design.scaffold_failed <asset_name>: <UE error>
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
| `scaffold` | 1 | At least one `design.scaffold_failed`. The other items still ran. |
| `scaffold` | 2 | `mcp.unreal.unreachable`. The editor is not reachable. |

## Scaffolded assets

| Type | Asset | Path |
|------|-------|------|
| `region` | Level with a ground plane, `PlayerStart`, `DirectionalLight`, and `SkyLight` | `/Game/Levels/<Name>/L_<Name>` |
| `mission` | `UNmgMissionDefinition` data asset | `/Game/Missions/<Name>/DA_<Name>` |
| `system` | Actor Component Blueprint | `/Game/Systems/<Name>/BPC_<Name>` |

`UNmgMissionDefinition` is a `UPrimaryDataAsset` with primary asset type `NmgMission`, from the
nmg-game-dev runtime plugin. Its fields are `MissionName`, `Act`, `Region`, `DependsOn`, and
`DesignDocPath`, filled from the entry.

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
| `design.scaffold_failed` | Unreal work for one item failed. | Fix the UE error on the line, then rerun scaffold. Items already created report `unchanged`. |
| `mcp.unreal.unreachable` | The Unreal MCP endpoint is not reachable (exit 2). | Run `scripts/start-unreal-mcp.sh`, then rerun scaffold. |
| `design.backlog_update_failed` | Warning from finalize, not from sync or scaffold. | See `docs/mcp/finalize.md`. |

## Notes

- Scaffold never modifies an existing asset. Rerunning it after a partial failure is safe.
- Scaffold writes the backlog once, after all items, with the new statuses.
- Sync rewrites a byte-identical backlog when the design files have not changed.
