# Requirements: Optional Meshy model generation and retexturing

**Issue**: #98
**Date**: 2026-10-31
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/64-remove-meshy-from-the-pipeline-mcp-config-and-steering/

## User Story

**As an** NMG game developer working in Claude Code
**I want** the agent to generate 3D models from a text prompt, reference images, or both, and to retexture an authored mesh, through the Meshy API
**So that** a Meshy result arrives in my Blender session as a contract-named `<Name>` collection that the existing finalize pipeline can take to Unreal

## Background

Assets are authored freeform in Blender and textured with local models (`texture-gen`) or procedural materials. Meshy becomes an optional extra source. Generation takes a prompt alone, 1–4 reference images alone, or both. Meshy shapes geometry from text only when no image is given: with images, the images shape the model (image-to-3D for one image, multi-image-to-3D for two to four) and the prompt steers the texture. An optional `pose` (`a-pose` or `t-pose`) asks Meshy to hold a character's limbs away from its body; it is sent only when given, and is meant for characters and creatures with limbs, not props. Retexture produces PBR maps for a mesh that is already authored.

Meshy is opt-in: it runs only when a Meshy API key is available and the agent calls a Meshy tool. Nothing in `src/nmg_game_dev/pipeline/` or `src/nmg_game_dev/finalize/` depends on it. The key is read from `MESHY_API_KEY` in the process environment, else from the `MESHY_API_KEY=` line of the project's `.env` (project root = `CLAUDE_PROJECT_DIR`, else the working directory). `.env` is git-ignored in this repository, and `/onboard-consumer` adds `.env` to the consumer's `.gitignore`.

Meshy tasks run for minutes, longer than the 180 s MCP call limit, so they run as detached background jobs the agent polls, like `texture-gen` jobs.

## Acceptance Criteria

### AC1: Prompt-only generation lands in the Blender session

**Given** a Meshy API key is available, the Blender session is reachable, and it has no `Crate` collection
**When** the agent calls the `meshy` MCP tool `generate_model(name="Crate", prompt="weathered wooden crate")` and polls `get_meshy_job(job_id)` to completion
**Then** Meshy text-to-3D runs `preview` and then `refine` with `enable_pbr: true`
**And** the job reports `succeeded`, the GLB is saved as `SourceArt/Meshy/Crate/Crate.glb`, and the session has a `Crate` collection whose single root mesh object is `SM_Crate`, with the Meshy material renamed to `M_Crate_Body`
**And** the job result reports `loaded_into_session: true` and the GLB path

### AC2: Reference images alone shape the model

**Given** a Meshy API key is available and local PNG, JPEG, or WebP images exist
**When** the agent calls `generate_model(name="Lamppost", image_paths=[<one path>])`, or with two to four paths
**Then** one image is sent to Meshy image-to-3D as `image_url`, and two to four images are sent to Meshy multi-image-to-3D as `image_urls`, each as a base64 data URI with its matching MIME type
**And** no `texture_prompt` is sent, and the result lands as in AC1 under the name `Lamppost`

### AC3: Reference images and a prompt together

**Given** a Meshy API key is available and one to four local reference images exist
**When** the agent calls `generate_model(name="Ghost", image_paths=[...], prompt="pale translucent cloth")`
**Then** the images are sent as in AC2 and the prompt is sent as `texture_prompt` in the same request
**And** the result lands as in AC1 under the name `Ghost`

### AC4: Optional pose for characters

**Given** a Meshy API key is available
**When** the agent calls `generate_model` with `pose="a-pose"` or `pose="t-pose"` on any input combination
**Then** the geometry request (text-to-3D `preview`, image-to-3D, or multi-image-to-3D) carries `pose_mode` with that value
**And** when `pose` is omitted, no request carries `pose_mode`

### AC5: Untextured generation

**Given** a Meshy API key is available
**When** the agent calls `generate_model(..., texture=False)` with a prompt alone or with images alone
**Then** only the untextured stage runs (text-to-3D `preview` with no `refine` request, or image/multi-image-to-3D with `should_texture: false` and `enable_pbr: false`), and the untextured mesh lands as in AC1

### AC6: Session unreachable at import time keeps the file

