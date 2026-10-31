# Design contract

How a game's design is written so that nmg-game-dev can read it. The design lives in your repo as
one markdown file per entity under `docs/design/`. The tools read each file's YAML frontmatter and
ignore its body, so the body is free for notes to people and agents. The `design` skill runs the
commands in this contract.

## 1. Layout

- One entity per file. Every `.md` file under `docs/design/`, at any depth (`docs/design/**/*.md`),
  describes one character, vehicle, prop, environment, region, mission, or system.
- A file starts with a `---` line, then YAML frontmatter, then a closing `---` line. The body after
  it is free text that no tool parses.
- Files under `docs/design/` that are not `.md` are not read.
- `docs/design/backlog.json` is written by `sync`. Its `fields` are rebuilt from the design files on
  every sync, so edit the design files, not the backlog.

```markdown
---
type: prop
name: Crate
asset_class: standard_prop
category: Props
---

Wooden crate by the harbor gate. Free text.
```

## 2. Frontmatter

| Field | Required | Applies to | Rule |
|-------|----------|------------|------|
| `type` | yes | all | One of `character`, `vehicle`, `prop`, `environment`, `region`, `mission`, `system`. |
| `name` | yes | all | Free text. Its asset name is derived from it (section 3). |
| `asset_class` | yes | `character`, `vehicle`, `prop`, `environment` | One of `small_prop`, `standard_prop`, `hero_prop`, `character`, `environment_piece`. |
| `category` | yes | `character`, `vehicle`, `prop`, `environment` | PascalCase, matching `^[A-Z][A-Za-z0-9]*$`. The Unreal category: finalized content lands in `/Game/<Category>/<Name>/`. |
| `act` | no | all | Integer, 1 or more. |
| `depends_on` | no | all | List of other entries' `name` values. |
| `region` | no | `mission` | The `name` of a `region` entry. |

The types `character`, `vehicle`, `prop`, and `environment` are asset types. Finalize turns them
into assets. The types `region`, `mission`, and `system` are scaffolded in Unreal (section 6).

Any other key in the frontmatter is kept in the entry's `fields`.

## 3. Asset names

An entry's `asset_name` is the PascalCase join of the words in its `name`. A word is a run of ASCII
letters and digits. Each word's first letter is uppercased, and the words are joined with no
separator.

| `name` | `asset_name` |
|--------|--------------|
| `Old Town` | `OldTown` |
| `old-town 2` | `OldTown2` |
| `Crate` | `Crate` |
| `3 Crates` | none, reported as `design.invalid_name` |

The result must match `^[A-Z][A-Za-z0-9]*$`. A `name` that does not yield a match is
`design.invalid_name`. Two entries that derive the same `asset_name` are `design.duplicate_name`.

The asset name is also the Blender collection name `<Name>` in the asset contract
(`docs/nmg-game-dev/asset-contract.md` in your project) and the `<Name>` in every Unreal path for the
asset.

## 4. Statuses

| Status | Meaning | Set by |
|--------|---------|--------|
| `planned` | Read from a design file and not yet done. | `sync`: a new entry, or an `orphaned` entry whose file came back. |
| `finalized` | An asset entry whose `finalize_asset` job succeeded. | Finalize, on a successful `finalize_asset` job. |
| `scaffolded` | A region, mission, or system that scaffold created, or found already in Unreal. | `scaffold`. |
| `orphaned` | Its design file was deleted. The entry stays so its progress is not lost. | `sync`. |

What moves an entry between statuses:

- Sync matches entries by `asset_name`, not by file path. Renaming a file without changing its
  `name` keeps the entry's status. Changing `name` makes a new entry and orphans the old one.
- Editing a design file keeps the entry's status and updates its `fields`.
- A new design file adds a `planned` entry.
- A deleted design file makes its entry `orphaned`.
- An `orphaned` entry whose design file returns becomes `planned`.
- A successful `finalize_asset` job makes the matching asset entry `finalized`.
- `scaffold` makes a region, mission, or system `scaffolded` when its Unreal asset is created or
  already exists. An item that fails keeps its status. `orphaned` entries are skipped and stay
  `orphaned`.
- Re-running `sync` on an unchanged set of design files rewrites a byte-identical backlog.

## 5. Backlog

`docs/design/backlog.json` has this shape:

```json
{
  "entries": [
    {
      "asset_name": "Crate",
      "fields": {
        "asset_class": "standard_prop",
        "category": "Props"
      },
      "name": "Crate",
      "source": "docs/design/props/crate.md",
      "status": "planned",
      "type": "prop"
    }
  ],
  "version": 1
}
```

- The top level is `{"version": 1, "entries": [...]}`. Object keys are written in sorted order, so
  `entries` appears before `version` in the file.
- Entries are sorted by `type`, then by `asset_name`.
- Each entry has `type`, `name`, `asset_name`, `source`, `fields`, and `status`. `source` is the
  design file's path relative to the project root. `fields` holds every frontmatter key except
  `type` and `name`.
