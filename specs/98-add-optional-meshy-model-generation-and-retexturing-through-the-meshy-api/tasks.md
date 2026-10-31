# Tasks: Optional Meshy model generation and retexturing

**Issue**: #98
**Date**: 2026-10-31
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/64-remove-meshy-from-the-pipeline-mcp-config-and-steering/

## Implementation Tasks

### T001: Meshy errors, key resolution, paths, request validation, and routing

**File(s)**: `src/nmg_game_dev/meshy/__init__.py`, `src/nmg_game_dev/meshy/errors.py`, `src/nmg_game_dev/meshy/config.py`, `src/nmg_game_dev/meshy/paths.py`, `src/nmg_game_dev/meshy/request.py`
**Type**: Create
**Depends**: none
**Acceptance**:
- `api_key` returns the process `MESHY_API_KEY` when non-empty, else the project `.env` value, else raises `meshy.api_key_missing` whose remediation names `MESHY_API_KEY` and the git-ignored project `.env` (AC8, AC9)
- Validation enforces every rule in design.md § Validation rules with `meshy.invalid_request` (AC11)
- `route` returns `text`, `image`, or `multi_image` by image count; `image_data_uri` emits the matching MIME type for PNG, JPEG, and WebP (AC1, AC2, AC3)

### T002: Meshy REST client with injectable transport

**File(s)**: `src/nmg_game_dev/meshy/client.py`
**Type**: Create
**Depends**: T001
**Acceptance**:
- Sends Bearer auth to the text-to-3D, image-to-3D, multi-image-to-3D, retexture, and status endpoints in design.md; downloads omit the auth header (FR1)
- Maps 401/402/429/other failures to `meshy.auth_failed`, `meshy.insufficient_credits`, `meshy.rate_limited`, `meshy.request_failed`; no message contains the key (AC10)

### T003: Session script and generic session-script parameter

**File(s)**: `scripts/blender/meshy_session.py`, `src/nmg_game_dev/pipeline/clients/blender_session.py`, `src/nmg_game_dev/meshy/session.py`
**Type**: Create, Modify
**Depends**: T001
**Acceptance**:
- `session_code` and `run_session_op` accept `script=` defaulting to `finalize_session.py`; existing callers unchanged; no Meshy text in `pipeline/` (AC13)
- `collection_state`, `import_glb`, `export_glb`, and `apply_maps` behave as design.md describes (AC1, AC7, AC11)

### T004: Background jobs

**File(s)**: `src/nmg_game_dev/meshy/jobs.py`
**Type**: Create
**Depends**: T002, T003
**Acceptance**:
- `start_generate` / `start_retexture` run validation, key, and session checks in the design order before any write or Meshy request, then spawn a detached `run-job` (AC9, AC11, FR4)
- `run_job` follows the routing table: prompt-only text-to-3D (refine only when textured), one image → image-to-3D, two to four → multi-image-to-3D, prompt with images → `texture_prompt`, `pose_mode` only when `pose` is given (AC1–AC5)
- Downloads outputs to the design paths, then imports or applies them; an unreachable session at that point yields `succeeded` with `loaded_into_session`/`applied_to_session` false and an `mcp.blender.unreachable` warning, keeping files (AC6, AC7, FR6)
- Terminal `FAILED|CANCELED|EXPIRED` → `meshy.task_failed` with Meshy's message; 30 minutes → `meshy.task_timeout`; unknown job → `meshy.job_not_found`; the key reaches no job file (AC10, FR7)

### T005: CLI

**File(s)**: `src/nmg_game_dev/meshy/__main__.py`
**Type**: Create
**Depends**: T004
**Acceptance**:
- `generate` (repeatable `--image`, `--pose`, `--no-texture`), `retexture`, `status`, and `run-job` call the same `jobs` functions as the MCP tools and print the same JSON; errors print `ERROR [<code>]` / `Remediation:` and exit 1 (AC12)

### T006: meshy MCP server and .mcp.json registration

**File(s)**: `mcp-servers/meshy/pyproject.toml`, `mcp-servers/meshy/uv.lock`, `mcp-servers/meshy/tools.json`, `mcp-servers/meshy/src/meshy_mcp/__init__.py`, `mcp-servers/meshy/src/meshy_mcp/server.py`, `.mcp.json`
**Type**: Create, Modify
**Depends**: T004
**Acceptance**:
- FastMCP server `meshy` registers `generate_model` (`name`, `prompt`, `image_paths`, `texture`, `pose`), `retexture_model`, and `get_meshy_job`; returns `{"error": {code, message, remediation}}` on `MeshyError`/`PipelineError`; logs to stderr only (FR8)
- The `generate_model` description explains the input combinations and says to set `pose` only for characters and creatures with limbs, never for props (AC13)
- `tools.json` matches the registered tools; `scripts/validate-mcp-tools.py` exits 0; `uv.lock` matches `pyproject.toml` (`tests/unit/test_lockfiles.py` passes) (AC13)
- `.mcp.json` adds the `meshy` entry from design.md; other entries unchanged; no `MESHY_API_KEY` text (AC13)

