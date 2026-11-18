# ElevenLabs audio: sound effects and music through the official MCP

nmg-game-dev does not generate audio. The official ElevenLabs MCP server generates sound effects and
music, and you run it yourself, with your own key. nmg-game-dev takes the file that server saves and
imports it: a 16-bit WAV under `SourceArt/Audio/`, and an audio stream in the consumer's Godot
project, imported with `godot --headless`. Nothing here calls the
ElevenLabs API or reads an ElevenLabs key, and `.mcp.json` declares no ElevenLabs server.

Audio is optional. A project that never imports sound needs none of this.

## Set up the official server

Install the official ElevenLabs MCP server at its latest version, and configure its API key in your
own environment. nmg-game-dev never reads that key. Onboarding asks for no key and installs no
ElevenLabs server. Once the server runs, your agent can call its sound-effect and music tools.

## The flow

1. **Generate.** Ask the agent for a sound effect or a music track. It uses the official ElevenLabs
   MCP tools.
2. **Save.** Save the output to a local file. The server saves MP3 by default. Any of the four
   supported formats imports.
3. **Import.** Call `import_audio` with the file, a PascalCase name, the kind, and an optional loop
   flag:

   ```text
   import_audio(file="/Users/me/Downloads/door.mp3", name="DoorCreak", kind="sfx")
   import_audio(file="/Users/me/Downloads/forest.mp3", name="ForestTheme", kind="music", loop=true)
   ```

   The same call from a shell:

   ```text
   python -m nmg_game_dev.audio import --file door.mp3 --name DoorCreak --kind sfx [--loop]
   ```

## Parameters

| Parameter | Required | Meaning |
|-----------|----------|---------|
| `file` | yes | The saved file: `.wav`, `.mp3`, `.ogg`, or `.flac` |
| `name` | yes | PascalCase, matching `^[A-Z][A-Za-z0-9]*$`. It must not start with `SFX_` or `MUS_` |
| `kind` | yes | `sfx` (sound effect) or `music` |
| `loop` | no | `true` makes the stream loop. Default `false` |

## What lands where

| Kind | Stored WAV | Godot file | Godot resource |
|------|------------|------------|----------------|
| `sfx` | `SourceArt/Audio/SFX/<Name>.wav` | `game/assets/Audio/<Name>.wav` | `AudioStreamWAV`. Its `.import` sets `edit/loop_mode=2` (Forward, looping the whole file) when `loop` is true, otherwise `edit/loop_mode=1` |
| `music` | `SourceArt/Audio/Music/<Name>.wav` | `game/assets/Audio/<Name>.ogg` | `AudioStreamOggVorbis`, encoded with ffmpeg (`-c:a libvorbis -q:a 5`). Its `.import` sets `loop=true` when `loop` is true, otherwise `loop=false` |

After writing the file and its `.import`, the import runs `godot --headless --path game --import` and a
probe that loads the resource. The probe must report the expected class and loop setting, otherwise the
call fails with `audio.import_failed`.

The stored WAV is written under the project root (`CLAUDE_PROJECT_DIR`, else the working directory).
Commit it like other source art. Git LFS tracks `.wav` once onboarding has run.

## Formats

- **WAV** is copied byte for byte. `converted` is `false`.
- **MP3, OGG (Vorbis), and FLAC** are decoded in process with `miniaudio` and written as 16-bit PCM
  WAV. The sample rate and channel count stay the same as the source. `converted` is `true`.
- Any other extension is rejected with `audio.unsupported_format`.
- Music is encoded to Ogg Vorbis for Godot with ffmpeg, resolved from `FFMPEG_BIN` (it must be
  executable), then `ffmpeg` on `PATH`. Without it a music import fails with `audio.ffmpeg_not_found`
  before anything is written under `game/`. Sound effects need no ffmpeg.

## Result

`import_audio` returns this JSON. The CLI prints the same object.

| Field | Meaning |
|-------|---------|
| `kind`, `name` | The request, as given |
| `source_art` | Absolute path of the stored WAV |
| `godot_asset` | The resource path: `res://assets/Audio/<Name>.wav` for a sound effect, `res://assets/Audio/<Name>.ogg` for music |
| `converted` | `true` when the input was decoded and written as a new WAV |
| `source_format` | `wav`, `mp3`, `ogg`, or `flac` |
| `sample_rate`, `channels` | The stored WAV's rate and channel count |
| `duration_seconds` | The length of the stored audio |
| `looping` | Whether the stream loops |
| `imported_to_godot` | `true` when the stream was imported into the Godot project |
| `warning` | Present only when no Godot binary was found. See below |

## When Godot is not installed

If no Godot binary is found (`GODOT_BIN`, then `godot` on `PATH`, then `/Applications/Godot.app`), the
call still succeeds. It returns `imported_to_godot: false`, the `source_art` path, and a `warning`:

```json
"warning": {
  "code": "godot.not_found",
  "message": "...",
  "remediation": "Install Godot 4 (latest stable) or set GODOT_BIN to its executable."
}
```

The stored WAV stays under `SourceArt/Audio/`. Import is not retried automatically. Once Godot is
installed, a second `import_audio` call with the same name stops at `audio.asset_exists`, because the
WAV is already there. To import it again, either use a new name or delete the stored WAV first and call
`import_audio` again.

## Error codes

| Code | Meaning | Remediation |
|------|---------|-------------|
| `audio.invalid_request` | The name is not PascalCase or starts with `SFX_` or `MUS_`, the kind is not `sfx` or `music`, or the file does not exist | Pass a PascalCase name, a kind of `sfx` or `music`, and a file that exists |
| `audio.unsupported_format` | The extension is not `.wav`, `.mp3`, `.ogg`, or `.flac` | Save the sound in one of the four formats |
| `audio.asset_exists` | `SourceArt/Audio/<SFX\|Music>/<Name>.wav`, or the target under `game/assets/Audio/`, already exists. Nothing is overwritten | Choose another name, or delete the stored WAV and the Godot file if you mean to replace them |
| `audio.decode_failed` | The file could not be decoded. No partial WAV is left behind | Re-export the file, check that it is not truncated, then import again |
| `audio.ffmpeg_not_found` | A music import found no ffmpeg at `FFMPEG_BIN` or on `PATH`. Nothing was written under `game/` | Install ffmpeg or set `FFMPEG_BIN` to its executable |
| `audio.import_failed` | The headless Godot import reported an error, or the probe did not find the expected stream class or loop setting. The stored WAV is kept | Read the error in the message, run `godot --headless --path game --import` to see the full output, then import again |
| `godot.not_found` | Returned as the `warning` above, not as an error | Install Godot 4 (latest stable) or set `GODOT_BIN` to its executable |

Errors come back from the `finalize` MCP tool as `{"error": {"code", "message", "remediation",
"stage"}}`. The CLI prints `ERROR [code] message` and a `Remediation:` line to stderr, then exits 1.
Argument errors exit 2.

## Scope

- nmg-game-dev imports saved audio. It does not generate, edit, or trim it, and it does not handle
  ElevenLabs keys or call the ElevenLabs API.
- Each import makes one audio stream resource. Audio buses, players, and effects are not created.
- Overwriting an imported sound in place is not supported.
- The `miniaudio` decoder is a floor dependency (`miniaudio>=1.59`) and tracks its latest release.