- The file holds no timestamps. Identical input gives identical bytes.
- `sync` replaces the file atomically: it writes a temporary file beside it, then renames it.

## 6. Commands

```text
python -m nmg_game_dev.design sync [--project DIR]
python -m nmg_game_dev.design scaffold [--project DIR] [--url URL]
```

The project root is `--project DIR` when given. Otherwise it is `CLAUDE_PROJECT_DIR` when that is set,
and the working directory when it is not. `docs/design/` and `docs/design/backlog.json` are read and
written under that root.

### sync

Reads and checks every design file, then writes the backlog.

- If any file has an error, every error is printed, nothing is written, and the command exits 1. An
  existing backlog is left byte-identical.
- Otherwise the backlog is merged with the previous one (section 4), written, and one line is printed
  per entry. The command exits 0.
- If `docs/design/` does not exist, the command exits 1 with `design.dir_missing`.

Entry lines use the status after the merge:

```text
<status> <type> <asset_name>: <source>
```

On a fresh sync every entry is `planned`.

Error lines:

```text
error <code> <source>: <field> — <message>
```

### scaffold

Creates the Unreal assets for every `region`, `mission`, and `system` entry that is not `orphaned`,
in the open Unreal editor. The Unreal MCP endpoint is `--url` when given. Otherwise it is
`http://127.0.0.1:$UE_MCP_PORT/mcp`, using port 8000 when `UE_MCP_PORT` is unset.

- An asset whose path already exists is not modified.
- An item whose Unreal work fails is reported, and the other items still run.
- The backlog is written once, after all items, with the new statuses.
- If the editor cannot be reached, the command exits 2.

Report lines, one per item:

```text
created <type> <asset_name>: <asset path>
unchanged <type> <asset_name>: <asset path>
skipped <type> <asset_name>: <source>
error design.scaffold_failed <asset_name>: <UE error>
```

`skipped` is printed for `orphaned` entries. `created` and `unchanged` both mean the item is now
`scaffolded`.

## 7. Exit codes

| Command | Exit | Meaning |
|---------|------|---------|
| `sync` | 0 | The backlog was written. |
| `sync` | 1 | A design file has an error, or `docs/design/` is missing. Nothing was written. |
| `scaffold` | 0 | Every item was created, unchanged, or skipped. |
| `scaffold` | 1 | At least one item failed with `design.scaffold_failed`. The other items still ran. |
| `scaffold` | 2 | The Unreal editor is unreachable (`mcp.unreal.unreachable`). |

## 8. Scaffolded assets

| Type | Asset | Path | Contents |
|------|-------|------|----------|
| `region` | Level | `/Game/Levels/<Name>/L_<Name>` | Ground plane, `PlayerStart`, `DirectionalLight`, `SkyLight`. |
| `mission` | Mission data asset (`UNmgMissionDefinition`) | `/Game/Missions/<Name>/DA_<Name>` | `MissionName`, `Act`, `Region`, `DependsOn`, and `DesignDocPath` from the entry. `Act` is 0 when `act` is absent. `Region` and `DependsOn` hold asset names. |
| `system` | Actor Component Blueprint | `/Game/Systems/<Name>/BPC_<Name>` | The Blueprint only. |

Mission assets need the `UNmgMissionDefinition` class from the nmg-game-dev runtime plugin. If the
editor does not have it, the mission fails with `design.scaffold_failed`.

## 9. Errors

Sync reports every error it finds. A sync error exits 1 and leaves the backlog untouched.

| Code | Raised when |
|------|-------------|
| `design.frontmatter_missing` | A design file does not start with a frontmatter block. |
| `design.frontmatter_invalid` | The frontmatter block is not valid YAML. |
| `design.unknown_type` | `type` is not one of the seven types in section 2. |
| `design.missing_field` | A required field is absent (section 2). |
| `design.invalid_field` | A field value breaks its rule in section 2, such as an unknown `asset_class`, a `category` that is not PascalCase, or an `act` that is not an integer of 1 or more. |
| `design.duplicate_name` | Two entries derive the same `asset_name`. |
| `design.invalid_name` | `name` does not yield a valid `asset_name` (section 3). |
| `design.unknown_reference` | A `depends_on` name matches no entry, or a `region` name matches no `region` entry. |
| `design.dir_missing` | `docs/design/` does not exist. Sync exits 1. |
| `design.scaffold_failed` | Unreal work for one scaffold item failed. The item keeps its status, the other items still run, and scaffold exits 1. |
| `mcp.unreal.unreachable` | Scaffold could not reach the Unreal MCP endpoint. Scaffold exits 2. |
| `design.backlog_update_failed` | Warning only. Finalize could not update the backlog after a successful job. The job still succeeds, and the warning is in its result. Sync and scaffold never raise it. |

## 10. Finalize fallback

When a finalize call omits `category` or `asset_class`, finalize takes the missing value from the
asset entry whose `asset_name` equals the collection name. An explicit argument always wins. When
the argument is still missing and no entry matches, the call fails with `finalize.invalid_request`,
which names the argument and the backlog path it checked.
