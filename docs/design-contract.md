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
| `asset_class` | yes | `character`, `vehicle`, `prop`, `environment` | One of `small_prop`, `standard_prop`, `hero_prop`, `character`, `environment_piece`, `terrain`. Use `terrain` for an `environment` entry that is a heightfield (`docs/asset-contract.md` section 9). |
| `category` | yes | `character`, `vehicle`, `prop`, `environment` | PascalCase, matching `^[A-Z][A-Za-z0-9]*$`. The asset category: finalized files land in `game/assets/<Category>/<Name>/`. |
| `act` | no | all | Integer, 1 or more. |
| `depends_on` | no | all | List of other entries' `name` values. |
| `region` | no | `mission` | The `name` of a `region` entry. |
| `terrain` | no | `region` | The `name` of an `environment` entry whose `asset_class` is `terrain`. The region's ground is that terrain's scene, loaded for each platform's variant (section 8). |
| `template` | no | `system` | Only `audio`. An `audio` system scaffolds an `NmgAudio` component and its name table (section 8). Any other value is `design.invalid_field`. |
| `music` | no | `region` | A non-empty string: the name of an imported sound. The region's scene plays it while it is current (section 8). Any other value is `design.invalid_field`. |

The types `character`, `vehicle`, `prop`, and `environment` are asset types. Finalize turns them
into assets. The types `region`, `mission`, and `system` are scaffolded as Godot files (section 6).

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
(`docs/nmg-game-dev/asset-contract.md` in your project) and the `<Name>` in every Godot path for the
asset.

## 4. Statuses

| Status | Meaning | Set by |
|--------|---------|--------|
| `planned` | Read from a design file and not yet done. | `sync`: a new entry, or an `orphaned` entry whose file came back. |
| `finalized` | An asset entry whose `finalize_asset` job succeeded. | Finalize, on a successful `finalize_asset` job. |
| `scaffolded` | A region, mission, or system whose Godot file scaffold created, or found already present. | `scaffold`. |
| `orphaned` | Its design file was deleted. The entry stays so its progress is not lost. | `sync`. |

What moves an entry between statuses:

- Sync matches entries by `asset_name`, not by file path. Renaming a file without changing its
  `name` keeps the entry's status. Changing `name` makes a new entry and orphans the old one.
- Editing a design file keeps the entry's status and updates its `fields`.
- A new design file adds a `planned` entry.
- A deleted design file makes its entry `orphaned`.
- An `orphaned` entry whose design file returns becomes `planned`.
- A successful `finalize_asset` job makes the matching asset entry `finalized`.
- `scaffold` makes a region, mission, or system `scaffolded` when its Godot file is created or
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
python -m nmg_game_dev.design scaffold [--project DIR]
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

Writes the Godot files for every `region`, `mission`, and `system` entry that is not `orphaned`. It
writes text files directly into `game/` and never starts Godot or needs an open editor. The project
must hold `game/project.godot`; otherwise scaffold exits 1 with `design.godot_project_missing`.

- A file that already exists is never overwritten.
- An item whose write fails is reported, and the other items still run.
- The backlog is written once, after all items, with the new statuses.

Report lines, one per item:

```text
created <type> <asset_name>: <file path>
unchanged <type> <asset_name>: <file path>
skipped <type> <asset_name>: <source>
error design.scaffold_failed <asset_name>: <error>
error design.unknown_reference <asset_name>: <message>
```

`skipped` is printed for `orphaned` entries. `created` and `unchanged` both mean the item is now
`scaffolded`. A region whose `terrain` names no terrain entry is reported with `design.unknown_reference`,
writes nothing, and does not stop the other items. An entry whose `asset_name` is not PascalCase (a
hand-edited backlog) is reported with `design.scaffold_failed` the same way, because the name becomes
a file path and a class name.

## 7. Exit codes

| Command | Exit | Meaning |
|---------|------|---------|
| `sync` | 0 | The backlog was written. |
| `sync` | 1 | A design file has an error, or `docs/design/` is missing. Nothing was written. |
| `scaffold` | 0 | Every item was created, unchanged, or skipped. |
| `scaffold` | 1 | At least one item failed with `design.scaffold_failed` or `design.unknown_reference`, and the other items still ran; or `game/project.godot` is missing (`design.godot_project_missing`). |

## 8. Scaffolded files

