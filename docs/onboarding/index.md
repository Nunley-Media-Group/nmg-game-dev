# Onboarding: start and ship your first game

This is the path from an empty consumer project to a shipped build. Run the onboarding skill
first, then follow the guides in order.

## The flow

1. **Onboard the project.** Run `/onboard-consumer` in the game's project. It installs the Blender
   start script and its SessionStart hook, the asset contract and the design contract, the Godot
   project in `game/` (`game/project.godot` with the Compatibility renderer for mobile and web, the
   `nmg_game_dev` add-on in `game/addons/nmg_game_dev/`, and `game/export_presets.cfg` with one
   preset per ship target), the Blender add-on link, the two local texture models, `.gitignore`
   entries for `.env` and `game/.godot/`, and Git LFS tracking for binary assets (install Git LFS
   first; see below). It also creates `docs/design/` for your design docs, and reports whether Godot
   4 (`GODOT_BIN`, then `godot` on PATH) and ffmpeg (`FFMPEG_BIN`, then PATH) were found. The `CLAUDE.md` block it writes routes Blender asset authoring and editing to `/model-asset`;
   scene inspection and `/finalize-asset` runs are exempt (see [model-asset.md](../skills/model-asset.md)).
   See `skills/onboard-consumer/SKILL.md`.
2. **Make your first asset.** [first-asset.md](first-asset.md) covers prompting for an asset, the
   review loop, the contract checks, texture sources, budget overrides, and import into Godot.
3. **Ship it.** [first-ship.md](first-ship.md) walks through the `ship` skill on a fixture project.
4. **Run and capture it.** [run-and-capture.md](run-and-capture.md) covers the launch options that
   read the same on desktop and web, the headless smoke run that `/ship` gates on, and screenshots
   of the running game.
5. **Keep up to date.** [upgrading.md](upgrading.md) covers reviewing breaking changes, re-registering
   the plugin, and re-running onboarding with `--refresh`.

## Converting an existing project

A project that was set up for the previous engine target converts to Godot with one command,
`/convert-to-godot`. It onboards the Godot project, re-finalizes every asset from its Blender
source, imports the audio, re-scaffolds the design backlog, and removes the old engine files only
after every item converts. See [docs/skills/convert-to-godot.md](../skills/convert-to-godot.md).

## Local texture models

Generating seamless textures locally needs the two models that onboarding installs. Read
[texture-models.md](texture-models.md) for the hardware requirements, where the weights live, how to
generate with the CLI or the `texture-gen` MCP tools, and what the output folder holds.

## Git LFS for binary assets

The pipeline writes large binaries into your repository: Blender sources, the finalized `.glb`
variants, Meshy GLBs, generated textures, and audio. Onboarding tracks them in Git LFS, so git
history stores small pointers instead of full copies. The tracked types are `.blend`, `.glb`,
`.fbx`, `.obj`, `.abc`, `.usd`, `.usdz`, the common image formats (`.png`,
`.jpg`, `.jpeg`, `.tga`, `.tif`, `.tiff`, `.exr`, `.hdr`, `.psd`), `.wav`, `.mp3`, `.ogg`, and `.mp4`.

Install Git LFS before you onboard (`brew install git-lfs`). Onboarding stops with
`onboard.git_lfs_missing` until `git-lfs` is on your PATH. It then writes the tracking rules into a
marked block in `.gitattributes`, leaves every other line of that file as it was, and runs
`git lfs install --local` in your repository. A re-run changes nothing unless you pass `--refresh`.

Files committed before this setup are still full blobs in your history. To convert the ones in the
index, review the change, then run this from the project root and commit the result on its own:

```
git add --renormalize .
git commit -m "Store binary assets in Git LFS"
```

Onboarding never runs `git add --renormalize .` or `git lfs migrate`. `git lfs migrate` rewrites
commit history, so run it only as a deliberate decision with the rest of your team.

## Secret scan

Keep every API key in the git-ignored `.env` at the consumer root. The secret scan stops a key that
has been pasted anywhere else from reaching a commit or a build. It recognizes these shapes:

| Pattern name | Matches |
|---|---|
| `meshy` | A Meshy key, `msy_` followed by its characters |
| `elevenlabs` | An ElevenLabs key, `sk_` followed by 48 hex characters |
| `anthropic` | An Anthropic key, `sk-ant-…` |
| `openai` | An OpenAI key, `sk-…`, including `sk-proj-…` |
| `github` | A GitHub token, `ghp_…` or `github_pat_…` |
| `aws` | An AWS access key ID, `AKIA…` |
| `private-key` | A PEM private-key header |
| `env-file` | A staged or tracked file named exactly `.env` (reported on line 0) |

**The hook.** Onboarding copies the scanner to `scripts/nmg_secret_scan.py` and writes
`.git/hooks/pre-commit`, which runs the scanner with `--staged`. It reads the content you are about
to commit (the index), not the working tree, so an unstaged edit does not block anything. A commit
that stages a match exits 1 and prints one line per match:

```
scripts/setup.gd:3: meshy msy_… (sha256:<hex>)
```

Each line gives the file, the line number, the pattern name, the first four characters of the value
followed by `…`, and the SHA-256 fingerprint. The full value is never printed. Run the scan by hand
with `python3 scripts/nmg_secret_scan.py --staged`, or `--tracked` for every tracked file.

**The allow file.** A false positive, such as a documented example key, can be allowed in
`.nmg/secret-scan-allow`. Each line is one of two forms; blank lines and `#` comments are ignored:

- `sha256:<hex>` allows the one match whose value has that fingerprint.
- `<path>:<pattern>` allows that pattern in that file, for example `docs/setup.md:openai`.

Allow only matches you have reviewed. Both forms also apply to `/ship`.

**A foreign hook.** Onboarding never overwrites a `pre-commit` hook you already have. It reports the
`precommit_hook` step as `conflict` with `onboard.precommit_hook_conflict`, leaves the file
byte-identical, and names the line to add to it:

```sh
python3 "$(git rev-parse --show-toplevel)/scripts/nmg_secret_scan.py" --staged || exit 1
```

Add that line to your hook, then re-run onboarding. A repository with no git work tree gets no hook
and reports the step as `skipped`.

**The build.** `/ship` runs the scan as its first gate, also in a dry run. In a git work tree it
scans the tracked files plus the untracked files under `game/` that `.gitignore` does not cover,
because Godot exports those files whether or not git tracks them. Files that `.gitignore` covers,
files outside `game/`, and the `game/.godot/` editor cache are not scanned, so a local, ignored key
does not block the build. A match stops the ship with `ship.secret_found`, listing each masked match,
before any Godot command runs. Outside a git work tree the gate scans every regular file under the
consumer root instead, except where keys are meant to live and folders that are never committed:
`.env` and `.env.*` files, `.claude/settings.local.json`, and the `.git/`, `release/`,
`game/.godot/`, `.venv/`, and `node_modules/` folders. A key pasted anywhere else stops the ship in
that layout too. If git itself fails while listing the files, the ship stops with
`ship.secret_scan_failed`.

## Optional: Meshy generation

Meshy is an opt-in, paid source of models and retextures. Onboarding asks for no key. To use it,
add `MESHY_API_KEY=<key>` to the project's `.env`. Onboarding adds `.env` to your `.gitignore`
(step `gitignore_env`), so the key stays out of git. See [docs/mcp/meshy.md](../mcp/meshy.md).

## Optional: generated audio

Sound effects and music are optional. The official ElevenLabs MCP server generates them, and you run
it yourself with your own key. Onboarding asks for no key and installs no ElevenLabs server. To bring
a saved file into Godot, call `import_audio`. Music is encoded to Ogg Vorbis with ffmpeg, so
install ffmpeg (or set `FFMPEG_BIN`) before you import music. See [docs/mcp/elevenlabs.md](../mcp/elevenlabs.md).

## Reference

- Asset contract: `docs/asset-contract.md` (installed into your project at
  `docs/nmg-game-dev/asset-contract.md`).
- Design contract: `docs/design-contract.md` (installed into your project at
  `docs/nmg-game-dev/design-contract.md`). Write the design as one markdown file per entity under
  `docs/design/`, then run the `design` skill. See [docs/skills/design.md](../skills/design.md).
- Onboarding skill and install rules: `skills/onboard-consumer/SKILL.md` and
  `skills/onboard-consumer/references/install-steps.md`.
