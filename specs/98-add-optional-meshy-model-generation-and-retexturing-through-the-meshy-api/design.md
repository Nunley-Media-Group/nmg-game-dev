# Design: Optional Meshy model generation and retexturing

**Issue**: #98
**Date**: 2026-10-31
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/64-remove-meshy-from-the-pipeline-mcp-config-and-steering/

## Overview

A new `src/nmg_game_dev/meshy/` package owns everything Meshy: key resolution, request validation and routing, the REST client, background jobs, and the session operations. The `meshy` MCP server (`mcp-servers/meshy/`) and `python -m nmg_game_dev.meshy` are thin wrappers over it, mirroring `texture-gen` (`src/nmg_game_dev/texture/jobs.py`, `mcp-servers/texture-gen/src/texture_gen_mcp/server.py`). Blender work goes through `BlenderSessionClient` (`src/nmg_game_dev/pipeline/clients/blender_session.py`) running a new session script `scripts/blender/meshy_session.py`. The pipeline and finalize packages gain no Meshy code; the only pipeline change is a generic `script` parameter on the session client.

## Architecture

| Module | Role |
|--------|------|
| `src/nmg_game_dev/meshy/errors.py` | `MeshyError(PipelineError)` with `code`, `message`, `remediation`, stage `meshy` |
| `src/nmg_game_dev/meshy/config.py` | `project_root(env, cwd)` (`CLAUDE_PROJECT_DIR` else cwd); `read_dotenv(path)`; `api_key(env, cwd)` → env `MESHY_API_KEY` if non-empty, else `.env` value if non-empty, else `meshy.api_key_missing` |
| `src/nmg_game_dev/meshy/paths.py` | `model_dir(root, name)` = `SourceArt/Meshy/<Name>/`; `maps_dir(root, name)` = `SourceArt/Textures/Meshy/<Name>/`; `jobs_root(root)` = `SourceArt/Meshy/.jobs/` |
| `src/nmg_game_dev/meshy/request.py` | `GenerateRequest(name, prompt=None, image_paths=(), texture=True, pose=None)`, `RetextureRequest(name, prompt=None, image_path=None)`; `validate()` raising `meshy.invalid_request`; `image_data_uri(path)`; `route(request) -> "text" | "image" | "multi_image"` |
| `src/nmg_game_dev/meshy/client.py` | `Transport` protocol `send(method, url, headers, body: bytes | None) -> (status, bytes)`; `UrllibTransport`; `MeshyClient(key, transport)` with `create_text_preview`, `create_text_refine`, `create_image_to_3d`, `create_multi_image_to_3d`, `create_retexture`, `get_task(kind, id)`, `download(url) -> bytes` |
| `src/nmg_game_dev/meshy/session.py` | `MeshySession(client: BlenderSessionClient)`: `collection_state(name)`, `import_glb(name, path)`, `export_glb(name, path)`, `apply_maps(name, maps)`; each calls `run_session_op(op, payload, script=MESHY_SESSION_SCRIPT)` |
| `src/nmg_game_dev/meshy/jobs.py` | `start_generate`, `start_retexture`, `status`, `run_job` (injectable `transport`, `session`, `spawn`, `sleep`, `clock`) |
| `src/nmg_game_dev/meshy/__main__.py` | CLI `generate`, `retexture`, `status <job_id>`, internal `run-job <job_dir>` |
| `scripts/blender/meshy_session.py` | Session-side ops; same `NMG_OP` / `NMG_PAYLOAD` / one `NMG_RESULT {json}` line contract as `scripts/blender/finalize_session.py` |
| `mcp-servers/meshy/` | `pyproject.toml` (`mcp==1.30.0`, `nmg-game-dev` path source, script `meshy-mcp = "meshy_mcp.server:main"`), `uv.lock`, `tools.json`, `src/meshy_mcp/server.py` |
| `src/nmg_game_dev/onboard/gitignore.py` | `ensure_gitignore_env(name, path) -> StepResult` |

