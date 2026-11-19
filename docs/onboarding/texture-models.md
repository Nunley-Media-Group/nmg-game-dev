# Local texture models

nmg-game-dev generates seamless albedo textures on your Mac with two pinned models, then derives the
normal, roughness, metallic, and optional AO maps. Nothing leaves the machine.

## Hardware requirements

- Apple Silicon Mac (arm64 macOS). Other hosts are refused with `texture.unsupported_platform`.
- Enough RAM for each model, after the Blender reserve. Peak memory is 14.6 GB for Z-Image Turbo and
  12.9 GB for FLUX.2 klein 4B. The reserve is 8 GB by default (`TEXTURE_GEN_BLENDER_RESERVE_GB`). A
  32 GB Mac runs both. A 16 GB Mac is refused with `texture.insufficient_memory`.
- About 60 GiB free on the volume that holds the weights.
- The `mflux` and `mlx` Python modules, installed with the plugin root project (see Run from the plugin
  root). Without them every request is refused with `texture.dependencies_missing`.

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
`not_installed`, `unsupported_platform`, `insufficient_memory`, or `dependencies_missing` for each backend.

## Run from the plugin root

The generation dependencies, `mflux` and `mlx`, are part of the plugin root project. On an Apple Silicon
Mac, run the generate command from the plugin root so that `uv` uses that environment:

```sh
uv run --project <plugin root> python -m nmg_game_dev.texture generate --prompt "burlap weave" --name burlap
```

`<plugin root>` is the nmg-game-dev plugin directory. When `CLAUDE_PLUGIN_ROOT` is set, the error messages
use it; otherwise they use the checkout that holds the package. Either way the message prints the exact
command with the path filled in.

When a module is missing, the request fails before any worker starts or any job is queued, with
`texture.dependencies_missing`. The message names the module (`mflux` or `mlx`), and the remediation is
the plugin-root command. The `status` and `texture_backends` tools report `dependencies_missing` for each
backend that would otherwise be `available`. A worker that exits because it cannot import a module reports
`texture.worker_failed` with the module named in the remediation, not the models or the memory reserve.

## Generate

From the CLI, the command waits and prints a JSON result. Run it from the plugin root (see above):

```sh
uv run --project <plugin root> python -m nmg_game_dev.texture generate --prompt "burlap weave" --backend flux2-klein-4b --resolution 1024 --name burlap --maps fabric --ao
```

Options:

- `--backend`: `z-image-turbo`, `flux2-klein-4b`, or `both` (default `flux2-klein-4b`).
- `--seed` (repeatable): one image per seed. Default: one random seed.
- `--resolution`: a power of two from 256 to 2048 (default 1024).
- `--maps`: a material preset (`fabric`, `wood`, `stone`, `plastic`, `metal`), or explicit values with
  `--roughness` and `--metallic`.
- `--ao`: also derive the AO map (needs `--maps`).
- `--style-suffix`: the text added to every prompt.

### Batch input

`--batch FILE` generates a JSON array of requests in one run, and prints one JSON object with `results`,
one entry per request in order. Each object takes the request fields (`prompt`, `backend`, `seeds`,
`resolution`, `name`, `maps`, `ao`, `style_suffix`); absent and null fields take their defaults. The
single-request options above are not read when `--batch` is given, so put each request's settings in its
object. Each backend's model loads once for the whole batch.

```json
[
  {"prompt": "burlap weave", "name": "burlap", "maps": "fabric", "ao": true},
  {"prompt": "oak planks", "name": "oak", "backend": "z-image-turbo", "seeds": [7]}
]
```

```sh
uv run --project <plugin root> python -m nmg_game_dev.texture generate --batch textures.json
```

Batch validation runs before anything is generated or queued. If any request is invalid, the command
exits 1 with `texture.invalid_request`, and the message lists the zero-based index and reason of each
invalid request. Requests that resolve to the same output name are refused the same way: a request's
output name is its `name`, or its prompt when it has no name, slugified. Two requests with one output
name would write into one folder and overwrite each other. The message names the output name and the
zero-based indexes of the requests that share it, for example
`requests 0, 2: output name 'burlap' is used more than once`. Give each request in a batch its own name.

From the agent, use the `texture-gen` MCP tools. `generate_textures` returns a job id at once. Pass
`prompt` for one texture, or `requests` (a list of request objects with the same fields) for a batch that
runs as one job. The `requests` batch is validated as a whole, as the CLI does.
`get_texture_job(job_id)` reports `queued`, `running` with completed and total, `succeeded` with the
PNG paths, derived-map paths, and per-image timings, or `failed` with a code, message, and remediation.
For a batch, `succeeded` holds `results`, one per request in order, and `completed` and `total` count every
image in the batch. Generation can take minutes, so poll the job rather than waiting on the call.

Texture jobs run one at a time, in the order they were submitted. A job started while another is running
is queued and runs after it, so you do not need to wait before starting it. Its state is `queued` until
its turn comes. A queued job is not cancelled or reprioritized, and a job that cannot start because a
dependency is missing is refused at start with `texture.dependencies_missing`, not queued.

