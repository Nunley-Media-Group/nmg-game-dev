# Design: Generate and finish 2D game art (icons, UI art, paintings) with the local texture models

**Issue**: #253
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley

## Overview

A new `src/nmg_game_dev/texture/art.py` builds art requests, prompts, sizes, and raw paths. It feeds them through the existing backend batches (`batch.run_backend_batches`) with no seamless pass and no maps. A new `texture/art_finish.py` turns a picked raw take into game PNGs. `texture/style.py` reads the project style. The job queue learns an `art_request` payload, so the MCP `generate_art` tool queues like `generate_textures`. The worker and `ImageItem` gain explicit width and height.

## Architecture

```
texture art / generate_art ─► art.validate ─► art.plan (prompt, size, raw paths, skip existing)
        │ (MCP: jobs.start(art_request) → run-queue → jobs.run_job → art.run)
        ▼
batch.run_backend_batches(one backend, items with width/height) ─► worker.py (no seamless)
        ▼
SourceArt/Art/raw/<kind>/<Name>-<seed>.png, <Name>.json, <Name>_sheet.png (sheet.compare)

texture art-finish / finish_art ─► art_finish.finish(kind, name, pick)
        icon/ui: flat check → flood fill → feather → crop → place → game/assets/UI/{Icons|Panels}/
        painting: resize → RGB → game/assets/UI/Paintings/
```

### Style (`texture/style.py`)

`project_style(root) -> str | None` reads `<root>/SourceArt/Art/style.json` and returns its stripped `style` string, or `None` when the file is absent. Invalid JSON, a missing `style` string, or an empty one raises `art.style_invalid`. `root` is `CLAUDE_PROJECT_DIR`, else cwd (as in `paths.output_root`).

`generate._generate` adds `"project_style": project_style(root)` to each `textures.json`. Texture prompts are unchanged.

### Art requests and generation (`texture/art.py`)

- `KINDS` maps each kind to its framing text and allowed aspects:
  - `icon`: "single game item icon, one object centered, whole object visible with empty space around it, flat plain solid light grey background, no shadow on the background, no text, no border". Aspects: `1:1`.
  - `ui`: "game interface panel or frame, centered, whole element visible with empty space around it, flat plain solid light grey background, no text". Aspects: `1:1`.
  - `painting`: "painterly illustration, full composition filling the frame, no text, no border". Aspects: `16:9`, `3:2`, `1:1`; default `16:9`.
- `ArtRequest(kind, name, prompt, seeds, backend="flux2-klein-4b", aspect=None, resolution=1024)`.
- `validate()` raises `texture.invalid_request` for:
  - an unknown kind;
  - a name not matching `^[A-Z][A-Za-z0-9]*$`;
  - an empty prompt or no seeds;
  - an aspect not allowed for the kind;
  - `backend == "both"`;
  - a resolution that is not a multiple of 64 in [256, 2048].
- `size(aspect, resolution) -> (width, height)`: the long side is `resolution`, and the short side is `max(64, round(resolution / ratio / 64) × 64)`.
- `full_prompt(request, style) = ", ".join(part for part in (prompt, style, kind_text) if part)`.
- `raw_dir(root, kind) = root / "SourceArt/Art/raw" / kind`. The take path is `<raw_dir>/<Name>-<seed>.png`.
- `run(request, *, registry, env, facts, spawn, cwd, on_progress, deps_probe) -> ArtResult`:
  1. Validate, then call `select_backends(backend)`.
  2. Split the seeds into existing (`skipped`) and missing.
  3. When none are missing, skip the backend availability check, `require_dependencies`, and the batch run, so no worker starts.
  4. Otherwise build `ImageItem`s with `width` and `height` and call `run_backend_batches`. The raw PNGs are kept as written: no `make_seamless`, no `derive`.
  5. Write `<Name>.json` with `{kind, name, prompt, project_style, kind_style, full_prompt, backend, repo, revision, aspect, width, height, takes: [{seed, path, seconds}], skipped: [seed...]}`, merging takes from earlier runs.
  6. Write `<Name>_sheet.png` with `sheet.compare` over every existing take, labelled `seed <n>`.
- `ArtResult.as_json()` returns `{kind, name, prompt, images: [...], skipped: [...], manifest, contact_sheet}`.

### Worker and batch (`texture/batch.py`, `texture/worker.py`)

`ImageItem` gains `width: int | None = None` and `height: int | None = None`. `Batch.as_json` emits them when set. `worker.run_batch` uses `item.get("width") or item["resolution"]` (and likewise for height), so texture items are unchanged.