Pipeline change: `session_code(op, payload, *, script=SESSION_SCRIPT)` and `BlenderSessionClient.run_session_op(op, payload, *, script=SESSION_SCRIPT)` accept an alternative session script path. Default behavior is unchanged.

### Generation routing

| Inputs | Requests (in order) | Body fields |
|--------|---------------------|-------------|
| prompt, `texture=True` | `POST /openapi/v2/text-to-3d` preview → poll → `POST /openapi/v2/text-to-3d` refine → poll | preview: `mode: "preview"`, `prompt`, `pose_mode`?; refine: `mode: "refine"`, `preview_task_id`, `enable_pbr: true` |
| prompt, `texture=False` | preview → poll | preview only |
| 1 image (± prompt) | `POST /openapi/v1/image-to-3d` → poll | `image_url` (data URI), `should_texture: texture`, `enable_pbr: texture`, `texture_prompt`? (prompt), `pose_mode`? |
| 2–4 images (± prompt) | `POST /openapi/v1/multi-image-to-3d` → poll | `image_urls` (data URIs), `should_texture`, `enable_pbr`, `texture_prompt`?, `pose_mode`? |

`pose_mode` is present only when `pose` is given. The GLB comes from the last task's `model_urls.glb`. Task status: `GET` on the create path + `/<id>`.

### Flow

`start_*` runs synchronously inside the MCP call or CLI, in this order:
1. Validate the request (`meshy.invalid_request`).
2. Resolve the key (`meshy.api_key_missing`). Nothing is written before this point.
3. Session checks: generate — `collection_state(name)`; `exists` → `meshy.collection_exists`; unreachable → continue. Retexture — create the job dir, `export_glb(name, <job_dir>/input.glb)`; `missing` or no `SM_<Name>` → `meshy.collection_not_found`; unreachable → `mcp.blender.unreachable`; on any failure the job dir is removed.
4. Write `request.json` (image paths, never image bytes or the key) and `status.json` (`queued`); spawn `python -m nmg_game_dev.meshy run-job <job_dir>` detached (`start_new_session=True`, stdout/stderr to `job.log`); return `{"job_id"}`.

`run_job` (detached child) re-resolves the key from env / `.env`, then:
- Generate: runs the routing table.
- Retexture: `POST /openapi/v1/retexture` with `model_url` = `data:application/octet-stream;base64,<input.glb>`, `text_style_prompt` or `image_style_url`, `enable_pbr: true` → poll; maps from `texture_urls[0]` keys `base_color`, `normal`, `roughness`, `metallic`.
- Poll every 5 s; write `running` with Meshy `progress` and `stage`; `SUCCEEDED` continues; `FAILED|CANCELED|EXPIRED` → `meshy.task_failed` with `task_error.message`; 30 minutes without a terminal state → `meshy.task_timeout`.
- Download outputs (no auth header on asset URLs), then import or apply maps through the session. `PipelineError` `mcp.blender.unreachable` here becomes a warning, not a failure.
- Any other exception → `meshy.job_crashed`, message redacted.

## API / Interface Changes

