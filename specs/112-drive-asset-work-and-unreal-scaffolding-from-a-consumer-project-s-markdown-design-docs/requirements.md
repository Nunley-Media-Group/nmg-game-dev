# Requirements: Drive asset work and Unreal scaffolding from a consumer project's markdown design docs

**Issue**: #112
**Date**: 2026-10-31
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/69-reshape-the-pipeline-to-finalize-an-authored-asset-instead-of-generating-from-a-prompt/

## User Story

**As a** game developer working in a consumer project onboarded to nmg-game-dev
**I want** the game's design (characters, vehicles, props, environments, regions, missions, systems), written as markdown files in the repo, to drive the plugin's work
**So that** asset finalization and Unreal scaffolding follow the design instead of being typed in by hand each time

## Background

Nothing in nmg-game-dev reads a consumer's design today. Every `finalize_asset` call needs `category` and `asset_class`, and levels, missions, and gameplay systems have no generated starting point. The design lives in the consumer repo as one markdown file per entity under `docs/design/`: a YAML frontmatter the tools read and a free-form body they ignore. The project root is `CLAUDE_PROJECT_DIR` when set, otherwise the working directory.

Frontmatter fields:

| Field | Types | Rule |
|-------|-------|------|
| `type` | all | One of `character`, `vehicle`, `prop`, `environment`, `region`, `mission`, `system` |
| `name` | all | Free text. Its asset name is the PascalCase join of its alphanumeric words (`Old Town` → `OldTown`), which must match `^[A-Z][A-Za-z0-9]*$` |
| `asset_class` | character, vehicle, prop, environment (required) | One of `small_prop`, `standard_prop`, `hero_prop`, `character`, `environment_piece` |
| `category` | character, vehicle, prop, environment (required) | PascalCase |
| `act` | all (optional) | Integer ≥ 1 |
| `depends_on` | all (optional) | List of other entries' names |
| `region` | mission (optional) | The name of a `region` entry |

Statuses: `planned`, `finalized`, `scaffolded`, `orphaned`.

## Acceptance Criteria

### AC1: Design docs parse into a backlog

**Given** a consumer project whose `docs/design/**/*.md` files have valid frontmatter
**When** `python -m nmg_game_dev.design sync` runs
**Then** it writes `docs/design/backlog.json` as `{"version": 1, "entries": [...]}`. There is one entry per file, with `type`, `name`, `asset_name`, `source` (path relative to the project root), `fields` (the remaining frontmatter keys), and `status: "planned"`. Entries are sorted by type, then asset name. The command prints one line `planned <type> <asset_name>: <source>` per entry and exits 0

### AC2: Re-sync preserves progress and flags removed items

**Given** an existing `backlog.json` with entries at `finalized` or `scaffolded`
**When** one design file is edited, one is added, and one is deleted, and sync runs again
**Then** existing entries keep their status and take the edited fields. The new file adds a `planned` entry. The deleted file's entry stays with status `orphaned`, and an orphaned entry whose file returns becomes `planned`. Running sync on an unchanged doc set rewrites a byte-identical backlog

### AC3: Invalid design files are reported, not guessed

**Given** design files with missing or unparseable frontmatter, an unknown `type`, an asset type missing `asset_class` or `category`, an invalid field value, a duplicate asset name, a name that yields no valid asset name, or a `depends_on`/`region` that names no entry
**When** sync runs
**Then** it prints one `error <code> <source>: <field> — <message>` line for every problem, using `design.frontmatter_missing`, `design.frontmatter_invalid`, `design.unknown_type`, `design.missing_field`, `design.invalid_field`, `design.duplicate_name`, `design.invalid_name`, or `design.unknown_reference`. It exits 1 and leaves any existing `backlog.json` byte-identical. A missing `docs/design/` exits 1 with `design.dir_missing`

### AC4: finalize_asset resolves category and class from the backlog

**Given** a backlog entry of an asset type whose `asset_name` is `<Name>`
**When** `finalize_asset` (the MCP tool or `python -m nmg_game_dev.finalize`) is called for collection `<Name>` without `category` or `asset_class`
**Then** it uses the entry's values. When the job succeeds, the entry's status becomes `finalized`, and explicit arguments still take precedence. When no matching entry exists and an argument is missing, it returns `finalize.invalid_request` naming the missing argument and the backlog it checked. If updating the backlog fails, the job still succeeds and its result carries a warning

### AC5: Non-asset items are scaffolded in Unreal

**Given** backlog entries of type `region`, `mission`, and `system` that are not `orphaned`
**When** `python -m nmg_game_dev.design scaffold` runs against the open Unreal editor
**Then** each region gets level `/Game/Levels/<Name>/L_<Name>` with a ground plane, a `PlayerStart`, a `DirectionalLight`, and a `SkyLight`. Each mission gets a `UNmgMissionDefinition` data asset at `/Game/Missions/<Name>/DA_<Name>` with `MissionName`, `Act`, `Region`, `DependsOn`, and `DesignDocPath` from the entry. Each system gets an Actor Component Blueprint at `/Game/Systems/<Name>/BPC_<Name>`. Each gets a `created <type> <Name>: <asset path>` line, and its status becomes `scaffolded`

### AC6: Scaffolding never overwrites existing work

**Given** a target asset path that already exists
**When** scaffold runs
**Then** that item prints `unchanged <type> <Name>: <asset path>`, the asset is not modified, its status becomes `scaffolded`, and the other items still scaffold. Orphaned entries print `skipped`. An item whose UE work fails prints `error design.scaffold_failed <Name>: <UE error>`, the others still run, and the command exits 1. An unreachable editor exits 2 with `mcp.unreal.unreachable`

### AC7: Onboarding installs the design-doc contract

**Given** a consumer project
**When** `onboard-consumer` runs
**Then** it copies `docs/design-contract.md` to `docs/nmg-game-dev/design-contract.md` with the same installed/unchanged/drift/refreshed behavior as the asset contract. It creates `docs/design/` when absent without touching existing files there. The marked CLAUDE.md/AGENTS.md block also points at the design contract

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | `docs/design-contract.md` defines the file layout, frontmatter fields, statuses, and commands above | Must |
| FR2 | `python -m nmg_game_dev.design sync [--project DIR]` writes a deterministic, sorted, atomically replaced `docs/design/backlog.json` | Must |
| FR3 | Re-sync preserves status, updates fields, adds new entries, and marks removed entries `orphaned` | Must |
| FR4 | Validation reports every `design.*` error with file and field and leaves the backlog untouched | Must |
| FR5 | `finalize_asset` and `run_finalize_step` (MCP and CLI) fall back to backlog `category`/`asset_class`, and a successful `finalize_asset` job marks the entry `finalized` | Must |
| FR6 | `python -m nmg_game_dev.design scaffold [--project DIR] [--url URL]` creates region levels, mission data assets of the new runtime class `UNmgMissionDefinition` (a `UPrimaryDataAsset` with primary asset type `NmgMission`), and system component Blueprints, and marks them `scaffolded` | Must |
| FR7 | Scaffolding skips existing targets and continues past per-item failures | Must |
| FR8 | `onboard-consumer` installs the design contract, creates `docs/design/`, and extends the agent-instructions block | Must |
| FR9 | `skills/design/SKILL.md` documents running sync and scaffold and relaying their report lines. `skills/finalize-asset/SKILL.md` and the onboarding docs mention the backlog fallback | Should |

## Out of Scope

- Authoring asset geometry or textures from the design body
- Mission logic, system behavior, or level art beyond the graybox
- Reading design content from outside the repository
- Parsing the markdown body into structured data

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #112 | 2026-10-31 | Initial feature spec |
