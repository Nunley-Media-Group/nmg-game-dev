# Local texture models

nmg-game-dev generates seamless albedo textures on your Mac with two pinned models, then derives the
normal, roughness, metallic, and optional AO maps. Nothing leaves the machine.

## Hardware requirements

- Apple Silicon Mac (arm64 macOS). Other hosts are refused with `texture.unsupported_platform`.
- Enough RAM for each model, after the Blender reserve. Peak memory is 14.6 GB for Z-Image Turbo and
  12.9 GB for FLUX.2 klein 4B. The reserve is 8 GB by default (`TEXTURE_GEN_BLENDER_RESERVE_GB`). A
  32 GB Mac runs both. A 16 GB Mac is refused with `texture.insufficient_memory`.
- About 60 GiB free on the volume that holds the weights.

The two models are `z-image-turbo` (Tongyi-MAI/Z-Image-Turbo) and `flux2-klein-4b`
(black-forest-labs/FLUX.2-klein-4B). Both are saved with 4-bit quantization. Only these two load.

## Where the weights live

- `TEXTURE_GEN_MODELS_DIR` points at the models folder. Onboarding writes it to
  `.claude/settings.local.json`. The folders are `<dir>/z-image-turbo-q4` and `<dir>/flux2-klein-4b-q4`.
- `HF_HOME` points at `<dir>/hf-cache`, the Hugging Face cache used to save the weights.

## Install through onboarding

Run `/onboard-consumer`. The skill lists the volumes that have 60 GiB free and asks which one holds the
models. It saves them into `<volume>/nmg-texture-models`. Each model takes a while to download and save.
Re-running onboarding skips models that are already present.

To check what is installed, run `python -m nmg_game_dev.texture status`. It prints `available`,
`not_installed`, `unsupported_platform`, or `insufficient_memory` for each backend.

## Generate

From the CLI, the command waits and prints a JSON result:

```sh
python -m nmg_game_dev.texture generate --prompt "burlap weave" --backend flux2-klein-4b --resolution 1024 --name burlap --maps fabric --ao
```

Options:

- `--backend`: `z-image-turbo`, `flux2-klein-4b`, or `both` (default `flux2-klein-4b`).
- `--seed` (repeatable): one image per seed. Default: one random seed.
- `--resolution`: a power of two from 256 to 2048 (default 1024).
- `--maps`: a material preset (`fabric`, `wood`, `stone`, `plastic`, `metal`), or explicit values with
  `--roughness` and `--metallic`.
- `--ao`: also derive the AO map (needs `--maps`).
- `--style-suffix`: the text added to every prompt.

From the agent, use the `texture-gen` MCP tools. `generate_textures` returns a job id at once.
`get_texture_job(job_id)` reports `queued`, `running` with completed and total, `succeeded` with the
PNG paths, derived-map paths, and per-image timings, or `failed` with a code, message, and remediation.
Generation can take minutes, so poll the job rather than waiting on the call.

Only one texture job runs at a time. Starting a second while one is running returns
`texture.job_running`, and the message names the running job.

## Both: comparison sheets

With `--backend both`, each available model runs in turn, never at the same time. A model that is not
available is listed under `skipped` with its reason. When both models produce images, a side-by-side
comparison sheet `<name>_compare.png` labels each image with its backend, seed, and seconds.

## Output folder

Images go to `<project>/SourceArt/Textures/Generated/<name>/`. The project is `CLAUDE_PROJECT_DIR`, or
the working directory when that is unset. Set `NMG_GAME_DEV_TEXTURE_DIR` to use another root. The
folder holds:

- `<backend>_<seed>_<resolution>.png`: the seamless albedo.
- `<backend>_<seed>_<resolution>_{N,R,M,AO}.png`: derived maps, when requested.
- `<name>_compare.png`: the comparison sheet, for `both`.
- `textures.json`: the prompt, style suffix, backend, repo, revision, seed, steps, timing, and paths
  for each image.

The output lives under `SourceArt/`, not `Content/`. Unreal does not auto-import it. Import the textures
you keep through the asset pipeline.

## Derived maps

- `_N`: an OpenGL normal map, from the luminance of the albedo as height.
- `_R` and `_M`: constant roughness and metallic from the preset or your explicit values.
- `_AO`: ambient occlusion from the height, when `--ao` is set.

Every map is the albedo's resolution and wraps seamlessly.
