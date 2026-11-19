# Design: Trim, cut, loudness-match, and loop-crossfade sounds when import_audio imports them

**Issue**: #252
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/249-replace-unreal-engine-with-godot-4-and-convert-existing-consumer-projects/

## Overview

A new numpy module `src/nmg_game_dev/audio/finish.py` turns the stored WAV into a finished 16-bit WAV in a scratch folder. `import_audio` then hands that file to the existing `godot_import.import_wav` (copy) or `import_ogg` (ffmpeg encode). Settings live in `SourceArt/Audio/audio.json` through a new `settings.py`. A new `refinish` entry re-runs finishing from the stored WAVs. Sound effects need no ffmpeg; the music path is unchanged apart from its input.

## Architecture

```
import_audio(file, name, kind, loop, max_seconds, loudness_lufs, loop_crossfade_ms, finish)
  validate request + settings
  resolve settings  (explicit > audio.json entry > defaults)
  SourceArt target exists?  identical bytes -> replace mode ; different -> audio.asset_exists
  music: resolve ffmpeg (audio.ffmpeg_not_found before any write)
  store_wav (skipped in replace mode)
  finish_wav(stored, scratch/<Name>.wav, settings, kind, loop)   # or stored path when finish=false
  import_wav / import_ogg(..., replace=replace_mode)
  settings.save(entry)
refinish(names | all) -> same finish + import with replace=True for each audio.json entry
```

### Finishing (`src/nmg_game_dev/audio/finish.py`)

- `read_pcm(path) -> tuple[np.ndarray, int]` reads 8-, 16-, 24- or 32-bit PCM WAV with `wave` into float64 frames × channels in [−1, 1]. `write_pcm(path, samples, rate)` writes 16-bit PCM with `np.rint` and clipping, through `convert._write_atomic`.
- `integrated_loudness(samples, rate) -> float` implements ITU-R BS.1770-4. It applies the K-weighting pre-filter and RLB high-pass biquads with coefficients derived for `rate` (via `scipy`-free direct biquad recurrence on numpy arrays), then 400 ms blocks with 75 % overlap, the −70 LUFS absolute gate, and the −10 LU relative gate, with channel weights of 1.0. A sound shorter than 400 ms is measured as one block. An all-gated sound returns `-inf`.
- `finish(samples, rate, settings, loop) -> tuple[np.ndarray, dict]` runs these steps in order:
  1. **Trim.** Drop the frames before the first frame where any channel's |x| > 10^(−50/20). If no frame is above the threshold, nothing is trimmed and loudness is skipped (`silent: true`).
  2. **Cut.** When `max_seconds` is set and the sound is longer, keep `round(max_seconds × rate)` frames. When `loop` is false, apply a linear fade to zero over the last `FADE_OUT_MS = 20` ms.
  3. **Loop crossfade.** When `loop` is true, set `n = min(round(loop_crossfade_ms × rate / 1000), len // 4)`. `head = x[:n]`, `tail = x[-n:]`, and `w = linspace(0, 1, n)`. The output is `concat(tail × (1 − w) + head × w, x[n:-n])`. Its last frame was originally adjacent to the original frame `len − n`, which is the output's first frame (w = 0), so the seam step equals an existing adjacent step.
  4. **Loudness.** `gain_db = target − integrated_loudness`. When `peak × 10^(gain_db/20) > 10^(−1/20)`, lower the gain to hit a −1 dBFS peak and set `loudness_capped`. Multiply by the linear gain. Gain is a single scale factor, so it keeps the AC4 step relation.
  - The returned report is `{applied: true, trimmed_ms, cut, loop_crossfade_ms (applied n in ms), loudness_lufs (measured after gain), target_lufs, loudness_capped, silent, duration_seconds}`.
- `finish_wav(src, dest, settings, loop) -> dict` reads, finishes, writes 16-bit PCM, and returns the report. Byte-for-byte determinism comes from fixed float64 numpy operations and the stdlib `wave` writer.

### Settings (`src/nmg_game_dev/audio/settings.py`)

- `DEFAULT_LUFS = {"sfx": -16.0, "music": -18.0}`, `DEFAULT_LOOP_CROSSFADE_MS = 500`.
- `FinishSettings(finish: bool = True, max_seconds: float | None = None, loudness_lufs: float, loop_crossfade_ms: int = 500)`.
- `validate()` raises `audio.invalid_request` when `max_seconds <= 0`, `loudness_lufs` is outside [−40, −5], or `loop_crossfade_ms < 0`.
- `SourceArt/Audio/audio.json` has this shape:
  ```json
  {"version": 1, "sounds": {"DoorCreak": {"kind": "sfx", "loop": false, "finish": true, "max_seconds": null, "loudness_lufs": -16.0, "loop_crossfade_ms": 500}}}
  ```
  It is written with `indent=2, sort_keys=True` and a trailing newline, through `_write_atomic`. An unreadable or invalid file raises `audio.settings_invalid`.
