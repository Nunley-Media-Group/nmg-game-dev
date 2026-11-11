# Tasks: Texture generation from the plugin root, with queued and batched jobs

**Issue**: #143
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/7-consumer-onboarding-onboard-consumer-skill-asset-contract-install-and-onboarding-docs/

## Implementation Tasks

### T001: Platform-marked generation dependencies in the root project

**File(s)**: `pyproject.toml`, `uv.lock`
**Type**: Modify
**Depends**: none
**Acceptance**:
- `[project] dependencies` include `mflux>=0.24.0` and `hf_transfer>=0.1.9` (floors), each with `sys_platform == 'darwin' and platform_machine == 'arm64'` (AC1, FR1).
- The `texture-ai` extra uses the same floors instead of exact pins (AC1, FR1).
- `uv.lock` is regenerated to the latest compatible versions, and `uv lock --check` passes (AC1).

### T002: Dependency probe and availability state

**File(s)**: `src/nmg_game_dev/texture/deps.py`, `src/nmg_game_dev/texture/hardware.py`, `src/nmg_game_dev/texture/generate.py`
**Type**: Create
**Depends**: none
**Acceptance**:
- `deps.missing_module` uses `importlib.util.find_spec` on `mflux` and `mlx` without importing them. `require_dependencies` raises `texture.dependencies_missing`, naming the module and the plugin-root `uv run --project …` command (AC2, FR2).
- `availability` returns `dependencies_missing` when platform, memory, and weights pass but a module is missing. `status` and `texture_backends` report it (AC2, FR3).
- `generate.run` raises `dependencies_missing` before any spawn (AC2).
- No module other than `texture/worker.py` imports mflux or mlx (FR10).

### T003: Cause-aware worker failure remediation

**File(s)**: `src/nmg_game_dev/texture/batch.py`
**Type**: Modify
**Depends**: T002
**Acceptance**:
- When stderr contains `No module named '<module>'`, the `texture.worker_failed` remediation names the module and the plugin-root command. Otherwise the existing remediation and the stderr tail are kept (AC3, FR4).

### T004: Batch generation

**File(s)**: `src/nmg_game_dev/texture/generate.py`
**Type**: Modify
**Depends**: T002
**Acceptance**:
- `validate_batch` rejects an empty list or any invalid request with one `texture.invalid_request` listing `request <i>: <reason>` for each failure (AC7, FR8).
- `run_batch` builds one `Batch` per backend across all requests, so each backend's worker spawns once. It reports progress over every image, finishes each request as `run` does, and returns `{"results": [...]}` in request order (AC5, AC6, FR6).
- `run` keeps its parameters and result shape (AC8).
- When #152's contact-sheet refresh exists, the batch refreshes it once after all manifests.

### T005: FIFO job queue

**File(s)**: `src/nmg_game_dev/texture/jobs.py`, `src/nmg_game_dev/texture/__main__.py`
**Type**: Modify
**Depends**: T002, T004
**Acceptance**:
- `start` validates (single or batch), checks dependencies, writes the job as `queued` with `submitted_ns`, spawns a detached `run-queue` runner, and returns the job id. It never raises `texture.job_running`, and that code is removed (AC4, FR5).
- `run_queue` claims the PID lock (a live holder means exit; a stale lock is replaced), runs queued jobs in `(submitted_ns, job_id)` order one at a time, and re-checks the queue after releasing the lock (AC4, FR5).
- A batch job's succeeded result is `{"results": [...]}`, and `completed`/`total` count every image (AC5).
- `__main__` adds `run-queue <jobs_root>` and `generate --batch FILE` (mutually exclusive with `--prompt`, argument error exit 2). Batch output is the combined JSON (AC6, FR7).

### T006: MCP tool and schema

