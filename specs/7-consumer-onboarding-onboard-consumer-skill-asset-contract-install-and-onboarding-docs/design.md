# Design: Consumer onboarding — onboard-consumer skill, asset contract install, and onboarding docs

**Issue**: #7
**Date**: 2026-10-30
**Status**: Approved
**Author**: Rich Nunley

## Overview

Onboarding has two layers, matching `steering/structure.md`:

1. **Skill**: `skills/onboard-consumer/SKILL.md` gathers the models disk from the developer, then runs `uv run --project "${CLAUDE_PLUGIN_ROOT}" python -m nmg_game_dev.onboard install --consumer "$CLAUDE_PROJECT_DIR" --models-dir <dir>` and relays the report.
2. **Python**: `src/nmg_game_dev/onboard/` owns every copy, link, merge, clone, model install, and drift check. Each step is a pure function of (framework root, consumer dir, options, injected runners), so it can be unit tested on temp directories.

Execution is **preflight → steps → report**. Preflight raises `OnboardError` before any write. Each step returns `StepResult(name, status ∈ {installed, unchanged, drift, refreshed}, detail, remediation)`.

Texture generation lives in `src/nmg_game_dev/texture/` and is reached two ways:

- the `python -m nmg_game_dev.texture` CLI;
- the `texture-gen` MCP server in `mcp-servers/texture-gen/`, a thin FastMCP wrapper over the package.

The package's registry is the single source for the two models, and `onboard/textures.py` reads it.

## Architecture

```
python -m nmg_game_dev.onboard install --consumer C [--uproject P] [--models-dir D] [--refresh] [--json]
  framework_root = $CLAUDE_PLUGIN_ROOT or Path(__file__).resolve().parents[3]
  preflight:
    resolve uproject (P, else exactly one *.uproject in C)  → onboard.uproject_not_found | onboard.uproject_ambiguous
    resolve models dir (D, else $TEXTURE_GEN_MODELS_DIR)     → onboard.models_dir_missing
    if any model missing: Apple Silicon macOS?               → onboard.unsupported_platform
                          free bytes on D's volume ≥ 60 GiB  → onboard.insufficient_disk
    framework sources present                                → onboard.framework_incomplete
  steps (in order):
    scripts → settings_hooks → asset_contract → agent_instructions →
    ue_plugin → vibeue → uproject_plugins → mcp_autostart_ini →
    blender_addon → texture_models → texture_env
  print report (text, or JSON with --json); exit 0

agent ─► texture-gen MCP: generate_textures(...) ─► jobs.start() ─► detached `python -m nmg_game_dev.texture run-job <job_dir>`
      └► get_texture_job(id) ─► jobs.status() reads <job_dir>/status.json
agent ─► python -m nmg_game_dev.texture generate ... (synchronous)
both paths ─► generate.run(request, registry=REGISTRY)
                ├─ registry.resolve + allowlist + availability (hardware, weights)
                ├─ for each backend, sequentially: worker child process (load once → N images → exit)
                ├─ seamless.make_seamless on every PNG
                ├─ maps.derive (optional) ; sheet.compare (both)
                └─ textures.json manifest
```

### Modules (`src/nmg_game_dev/onboard/`)

| Module | Contents |
|--------|----------|
| `__init__.py` | Re-exports `OnboardError`, `StepResult`, `run_onboard`, `list_volumes` |
| `errors.py` | `OnboardError(PipelineError)`, `stage="onboard"` |
| `paths.py` | `framework_root(env)`, `EXCLUDED = ("fixtures", ".mcp.json")`, `assert_not_excluded(path)` used by every copy helper |
| `files.py` | `sync_file` / `sync_tree(src, dst, refresh, ignore=("Binaries","Intermediate"))` returning installed/unchanged/drift/refreshed by byte/tree comparison; preserves the executable bit |
| `settings.py` | `merge_session_hooks(settings_path, template_path)`: adds the template's `SessionStart` group only when no existing hook has an identical `command`, keeps all other keys, writes 2-space JSON; `merge_env(settings_local_path, {...})` |
| `instructions.py` | Marked block between `<!-- nmg-game-dev:begin -->` and `<!-- nmg-game-dev:end -->` referencing `docs/nmg-game-dev/asset-contract.md`; appended once, replaced in place when its content differs; creates `CLAUDE.md` if missing; touches `AGENTS.md` only if present |
| `unreal.py` | `enable_plugins(uproject, names)`; `ensure_mcp_autostart(ini_path)`; `ensure_vibeue(plugins_dir, run, refresh)` |
| `blender.py` | `link_addon(src, extensions_dir)`: creates the symlink; an existing correct link → unchanged; a link elsewhere or a non-link → drift (refresh replaces it) |
| `textures.py` | `TEXTURE_MODELS = tuple((b.id, b.repo) for b in nmg_game_dev.texture.registry.REGISTRY.values())`; `REQUIRED_FREE_BYTES = 60 * 2**30`; `MFLUX_VERSION = "0.24.0"`; `missing_models(dir)`; `install_models(dir, run, which)`; `install_command(id, dir)` shared with the texture remediation |
| `volumes.py` | `list_volumes(disk_usage=shutil.disk_usage, mounts=...)` over `/` and `/Volumes/*` |
| `runner.py` | `run_onboard(consumer, framework, uproject, models_dir, refresh, env, run, which, host) -> list[StepResult]` |
| `__main__.py` | argparse with `install` / `volumes` subcommands; `OnboardError` → `ERROR [code]: …` / `Remediation: …` on stderr, exit 1 |

