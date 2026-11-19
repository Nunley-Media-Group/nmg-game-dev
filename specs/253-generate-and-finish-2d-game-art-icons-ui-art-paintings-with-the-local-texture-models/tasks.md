# Tasks: Generate and finish 2D game art (icons, UI art, paintings) with the local texture models

**Issue**: #253
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley

## Implementation Tasks

### T001: Read the project style and record it in texture manifests

**File(s)**: `src/nmg_game_dev/texture/style.py`, `src/nmg_game_dev/texture/generate.py`
**Type**: Create
**Depends**: none
**Acceptance**:
- FR2, AC3: `project_style` returns the `style` sentence or `None`; invalid content raises `art.style_invalid`; `textures.json` gains `project_style` while texture prompts are unchanged.

### T002: Pass width and height through batches and the worker

**File(s)**: `src/nmg_game_dev/texture/batch.py`, `src/nmg_game_dev/texture/worker.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- FR1, AC2: `ImageItem` carries optional `width`/`height`; `Batch.as_json` emits them; the worker generates `width × height` when given and `resolution × resolution` otherwise.

### T003: Add art generation

**File(s)**: `src/nmg_game_dev/texture/art.py`, `src/nmg_game_dev/texture/jobs.py`
**Type**: Create
**Depends**: T001, T002
**Acceptance**:
- AC1: raw takes land at `SourceArt/Art/raw/<kind>/<Name>-<seed>.png` with no seamless pass or maps; the prompt is `<prompt>, <project style>, <kind style>`; `<Name>.json` and `<Name>_sheet.png` are written.
- AC2: sizes follow the kind's aspect (icon/ui 1:1; painting 16:9 default, 3:2, 1:1), long side = resolution, multiples of 64, within 5 %; invalid kind, aspect, name, `both`, or resolution raise `texture.invalid_request`.
- AC4: existing seeds are reported in `skipped`; with none missing, no worker is spawned.
- Jobs: `start` queues an `art_request`, and `run_job` runs it, so `get_texture_job` reports its progress and result.

### T004: Add art finishing

**File(s)**: `src/nmg_game_dev/texture/art_finish.py`
**Type**: Create
**Depends**: none
**Acceptance**:
- FR4, AC5: the corner flood fill, 2 px feather, crop, 8 % margin and bottom baseline placement; icons write 512 px and 64 px `_small` PNGs to `game/assets/UI/Icons/`; ui writes 1024 px to `game/assets/UI/Panels/`; output is byte-identical across runs.
- AC6: differing corners raise `art.background_not_flat`; a subject on the border (or no subject) raises `art.subject_cropped`; nothing is written.
- AC7: a painting is resized to `--width` (default 1920) keeping the aspect ratio, RGB with no alpha, into `game/assets/UI/Paintings/`.
- A missing pick raises `art.take_not_found`.

### T005: Add the CLI commands and MCP tools

**File(s)**: `src/nmg_game_dev/texture/__main__.py`, `mcp-servers/texture-gen/src/texture_gen_mcp/server.py`, `mcp-servers/texture-gen/tools.json`
**Type**: Modify
**Depends**: T003, T004
**Acceptance**:
- FR3: `texture art` and `texture art-finish` with the options in design.md; MCP `generate_art` returns a `job_id` and `finish_art` returns the finish JSON or `{"error"}`.
- Evidence: `gate-mcp-schema` (`uv run python scripts/validate-mcp-tools.py`).

### T006: Unit tests

**File(s)**: `tests/unit/texture/test_art.py`, `tests/unit/texture/test_art_finish.py`, `tests/unit/texture/test_style.py`, `tests/unit/texture/test_generate.py`, `tests/unit/texture/test_cli.py`, `tests/unit/texture/test_mcp_server.py`, `tests/unit/texture/test_jobs.py`, `tests/texture_fakes.py`
**Type**: Create
**Depends**: T005
**Acceptance**:
- AC1, AC2, AC4: with the fake worker, raw take paths, sizes per kind and aspect, prompts, the manifest and sheet, no seamless change to the raw pixels, `skipped` seeds, and no spawn when all seeds exist; the fake worker honours `width`/`height`.
- AC3: art prompts with and without `style.json`; `textures.json` records `project_style` and texture prompts are unchanged.
- AC5–AC7: synthetic images (a disc on a flat grey background; a gradient-corner image; a subject touching the edge; a 16:9 painting) give the expected files, sizes, transparent corners, feathered edge alpha values strictly between 0 and 255 within 2 px of the edge, the same bottom baseline for two different subjects, byte-identical reruns, and the error codes with nothing written.
- Jobs: an `art_request` job runs to `succeeded` with the fake spawn.
- Evidence: `uv run pytest tests/unit -q` (`repository.tests`), `repository.lint`, `repository.format`, `repository.types`.

### T007: BDD scenarios

**File(s)**: `tests/bdd/features/game_art.feature`, `tests/bdd/test_game_art_bdd.py`
**Type**: Create
**Depends**: T006
**Acceptance**:
- SCN001–SCN007 bind AC1–AC7 using the fake worker, `APPLE_SILICON_32GB` facts, and synthetic images.
- Evidence: `uv run pytest tests/bdd -q` (`repository.tests`).

### T008: Document the art flow

**File(s)**: `docs/onboarding/texture-models.md`, `docs/mcp/texture-gen.md`, `CHANGELOG.md`
**Type**: Modify
**Depends**: T005
**Acceptance**:
- FR7: `docs/onboarding/texture-models.md` gains an art section: kinds and aspects, `style.json`, raw takes and the contact sheet, skipping, `art-finish` outputs and error codes, and the `generate_art`/`finish_art` tools; the texture-gen MCP doc (created if absent) lists both tools.
- `CHANGELOG.md` `[Unreleased]` bullets for this issue each end with `(#253)`.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #253 | 2026-11-18 | Initial feature tasks |