If a runner exits while a job is `running`, for example because its process was killed, the next runner
marks that job `failed` with `texture.runner_exited` when it starts, then runs the queued jobs after it.
Start the job again. The queue runner logs to `<output root>/.jobs/runner.log`, and each job's `job.log`
holds only that job's output.

## Both: comparison sheets

With `--backend both`, each available model runs in turn, never at the same time. A model that is not
available is listed under `skipped` with its reason. When both models produce images, a side-by-side
comparison sheet `<name>_compare.png` labels each image with its backend, seed, and seconds.

## Contact sheet

Every successful `generate` run rebuilds a contact sheet at the output root: `contact_sheet_001.png`,
`contact_sheet_002.png`, and so on. It shows every albedo of every texture set in the root, so a texture
whose look does not match its name, or that repeats or seams badly, is visible before you build on it.

- Each cell is the albedo tiled 2x2, with a label strip that names the texture set, then the backend and
  seed on the line beneath.
- Cells are ordered by set name, then backend, then seed. A page holds 24 cells in 6 columns and 4 rows.
  A larger root continues on the next numbered page. Pages left over from an earlier, larger build are
  removed.
- Derived maps (`_N`, `_R`, `_M`, `_AO`) and `<name>_compare.png` never appear as cells.

To rebuild the sheet from the current sets without generating, run:

```sh
python -m nmg_game_dev.texture sheet
python -m nmg_game_dev.texture sheet --root SourceArt/Textures/Generated
```

Without `--root` the command reads the same output folder that `generate` writes to. It prints JSON with
`pages`, `cells`, and `skipped`, and exits 0. The agent can run the same rebuild through the
`texture_contact_sheet` tool of the `texture-gen` MCP server, which returns the same JSON.

An albedo that is missing or is not a readable image, or a `textures.json` that is not valid JSON, is left
out of the pages and listed under `skipped` with its `path` and `reason`. The other albedos still appear,
and the generate run still succeeds. A root with no texture sets is an error on demand: the command prints
`ERROR [texture.no_texture_sets]` with a `Remediation:` line and exits 1, and the tool returns that error
code. The rebuild needs no texture model, so it runs even when the weights are not installed.

## Make a source texture seamless

A texture from another source (a photo, a stock image, or an earlier export) often does not tile. The
bake rejects such a texture with `not_seamless`. Make it tile with the `seamless` subcommand:

```sh
python -m nmg_game_dev.texture seamless SourceArt/Textures/Stone.png
python -m nmg_game_dev.texture seamless SourceArt/Textures/Stone.png --out SourceArt/Textures/Stone_tile.png
```

The repair depends on how badly the image fails the bake's seam check:

- An image that already passes is written unchanged.
- An image that fails narrowly (each wrap within 3 times its allowance) gets an 8 px edge blend: the
  pixels near each edge are cross-faded with their mirror pixels across the wrap.
- An image that does not tile gets the same cross-fade the generator uses, then the 8 px edge blend on
  any axis that still fails or whose wrap is now larger than the input's.

The output always passes the seam check, and its wrap is never worse than the input's on either axis.
Without `--out` it writes over the input; with
`--out` it writes a new PNG and creates its folder, and the input is left unchanged. It prints JSON with
the output `path` and `seamless`, the result of the same seam check the bake runs. A channel passes when
its wrap differs from the opposite edge by at most 1.5 times the interior adjacent-pixel difference
(minimum 2/255). A missing or unreadable input exits 1 with `texture.input_missing`.

Images packed into a `.blend` file keep their old pixels until they are reloaded or repacked from the
fixed files. After fixing the files on disk, reload each image in Blender (Image > Reload), or unpack
and repack it from the fixed file, before you rerun the bake.

## Output folder

Images go to `<project>/SourceArt/Textures/Generated/<name>/`. The project is `CLAUDE_PROJECT_DIR`, or
the working directory when that is unset. Set `NMG_GAME_DEV_TEXTURE_DIR` to use another root. The
folder holds:

- `<backend>_<seed>_<resolution>.png`: the seamless albedo.
- `<backend>_<seed>_<resolution>_{N,R,M,AO}.png`: derived maps, when requested.
- `<name>_compare.png`: the comparison sheet, for `both`.
- `textures.json`: the prompt, style suffix, backend, repo, revision, seed, steps, timing, and paths
  for each image.

The output root, `SourceArt/Textures/Generated/`, also holds the contact sheet pages,
`contact_sheet_NNN.png`, beside the set folders (see Contact sheet).

The output lives under `SourceArt/`, not `game/`. Godot does not import it. Bring the textures you
keep into a game through the asset pipeline.

## Derived maps

- `_N`: an OpenGL normal map, from the luminance of the albedo as height.
- `_R` and `_M`: constant roughness and metallic from the preset or your explicit values.
- `_AO`: ambient occlusion from the height, when `--ao` is set.

