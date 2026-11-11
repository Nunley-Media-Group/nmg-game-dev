# Design: Contact sheet for reviewing generated tiling textures

**Issue**: #152
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/7-consumer-onboarding-onboard-consumer-skill-asset-contract-install-and-onboarding-docs/

## Overview

A new module `src/nmg_game_dev/texture/contact_sheet.py` scans the output root for texture sets, renders paged contact sheets with Pillow, and returns a `ContactSheet` result. Three entry points call it: `generate.run` (after it writes the manifest), a new `sheet` CLI subcommand, and a new `texture_contact_sheet` MCP tool. The module imports only Pillow, `paths`, and `errors`, so no backend, hardware probe, or model weights are involved.

## Architecture

- `contact_sheet.collect(root) -> tuple[list[Cell], list[dict[str, str]]]`
  - Iterates the sorted direct subdirectories of `root` that contain `textures.json`. Hidden folders such as `.jobs` have no manifest and are ignored.
  - Parses each manifest. Invalid JSON, or a missing or malformed `images` list, adds `{"path": <manifest>, "reason": "unreadable manifest: …"}` to `skipped`.
  - For each `images` entry, it builds `Cell(set_name=<folder name>, backend, seed, path=<set folder>/<Path(entry["path"]).name>)`. Only manifest images become cells, so derived maps and `_compare.png` never do.
  - Cells are sorted by `(set_name, backend, seed)`.
- `contact_sheet.build(root, *, require_sets: bool) -> ContactSheet`
  - When the root is missing or `collect` finds no texture set and `require_sets` is true, it raises `TextureGenError("texture.no_texture_sets", "No texture sets under <root>.", "Generate a texture first (python -m nmg_game_dev.texture generate --prompt … or the generate_textures tool), or pass --root / set NMG_GAME_DEV_TEXTURE_DIR to the folder that holds them.")`.
  - Each cell image is opened with `PIL.Image.open(path).convert("RGB")`. A `FileNotFoundError`, `OSError`, or `PIL.UnidentifiedImageError` moves the cell to `skipped` with `{"path": str(path), "reason": "<ExceptionType>: <message>"}`.
  - Readable cells are chunked 24 per page and written to `root/contact_sheet_{n:03d}.png`.
  - Afterwards it deletes `root/contact_sheet_*.png` files whose number is above the page count, including all of them when no cell was readable.
  - Returns `ContactSheet(pages, cells=<rendered count>, skipped)`.
- Page layout constants: `CELL = 384`, `TILE = 192`, `COLUMNS = 6`, `ROWS = 4`, `PER_PAGE = 24`, `LABEL_HEIGHT = 40` (two text lines), and `GUTTER = sheet.GUTTER` (12). Each page's height covers only the rows it uses. The background is `(24, 24, 24)` and the text is `(235, 235, 235)`, matching `sheet.compare`.
- `ContactSheet.as_json()` returns `{"pages": [str, …], "cells": int, "skipped": [{"path", "reason"}, …]}`.

## API / Interface Changes

| Interface | Input | Output / Error | Behavior |
|-----------|-------|----------------|----------|
| `contact_sheet.build(root, *, require_sets)` | `Path`, bool | `ContactSheet` / `texture.no_texture_sets` | Scan, render, page, prune |
| `generate.run(...)` | unchanged | `TextureResult` with `contact_sheet` | Calls `build(base, require_sets=False)` after the manifest write. An unexpected `OSError` while writing the sheet becomes `contact_sheet: {"pages": [], "cells": 0, "skipped": [{"path": str(base), "reason": …}]}`, so the run still succeeds |
| `TextureResult.as_json()` | — | adds `"contact_sheet": {...}` | Flows into the job's `result` through `jobs.run_job` |
| `python -m nmg_game_dev.texture sheet [--root PATH]` | optional path | stdout JSON, exit 0 / stderr `ERROR [texture.no_texture_sets]`, exit 1 | `build(root, require_sets=True)` |
| MCP `texture_contact_sheet()` | none | `ContactSheet.as_json()` / `{"error": {...}}` | `build(output_root(os.environ, Path.cwd()), require_sets=True)` through the existing `_error` |
| `mcp-servers/texture-gen/tools.json` | — | new tool entry with an empty-object `inputSchema` | Declares the tool |

## Data / Storage Changes

- New files at the output root: `contact_sheet_001.png`, `contact_sheet_002.png`, …. They sit beside the set folders and are never inside one. They are rewritten on every build, and stale higher pages are deleted.
- `textures.json` is unchanged.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| New `contact_sheet.py` module | Selected | Keeps `sheet.compare` unchanged (out of scope) and keeps the rebuild free of backend imports |
| Extend `sheet.py` | Rejected | Mixes the per-run comparison with the root-wide sheet |
| Derive cells by globbing `*.png` | Rejected | Would pick up derived maps and compare sheets; the manifest is authoritative |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #152 | 2026-11-11 | Initial feature design |