**File(s)**: `mcp-servers/texture-gen/src/texture_gen_mcp/server.py`, `mcp-servers/texture-gen/tools.json`
**Type**: Modify
**Depends**: T005
**Acceptance**:
- `generate_textures` accepts `requests: list[dict] | None`. Passing both `prompt` and `requests`, or neither, returns `texture.invalid_request`. A batch goes to `jobs.start` as one job (AC5, AC7).
- `tools.json` declares `requests` and describes queueing, batch input, and `dependencies_missing`. `gate-mcp-schema` passes (FR9).

### T007: Documentation

**File(s)**: `docs/onboarding/texture-models.md`
**Type**: Modify
**Depends**: T005, T006
**Acceptance**:
- Documents `uv run --project <plugin root> python -m nmg_game_dev.texture generate …`, the `dependencies_missing` state and error, FIFO queueing (replacing the `texture.job_running` text), `generate --batch FILE`, and the `requests` tool input (FR9).

### T008: Tests

**File(s)**: `tests/unit/texture/conftest.py`, `tests/unit/texture/test_deps.py`, `tests/unit/texture/test_hardware.py`, `tests/unit/texture/test_batch.py`, `tests/unit/texture/test_generate.py`, `tests/unit/texture/test_jobs.py`, `tests/unit/texture/test_cli.py`, `tests/unit/texture/test_mcp_server.py`, `tests/unit/test_pyproject_texture_deps.py`, `tests/bdd/features/texture_generation.feature`, `tests/bdd/test_texture_bdd.py`, `tests/bdd/features/texture_queue_batch.feature`, `tests/bdd/test_texture_queue_batch_bdd.py`
**Type**: Modify
**Depends**: T001, T002, T003, T004, T005, T006
**Acceptance**:
- An autouse fixture makes the dependency probe report everything present for the existing texture tests, so their behavior is unchanged on Linux CI.
- `test_pyproject_texture_deps.py` parses `pyproject.toml` and asserts (AC1):
  - the root floors `mflux>=0.24.0` and `hf_transfer>=0.1.9` with the exact marker;
  - the `texture-ai` extra holds the same floors and no `==` pin;
  - `mcp-servers/texture-gen/pyproject.toml`'s dependency is unchanged.
- Probe tests use an injected `find_spec` returning `None` for `mlx`:
  - `generate.run`, `jobs.start`, and `generate_textures` raise or return `texture.dependencies_missing` naming `mlx` and `uv run --project`, and the fake spawn is never called and no job directory is created;
  - `backend_status` reports `dependencies_missing`;
  - a guard test asserts `mlx` is absent from `sys.modules` after the probe (AC2).
- A fake worker that prints `ModuleNotFoundError: No module named 'mlx'` and exits 1 gets the module remediation. A generic failure keeps the models/memory text (AC3).
- Queue:
  - With a fake runner, `start` twice returns two job ids, both `queued`, and no `job_running`.
  - `run_queue` with the fake worker runs them in submission order (recorded spawn order) and leaves both `succeeded`.
  - A live lock holder makes `run_queue` exit without running.
  - A stale lock is replaced (AC4).
- Batch:
  - Two requests on the same backend spawn that backend's worker once, with items from both.
  - Progress `total` equals the image count of both requests.
  - The result has two `results` entries in order (AC5).
  - `main(["generate", "--batch", file])` prints `results` (AC6).
  - A batch with invalid entries 1 and 3 raises `texture.invalid_request` naming both indices, with no spawn and no job directory (AC7).
- Single CLI and MCP requests keep their result keys (AC8).
- The existing BDD scenario asserting `texture.job_running` is updated to assert queueing. New BDD scenarios SCN001–SCN008 are bound with the fake worker.
- Evidence:
  - `uv run pytest tests/unit/texture tests/unit/test_pyproject_texture_deps.py tests/bdd -q`;
  - `uv lock --check`;
  - `repository.tests`, `repository.lint`, `repository.format`, `repository.types`;
  - `gate-mcp-schema`.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #143 | 2026-11-11 | Initial feature tasks |
