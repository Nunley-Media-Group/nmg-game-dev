# Onboarding: start and ship your first game

This is the path from an empty consumer project to a shipped build. Run the onboarding skill
first, then follow the guides in order.

## The flow

1. **Onboard the project.** Run `/onboard-consumer` in the game's project. It installs the start
   scripts and SessionStart hooks, the asset contract and the design contract, the Unreal and Blender
   plugins, the two local texture models, and a `.gitignore` entry for `.env`. It also creates
   `docs/design/` for your design docs. See `skills/onboard-consumer/SKILL.md`.
2. **Make your first asset.** [first-asset.md](first-asset.md) covers prompting for an asset, the
   review loop, the contract checks, texture sources, budget overrides, and import into Unreal.
3. **Ship it.** [first-ship.md](first-ship.md) walks through the `ship` skill on a fixture project.
4. **Keep up to date.** [upgrading.md](upgrading.md) covers reviewing breaking changes, re-registering
   the plugin, and re-running onboarding with `--refresh`.

## Local texture models

Generating seamless textures locally needs the two models that onboarding installs. Read
[texture-models.md](texture-models.md) for the hardware requirements, where the weights live, how to
generate with the CLI or the `texture-gen` MCP tools, and what the output folder holds.

## Optional: Meshy generation

Meshy is an opt-in, paid source of models and retextures. Onboarding asks for no key. To use it,
add `MESHY_API_KEY=<key>` to the project's `.env`. Onboarding adds `.env` to your `.gitignore`
(step `gitignore_env`), so the key stays out of git. See [docs/mcp/meshy.md](../mcp/meshy.md).

## Reference

- Asset contract: `docs/asset-contract.md` (installed into your project at
  `docs/nmg-game-dev/asset-contract.md`).
- Design contract: `docs/design-contract.md` (installed into your project at
  `docs/nmg-game-dev/design-contract.md`). Write the design as one markdown file per entity under
  `docs/design/`, then run the `design` skill. See [docs/skills/design.md](../skills/design.md).
- Onboarding skill and install rules: `skills/onboard-consumer/SKILL.md` and
  `skills/onboard-consumer/references/install-steps.md`.
