# texture-gen MCP: local textures and 2D art

The `texture-gen` MCP server runs the local texture models (Z-Image Turbo and FLUX.2 klein 4B) through
the same implementation as `python -m nmg_game_dev.texture`. Long generations run as background jobs:
a tool returns a `job_id` at once, and you poll `get_texture_job` for progress and the result. The setup,
the models, and the output folders are in `docs/onboarding/texture-models.md`.

Tools return structured results. A refused request comes back as
`{"error": {"code", "message", "remediation"}}`, not as an exception.

| Tool | Purpose | Returns |
|------|---------|---------|
| `generate_textures` | Start a seamless texture job (one `prompt`, or a `requests` batch) | `{"job_id"}` |
| `get_texture_job` | Poll a texture or art job | `queued`, `running` (with `completed`/`total`), `succeeded` (with the result), or `failed` |
| `texture_backends` | Report each backend's availability | `{"backends"}` |
| `texture_contact_sheet` | Rebuild the contact sheet from every texture set | pages, cells, and skipped albedos |
| `generate_art` | Start an untiled 2D art job (`icon`, `ui`, or `painting`) | `{"job_id"}` |
| `finish_art` | Cut a picked art take out into game files | the files written, or an error |

## Art

`generate_art(kind, name, prompt, seeds=None, backend="flux2-klein-4b", aspect=None, resolution=1024)`
writes each take to `SourceArt/Art/raw/<kind>/<name>-<seed>.png`. Seeds that already have a take are
skipped. The prompt adds the project style from `SourceArt/Art/style.json` when that file is present.
Poll with `get_texture_job(job_id)`; its result lists the takes, the skipped seeds, the manifest, and the
contact sheet.

`finish_art(kind, name, pick, width=None)` writes:

- `icon`: `game/assets/UI/Icons/<name>.png` (512 px) and `<name>_small.png` (64 px).
- `ui`: `game/assets/UI/Panels/<name>.png` (1024 px).
- `painting`: `game/assets/UI/Paintings/<name>.png` at `width` (default 1920), with no alpha.

Its errors are `art.take_not_found`, `art.background_not_flat`, and `art.subject_cropped`. A refused
take writes nothing. The full rules are in `docs/onboarding/texture-models.md`, under "Generate 2D art".

## Tool schemas

The inputs and descriptions of every tool are declared in `mcp-servers/texture-gen/tools.json`, and
`scripts/validate-mcp-tools.py` checks them against the registered server.
