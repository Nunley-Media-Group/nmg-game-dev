# Design: Add launch options, a headless autoplay smoke run, and on-demand game screenshots for Godot games

**Issue**: #251
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/249-replace-unreal-engine-with-godot-4-and-convert-existing-consumer-projects/

## Overview

A new `NmgLaunch` autoload in the runtime add-on owns launch options, the autoplay signal, the test save folder, and the in-game screenshot. On the Python side, `src/nmg_game_dev/godot/` gains `smoke.py`, `shot.py`, and a `__main__.py` CLI. Both drive Godot through the existing injectable `GodotRunner`. `/ship` reuses the smoke check as a gate. The finalize MCP server exposes the shot as `game_screenshot`. Onboarding registers the new autoload the same way it registers `NmgAssets`.

## Architecture

```
game (Godot)                           host (Python)
addons/nmg_game_dev/nmg_launch.gd  <-- python -m nmg_game_dev.godot smoke  --> godot.smoke.run_smoke
  options, autoplay_requested,          python -m nmg_game_dev.godot shot   --> godot.shot.take_shot
  save_dir, --nmg-shot                  finalize MCP game_screenshot        --> finalize.mcp_tools.game_screenshot -> take_shot
                                        /ship gates                         --> ship.runner._run_smoke -> godot.smoke
```

### NmgLaunch (`plugins/nmg-game-dev-godot-addon/addons/nmg_game_dev/nmg_launch.gd`)

`extends Node`, statically typed, no `_process` hook.

- `signal autoplay_requested`
- `const TEST_SAVE_DIR: String = "user://nmg-test/"`, `const DEFAULT_SAVE_DIR: String = "user://"`
- `configure(user_args: PackedStringArray, url_hash: String) -> void` clears and parses the options. Each user argument starting with `--` is stripped of `--` and split at its first `=`. A token without `=` maps to `"true"`, and tokens not starting with `--` are ignored. The hash is parsed after the arguments, so the hash wins on a repeated name. A leading `#` is stripped, the rest is split on `&`, empty parts are skipped, each part is split at its first `=`, and names and values are `uri_decode()`d. A bare name maps to `"true"`.
- `get_option(name: String, default_value: String = "") -> String`, `has_option(name: String) -> bool`.
- `save_dir() -> String` returns `TEST_SAVE_DIR` and makes the folder (`DirAccess.make_dir_recursive_absolute`) when `nmg-test-saves` is set, else `DEFAULT_SAVE_DIR`.
- `_ready()` calls `configure(OS.get_cmdline_user_args(), _web_hash())`. `_web_hash()` returns `str(JavaScriptBridge.eval("window.location.hash", true))` only when `OS.has_feature("web")`, else `""`. When `nmg-shot` is set it starts `_take_shot()`. When `nmg-autoplay` is set it awaits `get_tree().process_frame` until `get_tree().current_scene` is not null (at most 600 frames) and then calls `request_autoplay()`.
- `request_autoplay() -> void` emits `autoplay_requested` only the first time it is called.
- `_take_shot()` reads `nmg-shot-after` as a float (default 0), awaits `get_tree().create_timer(after).timeout`, then awaits `RenderingServer.frame_post_draw`. It saves `get_viewport().get_texture().get_image()` with `save_png(get_option("nmg-shot"))` and calls `get_tree().quit(0)` on `OK`. Otherwise it calls `push_error` with the path and quits with 1.

`plugin.gd` registers `NmgLaunch` → `res://addons/nmg_game_dev/nmg_launch.gd` beside `NmgAssets` and removes both on exit.

### Smoke (`src/nmg_game_dev/godot/smoke.py`)

- `DEFAULT_FRAMES = 600`, `MAX_ERROR_LINES = 20`.
- `smoke_args(frames: int) -> list[str]` returns `["--fixed-fps", "60", "--quit-after", str(frames), "--", "--nmg-autoplay", "--nmg-test-saves"]`. `SubprocessGodotRunner` prepends `--headless --audio-driver Dummy --path <game>`.
- `error_lines(result) -> list[str]` returns the stripped stdout+stderr lines that start with `SCRIPT ERROR` or `ERROR:`, or that contain `Parse Error`, in order.
- `check_smoke(result: CommandResult) -> None` raises `PipelineError(code="smoke.timeout", stage="smoke")` with `TIMEOUT_REMEDIATION` when `returncode == TIMEOUT_EXIT`. It raises `smoke.runtime_error` when there are error lines or a non-zero exit. The message carries up to the first 20 error lines, or `Godot exited <n>` when there are none. The remediation is `Fix the first error above (run the game in Godot to reproduce it), then rerun the smoke run.`
- `run_smoke(runner: GodotRunner, project_dir: Path, frames: int = DEFAULT_FRAMES) -> CommandResult` runs and checks one smoke.

### Shot (`src/nmg_game_dev/godot/shot.py`)

- `SHOT_GRACE_S = 60.0`.
- `shot_args(path: Path, after: float, options: Sequence[str]) -> list[str]` returns `["--", *options, "--nmg-test-saves", f"--nmg-shot={path}", f"--nmg-shot-after={after:g}"]`.
- `take_shot(project_dir, path, after, options, *, runner=None, env=None) -> dict` works as follows:
  - Resolves `path` to an absolute path, makes its parent, and deletes a stale file at the path.
  - With no runner, builds `SubprocessGodotRunner(resolve_godot(env), headless=False)`, so `godot.not_found` propagates.
  - Runs with `timeout = after + SHOT_GRACE_S`.
  - Reads width and height from the PNG IHDR (bytes 16–24 after the 8-byte signature).
  - Returns `{"path": str(path), "width": w, "height": h}`.
  - A missing or non-PNG file raises `shot.no_image` (stage `shot`), with the last 20 output lines in the message and the remediation `Check that the game starts in a window and that NmgLaunch is registered as an autoload, then rerun.`