Every map is the albedo's resolution and wraps seamlessly. Before it is written, each map is checked
against the same seam rule the bake uses, and a failing `_N` or `_AO` gets the 8 px edge blend, so
every generated map passes the bake's `not_seamless` check.

## Generate 2D art

Icons, UI panels, and paintings come from the same local models, but their takes are never tiled and
no maps are derived from them. Use `art` to make the raw takes, pick one, and `art-finish` to cut it out
into a game image. The raw takes under `SourceArt/Art/raw/` are the kept source. The game images under
`game/assets/UI/` can always be rebuilt from them.

```sh
uv run --project <plugin root> python -m nmg_game_dev.texture art --kind icon --name HealthPotion --prompt "red potion bottle" --seeds 1,2,3
uv run --project <plugin root> python -m nmg_game_dev.texture art-finish --kind icon --name HealthPotion --pick 2
```

`art` options:

- `--kind`: `icon`, `ui`, or `painting` (required). `--name` is PascalCase, such as `HealthPotion`, and names
  the takes.
- `--seeds`: comma-separated seeds, such as `1,2,3`. Default: one random seed.
- `--backend`: `z-image-turbo` or `flux2-klein-4b` (default `flux2-klein-4b`). `both` is not allowed for art.
- `--aspect`: `16:9`, `3:2`, or `1:1` for a painting (default `16:9`). Icons and UI art are `1:1`.
- `--resolution`: the long side, a multiple of 64 from 256 to 2048 (default 1024).

| Kind | Framing | Aspects |
|------|---------|---------|
| `icon` | one object, centred, whole object visible, flat plain light grey background, no shadow or text | `1:1` |
| `ui` | a game interface panel or frame, centred, flat plain light grey background, no text | `1:1` |
| `painting` | a painterly illustration filling the frame, no text or border | `16:9`, `3:2`, `1:1` |

### Project style

Put one sentence in `SourceArt/Art/style.json` to give a set of art one look:

```json
{"style": "hand-painted, warm palette"}
```

Every art prompt becomes `<prompt>, <project style>, <kind framing>`. The sentence is recorded as
`project_style` in the art manifest and in `textures.json`. Texture prompts do not change. Without the
file, art prompts use only the kind framing, and `project_style` is `null`.

### Raw takes, the manifest, and the contact sheet

`art` writes into `SourceArt/Art/raw/<kind>/`:

- `<Name>-<seed>.png`: one take per seed, exactly as the model wrote it. No seamless pass runs.
- `<Name>.json`: the prompt, project style, kind framing, full prompt, backend, repo, revision, size,
  each take with its seed and seconds, and the seeds skipped in the latest run.
- `<Name>_sheet.png`: every take side by side, labelled by seed.

A seed whose take already exists is reported under `skipped` and is not regenerated. When every seed has a
take, `art` starts no worker and loads no model. To try another look, pass new seeds. To redo one, delete its
take first.

### Finish a take

`art-finish --kind <kind> --name <Name> --pick <seed>` writes the game files and prints them:

| Kind | Written to | Size |
|------|------------|------|
| `icon` | `game/assets/UI/Icons/<Name>.png` and `<Name>_small.png` | 512 px and 64 px |
| `ui` | `game/assets/UI/Panels/<Name>.png` | 1024 px |
| `painting` | `game/assets/UI/Paintings/<Name>.png` | `--width` (default 1920), aspect kept, RGB with no alpha |

For an icon or UI take, the background must be flat: the four corners must agree within a small colour
tolerance. The background, reached from the corners, becomes transparent, with a feathered 2 px edge. The
subject is cropped, scaled to an 8 % margin, and centred horizontally with its bottom on the baseline at 92 %
of the height. Running `art-finish` again gives byte-identical files. `art-finish` does not run a Godot
import; import the files as you would any other asset.

`art-finish` writes nothing when it refuses a take:

| Code | Meaning | What to do |
|------|---------|------------|
| `art.take_not_found` | No raw take for that name and seed | Generate it with `art`, or pick a seed that exists |
| `art.background_not_flat` | The corners differ in colour | Regenerate on a flat background, or pick another take |
| `art.subject_cropped` | The subject touches the edge, or there is no subject | Regenerate with room around the subject, or pick another take |
| `art.style_invalid` | `SourceArt/Art/style.json` is not `{"style": "<sentence>"}` | Fix or delete the file |
| `texture.invalid_request` | A bad kind, name, aspect, seed list, or `--width` for a non-painting | Fix the option named in the message |

### Art tools

The `texture-gen` MCP server exposes the same flow, documented in `docs/mcp/texture-gen.md`:

- `generate_art(kind, name, prompt, seeds, backend, aspect, resolution)` queues the missing takes and returns a
  `job_id`. Poll it with `get_texture_job`, the same tool that polls texture jobs.
- `finish_art(kind, name, pick, width)` finishes a take and returns the files written, or the structured error.