### T007: Git-ignore .env and the onboarding gitignore step

**File(s)**: `.gitignore`, `src/nmg_game_dev/onboard/gitignore.py`, `src/nmg_game_dev/onboard/runner.py`
**Type**: Create, Modify
**Depends**: none
**Acceptance**:
- `.gitignore` contains `.env`; `git check-ignore .env` succeeds (AC14)
- `run_onboard` reports `gitignore_env`: appends `.env` (creating `.gitignore` when missing) → `installed`; an existing `.env` or `/.env` line → `unchanged`; never creates `.env` (AC14)

### T008: Narrow the Meshy guards

**File(s)**: `tests/unit/pipeline/test_no_meshy.py`, `tests/unit/test_scaffold_guards.py`, `tests/_scaffold_contract.py`
**Type**: Modify
**Depends**: T006
**Acceptance**:
- Guards scan only `pipeline/` and `finalize/` for Meshy text, allow the `meshy` server entry, still ban `MESHY_API_KEY` and `meshy-mcp-server` in `.mcp.json` and the steering source strings, and assert the four existing entries unchanged and the `meshy` entry's command/args (AC13)

### T009: Steering and documentation

**File(s)**: `steering/snippets/project-product.md`, `docs/mcp/meshy.md`, `docs/onboarding/index.md`, `docs/onboarding/first-asset.md`
**Type**: Create, Modify
**Depends**: T006, T007
**Acceptance**:
- Product steering no longer lists Meshy under Won't Have and describes it as optional, opt-in, paid; no `MESHY_API_KEY` text in steering (AC13)
- `docs/mcp/meshy.md` documents the tools, the input-combination routing (images shape geometry; a prompt with images steers only the texture), `pose` and when to use it, the CLI, the status document, error codes, output paths, and the `MESHY_API_KEY=` line in the git-ignored project `.env` (environment overrides) (AC13)
- Onboarding docs describe the optional `.env` key and the `.gitignore` step, and still state onboarding asks for no API key (AC13, AC14)

### T010: Fakes and unit tests

**File(s)**: `tests/meshy_fakes.py`, `tests/unit/meshy/__init__.py`, `tests/unit/meshy/test_config.py`, `tests/unit/meshy/test_request.py`, `tests/unit/meshy/test_client.py`, `tests/unit/meshy/test_jobs.py`, `tests/unit/meshy/test_cli.py`, `tests/unit/meshy/test_mcp_server.py`, `tests/unit/onboard/test_gitignore.py`, `tests/unit/onboard/test_runner.py`, `tests/unit/pipeline/test_session_client.py`
**Type**: Create, Modify
**Depends**: T005, T006, T007
**Acceptance**:
- `FakeTransport` records requests and scripts responses; `FakeSessionClient` records ops and can raise `mcp.blender.unreachable`; no test touches the network
- Covers AC1–AC14 unit behavior including each routing row, `texture_prompt` only with images, `pose_mode` presence and absence, every validation rule, key precedence, redaction (the key is absent from every file under the job dir and from all error text), timeout, `job_not_found`, `session_code(script=…)`, and gitignore idempotence
- `pytest tests/unit/` exits 0

### T011: BDD scenarios

**File(s)**: `tests/bdd/features/meshy.feature`, `tests/bdd/test_meshy_bdd.py`
**Type**: Create
**Depends**: T010
**Acceptance**:
- SCN001–SCN014 from feature.gherkin bound with the fakes from `tests/meshy_fakes.py`; `pytest tests/bdd/` exits 0 (AC1–AC14)

### T012: Headless Blender tests for the session script

**File(s)**: `tests/blender/test_meshy_session.py`
**Type**: Create
**Depends**: T003
**Acceptance**:
- A GLB built and exported in-test imports as collection `Crate` with one `SM_Crate` and material `M_Crate_Body`; a second import returns `meshy.collection_exists` (AC1, AC11)
- `export_glb` writes a GLB of the collection's meshes and returns `meshy.collection_not_found` for a missing collection or missing `SM_<Name>` (AC7, AC11)
- `apply_maps` wires four PNGs into `M_Crate_Body` with sRGB base color, Non-Color others, a Normal Map node, and `SM_Crate`'s only material slot (AC7)
- `scripts/run-blender-tests.sh` exits 0

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #98 | 2026-10-31 | Initial feature tasks |
