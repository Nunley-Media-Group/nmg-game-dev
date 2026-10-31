# Onboarding: start and ship your first game

This is the path from an empty consumer project to a shipped build. Run the onboarding skill
first, then follow the guides in order.

## The flow

1. **Onboard the project.** Run `/onboard-consumer` in the game's project. It installs the start
   scripts and SessionStart hooks, the asset contract, the Unreal and Blender plugins, and the two
   local texture models. See `skills/onboard-consumer/SKILL.md`.
2. **Make your first asset.** [first-asset.md](first-asset.md) covers prompting for an asset, the
   review loop, the contract checks, texture sources, budget overrides, and import into Unreal.
3. **Ship it.** [first-ship.md](first-ship.md) walks through the `ship` skill on a fixture project.
4. **Keep up to date.** [upgrading.md](upgrading.md) covers reviewing breaking changes, re-registering
   the plugin, and re-running onboarding with `--refresh`.

## Local texture models

Generating seamless textures locally needs the two models that onboarding installs. Read
[texture-models.md](texture-models.md) for the hardware requirements, where the weights live, how to
generate with the CLI or the `texture-gen` MCP tools, and what the output folder holds.

## Reference

- Asset contract: `docs/asset-contract.md` (installed into your project at
  `docs/nmg-game-dev/asset-contract.md`).
- Onboarding skill and install rules: `skills/onboard-consumer/SKILL.md` and
  `skills/onboard-consumer/references/install-steps.md`.
