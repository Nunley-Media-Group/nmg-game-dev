# Requirements: Texture generation from the plugin root, with queued and batched jobs

**Issue**: #143
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/7-consumer-onboarding-onboard-consumer-skill-asset-contract-install-and-onboarding-docs/

## User Story

**As a** developer or agent generating textures with nmg-game-dev
**I want** the documented texture CLI to run from the plugin root project, and texture requests to be queued or batched instead of rejected
**So that** I can generate a full set of textures with one command or a series of tool calls, without hand-written wait loops or misleading errors

## Background

`uv run --project <plugin root> python -m nmg_game_dev.texture generate` fails every job with `texture.worker_failed`. mflux and hf_transfer exist only in the `texture-ai` extra, which only the texture-gen MCP server environment installs, so the worker hits `ModuleNotFoundError: No module named 'mlx'`. The remediation then points at models and the Blender memory reserve. `status` and `texture_backends` still report `available`, because availability checks only the platform, memory, and weights.

Only one texture job may run at a time: a second `generate_textures` call returns `texture.job_running`, and each job carries exactly one request.

## Acceptance Criteria

### AC1: The plugin root project carries the generation dependencies on Apple Silicon

**Given** the root `pyproject.toml`
**When** its `[project] dependencies` are read
**Then** it declares `mflux>=0.24.0` and `hf_transfer>=0.1.9` as floors, not exact pins, each with the marker `sys_platform == 'darwin' and platform_machine == 'arm64'`
**And** the `texture-ai` extra declares the same floors, `mflux>=0.24.0` and `hf_transfer>=0.1.9`
**And** `uv lock --check` passes with `uv.lock` resolved to the latest compatible versions
**And** the texture-gen MCP server's `nmg-game-dev[texture-ai]` dependency is unchanged

### AC2: Missing generation dependencies fail fast with an accurate error

**Given** an environment where `mflux` or `mlx` cannot be found by an import probe
**When** `generate` (CLI) or `generate_textures` (MCP) is called
**Then** the request fails before any worker is spawned or job is queued, with `texture.dependencies_missing`
**And** the message names the missing module, and the remediation names `uv run --project <plugin root> python -m nmg_game_dev.texture generate …` on an Apple Silicon Mac
**And** `status` and `texture_backends` report `dependencies_missing` for each backend that would otherwise be `available`

### AC3: Worker import failures report the real cause

**Given** a worker that exits non-zero with `ModuleNotFoundError: No module named '<module>'` in its stderr
**When** `run_backend_batches` raises `texture.worker_failed`
**Then** the remediation names `<module>` and the plugin-root command, not models or the memory reserve
**And** other worker failures keep the existing models/memory remediation and stderr tail

### AC4: A second request is queued, not rejected

**Given** a texture job is running
**When** `generate_textures` (or `jobs.start`) is called with another valid request
**Then** it returns a new `job_id` whose status is `queued`
**And** the queued job starts automatically after the running job finishes, and jobs run one at a time in FIFO submission order
**And** `texture.job_running` is no longer returned

### AC5: Batch request through the MCP tool

**Given** `generate_textures` called with `requests`, a list of request objects with the same fields as a single request
**When** the job runs
**Then** every request is produced in one job, and each backend's worker runs once for the whole batch
**And** `get_texture_job` reports `completed`/`total` across every image in the batch
**And** the succeeded result holds `results`, one per request in order, each in the single-request result shape

### AC6: Batch request through the CLI

**Given** a JSON file holding an array of request objects
**When** the developer runs `python -m nmg_game_dev.texture generate --batch <file.json>`
**Then** every request is generated and the command prints one JSON object with `results`, one per request in order

### AC7: Invalid batch is rejected before work starts

**Given** a batch in which one or more requests fail validation
**When** it is submitted through the CLI or `generate_textures`
**Then** nothing is generated or queued
**And** a `texture.invalid_request` error lists the zero-based index and reason of each invalid request

### AC8: Single-request forms are unchanged

**Given** a single request through the CLI (`--prompt …`) or `generate_textures(prompt=…)`
**When** it runs to completion
**Then** its parameters and its result shape are as before

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | Root `pyproject.toml` `[project] dependencies` add `mflux>=0.24.0` and `hf_transfer>=0.1.9` (floors) with marker `sys_platform == 'darwin' and platform_machine == 'arm64'`; the `texture-ai` extra changes from exact pins to the same floors; `uv.lock` resolves the latest compatible versions; the texture-gen server dependency is unchanged | Must |
| FR2 | Before spawning a worker or queuing a job, generation checks with `importlib.util.find_spec` that `mflux` and `mlx` are importable, without importing them, and otherwise raises `texture.dependencies_missing` naming the module and the plugin-root command | Must |
| FR3 | `hardware.availability` returns `dependencies_missing` for a backend that passes the platform, memory, and weights checks when the probe finds a missing module; `status` and `texture_backends` show it | Must |
| FR4 | `texture.worker_failed` remediation names the module from a `ModuleNotFoundError` in the worker stderr, with the plugin-root command; other failures keep the existing remediation | Must |
| FR5 | `jobs.start` always enqueues a job as `queued` with a submission sequence; a single queue runner, guarded by the existing PID lock with stale-lock recovery, runs queued jobs one at a time in FIFO order; `texture.job_running` is removed | Must |
| FR6 | `generate_textures` accepts `requests` (a list) as one job; one worker runs per backend for the whole batch; progress counts every image; the result lists per-request outputs under `results` | Must |
| FR7 | CLI `generate --batch <file.json>` accepts a JSON array of requests and prints the combined result | Must |
| FR8 | Batch validation rejects the whole batch with `texture.invalid_request` listing each invalid index and reason, before anything is queued or generated | Must |
| FR9 | `docs/onboarding/texture-models.md` and `mcp-servers/texture-gen/tools.json` describe the plugin-root command, `dependencies_missing`, queueing, and batch input | Must |
| FR10 | `texture/worker.py` stays the only module that imports mflux or mlx | Must |

## Out of Scope

- Running two texture jobs concurrently
- Cancelling or reprioritizing queued jobs
- Texture generation on non-Apple-Silicon hosts
- Skipping requests whose outputs already exist
- Changes to the finalize or meshy MCP servers

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #143 | 2026-11-11 | Initial feature spec |
