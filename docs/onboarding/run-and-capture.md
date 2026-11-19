# Run the game, smoke-test it, and capture screenshots

Three commands run your Godot game without an editor: a launch-option set that reads the same on
desktop and web, a headless smoke run that fails on runtime errors, and a screenshot of the running
game. Claude uses them to start the game at a chosen state, catch errors before a ship, and review
how finalized assets look under the game's own lighting and materials. Onboarding registers the
`NmgLaunch` autoload that all three rely on (`game/project.godot`, `[autoload]`).

## Launch options

`NmgLaunch` is an autoload in the `nmg_game_dev` add-on. It reads the same option names on both
platforms:

| Platform | How the options arrive | Example |
|---|---|---|
| Desktop | After `--` on the command line | `godot --path game -- --hour=12 --at=Forest` |
| Web | In the URL hash | `https://example.com/game/#hour=12&at=Forest` |

A bare flag, such as `--nmg-autoplay` or `#nmg-autoplay`, reads `"true"`. An option that was not
given returns the default you pass. When a name appears in both the command line and the hash, the
hash wins.

Game code reads the options through the autoload:

```gdscript
var at: String = NmgLaunch.get_option("at", "Town")
var hour: int = int(NmgLaunch.get_option("hour", "12"))
if NmgLaunch.has_option("at"):
	pass  # the player asked for a specific place
```

Two more calls cover the test runs and the autoplay:

- `NmgLaunch.autoplay_requested` is a signal. With `--nmg-autoplay`, it fires once, on a frame
  after the main scene's `_ready`, so connecting it in the main scene's `_ready` is enough. Connect
  it to whatever your game does when a player takes over. Autoplay itself is the game's own
  behavior.
- `NmgLaunch.save_dir()` returns `user://nmg-test/` (created on demand) when the game runs with
  `--nmg-test-saves`, and `user://` otherwise. Save through it, so test runs never touch the
  player's saves.

## Smoke run

The smoke run starts the game headless for 600 frames with `--nmg-autoplay --nmg-test-saves`, then
checks the output:

```
uv run --project "${CLAUDE_PLUGIN_ROOT}" python -m nmg_game_dev.godot smoke [--frames N] [--project PATH]
```

A clean run prints `smoke passed (600 frames)` and exits 0. It fails with `smoke.runtime_error`
when the output has a `SCRIPT ERROR`, `Parse Error`, or `ERROR:` line, or when Godot exits non-zero.
It fails with `smoke.timeout` when the run does not finish in time. A failure prints up to the first
20 error lines and a `Remediation:` line, and exits 1. `--project` defaults to
`game/project.godot` under the consumer root.

`/ship` runs the same smoke run as a gate after the project tests and before the mobile budget gate
and any export. A failing smoke run stops the ship with `ship.smoke_failed`, and no export runs. See
[docs/skills/ship.md](../skills/ship.md).

## Screenshots

A screenshot runs the game in a window, saves the root viewport as a PNG after a delay, and quits:

```
uv run --project "${CLAUDE_PLUGIN_ROOT}" python -m nmg_game_dev.godot shot build/shots/forest.png --after 3 -- --at=Forest --hour=18
```

The game runs with your launch options after `--`, plus `--nmg-test-saves`, `--nmg-shot=<absolute
path>`, and `--nmg-shot-after=<seconds>`. On success the command prints the result as JSON, with
`path`, `width`, and `height`, and exits 0. `--after` defaults to 3 seconds, and the run is bounded
by `after` plus 60 seconds. A relative path resolves against the consumer root. The window needs a
display, so run this on a machine with a desktop session, not a headless CI host.

The finalize MCP server exposes the same capture as the `game_screenshot` tool. It takes `path`,
`after` (0 to 60 seconds, default 3), and `options` (a list of launch options such as
`["--at=Forest", "--hour=18"]`), and returns `{"path", "width", "height"}`. See
[docs/mcp/finalize.md](../mcp/finalize.md#game_screenshot-251).

## Failures

| Code | Meaning | Remediation |
|---|---|---|
| `smoke.runtime_error` | The smoke run printed an error line or exited non-zero | Fix the first error line, then rerun |
| `smoke.timeout` | The smoke run did not finish in time | Make sure the main scene quits after its frames and does not hang, or raise `NMG_GODOT_TIMEOUT_S` |
| `shot.no_image` | The game exited without writing the PNG | Check that the game starts in a window and that `NmgLaunch` is registered. The message carries the last output lines |
| `shot.invalid_path` | The path is a folder, or its folder cannot be written to | Pass a `.png` file path in a folder you can write to |
| `shot.invalid_after` | `after` is negative (CLI) or outside 0 to 60 seconds (tool) | Pass a shorter or non-negative delay |
| `godot.not_found` | No Godot binary | Install Godot 4 or set `GODOT_BIN` |
| `godot.project_missing` | No `project.godot` at the expected path | Run `/onboard-consumer`, or pass `--project` |

No screenshot runs during `/ship`, and the capture does not compare images against reference
renders. The gate that protects the add-on runs its own unit tests only, not the game.
