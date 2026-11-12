# ElevenLabs audio: sound effects and music through the official MCP

nmg-game-dev does not generate audio. The official ElevenLabs MCP server generates sound effects and
music, and you run it yourself, with your own key. nmg-game-dev takes the file that server saves and
imports it: a 16-bit WAV under `SourceArt/Audio/`, and a SoundWave in Unreal. Nothing here calls the
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
| `loop` | no | `true` makes the SoundWave loop. Default `false` |

## What lands where

| Kind | Stored WAV | Unreal asset |
|------|------------|--------------|
| `sfx` | `SourceArt/Audio/SFX/<Name>.wav` | `/Game/Audio/SFX/SW_<Name>` |
| `music` | `SourceArt/Audio/Music/<Name>.wav` | `/Game/Audio/Music/SW_<Name>` |

The stored WAV is written under the project root (`CLAUDE_PROJECT_DIR`, else the working directory).
Commit it like other source art. Git LFS tracks `.wav` once onboarding has run.

## Formats

- **WAV** is copied byte for byte. `converted` is `false`.
- **MP3, OGG (Vorbis), and FLAC** are decoded in process with `miniaudio` and written as 16-bit PCM
  WAV. The sample rate and channel count stay the same as the source. `converted` is `true`.
- Any other extension is rejected with `audio.unsupported_format`. No ffmpeg or other system tool is
  needed.

## Result

`import_audio` returns this JSON. The CLI prints the same object.

| Field | Meaning |
|-------|---------|
| `kind`, `name` | The request, as given |
| `source_art` | Absolute path of the stored WAV |
| `unreal_asset` | The SoundWave path, for example `/Game/Audio/SFX/SW_DoorCreak` |
| `converted` | `true` when the input was decoded and written as a new WAV |
| `source_format` | `wav`, `mp3`, `ogg`, or `flac` |
| `sample_rate`, `channels` | The stored WAV's rate and channel count |
| `duration_seconds` | The length of the stored audio |
| `looping` | Whether the SoundWave loops |
| `imported_to_unreal` | `true` when the SoundWave was imported |
| `warning` | Present only when the import did not reach Unreal. See below |

## When Unreal is not reachable

If the Unreal MCP endpoint does not answer, the call still succeeds. It returns
`imported_to_unreal: false`, the `source_art` path, and a `warning`:

```json
"warning": {
  "code": "mcp.unreal.unreachable",
  "message": "Unreal MCP is unreachable at http://127.0.0.1:8000/mcp: ...",
  "remediation": "Run scripts/start-unreal-mcp.sh, wait for the UE 5.8 editor to finish loading, ..."
}
```

The stored WAV stays under `SourceArt/Audio/`. Import is not retried automatically. Once the editor is
up, a second `import_audio` call with the same name stops at `audio.asset_exists`, because the WAV is
already there. To import it again, either use a new name or delete the stored WAV first and call
`import_audio` again.

## Error codes

| Code | Meaning | Remediation |
|------|---------|-------------|
| `audio.invalid_request` | The name is not PascalCase or starts with `SFX_` or `MUS_`, the kind is not `sfx` or `music`, or the file does not exist | Pass a PascalCase name, a kind of `sfx` or `music`, and a file that exists |
| `audio.unsupported_format` | The extension is not `.wav`, `.mp3`, `.ogg`, or `.flac` | Save the sound in one of the four formats |
| `audio.asset_exists` | `SourceArt/Audio/<SFX\|Music>/<Name>.wav` already exists. Nothing is overwritten | Choose another name, or delete the stored WAV if you mean to replace it |
| `audio.decode_failed` | The file could not be decoded. No partial WAV is left behind | Re-export the file, check that it is not truncated, then import again |
| `audio.import_failed` | The Unreal import ran and reported an error, or did not create a SoundWave. The stored WAV is kept | Read the UE error in the message, check the editor Output Log, then import again |
| `mcp.unreal.unreachable` | Returned as the `warning` above, not as an error | Run `scripts/start-unreal-mcp.sh` and confirm `UE_MCP_PORT` |

Errors come back from the `finalize` MCP tool as `{"error": {"code", "message", "remediation",
"stage"}}`. The CLI prints `ERROR [code] message` and a `Remediation:` line to stderr, then exits 1.
Argument errors exit 2.

## Scope

- nmg-game-dev imports saved audio. It does not generate, edit, or trim it, and it does not handle
  ElevenLabs keys or call the ElevenLabs API.
- Each import makes one SoundWave. SoundCues, MetaSounds, attenuation, sound classes, and
  per-platform compression are not created.
- Overwriting an imported sound in place is not supported.
- The `miniaudio` decoder is a floor dependency (`miniaudio>=1.59`) and tracks its latest release.