| Type | File | Contents |
|------|------|----------|
| `region` | `game/levels/<Name>/<Name>.tscn` | A `Node3D` root with a `Marker3D` named `PlayerSpawn`, a `DirectionalLight3D`, a `WorldEnvironment` with an `Environment` sub-resource, and a ground: a flat plane, or the terrain scene described below. |
| `mission` | `game/missions/<Name>.tres` | An `NmgMissionDefinition` resource (the add-on's `res://addons/nmg_game_dev/nmg_mission_definition.gd`) with `mission_name`, `act`, `region`, `depends_on` (`Array[StringName]`), and `design_doc_path` from the entry. `act` is 0 when it is absent. `region` and `depends_on` hold asset names. |
| `system` | `game/systems/<Name>/<snake_name>.gd` | A component script: `class_name <Name>Component` and `extends Node`, where `<snake_name>` is the snake_case form of `<Name>`. |
| `system` with `template: audio` | `game/systems/<Name>/<snake_name>.gd` and `game/systems/<Name>/audio_table.tres` | A component script: `class_name <Name>Component` and `extends NmgAudio`, whose `_init` loads `res://systems/<Name>/audio_table.tres` into `table`. The table is an `NmgAudioTable` resource with `sounds`, each file under `game/assets/Audio/` keyed by its file stem to its `res://` path, and `themes`, each region's `music` field keyed by the region's asset name. `python -m nmg_game_dev.audio refresh` and every successful `import_audio` rewrite the table; scaffold never overwrites either file once it exists. |

A region with a `terrain` field, once that terrain is finalized (its
`res://assets/<Category>/<Name>/Desktop/<Name>.tscn` exists), gets an `NmgVariantScene` node (the
add-on's `res://addons/nmg_game_dev/nmg_variant_scene.gd`) named `<Name>` whose `scene_path` is the
variant-free `res://assets/<Category>/<Name>/<Name>.tscn`, where `<Category>` and `<Name>` are the
terrain entry's. At run time it loads the variant `NmgAssets.resolve_variant_path` picks (Mobile on
mobile and web, Desktop elsewhere), so the region never hard-links a `Desktop/` or `Mobile/` path
that an export preset drops. It gets no flat plane. A region without `terrain`, or whose terrain
scene does not exist yet, gets the flat ground: a `MeshInstance3D` with a 200 m `PlaneMesh` and a `StaticBody3D` with a
`BoxShape3D`.

Mission resources need the `addons/nmg_game_dev` add-on, which `/onboard-consumer` installs into
`game/addons/nmg_game_dev/`.

## 9. Errors

Sync reports every error it finds. A sync error exits 1 and leaves the backlog untouched.

| Code | Raised when |
|------|-------------|
| `design.frontmatter_missing` | A design file does not start with a frontmatter block. |
| `design.frontmatter_invalid` | The frontmatter block is not valid YAML. |
| `design.unknown_type` | `type` is not one of the seven types in section 2. |
| `design.missing_field` | A required field is absent (section 2). |
| `design.invalid_field` | A field value breaks its rule in section 2, such as an unknown `asset_class`, a `category` that is not PascalCase, an `act` that is not an integer of 1 or more, a region's `terrain` that is not a non-empty string, a system's `template` other than `audio` (for example `template: lights`), or a region's `music` that is not a non-empty string. |
| `design.duplicate_name` | Two entries derive the same `asset_name`. |
| `design.invalid_name` | `name` does not yield a valid `asset_name` (section 3). |
| `design.unknown_reference` | A `depends_on` name matches no entry, a `region` name matches no `region` entry, or a region's `terrain` names no `environment` entry with `asset_class` `terrain`. Sync reports it, and scaffold reports it for that region. |
| `design.dir_missing` | `docs/design/` does not exist. Sync exits 1. |
| `design.scaffold_failed` | Writing the file for one scaffold item failed. The item keeps its status, the other items still run, and scaffold exits 1. |
| `design.godot_project_missing` | Scaffold found no `game/project.godot`. Nothing is written, and scaffold exits 1. Run `/onboard-consumer` first. |
| `design.backlog_update_failed` | Warning only. Finalize could not update the backlog after a successful job. The job still succeeds, and the warning is in its result. Sync and scaffold never raise it. |

## 10. Finalize fallback

When a finalize call omits `category` or `asset_class`, finalize takes the missing value from the
asset entry whose `asset_name` equals the collection name. An explicit argument always wins. When
the argument is still missing and no entry matches, the call fails with `finalize.invalid_request`,
which names the argument and the backlog path it checked.
