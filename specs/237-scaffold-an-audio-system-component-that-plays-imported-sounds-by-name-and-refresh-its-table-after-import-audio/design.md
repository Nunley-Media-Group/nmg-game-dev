# Design: Scaffold an Audio system component that plays imported sounds by name and refresh its table after import_audio

**Issue**: #237
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley

## Overview

Three parts:

- Runtime GDScript in the Godot add-on: `NmgAudio` and `NmgAudioTable`.
- File-only Python that writes and refreshes the table as a Godot text resource: `nmg_game_dev.audio.tables`.
- Wiring: design-field validation and the audio scaffold, `import_audio` auto-refresh, a CLI subcommand, and an MCP tool.

No Godot process is needed to scaffold or refresh.

## Architecture

```text
design sync ──► parse._check_optional_fields  (template / music → design.invalid_field)
design scaffold ──► scaffold._render(system, template=audio)
                      ├─ game/systems/<Name>/<snake>.gd   (extends NmgAudio; _init loads table)
                      └─ game/systems/<Name>/audio_table.tres  ◄── audio.tables.render_table(root)
python -m nmg_game_dev.audio refresh ─┐
finalize MCP refresh_audio_table ─────┼─► audio.tables.refresh_tables(root) ─► rewrite each NmgAudioTable .tres
import_audio (success) ───────────────┘
Godot runtime: AudioComponent (NmgAudio) ── table.sounds[name] → load(path) → AudioStreamPlayer / 3D
```

## API / Interface Changes

| Interface | Input | Output / Error | Behavior |
|-----------|-------|----------------|----------|
| `NmgAudio.sfx(name: StringName, position := Vector3.ZERO) -> void` | sound name, optional position | none | Plays through a pooled `AudioStreamPlayer` (ZERO) or a new `AudioStreamPlayer3D` child at `position`, `pitch_scale = randf_range(1 - pitch_jitter, 1 + pitch_jitter)`, volume = master × sfx |
| `NmgAudio.ui(name) -> void` | name | none | Non-positional, no pitch change, volume = master × sfx |
| `NmgAudio.music(name) -> void` | name | none | Same name already current → return. Otherwise fades the current music player to silence and stops it, and starts the new track on the other player, fading in over `crossfade_seconds` (0 = instant). `finished` on the current music player calls `play()` again |
| `NmgAudio.stinger(name) -> void` | name | none | Plays one-shot; music volume target drops by `duck_db`; restored on the stinger's `finished` |
| `NmgAudio.region_music() -> void` | — | none | `get_tree().current_scene.name` → `table.themes` → `music(theme)`; nothing when absent. Called from `_ready` |
| `NmgAudio.set_volumes(master: float, music: float, sfx: float) -> void` | 0–1 each, clamped | none | Applies to players and saves to `settings_path` section `volumes` keys `master`, `music`, `sfx` |
| `NmgAudio` exports | — | — | `table: NmgAudioTable`, `crossfade_seconds := 1.0`, `duck_db := -12.0`, `pitch_jitter := 0.05`, `settings_path := "user://nmg_audio.cfg"` |
| Missing name (any play call) | — | `push_warning("NmgAudio: no sound named <name>")` once per name | Plays nothing |
| `nmg_game_dev.audio.tables.render_table(root: Path) -> str` | project root | `.tres` text | Header `[gd_resource type="Resource" script_class="NmgAudioTable" load_steps=2 format=3]`, `ext_resource` to `res://addons/nmg_game_dev/audio/nmg_audio_table.gd`, `sounds` and `themes` dictionaries with keys sorted, trailing newline |
| `nmg_game_dev.audio.tables.refresh_tables(root: Path) -> list[str]` | project root | project-relative paths rewritten, sorted | Raises `PipelineError` `audio.godot_project_missing` without `game/project.godot`. A file whose text is unchanged is not rewritten |
| `python -m nmg_game_dev.audio refresh [--project PATH]` | — | prints `{"refreshed_tables": [...]}` JSON; exit 0 / 1 on error | Same as `refresh_tables` |
| finalize MCP `refresh_audio_table(project: str \| None = None)` | — | `{"refreshed_tables": [...]}` or `{"error": {code, message, remediation, stage}}` | Registered in `server.py` and `tools.json` |
| `import_audio` result | — | adds `refreshed_tables: list[str]` | Calls `refresh_tables` after a successful import |

Sounds come from `game/assets/Audio/<Name>.wav` and `<Name>.ogg`. The key is the file stem and the value is `res://assets/Audio/<file>`. Themes are built from backlog entries of type `region` whose `fields["music"]` is set, as `asset_name → music`. A missing backlog gives `{}`.

## Data / Storage Changes

- `design/parse.py::_check_optional_fields`: `template` on `system` must be `"audio"`; `music` on `region` must be a non-empty string. Otherwise `design.invalid_field`.
- `design/scaffold.py`: `_render` returns `audio_system_script(entry)` when `entry.fields.get("template") == "audio"`. After writing the script, `run_scaffold` writes `game/systems/<Name>/audio_table.tres` through `_write_new(..., render_table(root))`. The script:

  ```gdscript
  ## The <name> system: plays sounds and music by name.
  ##
  ## Scaffolded by /design from <source>.
  class_name <Name>Component
  extends NmgAudio


  func _init() -> void:
  	table = load("res://systems/<Name>/audio_table.tres")
  ```

- User settings: `user://nmg_audio.cfg` (`ConfigFile`, section `volumes`).

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Special-case a system named `Audio` | Rejected | The issue picks an explicit `template` field |
| Store loaded `AudioStream` resources in the table | Rejected | Paths load lazily and let refresh write the table without Godot |
| Control volumes through audio buses | Rejected | Bus layout is out of scope; per-player volume needs no project bus setup |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #237 | 2026-11-18 | Initial feature design |