| Interface | Input | Output / Error | Behavior |
|-----------|-------|----------------|----------|
| MCP `generate_model` | `name`, `prompt?`, `image_paths?: list[str]` (1–4), `texture=True`, `pose?: "a-pose" | "t-pose"` | `{"job_id"}` or `{"error": {code, message, remediation}}` | Starts a generation job. Description: give a prompt, reference images, or both; with images the images shape the model and the prompt steers only the texture; set `pose` only for characters and creatures with limbs, never for props |
| MCP `retexture_model` | `name`, `prompt?`, `image_path?` (exactly one) | same | Exports the collection, starts a retexture job |
| MCP `get_meshy_job` | `job_id` | status doc or `meshy.job_not_found` | Reads `status.json` |
| `python -m nmg_game_dev.meshy generate --name N [--prompt P] [--image PATH ...] [--no-texture] [--pose a-pose|t-pose] [--wait]` | `--image` repeatable | prints `{"job_id"}`; with `--wait` polls and prints the final status JSON | Same `jobs.start_generate` |
| `python -m nmg_game_dev.meshy retexture --name N (--prompt P | --image PATH) [--wait]` | | same | Same `jobs.start_retexture` |
| `python -m nmg_game_dev.meshy status JOB_ID` | | status JSON identical to `get_meshy_job` | `MeshyError` → stderr `ERROR [<code>]: …` / `Remediation: …`, exit 1; argparse errors exit 2 |
| HTTP | base `https://api.meshy.ai`, `Authorization: Bearer <key>`; create response `{"result": "<task id>"}` | 401 → `meshy.auth_failed`; 402 → `meshy.insufficient_credits`; 429 → `meshy.rate_limited`; other non-2xx or network error → `meshy.request_failed` (status and Meshy `message` only) | |
| Session ops (`meshy_session.py`) | `collection_state {name}` → `{ok, state: missing|exists|no_mesh}`; `import_glb {name, path}`; `export_glb {name, path}`; `apply_maps {name, maps}` | `{ok: true, ...}` or `{ok: false, error}` | |
| `ensure_gitignore_env("gitignore_env", <consumer>/.gitignore)` | | `StepResult` `installed` / `unchanged` | Appended to `run_onboard` results after `texture_env` |

### Validation rules (`meshy.invalid_request`)

- `name` matches `^[A-Z][A-Za-z0-9]*$`.
- Generate: at least one of a non-blank `prompt` and `image_paths`; at most 4 images; each exists, has suffix `.png`, `.jpg`, `.jpeg`, or `.webp` (case-insensitive), and is at most 20 MB; with images, `prompt` is at most 800 characters; `texture=False` with both prompt and images is rejected (the prompt would be unused); `pose` is `None`, `"a-pose"`, or `"t-pose"`.
- Retexture: exactly one of `prompt` and `image_path`; image rules as above.
- MIME: `.png` → `image/png`; `.jpg`/`.jpeg` → `image/jpeg`; `.webp` → `image/webp`.

### Status document

`{"job_id", "kind": "generate"|"retexture", "state": "queued"|"running"|"succeeded"|"failed", "stage": str, "progress": 0-100, "result"?, "error"?: {code, message, remediation}}`

Generate result: `{"name", "route": "text"|"image"|"multi_image", "glb_path", "loaded_into_session", "collection"?, "mesh"?, "material"?, "warnings": [{code, message, remediation}]}`.
Retexture result: `{"name", "maps": {"base_color", "normal", "roughness", "metallic"}, "applied_to_session", "warnings": [...]}` — only maps Meshy returned are listed; a missing `base_color` → `meshy.task_failed`.

### Error codes

`meshy.api_key_missing`, `meshy.invalid_request`, `meshy.collection_exists`, `meshy.collection_not_found`, `meshy.auth_failed`, `meshy.insufficient_credits`, `meshy.rate_limited`, `meshy.request_failed`, `meshy.task_failed`, `meshy.task_timeout`, `meshy.job_not_found`, `meshy.job_crashed`; `mcp.blender.unreachable` passes through from the session client.

### Key handling

- `.env` parser: one `KEY=VALUE` per line; ignores blank lines and `#` comments; strips an optional `export ` prefix, surrounding whitespace, and one pair of matching quotes. Unreadable or missing file = no value.
- The key exists only in `MeshyClient`'s header construction. It is never written to `request.json`, `status.json`, or `job.log`, and never included in a message. `jobs.run_job` passes every error message through `redact(text, key)` (replaces the key with `***`) before writing status.
- The child process gets `os.environ` and re-reads `.env` itself.

### Session-side behavior (`scripts/blender/meshy_session.py`)