`run`, `which`, `host` (platform/machine), and `disk_usage` are injected. Production code uses `subprocess.run`, `shutil.which`, `platform`, and `shutil.disk_usage`.

### Modules (`src/nmg_game_dev/texture/`)

| Module | Contents |
|--------|----------|
| `__init__.py` | Re-exports `TextureGenError`, `REGISTRY`, `generate`, `TextureRequest`, `TextureResult` |
| `errors.py` | `TextureGenError(PipelineError)`, `stage="texture_gen"`, codes `texture.*` |
| `registry.py` | `BackendSpec` (frozen dataclass: `id`, `repo`, `revision`, `license`, `quantization`, `default_steps`, `peak_memory_gb`, `mflux_entry`); `REGISTRY: Mapping[str, BackendSpec]` as a `MappingProxyType` holding exactly the two specs; `resolve(id, registry, model_ref=None)` raises `texture.unknown_backend` / `texture.model_not_allowed` |
| `hardware.py` | `HardwareFacts(system, machine, total_ram_gb)`, `probe()` (via `platform` and `sysctl hw.memsize`), `availability(spec, facts, models_dir, reserve_gb) -> Literal["available","not_installed","unsupported_platform","insufficient_memory"]`, `require_available(...)` raising the matching `texture.*` code |
| `paths.py` | `models_dir(env)`, `weights_dir(spec, models_dir) = <dir>/<id>-q4`, `output_root(env, cwd)` (`NMG_GAME_DEV_TEXTURE_DIR`, else `<CLAUDE_PROJECT_DIR or cwd>/SourceArt/Textures/Generated`), `slugify(prompt)` (kebab case, ≤ 48 chars) |
| `worker.py` | `python -m nmg_game_dev.texture.worker <batch.json>`: loads the backend once through mflux (`ZImage` / `Flux2Klein` + `ModelConfig.flux2_klein_4b()`, `compute_precision=mx.float16`, weights from `weights_dir`), generates each request, writes the raw PNGs, and prints one JSON line per image (`index`, `path`, `seconds`). Imports mflux only here |
| `batch.py` | `run_backend_batches(batches, registry, spawn)`: for each backend in order, `spawn` runs the worker and waits for exit before the next starts; non-zero exit → `texture.worker_failed` with stderr tail. `spawn` defaults to `subprocess.run([sys.executable, "-m", "nmg_game_dev.texture.worker", batch_file])` and is injected in tests |
| `seamless.py` | `make_seamless(img: np.ndarray) -> np.ndarray`: for each axis, `shifted = np.roll(img, n // 2, axis)`, `w = sin²(π(i + 0.5) / n)` along that axis, `out = w·img + (1 − w)·shifted`; `seam_mad(img, axis)` and `interior_mad(img, axis)` for the AC18 check |
| `maps.py` | `PRESETS = {"fabric": (0.9, 0.0), "wood": (0.7, 0.0), "stone": (0.85, 0.0), "plastic": (0.5, 0.0), "metal": (0.35, 1.0)}`. `derive(albedo_path, roughness, metallic, ao=False, strength=2.0)`: height from Rec.709 luminance; wrap-around central differences via `np.roll`; normal `normalize(−dx·s, −dy·s, 1)` (OpenGL, green up) encoded `(n + 1) / 2`; constant R and M; AO `1 − clamp(4·(blur(h) − h))` with a wrap-aware box blur |
| `sheet.py` | `compare(images, labels, out_path)`: images side by side with a label strip (`<backend> seed <n> — <s>s`) via Pillow |
| `generate.py` | `TextureRequest(prompt, backend: str = "flux2-klein-4b", seeds: list[int] = [random], resolution: int = 1024, name: str | None, maps: str | tuple[float,float] | None, ao: bool = False, style_suffix: str = STYLE_SUFFIX)`; `run(request, registry=REGISTRY, env, facts, spawn) -> TextureResult`; expands `both` into the available backends in registry order (unavailable ones are skipped and listed in the result; if none is available, the first backend's error is raised) |
| `jobs.py` | `start(request) -> job_id`: writes `<output_root>/.jobs/<job_id>/request.json` and `status.json` (`queued`), takes `<output_root>/.jobs/lock` (PID; a live PID → `texture.job_running`), and spawns `python -m nmg_game_dev.texture run-job <job_dir>` detached (`start_new_session=True`). `status(job_id)` reads `status.json` |
| `__main__.py` | argparse: `generate` (synchronous, JSON to stdout, exit 1 with `ERROR [texture.*]` / `Remediation:` on failure), `status` (availability table for both backends), and `run-job` (internal) |

`STYLE_SUFFIX = "seamless tileable texture, flat top-down orthographic photo scan, uniform even diffuse lighting, no shadows, no perspective, fills the entire frame edge to edge, photorealistic, PBR albedo, no objects, no text, no watermark"`, appended as `f"{prompt}, {suffix}"`.

### MCP server (`mcp-servers/texture-gen/`)

| Path | Contents |
|------|----------|
| `pyproject.toml` | Package `texture-gen-mcp`; depends on `mcp` (exact pin, `<2`) and the root `nmg-game-dev[texture-ai]` as a path dependency; script `texture-gen-mcp` |
| `src/texture_gen_mcp/server.py` | FastMCP server `texture-gen` with tools `generate_textures(prompt, backend="flux2-klein-4b", seeds=None, resolution=1024, name=None, maps=None, ao=False) -> {"job_id"}`, `get_texture_job(job_id) -> status`, and `texture_backends() -> availability`. Errors are returned as `{"error": {"code", "message", "remediation"}}`. Logs go to stderr only |
| `tools.json` | The three tool names, one-line descriptions, and required parameters |

`.mcp.json` gains a `texture-gen` entry: `"command": "uv", "args": ["run", "--project", "${CLAUDE_PLUGIN_ROOT}/mcp-servers/texture-gen", "texture-gen-mcp"]` and a description. The `blender` and `unreal` entries stay unchanged, and the entry text must not contain `latest`, `main`, or `HEAD`. `scripts/validate-mcp-tools.py` imports each `mcp-servers/*/src/*/server.py`, lists the registered tools, and exits 1 when they differ from `tools.json` or when a description or input schema is missing.

## API / Interface Changes

| Interface | Input | Output / Error | Behavior |
|-----------|-------|----------------|----------|
| `python -m nmg_game_dev.onboard install` | `--consumer`, `--uproject`, `--models-dir`, `--refresh`, `--json` | Exit 0 with step report (drift included); exit 1 with `ERROR [onboard.*]` | FR1, FR2, FR9 |
| `python -m nmg_game_dev.onboard volumes` | none | JSON `[{"mount": str, "free_bytes": int, "fits_models": bool}]` | FR1, AC6 |
| VibeUE clone | missing `Plugins/VibeUE` | `git clone --depth 1 --branch v5.0-ue5.8 https://github.com/kevinpbuckley/VibeUE.git <C>/Plugins/VibeUE` | Present: `git -C … rev-parse HEAD` must equal `bc7bc45c1e2025123778560f45c15d1f8e1be41d`, else drift. Present without `.git`: drift. Refresh: `git -C … fetch --depth 1 origin tag v5.0-ue5.8` then `git -C … checkout --force bc7bc45c…`, or clone again if it isn't a git checkout |
| Model install | each missing `<D>/<id>-q4`, ids from `REGISTRY` | `mflux-save --model <id> --quantize 4 --path <D>/<id>-q4` with env `HF_HOME=<D>/hf-cache`, run sequentially | Non-zero exit → `OnboardError onboard.model_install_failed` naming the model; when `mflux-save` is missing, first `uv tool install mflux==0.24.0` (failure → `onboard.mflux_install_failed`) |
| `python -m nmg_game_dev.texture generate` | `--prompt`, `--backend`, `--seed` (repeatable), `--resolution`, `--name`, `--maps PRESET` or `--roughness R --metallic M`, `--ao`, `--style-suffix` | JSON `TextureResult`; exit 1 with `ERROR [texture.*]` | AC16–AC20 |
| `python -m nmg_game_dev.texture status` | none | JSON `{id: availability}` | AC14, AC15 |
| MCP `generate_textures` / `get_texture_job` / `texture_backends` | as above | job id / status / availability | AC20 |

Texture error codes: `texture.unknown_backend`, `texture.model_not_allowed`, `texture.model_not_installed`, `texture.unsupported_platform`, `texture.insufficient_memory`, `texture.worker_failed`, `texture.job_running`, `texture.job_not_found`, `texture.invalid_request` (resolution not a power of two in 256–2048, empty prompt, unknown preset).

## Data / Storage Changes

Consumer writes (all relative to the consumer root):

| Path | Owner | Drift-checked |
|------|-------|---------------|
| `scripts/start-blender-mcp.sh`, `scripts/start-unreal-mcp.sh` | framework | yes |
| `.claude/settings.json` (SessionStart group) | merged | no (merge only) |
| `.claude/settings.local.json` `env.TEXTURE_GEN_MODELS_DIR`, `env.HF_HOME` | merged | no (set to the resolved values) |
| `docs/nmg-game-dev/asset-contract.md` | framework | yes |
| `CLAUDE.md` / `AGENTS.md` marked block | framework block | block replaced in place |
| `Plugins/nmg-game-dev/` | framework | yes (tree, excluding `Binaries/`, `Intermediate/`) |
| `Plugins/VibeUE/` | pinned clone | yes (HEAD commit) |
| `<name>.uproject` `Plugins[]` | merged | no |
| `Config/DefaultEditorPerProjectUserSettings.ini` | merged | no |
| `nmg-budgets.json` | consumer | never read, written, or reported |
| `SourceArt/Textures/Generated/<name>/` | texture generation | not touched by onboarding |

`.uproject` merge: parse JSON; for each of `ModelContextProtocol`, `EditorToolset`, `VibeUE`, `nmg-game-dev`, set `Enabled: true` on an existing entry or append `{"Name": n, "Enabled": true}`; write back with tab indentation; leave every other field unchanged.

Ini merge: line-based. Add the section if absent; set `bAutoStartServer=True`; add `ServerPortNumber=8000` only when no `ServerPortNumber=` line exists in that section; keep every other line and section.

Blender link: `<BLENDER_EXTENSIONS_DIR>/nmg_game_dev_blender_addon` → `<framework>/plugins/nmg-game-dev-blender-addon` (the id from `blender_manifest.toml`). The directory is created if missing.

Texture output, for `<root>/<name>/`:

- `<backend>_<seed>_<res>.png` (seamless albedo)
- `<backend>_<seed>_<res>_{N,R,M,AO}.png` when maps are requested
- `<name>_compare.png` for `both`
- `textures.json`, with sorted keys: `{"name", "prompt", "style_suffix", "images": [{"backend", "repo", "revision", "seed", "steps", "resolution", "seconds", "path", "maps": {...}}], "skipped": [{"backend", "availability"}]}`

Re-running with the same name and seed overwrites those files.

Dependencies in `pyproject.toml`:

- core gains `numpy` and `pillow`, exact-pinned;
- optional extra `texture-ai = ["mflux==0.24.0", "hf_transfer==<exact>"]`;
- `uv.lock` is updated.

## State and UI Behavior

The skill flow:

1. Unless `NMG_SDLC_AUTOPILOT=1`, run `volumes`, then ask with `AskUserQuestion` which qualifying volume should hold the texture models, recommending the one with the most free space. The models dir is `<mount>/nmg-texture-models`. Under autopilot, use `TEXTURE_GEN_MODELS_DIR`; if it's unset, the install's `onboard.models_dir_missing` remediation is shown.
2. Run `install`.
3. Relay installed / unchanged / drift lines; for drift, offer re-running with `--refresh`.

Report lines are `<status> <step>: <detail>`, with a `Remediation:` line for drift.

Texture job `status.json`: `{"job_id", "state": "queued"|"running"|"succeeded"|"failed", "completed", "total", "result"?, "error"?}`. It is rewritten atomically (temp file + rename) after each image and at the end. The lock is released when the job process exits. A stale lock (dead PID) is replaced.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Python package with a thin skill | Selected | Testable on temp dirs; matches the `ship` package layout from #6 |
| All logic as SKILL.md instructions | Rejected | Not deterministic or testable; idempotency would depend on the agent |
| Optional texture models | Rejected | Interview decision: models are required and installed on a chosen disk |
| Leave VibeUE/Epic plugin setup to #68 | Rejected | Interview decision: consumer Unreal setup moves to #7 |
| Overwrite drifted files on every run | Rejected | A plain re-run reports drift; `--refresh` is the explicit repair |
| Texture generation in a separate issue (#65) | Rejected | Interview decision: #65 is folded into #7 so model install and generation share one registry |
| Open registration of extra texture models | Rejected | Interview decision: Z-Image Turbo and FLUX.2 klein 4B are the only texture models |
| Blocking MCP generate call | Rejected | Interview decision: batches exceed MCP timeouts, so the tool starts a job and is polled |
| Output under `Content/` or a temp dir | Rejected | Interview decision: `SourceArt/Textures/Generated/` keeps raw PNGs out of UE auto-import and survives cleanup |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #7 | 2026-10-29 | Initial feature design |
| #7 | 2026-10-30 | Spec revised before delivery |
