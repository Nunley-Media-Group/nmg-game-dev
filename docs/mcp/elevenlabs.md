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

4. **Finish.** The game copy is finished before it is imported, unless you turn that off. See
   [Finishing](#finishing).

## Parameters

| Parameter | Required | Meaning |
|-----------|----------|---------|
| `file` | yes | The saved file: `.wav`, `.mp3`, `.ogg`, or `.flac` |
| `name` | yes | PascalCase, matching `^[A-Z][A-Za-z0-9]*$`. It must not start with `SFX_` or `MUS_` |
| `kind` | yes | `sfx` (sound effect) or `music` |
| `loop` | no | `true` makes the stream loop. Default `false` |
| `max_seconds` | no | Cut the finished sound to this many seconds, with a 20 ms fade-out. Must be above 0. CLI `--max-seconds` |
| `loudness_lufs` | no | Integrated loudness target, from -40 to -5 LUFS. Default -16 for `sfx`, -18 for `music`. CLI `--loudness-lufs` |
| `loop_crossfade_ms` | no | Length of the loop seam crossfade, in milliseconds, zero or more. Default 500, capped at a quarter of the sound. CLI `--loop-crossfade-ms` |
| `finish` | no | `false` imports the stored WAV unchanged, with no trim, cut, crossfade, or loudness match. Default `true`. CLI `--no-finish` |

A setting you leave out comes from the sound's entry in `SourceArt/Audio/audio.json`, and then from
the default for its kind. A setting you pass is stored for that sound, so the next import of the same
file, or `refinish`, reuses it. Settings are stored per sound, and a stored `max_seconds` stays
until you pass a new value.

## What lands where

| Kind | Stored WAV (the untouched source) | Godot file (finished) | Godot resource |
|------|------------------------------------|-----------------------|----------------|
| `sfx` | `SourceArt/Audio/SFX/<Name>.wav` | `game/assets/Audio/<Name>.wav` | `AudioStreamWAV`. Its `.import` sets `edit/loop_mode=2` (Forward, looping the whole file) when `loop` is true, otherwise `edit/loop_mode=1` |
| `music` | `SourceArt/Audio/Music/<Name>.wav` | `game/assets/Audio/<Name>.ogg`, encoded from the finished WAV | `AudioStreamOggVorbis`, encoded with ffmpeg (`-c:a libvorbis -q:a 5`). Its `.import` sets `loop=true` when `loop` is true, otherwise `loop=false` |

`SourceArt/Audio/` always keeps the bytes you saved. Only the game copy is finished.

## Finishing

Finishing runs in Python, so a sound effect needs no ffmpeg. It runs these steps in order:

1. **Trim.** Leading frames below -50 dBFS are removed. A sound with no frame above that level is
   silent: it is not trimmed, and its loudness is not matched.
2. **Cut.** With `max_seconds`, the sound keeps `round(max_seconds × rate)` frames. Without
   `loop`, the last 20 ms fade linearly to zero.
3. **Loop crossfade.** With `loop`, the tail is blended into the head over `loop_crossfade_ms`,
   capped at a quarter of the sound. The step across the loop seam is then a step that already
   exists inside the sound, so the loop does not click.
4. **Loudness.** The integrated loudness is measured as ITU-R BS.1770-4 (K-weighting, 400 ms blocks
   with 75 % overlap, the -70 LUFS absolute gate, and the -10 LU relative gate), and the gain moves it
   to `loudness_lufs`. If that would put the peak above -1 dBFS, the gain stops at a -1 dBFS peak and
   the result reports `loudness_capped: true`. For music the measurement is on the finished WAV that
   ffmpeg encodes.

The output keeps the source's sample rate and channel count, and it is written as 16-bit PCM. The
same input and settings give byte-identical output.

### `audio.json`

Each sound's settings are stored in `SourceArt/Audio/audio.json`, written as sorted, indented JSON:

```json
{
  "sounds": {
    "DoorCreak": {
      "finish": true,
      "kind": "sfx",
      "loop": false,
      "loop_crossfade_ms": 500,
      "loudness_lufs": -16.0,
      "max_seconds": null
    }
  },
  "version": 1
}
```

(The example shows one entry. The file has an entry for every imported sound.) Commit it with the
stored WAVs. A file that cannot be read, or that has an invalid entry, fails with
`audio.settings_invalid` before anything is written.

### Re-import and `refinish`

Importing the same file again under the same name, with the same bytes, finishes the game copy again
with the stored settings, and the result is byte-identical to the first import. Importing a different
file under that name still fails with `audio.asset_exists`.

To re-finish stored sounds without importing them again, use `refinish`. It reads each WAV from
`SourceArt/Audio/`, applies the stored settings, and writes the game copy again:

```text
python -m nmg_game_dev.audio refinish --all
python -m nmg_game_dev.audio refinish DoorCreak ForestTheme
```

`refinish` prints a JSON list, one result per sound, in name order. A name with no entry in
`audio.json`, or with no stored WAV, fails with `audio.unknown_sound`. `refinish` is a CLI command,
not a finalize tool.

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
| `source_art` | Absolute path of the stored WAV, the untouched source |
| `godot_asset` | The resource path: `res://assets/Audio/<Name>.wav` for a sound effect, `res://assets/Audio/<Name>.ogg` for music |
| `converted` | `true` when the input was decoded and written as a new WAV |
| `source_format` | `wav`, `mp3`, `ogg`, or `flac` |
| `sample_rate`, `channels` | The stored WAV's rate and channel count |
| `duration_seconds` | The length of the stored audio |
| `looping` | Whether the stream loops |
| `imported_to_godot` | `true` when the stream was imported into the Godot project |
| `finish` | The finishing report: `applied`, `trimmed_ms`, `cut`, `loop_crossfade_ms`, `loudness_lufs` (measured after the gain), `target_lufs`, `loudness_capped`, `silent`, and `duration_seconds`. `{"applied": false}` when `finish` is off |
| `settings` | The settings used: `finish`, `max_seconds`, `loudness_lufs`, and `loop_crossfade_ms` |
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
| `audio.invalid_request` | The name is not PascalCase or starts with `SFX_` or `MUS_`, the kind is not `sfx` or `music`, the file does not exist, or a setting is out of range (`max_seconds` not above 0, `loudness_lufs` outside -40 to -5, `loop_crossfade_ms` below 0) | Pass a PascalCase name, a kind of `sfx` or `music`, a file that exists, and settings in range |
| `audio.unsupported_format` | The extension is not `.wav`, `.mp3`, `.ogg`, or `.flac` | Save the sound in one of the four formats |
| `audio.asset_exists` | `SourceArt/Audio/<SFX\|Music>/<Name>.wav` or the target under `game/assets/Audio/` already holds a different file. Nothing is overwritten. An identical file re-finishes instead | Choose another name, or delete the stored WAV and the Godot file if you mean to replace them |
| `audio.settings_invalid` | `SourceArt/Audio/audio.json` cannot be read, or an entry in it is invalid. Nothing is written | Fix or delete the entry in `audio.json`, then try again |
| `audio.unknown_sound` | `refinish` was asked for a name with no entry in `audio.json`, or the entry's stored WAV is missing | Pass a name that `audio.json` lists, or run `refinish --all`. Import the sound again if its stored WAV is gone |
| `audio.decode_failed` | The file could not be decoded. No partial WAV is left behind | Re-export the file, check that it is not truncated, then import again |
| `audio.ffmpeg_not_found` | A music import found no ffmpeg at `FFMPEG_BIN` or on `PATH`. Nothing was written under `game/` | Install ffmpeg or set `FFMPEG_BIN` to its executable |
| `audio.import_failed` | The headless Godot import reported an error, or the probe did not find the expected stream class or loop setting. The stored WAV is kept | Read the error in the message, run `godot --headless --path game --import` to see the full output, then import again |
| `godot.not_found` | Returned as the `warning` above, not as an error | Install Godot 4 (latest stable) or set `GODOT_BIN` to its executable |

Errors come back from the `finalize` MCP tool as `{"error": {"code", "message", "remediation",
"stage"}}`. The CLI prints `ERROR [code] message` and a `Remediation:` line to stderr, then exits 1.
Argument errors exit 2.

## Scope

- nmg-game-dev imports saved audio. It does not generate audio, and it does not handle ElevenLabs
  keys or call the ElevenLabs API. It finishes only the game copy (trim, cut, loop crossfade, and
  loudness), and the stored WAV under `SourceArt/Audio/` stays as you saved it.
- Each import makes one audio stream resource. Audio buses, players, and effects are not created.
- Overwriting an imported sound in place is not supported.
- The `miniaudio` decoder is a floor dependency (`miniaudio>=1.59`) and tracks its latest release.
