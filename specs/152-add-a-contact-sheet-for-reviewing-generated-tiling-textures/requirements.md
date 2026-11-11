# Requirements: Contact sheet for reviewing generated tiling textures

**Issue**: #152
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/7-consumer-onboarding-onboard-consumer-skill-asset-contract-install-and-onboarding-docs/

## User Story

**As a** developer (or agent) generating tiling textures with texture-gen
**I want** a contact sheet that shows every generated albedo, tiled 2x2 and labeled with its texture-set name
**So that** a texture whose look does not match its name, or that repeats or seams badly, is visible before assets are built on it

## Background

texture-gen writes one texture set per name under the output root (`<root>/<name>/`, with `<backend>_<seed>_<resolution>.png` albedos, derived maps, and a `textures.json` manifest). The only visual artifact is `<name>_compare.png`, written for `--backend both`, which shows one set's images untiled. Nothing shows every set at once or shows an albedo tiled. `TextureResult.as_json()`, which becomes the succeeded job's `result`, has no contact-sheet field.

## Acceptance Criteria

### AC1: Generate refreshes a root-wide contact sheet

**Given** an output root that already holds one or more texture sets with `textures.json` manifests
**When** a generate run (CLI `generate` or an MCP job) succeeds
**Then** the output root contains `contact_sheet_001.png` (and further numbered pages as needed) with one cell per albedo listed in every set's manifest, including the new set
**And** the run's JSON result includes `contact_sheet: {"pages": [...], "cells": N, "skipped": [...]}`

### AC2: Each cell shows the albedo tiled 2x2 with a name label

**Given** a contact sheet built from texture sets
**When** a cell is inspected
**Then** its image area is the albedo repeated in a 2x2 grid, and its label strip shows the texture-set name and, on the line beneath, the backend and seed
**And** cells are ordered by set name, then backend, then seed
**And** derived maps (`_N`, `_R`, `_M`, `_AO`) and `_compare.png` files never appear as cells

### AC3: On-demand rebuild through the CLI

**Given** an output root with texture sets
**When** the developer runs `python -m nmg_game_dev.texture sheet`, optionally with `--root PATH`
**Then** the pages are rebuilt from the current sets
**And** the command prints JSON with `pages`, `cells`, and `skipped`, and exits 0

### AC4: On-demand rebuild through MCP

**Given** the texture-gen MCP server
**When** the agent calls the `texture_contact_sheet` tool
**Then** the sheet is rebuilt for the project's output root and the tool returns `pages`, `cells`, and `skipped`
**And** the tool is declared in `mcp-servers/texture-gen/tools.json`

### AC5: Large roots page into numbered sheets

**Given** an output root with more than 24 albedos
**When** the contact sheet is built
**Then** cells are split in order across `contact_sheet_001.png`, `contact_sheet_002.png`, …, at 24 cells per page
**And** every page path is reported
**And** any `contact_sheet_NNN.png` left from an earlier build and numbered above the new page count is removed

### AC6: Unreadable albedos are skipped without failing

**Given** an output root where a manifest lists an albedo that is missing or not a readable image, or a `textures.json` that is not valid JSON
**When** a generate run or the `sheet` command builds the contact sheet
**Then** that albedo (or manifest) is left out of the pages and listed under `skipped` with its `path` and `reason`
**And** the remaining albedos still appear
**And** the generate run still succeeds with its textures

### AC7: Empty root on demand reports an error

**Given** an output root that is missing or holds no texture sets
**When** the `sheet` command or the `texture_contact_sheet` tool runs
**Then** the CLI prints `ERROR [texture.no_texture_sets]: …` and a `Remediation: …` line to stderr and exits 1
**And** the MCP tool returns `{"error": {"code": "texture.no_texture_sets", "message": …, "remediation": …}}`

### AC8: The rebuild needs no texture backend

**Given** a host with no texture model weights and no supported backend
**When** the `sheet` command or the `texture_contact_sheet` tool runs on an output root with texture sets
**Then** the sheet is built without a backend availability or hardware check

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | Build a contact sheet from every texture set (a direct subdirectory of the output root containing `textures.json`), one cell per manifest `images` entry | Must |
| FR2 | Locate each albedo by the file name of its manifest `path` inside its set folder, so a moved output root still builds | Must |
| FR3 | Render each cell as the albedo resized to 192 px and tiled 2x2 into a 384 px square, under a two-line label strip: the set name, then `<backend> seed <seed>` | Must |
| FR4 | Order cells by set name, backend, then seed; lay them out 6 columns × 4 rows (24 per page) into `contact_sheet_NNN.png` (three-digit, from 001) at the output root; remove stale higher-numbered pages | Must |
| FR5 | A successful generate run refreshes the root contact sheet after writing its manifest and reports it as `contact_sheet` in `TextureResult.as_json()`, and so in the succeeded job result | Must |
| FR6 | Add a `sheet` CLI subcommand with optional `--root` (default `paths.output_root(os.environ, Path.cwd())`) that rebuilds the sheet and prints its JSON | Must |
| FR7 | Add a `texture_contact_sheet` MCP tool that rebuilds the sheet for `paths.output_root` and returns the same JSON, declared in `tools.json` | Must |
| FR8 | Skip a missing or unreadable albedo, or an unreadable manifest, and report each under `skipped` with `path` and `reason`, without failing a generate run | Must |
| FR9 | Raise `TextureGenError("texture.no_texture_sets", …)` with a remediation from the on-demand rebuild when the root has no texture sets; the CLI exits 1 and the MCP tool returns the structured error | Must |
| FR10 | The rebuild imports and calls no backend, hardware probe, or model-weight check | Must |
| FR11 | Document the contact sheet, the `sheet` command, and the `texture_contact_sheet` tool in `docs/onboarding/texture-models.md` | Must |

## Out of Scope

- Automatically judging whether a texture matches its name
- Changing or replacing the `--backend both` comparison sheet
- Contact sheets for derived maps (normal, roughness, metallic, AO)
- Deleting or regenerating texture sets from the sheet

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #152 | 2026-11-11 | Initial feature spec |