### Jobs (`texture/jobs.py`)

`start` accepts an `ArtRequest` and stores `{"art_request": art.request_as_json(...)}`. `_total_images` counts missing seeds. `run_job` dispatches `art_request` to `art.run(..., output_root_override)`, recording the result and errors in the same status shape. The project root comes from the job's stored `project_root`.

### Finishing (`texture/art_finish.py`)

- `TOLERANCE = 24`, `MARGIN = 0.08`, `CORNER = 8` (px corner patch), `ICON_SIZES = {"icon": (512, 64), "ui": (1024, None)}`, `DEST = {"icon": "game/assets/UI/Icons", "ui": "game/assets/UI/Panels", "painting": "game/assets/UI/Paintings"}`, `PAINTING_WIDTH = 1920`.
- `finish(root, kind, name, pick, *, width=None) -> dict`:
  1. Load `raw/<kind>/<Name>-<pick>.png` as RGB. A missing take raises `art.take_not_found`.
  2. **Painting.** Resize with LANCZOS to `width × round(width × h / w)`, convert to RGB (no alpha), and save.
  3. **Icon or ui, flatness.** Take the mean of each 8×8 corner patch. If any two means differ by more than `TOLERANCE` in any channel, raise `art.background_not_flat`. The background colour is the mean of the four.
  4. **Flood fill.** Run a 4-connected flood fill from the four corner pixels over pixels whose max channel difference from the background colour is ≤ `TOLERANCE`. It uses an iterative numpy frontier, so there is no recursion. The subject mask is the pixels the fill did not reach.
  5. **Edge check.** If any subject pixel lies on the outer one-pixel border, raise `art.subject_cropped`. Also raise it when the subject mask is empty.
  6. **Feather.** Alpha is the mask (0/255, `L` mode) put through `ImageFilter.BoxBlur(1)` twice, so the edge ramps over 2 px.
  7. **Crop and place.** Crop RGBA to the alpha bounding box. Scale it with LANCZOS so `max(w, h) = size × (1 − 2 × MARGIN)`. Paste it on a transparent `size × size` canvas, horizontally centered, with its bottom edge at `size × (1 − MARGIN)`.
  8. **Small copy.** For icons, the small copy is the full canvas resized with LANCZOS to 64.
- Every PNG is saved with Pillow's `save(path, format="PNG")` with no `pnginfo` and fixed `compress_level=6`, through a temp file and `os.replace`. All validation happens before the first write, so a failure writes nothing.
- The function returns `{kind, name, pick, files: [{path, width, height}]}`.

### CLI and MCP

- `python -m nmg_game_dev.texture art --kind K --name N --prompt P [--seeds 1,2,3] [--backend B] [--aspect A] [--resolution R]` runs blocking and prints the `ArtResult` JSON.
- `python -m nmg_game_dev.texture art-finish --kind K --name N --pick SEED [--width W]` prints the finish JSON. Errors print `ERROR [code]` and `Remediation:` lines and exit 1, as the existing commands do.
- The texture-gen MCP server adds:
  - `generate_art(kind, name, prompt, seeds=None, backend="flux2-klein-4b", aspect=None, resolution=1024) -> {"job_id"}`; the job is polled with `get_texture_job`.
  - `finish_art(kind, name, pick, width=None) -> dict | {"error"}`.
  - `tools.json` gains both entries.

## API / Interface Changes

| Interface | Input | Output / Error | Behavior |
|-----------|-------|----------------|----------|
| `texture art` / `generate_art` | kind, name, prompt, seeds, backend, aspect, resolution | `ArtResult` JSON / job id; `texture.invalid_request`, backend availability codes, `art.style_invalid` | raw takes, manifest, contact sheet |
| `texture art-finish` / `finish_art` | kind, name, pick, width | files written; `art.take_not_found`, `art.background_not_flat`, `art.subject_cropped` | deterministic game PNGs |
| `SourceArt/Art/style.json` | `{"style": "..."}` | — | art prompts + `project_style` in manifests |
| `textures.json` | — | adds `project_style` | record only |
| worker batch item | adds `width`, `height` | — | non-square art |

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Run art through the texture job queue | Selected | Model loads take longer than an MCP call; the queue and `get_texture_job` already exist |
| Pillow `ImageDraw.floodfill` | Rejected | It fills one seed with an exact or threshold colour on the image itself; a numpy mask fill gives the mask directly from four seeds |
| Adding the project style to texture prompts | Rejected | Interview choice: record only |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #253 | 2026-11-18 | Initial feature design |