**Given** a Meshy generation job whose Meshy task succeeded
**When** the Blender session is unreachable at import time
**Then** the job reports `succeeded` with `loaded_into_session: false`, the GLB path, and a warning with code `mcp.blender.unreachable` and its remediation
**And** the GLB stays on disk

### AC7: Retexture an authored mesh

**Given** a Meshy API key is available and the session has a `Crate` collection with root mesh `SM_Crate`
**When** the agent calls `retexture_model(name="Crate", prompt="mossy stone")` (or `image_path=` for a style image) and polls it to completion
**Then** the collection's meshes are exported to GLB and sent to Meshy retexture
**And** the returned base color, normal, roughness, and metallic maps are saved under `SourceArt/Textures/Meshy/Crate/`
**And** they are wired into material `M_Crate_Body` on `SM_Crate` (base color as sRGB, the others as Non-Color, normal through a Normal Map node), replacing that object's previous material assignment
**And** the job result lists the map paths with `applied_to_session: true`

### AC8: The key comes from the environment or the project .env

**Given** `MESHY_API_KEY` is unset in the process environment and the project `.env` contains `MESHY_API_KEY=key-from-dotenv`
**When** a Meshy request is sent
**Then** it carries `Authorization: Bearer key-from-dotenv`
**And** when `MESHY_API_KEY=key-from-env` is also set in the process environment, the request carries `Authorization: Bearer key-from-env` instead

### AC9: Missing API key fails fast

**Given** `MESHY_API_KEY` is unset or empty in the process environment and absent or empty in the project `.env` (or there is no `.env`)
**When** any Meshy tool or CLI command that would call Meshy is invoked
**Then** it returns error code `meshy.api_key_missing` with a remediation telling the developer to add `MESHY_API_KEY=<key>` to the project's git-ignored `.env`, before any HTTP request, job start, or file write

### AC10: Meshy API failures are structured