- `resolve(root, name, kind, overrides) -> FinishSettings` resolves each field as the explicit value, else the stored entry's value, else the default for the kind. `save(root, name, kind, loop, settings)` upserts the entry.

### import_audio (`src/nmg_game_dev/audio/core.py`)

- The signature gains keyword parameters `max_seconds: float | None = None`, `loudness_lufs: float | None = None`, `loop_crossfade_ms: int | None = None`, and `finish: bool | None = None`.
- When the SourceArt target exists and `filecmp.cmp(file, target, shallow=False)` is false for a `.wav` input, it raises `audio.asset_exists` as before. A compressed input is compared after decoding to a scratch WAV. When the files are identical, it enters replace mode: `store_wav` is skipped, and `check_target` / `import_wav` / `import_ogg` get `replace=True`.
- ffmpeg is resolved only for music, before any write (unchanged). SFX no longer resolves ffmpeg.
- With `finish` true, it finishes into a `tempfile.TemporaryDirectory` and imports the finished file. With `finish` false, it imports the stored WAV as #249 does.
- After a successful import it calls `settings.save`. The result gains `finish` (the report, or `{"applied": false}`) and `settings` (the resolved values).

### godot_import (`src/nmg_game_dev/audio/godot_import.py`)

`check_target`, `import_wav`, and `import_ogg` gain `replace: bool = False`. With `replace=True`, an existing game copy and `.import` file do not raise `audio.asset_exists`. `_install` writes the new copy through its `.tmp` sibling and `os.replace`, and rewrites the `.import` file. The callers in `/convert-to-godot` keep the default.

### refinish (`src/nmg_game_dev/audio/core.py`, `__main__.py`)

`refinish(names: Sequence[str] | None, *, project_root=None, godot=None, ffmpeg=None) -> list[dict]` re-finishes each named entry of `audio.json`, or every entry when `names` is `None`, in sorted name order. For each entry it reads `SourceArt/Audio/<Kind>/<Name>.wav` with the stored settings and imports it with `replace=True`. An unknown name, or a missing stored WAV, raises `audio.unknown_sound`.

The CLI is `python -m nmg_game_dev.audio refinish (--all | <Name> ...) [--project PATH]` and prints the JSON list.

### Interfaces (CLI and MCP)

- `python -m nmg_game_dev.audio import … [--max-seconds S] [--loudness-lufs L] [--loop-crossfade-ms MS] [--no-finish]`.
- The finalize `import_audio` tool (`mcp_tools.py`, `server.py`) gains `max_seconds: float | None`, `loudness_lufs: float | None`, `loop_crossfade_ms: int | None`, and `finish: bool | None`. `tools.json` adds them as optional, with `max_seconds` exclusive minimum 0, `loudness_lufs` between −40 and −5, and `loop_crossfade_ms` minimum 0.

## API / Interface Changes

| Interface | Input | Output / Error | Behavior |
|-----------|-------|----------------|----------|
| `import_audio(...)` | new `max_seconds`, `loudness_lufs`, `loop_crossfade_ms`, `finish` | result adds `finish`, `settings`; `audio.invalid_request`, `audio.asset_exists`, `audio.ffmpeg_not_found` (music) | finishes the game copy, stores settings, re-finishes on identical re-import |
| `python -m nmg_game_dev.audio import` | `--max-seconds`, `--loudness-lufs`, `--loop-crossfade-ms`, `--no-finish` | same JSON | CLI over `import_audio` |
| `python -m nmg_game_dev.audio refinish` | `--all` or names | JSON list; `audio.unknown_sound`, `audio.settings_invalid` | re-finish from SourceArt with stored settings |
| finalize MCP `import_audio` | new optional fields | same result | same implementation |
| `SourceArt/Audio/audio.json` | — | per-sound settings | read on import and refinish |

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| numpy finishing in Python | Selected | Deterministic, needs no ffmpeg for SFX, and every AC is measurable in `repository.tests` on a host without ffmpeg |
| ffmpeg `silenceremove` / `atrim` / two-pass `loudnorm` | Rejected | Tests fake ffmpeg and the host has none, so loudness and trim could not be verified |
| Measuring music loudness on the Ogg copy | Rejected | Lossy encoding changes samples; the finished WAV is the defined measurement point |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #252 | 2026-11-18 | Initial feature design |