- `import_glb`: refuse if `<Name>` exists (`meshy.collection_exists`); import with `bpy.ops.import_scene.gltf` into a new collection `<Name>` linked to the scene; join imported mesh objects into one, clear parents keeping transforms, delete leftover empties; name the object and mesh data `SM_<Name>`; rename its first material `M_<Name>_Body` (create one if none). Returns `{ok, collection, mesh, material}`.
- `export_glb`: `<Name>` missing or without `SM_<Name>` → `meshy.collection_not_found`; select only the collection's mesh objects and export GLB with `use_selection=True`; restore the previous selection.
- `apply_maps`: get or create `M_<Name>_Body`, rebuild its node tree with Principled BSDF + Material Output; an Image Texture node per map; base color `colorspace_settings.name = "sRGB"`, others `"Non-Color"`; normal through a Normal Map node; roughness and metallic to their inputs. Clear `SM_<Name>`'s material slots and assign the material. Nodes are found by `type`, not name.

## Data / Storage Changes

- `<project>/SourceArt/Meshy/<Name>/<Name>.glb`; `<project>/SourceArt/Textures/Meshy/<Name>/{base_color,normal,roughness,metallic}.png`; jobs under `<project>/SourceArt/Meshy/.jobs/<job_id>/{request.json,status.json,job.log,input.glb}`.
- `status.json` and `request.json` are written atomically (temp file + `os.replace`), as in `src/nmg_game_dev/texture/jobs.py::_write_json_atomic`.
- No lock: several Meshy jobs may run at once.

## Configuration and guards

- `.mcp.json` gains `"meshy": {"command": "uv", "args": ["run", "--project", "${CLAUDE_PLUGIN_ROOT}/mcp-servers/meshy", "meshy-mcp"], "description": "meshy MCP — optional Meshy model generation and retexturing (#98); reads its key from the project .env"}`. The description must not contain `MESHY_API_KEY`.
- `tests/unit/pipeline/test_no_meshy.py`: scan only `src/nmg_game_dev/pipeline/` and `src/nmg_game_dev/finalize/`.
- `tests/unit/test_scaffold_guards.py`: drop the `"meshy" not in mcpServers` assertion; keep the `MESHY_API_KEY` and `meshy-mcp-server` text bans; add a test that the `meshy` entry has the expected command/args and no `env`, and that the other four entries equal their current literal values. `tests/_scaffold_contract.py` `REQUIRED_SERVERS` gains `meshy`. Steering bans (`MESHY_SOURCE_STRINGS`, `_SUPERSEDED_TERMS`) are unchanged, so steering text must not contain `MESHY_API_KEY`.
- `steering/snippets/project-product.md`: the Won't Have bullet becomes "Any cloud-hosted or paid generation service other than the optional Meshy source"; add a v1 bullet "Optional Meshy source — opt-in and paid: text, reference-image, or combined generation and retexture through the `meshy` MCP, used only when a Meshy API key is in the project's git-ignored `.env`"; Core Value Proposition 1's "No paid generation service in the loop" becomes "No paid generation service required".
- `.gitignore`: add `.env`.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Images shape geometry, prompt → `texture_prompt` | Selected | Meshy has no text-for-geometry input when images are given; the images carry the shape |
| Prompt shapes geometry, one image → `texture_image_url` on refine | Rejected | Allows only one image and drops the reference images' shape information |
| Always send `pose_mode` | Rejected | A/T pose distorts props; sent only when the agent sets `pose` for a limbed character |
| stdlib `urllib` transport | Selected | No new dependency or relock |
| `python-dotenv` | Rejected | A short parser covers `KEY=VALUE` |
| Separate session script | Selected | Keeps Meshy text out of `pipeline/` and `finalize/`; reuses the `NMG_RESULT` contract |
| Single-job lock like texture-gen | Rejected | Meshy runs remotely; local memory is not the constraint |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #98 | 2026-10-31 | Initial feature design |