**Given** a Meshy job in progress
**When** Meshy answers 401, 402, or 429, or the task ends `FAILED`, `CANCELED`, or `EXPIRED`
**Then** the job reports `failed` with code `meshy.auth_failed`, `meshy.insufficient_credits`, `meshy.rate_limited`, or `meshy.task_failed` (carrying Meshy's task error message), each with a remediation
**And** the API key never appears in any job file, log line, or error message

### AC11: Invalid requests are rejected before any Meshy call

**Given** a Meshy API key is available
**When** `name` is not PascalCase; or neither `prompt` nor `image_paths` is given; or `image_paths` has more than four entries, or an entry that does not exist, is not `.png`, `.jpg`, `.jpeg`, or `.webp`, or exceeds 20 MB; or a prompt sent with images exceeds 800 characters; or a prompt and images are given with `texture=False`; or `pose` is not `a-pose` or `t-pose`
**Or** `generate_model` targets a `<Name>` collection that already exists in a reachable session
**Or** `retexture_model` gets both or neither of `prompt` and `image_path`, or targets a `<Name>` collection that is missing from the session or has no `SM_<Name>` mesh
**Then** it returns `meshy.invalid_request`, `meshy.collection_exists`, or `meshy.collection_not_found` with a remediation, and no Meshy request is sent

### AC12: Shared CLI and MCP implementation

**Given** the same inputs
**When** the developer runs `python -m nmg_game_dev.meshy generate|retexture|status ...`
**Then** it runs the same job implementation as the MCP tools and prints the same result JSON

### AC13: Configuration, guards, steering, and docs admit optional Meshy

**Given** the repository
**When** the unit guard tests and `scripts/validate-mcp-tools.py` run
**Then** `.mcp.json` declares a `meshy` stdio server that runs `mcp-servers/meshy` with `uv run`, with no key or `MESHY_API_KEY` text in the file, and the `blender`, `unreal`, `finalize`, and `texture-gen` entries are unchanged
**And** `mcp-servers/meshy/tools.json` validates, and its `generate_model` description says to set `pose` only for characters and creatures with limbs
**And** `src/nmg_game_dev/pipeline/` and `src/nmg_game_dev/finalize/` still contain no Meshy code and no `source` parameter
**And** `steering/snippets/project-product.md` no longer lists Meshy under Won't Have and describes it as an optional, opt-in paid source
**And** `docs/mcp/meshy.md` and the onboarding docs document the input combinations, `pose`, and the optional `MESHY_API_KEY` line in the git-ignored project `.env`, while onboarding still prompts for no API key

### AC14: The project .env is git-ignored

**Given** this repository, and a consumer project whose `.gitignore` is missing or lacks a `.env` entry
**When** `git check-ignore .env` runs in this repository, and `/onboard-consumer` runs in the consumer
**Then** `.env` is ignored in this repository
**And** onboarding appends a `.env` line to the consumer `.gitignore` (creating it when missing) and reports the step `gitignore_env` as `installed`; a rerun reports `unchanged` and adds no duplicate line; an existing `.env` or `/.env` line counts as present
**And** onboarding never creates or writes `.env`

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | Add a `nmg_game_dev.meshy` package with a Meshy REST client: Bearer auth, an injectable HTTP transport (stdlib `urllib` by default), and text-to-3D, image-to-3D, multi-image-to-3D, retexture, task-status, and asset-download calls | Must |
| FR2 | Resolve the key from process `MESHY_API_KEY`, else the `MESHY_API_KEY` line of `<project>/.env`; empty values count as missing | Must |
| FR3 | Route generation by input: prompt only → text-to-3D; one image → image-to-3D; two to four images → multi-image-to-3D; a prompt with images → `texture_prompt`; `pose` → `pose_mode` on the geometry request only when given | Must |
| FR4 | Run Meshy work as detached background jobs with an atomically rewritten `status.json`; states are queued, running (with Meshy progress), succeeded, and failed | Must |
| FR5 | On generation success, download the GLB to `SourceArt/Meshy/<Name>/<Name>.glb` and import it into the session as collection `<Name>` with root mesh `SM_<Name>` and material `M_<Name>_Body`; if the session is unreachable, keep the file and warn | Must |
| FR6 | Retexture: export the `<Name>` collection's meshes to GLB, submit it, download PBR maps to `SourceArt/Textures/Meshy/<Name>/`, and wire them into `M_<Name>_Body` on `SM_<Name>` with the correct color spaces; if the session is unreachable when applying, keep the maps, report `applied_to_session: false`, and warn `mcp.blender.unreachable` | Must |
| FR7 | Validate inputs and the key before any Meshy request; map HTTP and task failures to `meshy.*` error codes with remediations; stop polling after 30 minutes with `meshy.task_timeout`; never log or persist the key | Must |
| FR8 | Add the `meshy` MCP server in `mcp-servers/meshy/` (`generate_model`, `retexture_model`, `get_meshy_job`) with `tools.json`, and add `python -m nmg_game_dev.meshy` over the same implementation | Must |
| FR9 | Register `meshy` in `.mcp.json`; narrow the Meshy guards so they still keep Meshy out of `pipeline`/`finalize` and still ban `source="meshy"`, `--source meshy`, `meshy-mcp-server`, and `MESHY_API_KEY` in `.mcp.json` and steering; update the product steering | Must |
| FR10 | Add `.env` to this repository's `.gitignore`; add an idempotent `/onboard-consumer` step `gitignore_env` that ensures the consumer `.gitignore` ignores `.env` | Must |
| FR11 | Add `docs/mcp/meshy.md` and document the optional `.env` key in the onboarding docs | Must |
| FR12 | Add unit and BDD tests using a fake Meshy transport and a fake session client, plus headless Blender tests for the session import, export, and material wiring | Must |

## Out of Scope

- Text that shapes geometry when reference images are given (Meshy offers no such input)
- Other 3D generation services
- Meshy remesh, rigging, animation, and text-to-image APIs
- Making Meshy a finalize step or a pipeline `source`
- Onboarding prompting for, creating, or storing a Meshy key or `.env`
- Choosing Meshy models, topology, polycount, or resolution beyond Meshy's defaults
- Multi-part assets (`SM_<Name>_<Part>`) from a single Meshy result
- Cancelling a running Meshy job

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #98 | 2026-10-31 | Initial feature spec |
