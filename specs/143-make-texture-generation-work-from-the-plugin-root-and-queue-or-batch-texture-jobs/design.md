# Design: Texture generation from the plugin root, with queued and batched jobs

**Issue**: #143
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/7-consumer-onboarding-onboard-consumer-skill-asset-contract-install-and-onboarding-docs/

## Overview

There are four changes:

1. Platform-marked mflux and hf_transfer in the root project.
2. An import probe that turns a missing mflux or mlx into `dependencies_missing`, both before work and in availability, plus a cause-aware `worker_failed` remediation.
3. A FIFO job queue drained by one detached runner, replacing the reject-on-busy lock.
4. Batch requests, which merge every request's images into one worker run per backend.

## Architecture

### Dependencies (`pyproject.toml`, `uv.lock`)

Add to `[project] dependencies`:

```
"mflux>=0.24.0; sys_platform == 'darwin' and platform_machine == 'arm64'",
"hf_transfer>=0.1.9; sys_platform == 'darwin' and platform_machine == 'arm64'",
```

Change the `texture-ai` extra from `==` pins to the same floors (`mflux>=0.24.0`, `hf_transfer>=0.1.9`). Third-party tooling tracks latest, so there are no exact pins. Regenerate `uv.lock` with `uv lock`, which resolves the latest compatible versions. Linux and CI resolve without mflux. The existing mypy override for `mflux`/`mlx` stays.

### Dependency probe (`texture/deps.py`, new)

- `REQUIRED_MODULES = ("mflux", "mlx")`.
- `missing_module(find_spec=importlib.util.find_spec) -> str | None` returns the first module whose top-level `find_spec` is `None`. It never imports the module.
- `plugin_root() -> Path` returns `CLAUDE_PLUGIN_ROOT` when set, else the repository root found by walking up from this file to the first `pyproject.toml` whose `[project] name` is `nmg-game-dev`.
- `run_command() -> str` returns `uv run --project <plugin_root> python -m nmg_game_dev.texture generate --prompt …`.
- `require_dependencies(probe=missing_module)` raises `TextureGenError("texture.dependencies_missing", f"The {module} module is not installed in this Python environment ({sys.executable}).", f"On an Apple Silicon Mac, run texture generation from the plugin root: {run_command()}")`.

### Availability (`texture/hardware.py`)

- `Availability` gains `"dependencies_missing"`.
- `availability(..., deps_probe=missing_module)` keeps the existing checks in order (platform, memory, weights). Only when they all pass does it return `"dependencies_missing"` if the probe finds a missing module, else `"available"`.
- `require_available` maps `dependencies_missing` to `require_dependencies`' error.
- `generate.select_backends` and `backend_status` pass the probe through.
- `generate.run` and `jobs.start` call `require_dependencies` after backend selection and before any spawn or enqueue.

The probe is injectable everywhere. The unit and BDD texture fixtures default it to "all present" through an autouse fixture in `tests/unit/texture/conftest.py` and `tests/bdd/conftest.py` (or the texture BDD module), so existing tests keep their meaning on Linux CI.

### Worker failure remediation (`texture/batch.py`)

`run_backend_batches` matches `No module named '([^']+)'` in the worker stderr.

- On a match, the remediation is `f"The worker cannot import {module}. {plugin-root command guidance}. Worker stderr tail:\n{tail}"`.
- Otherwise the existing models/memory remediation is used unchanged.

### Batch generation (`texture/generate.py`)

- `validate_batch(requests)` validates every request with `validate_request` and collects `(index, message)` for each failure. If any request fails, it raises one `texture.invalid_request` listing `request {i}: {message}` for every failure. An empty list is invalid too.
- `run_batch(requests, …) -> BatchResult`:
  - validates;
  - selects backends per request;
  - requires dependencies;
  - builds **one `Batch` per backend** whose items are all images of every request that uses that backend, each `ImageItem` with a globally unique `index` and its own request's output path;
  - runs `run_backend_batches` once, so each worker loads its model once;
  - then splits the timings back per request and finishes each request exactly as `run` does: seamless pass, derived maps, comparison sheet, and `textures.json`.
- `BatchResult.as_json()` returns `{"results": [TextureResult.as_json(), …]}` in request order.
- `run(request)` stays the single-request entry. It may delegate to the same internals, but its result shape does not change.
- When #152's contact-sheet refresh is present, `run_batch` refreshes it once after all manifests are written. Each per-request result carries the same `contact_sheet` value.
- Progress: `on_progress(done, total)` counts images across the whole batch.

### Queue (`texture/jobs.py`)

- Job files:
  - `request.json` holds `{"request": …}` for a single job or `{"requests": [...]}` for a batch, plus `output_root` and `submitted_ns` (`time.time_ns()`).
  - `status.json` starts as `{"job_id", "state": "queued", "completed": 0, "total"}`.
- `start(request_or_requests, …)`:
  - validates (a batch through `validate_batch`), selects backends, and calls `require_dependencies`;
  - writes the job as `queued`;
  - then spawns a detached runner with `python -m nmg_game_dev.texture run-queue <jobs_root>`, using the same `Popen` options as today;
  - returns the job id. It never raises `texture.job_running`.
- `run_queue(jobs_root, …)`:
  1. Try to claim `<jobs_root>/lock` for this PID. If a live PID holds it, exit 0, because the holder will pick the job up. A dead holder's lock is stale and is replaced, as today.
  2. Loop: pick the queued job with the smallest `(submitted_ns, job_id)` and run it with `run_job`, which handles single and batch requests. Repeat until no queued job remains.
  3. Release the lock, re-scan once, and when a queued job appeared in between, go back to step 1. This closes the race with a `start` that saw the lock held.
- `run_job` no longer takes or releases the lock. It keeps its status writes and its `failed`/`job_crashed` handling. A batch job's succeeded result is `BatchResult.as_json()`.
- `_job_running_error` and `_claim_lock`'s raise path are removed. The old `run-job <job_dir>` subcommand stays for single-job compatibility and runs one job without the queue.

### Interfaces

| Interface | Input | Output / Error | Behavior |
|-----------|-------|----------------|----------|
| `generate_textures` (MCP) | existing fields, or `requests: list[object]` | `{"job_id"}` / `{"error": {…}}` | Either `prompt` or `requests`, not both; batch is validated whole |
| `tools.json` `generate_textures` | adds `requests` (array of request objects); `prompt` no longer required in the schema | — | Description mentions queueing and batch |
| CLI `generate` | existing flags, or `--batch FILE` (mutually exclusive with `--prompt`) | JSON result; `ERROR [code]` exit 1; argument errors exit 2 | Batch prints `{"results": [...]}` |
| CLI `run-queue <jobs_root>` | — | — | Internal: drains the queue |
| `status` / `texture_backends` | — | adds `dependencies_missing` | — |

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Platform-marked root dependencies | Selected | Makes the documented `uv run --project <root>` work; Linux CI unaffected |
| Keep pointing users at the texture-gen venv (ghost1 workaround) | Rejected | Undocumented path; the issue asks for the root project to work |
| One queue runner draining FIFO | Selected | No caller polling; reuses the PID lock and stale recovery |
| Caller-side poll loop (`pgrep … sleep 5`, ghost1) | Rejected | Moves waiting onto every caller |
| One worker per request inside a batch | Rejected | Loads each model once per request; FR6 needs once per batch |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #143 | 2026-11-11 | Initial feature design |
