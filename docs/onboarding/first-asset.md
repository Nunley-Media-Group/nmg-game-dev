# Your first asset

This guide takes one prop from a prompt to an imported Godot asset with Desktop and Mobile variants.
Onboard the project first (see [index.md](index.md)).

## 1. Prompt for the asset

Describe what you want in conversation. Name the category and the asset, for example "a wooden
crate, Props, Crate." The agent drives the Blender MCP to model it in a collection named after the
asset. Model the asset freeform. The framework has no per-asset recipes. Keep each asset in its own
collection and export it on its own. Compose levels later, in Godot.

## 2. Review loop

The agent renders the collection so you can review it. Give feedback in plain terms: "the lid is too
thick," "the metal needs more wear." The agent changes the model and renders again until you are
happy. Textures come from one of two sources:

- **Local AI textures.** Generate seamless albedo with the two local models through the `texture-gen`
  MCP tools or `python -m nmg_game_dev.texture generate`. See [texture-models.md](texture-models.md).
- **Procedural Blender materials.** Build the material from nodes in Blender. Use this when a model
  is not a fit or the host is not Apple Silicon.

## 3. What the contract enforces

Finalize checks every asset against `docs/asset-contract.md` before it bakes or imports anything.
The contract covers the scene layout, units, orientation and pivot, geometry, UVs and materials,
variants, budgets, and export. A failing check reports the rule and a remediation. Fix the asset and
finalize again.

## 4. Budgets and overrides

Mobile variants must fit the mobile budget in the contract. If a specific asset legitimately needs
more, record the override in the project-root `nmg-budgets.json`. Onboarding never reads or changes
that file. Keep the reason next to the override so the next reviewer can judge it.

## Optional: Meshy generation or retexture

With a Meshy key in the project's `.env`, the `meshy` MCP can generate a model from a prompt, from
one to four reference images, or both, and retexture an authored mesh. Results land in the session
as the same `<Name>` collection this guide builds. Set `pose` only for characters with limbs. See
[docs/mcp/meshy.md](../mcp/meshy.md).

## Optional: generated audio

Sound effects and music are optional and come from the official ElevenLabs MCP server, which you run
with your own key. Onboarding asks for no key. Save the generated file, then call `import_audio` to
store it under `SourceArt/Audio/` and import it into Godot: a sound effect as an `AudioStreamWAV`,
a music track as an `AudioStreamOggVorbis` encoded with ffmpeg. See
[docs/mcp/elevenlabs.md](../mcp/elevenlabs.md).

## 5. Import

Finalize exports both variants as `.glb` into `game/assets/<Category>/<Name>/{Desktop,Mobile}/`,
each with its textures and `nmg-asset.json`, then runs a headless Godot import and checks the
imported meshes against the export. Godot generates the LODs at import. Gameplay code loads the asset
through `NmgAssets.resolve_variant_path(path)`, which picks the Mobile variant on mobile and web and
the Desktop variant elsewhere, never a hard path to either variant. Open `game/` in the Godot editor
and place the asset to check it. Commit the `game/assets/` folder as you would any other change.
