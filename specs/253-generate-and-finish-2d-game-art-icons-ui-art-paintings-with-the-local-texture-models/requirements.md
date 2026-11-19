# Requirements: Generate and finish 2D game art (icons, UI art, paintings) with the local texture models

**Issue**: #253
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley

## User Story

**As a** game developer making a game's interface and story art
**I want** to generate icons, UI panels, and paintings with the local texture models in one project style, and to turn them into cut-out game images
**So that** a set of forty icons looks like one set and lands in the game without hand editing

## Background

FLUX.2 klein 4B and Z-Image Turbo are general text-to-image models, but texture-gen uses them only for tiling material maps. It always appends a fixed tiling photo-scan suffix, runs the seamless pass, can derive maps, and generates square images only. A game also needs item icons, interface panels and frames, and paintings. Icons and UI art need a transparent background, the same framing, and (for icons) a small copy.

Raw takes under `SourceArt/Art/raw/` are the kept source; finished images under `game/assets/UI/` are derived and can be rebuilt.

## Acceptance Criteria

### AC1: 2D art generates without tiling

**Given** the local texture models are installed
**When** `python -m nmg_game_dev.texture art --kind icon --name HealthPotion --prompt "red potion bottle" --seeds 1,2,3` runs, or the texture-gen MCP tool `generate_art` is called with the same values and its job is polled with `get_texture_job`
**Then** three raw PNGs are written to `SourceArt/Art/raw/icon/HealthPotion-<seed>.png` with no seamless pass and no derived maps, the prompt used is `<prompt>, <project style>, <kind style>` (`<prompt>, <kind style>` without a project style), `SourceArt/Art/raw/icon/HealthPotion.json` records the prompt, style, backend, and takes, and a contact sheet `SourceArt/Art/raw/icon/HealthPotion_sheet.png` of the takes is written

### AC2: Kinds set framing and size

**Given** kinds `icon` and `ui` (1:1, subject centered on a flat plain background, nothing cropped) and `painting` (aspect `16:9`, `3:2`, or `1:1`, default `16:9`)
**When** art is generated for each kind
**Then** each raw image's long side is the requested resolution (default 1024), both sides are multiples of 64, its aspect ratio is within 5 % of the kind's, and its prompt carries the kind's framing text

### AC3: The project style is shared

**Given** `SourceArt/Art/style.json` with a `style` sentence
**When** art or texture generation runs
**Then** the sentence is added to every art prompt and recorded as `project_style` in the art manifest and in `textures.json`, while texture prompts stay unchanged; when the file is absent, art prompts use only the kind style and `project_style` is null

### AC4: Existing takes are skipped

**Given** `SourceArt/Art/raw/icon/HealthPotion-2.png` exists
**When** the same request runs again
**Then** seed 2 is reported in `skipped` and not regenerated, and when every requested seed exists no worker process is started and no model is loaded

### AC5: Icons and UI art are cut out

**Given** a raw `icon` or `ui` image on a flat background
**When** `python -m nmg_game_dev.texture art-finish --kind icon --name HealthPotion --pick 2` runs (or the MCP tool `finish_art`)
**Then** the background reachable from the four corners within the colour tolerance becomes transparent with an edge feathered over 1–2 px, the subject is cropped and scaled onto a square canvas with an 8 % margin, centered horizontally, with its bottom on the bottom margin line, `game/assets/UI/Icons/HealthPotion.png` (512 px) and `HealthPotion_small.png` (64 px) are written (for `ui`: `game/assets/UI/Panels/<Name>.png` at 1024 px only), and running it again gives byte-identical files

### AC6: A non-flat background is rejected

**Given** a raw image whose four corners differ by more than the tolerance, or whose subject touches the image edge
**When** `art-finish` runs
**Then** it fails with `art.background_not_flat` or `art.subject_cropped` and a remediation, and writes nothing

### AC7: Paintings are finished without a cut-out

**Given** a picked `painting`
**When** `art-finish --kind painting --name <Name> --pick <seed> [--width W]` runs
**Then** `game/assets/UI/Paintings/<Name>.png` is written at width `W` (default 1920) keeping the aspect ratio, with no alpha channel, and running it again gives a byte-identical file

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | Add an art mode to texture-gen: kind styles and aspect ratios, non-square width and height passed to the worker, no seamless pass, no maps | Must |
| FR2 | Read `SourceArt/Art/style.json`; add its sentence to art prompts and record it as `project_style` in art and texture manifests | Must |
| FR3 | Add `texture art` and `art-finish` CLI commands and the `generate_art` (queued job) and `finish_art` MCP tools | Must |
| FR4 | Implement the corner flood-fill cut-out, feather, crop, margin and baseline placement, and full and small sizes with Pillow and NumPy | Must |
| FR5 | Skip raw takes that exist; make finishing deterministic | Must |
| FR6 | Tests cover each AC with the fake worker and synthetic images | Must |
| FR7 | Document the art flow in `docs/onboarding/texture-models.md` | Should |

## Out of Scope

- Hosted image APIs.
- Drawing UI art in code or in Godot themes.
- Changing tiling texture prompts or output; texture generation only records `project_style`.
- Running a Godot import from `art-finish`.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #253 | 2026-11-18 | Initial feature spec |