- A negative `after` raises `shot.invalid_after`.

### Runner change (`src/nmg_game_dev/godot/runner.py`)

`SubprocessGodotRunner.__init__(binary, *, timeout=None, headless=True)`. With `headless=False`, `argv()` omits `--headless` but keeps `--audio-driver Dummy --path <project>`. Every existing caller keeps the default.

### CLI (`src/nmg_game_dev/godot/__main__.py`)

`python -m nmg_game_dev.godot smoke [--frames N] [--project PATH]` and `python -m nmg_game_dev.godot shot <path> [--after S] [--project PATH] [-- <launch options>]`.

- The argv is split at the first `--` before argparse. Tokens after it are the shot's launch options.
- `--project` defaults to `<project_root()>/game/project.godot` (`nmg_game_dev.audio.paths.project_root`). A missing file raises `godot.project_missing`.
- `--after` defaults to 3.
- Smoke success prints `smoke passed (<N> frames)`. Shot success prints the JSON object. Both exit 0.
- On `PipelineError` the CLI prints the error lines (smoke) or output lines (shot) already in the message, then `ERROR [<code>]: <message>` and `Remediation: <remediation>` to stderr, and exits 1. Argument errors exit 2.

### Ship gate (`src/nmg_game_dev/ship/runner.py`)

`_run_smoke(ship)` is called in `run_ship` immediately after `_run_project_tests(ship)` and before `_gate_mobile_budgets`. It runs `_godot_run(ship, smoke_args(DEFAULT_FRAMES), ship.gate_lines)`. In a dry run that prints and records `DRY-RUN: godot --headless --audio-driver Dummy --path <game> --fixed-fps 60 --quit-after 600 -- --nmg-autoplay --nmg-test-saves` and runs nothing. Otherwise it calls `check_smoke`. A `PipelineError` is re-raised as `ShipError(code="ship.smoke_failed", stage="smoke")` whose message names the smoke code and its lines and keeps the smoke remediation.

### MCP tool (`src/nmg_game_dev/finalize/mcp_tools.py`, `mcp-servers/finalize/`)

`game_screenshot(path: str, after: float = 3, options: list[str] | None = None, *, project_root=None, godot=None) -> dict` works as follows:

- Resolves `game/project.godot` under `project_root` or `project_root()`.
- Rejects `after` outside `[0, 60]` with `shot.invalid_after`.
- Resolves a relative `path` against the consumer root.
- Calls `take_shot` and returns its dict, or `{"error": error_dict(e)}` on a `PipelineError`.

`server.py` registers `@mcp.tool(name="game_screenshot")`. `tools.json` adds the entry: `path` (string, required), `after` (number, minimum 0, maximum 60), `options` (array of strings, or null).

### Onboarding (`src/nmg_game_dev/onboard/godot.py`)

Add `LAUNCH_AUTOLOAD_RES = "res://addons/nmg_game_dev/nmg_launch.gd"` and `("autoload", "NmgLaunch"): godot_string("*" + LAUNCH_AUTOLOAD_RES)` to `DRIFT_CHECKED`. `render_project` writes both autoloads, `NmgAssets` then `NmgLaunch`. The existing missing-key (`refreshed`) and differing-value (`drift`) handling applies unchanged. `tests/godot/fixture/project.godot` gains the same autoload line.

## API / Interface Changes

| Interface | Input | Output / Error | Behavior |
|-----------|-------|----------------|----------|
| `NmgLaunch.get_option(name, default)` | option name, default | String | value from user args or URL hash; bare flag `"true"`; absent → default |
| `NmgLaunch.has_option(name)` | option name | bool | whether the option was given |
| `NmgLaunch.save_dir()` | — | `user://nmg-test/` or `user://` | test folder only with `--nmg-test-saves` |
| `NmgLaunch.autoplay_requested` | — | signal | emitted once after the main scene loads with `--nmg-autoplay` |
| `python -m nmg_game_dev.godot smoke` | `--frames`, `--project` | `smoke passed (N frames)`, exit 0; `smoke.runtime_error` / `smoke.timeout` / `godot.not_found` / `godot.project_missing`, exit 1 | headless run with error-line detection |
| `python -m nmg_game_dev.godot shot` | `<path>`, `--after`, `--project`, `-- options` | JSON `{path,width,height}`, exit 0; `shot.no_image` / `shot.invalid_after` / `godot.not_found`, exit 1 | windowed run that saves a PNG |
| finalize MCP `game_screenshot` | `path`, `after` (0–60), `options` | `{path,width,height}` or `{"error"}` | same as `shot` |
| `/ship` gate | — | `ship.smoke_failed` | smoke after tests, before budgets and export |

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| `headless` flag on `SubprocessGodotRunner` | Selected | Keeps one runner, timeout handling, and the `GodotRunner` protocol; the fake needs no change |
| A separate windowed runner class | Rejected | Duplicates the subprocess, timeout, and exit-124 handling |
| Special-casing a project without a main scene | Rejected | Godot exits non-zero itself; `smoke.runtime_error` already reports it |
| Leaving the autoload to the editor plugin only | Rejected | nmg-game-dev never runs a live editor, so only onboarding can write the `[autoload]` key |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #251 | 2026-11-18 | Initial feature design |
