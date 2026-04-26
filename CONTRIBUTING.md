# Contributing

## Project Context

nmg-game-dev is a Blender-first content-generation framework for Unreal Engine games. It ships as a Codex plugin, Blender add-on, and Unreal Engine plugin, with consumer-side onboarding handled by framework skills and templates.

Before changing behavior, read:

- `steering/product.md` for the product mission, target users, value proposition, and success metrics.
- `steering/tech.md` for architecture, supported tool versions, versioning, coding standards, and verification gates.
- `steering/structure.md` for repository layout, layer boundaries, naming conventions, and file ownership.

Existing code and reconciled specs are contribution context. Treat `specs/` as the history of accepted product and technical decisions, not just planning notes.

## Issue and Spec Workflow

Start work from a clear GitHub issue with acceptance criteria. Feature and bug implementation should flow through nmg-sdlc specs in `specs/`, using the normal issue -> spec -> code -> simplify -> verify -> PR path.

Use `$nmg-sdlc:draft-issue` for new work, `$nmg-sdlc:start-issue` to pick up an issue, `$nmg-sdlc:write-spec` to create or amend specs, `$nmg-sdlc:write-code` to implement, `$nmg-sdlc:simplify` to clean up, `$nmg-sdlc:verify-code` to validate, and `$nmg-sdlc:open-pr` to deliver the branch.

## Steering Expectations

Align changes with the steering docs before editing code or specs:

- Product work should preserve the Blender-first authoring model, variant-aware asset flow, consumer onboarding path, and automated quality gates.
- Technical work should keep the Codex plugin, Blender add-on, Unreal plugin, MCP launchers, and version-managed artifacts in sync.
- Structural changes should respect the repo layout and the boundary between framework-owned artifacts and consumer-project templates.

If a change intentionally moves away from steering, update the relevant steering doc in the same branch and call out the decision in the spec or PR.

## Implementation and Verification

Keep edits scoped to the issue and spec. Update code, specs, tests, version-managed metadata, and docs together when the contract requires it.

Use the project gates described in `steering/tech.md`, including Python checks, BDD scenarios, Blender or Unreal automation where relevant, and version consistency across `VERSION`, `.codex-plugin/plugin.json`, Blender metadata, Unreal metadata, and `pyproject.toml`.

Consumer-facing behavior should include onboarding or template updates when needed, especially for `.codex` consumer artifacts installed by future onboarding skills.
