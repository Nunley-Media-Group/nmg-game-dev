# Defect Report: gate-ue-compile builds through UBA, so parallel worktrees corrupt each other's objects

**Issue**: #202
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/123-register-the-project-verification-gates-and-a-ue-compile-extension-in-steering/

## Reproduction

1. Check out this repository in two git worktrees, each with VibeUE installed in its own `fixtures/Plugins/`.
2. Run the registered validation `gate-ue-compile` (provider `project.ue-compile`) in both worktrees at the same time.
3. The provider runs `Build.sh DogfoodEditor Mac Development -Project=<worktree>/fixtures/dogfood.uproject -WaitMutex` in each. UE 5.8 builds through the Unreal Build Accelerator (UBA), which keeps one shared session and file cache per user.

## Expected vs Actual

| | Description |
|---|-------------|
| **Expected** | Each worktree's build compiles and links its own objects, whatever else is building at the same time. |
| **Actual** | The concurrent builds cross their output paths in the shared UBA cache. One build fails at link time with missing or truncated VibeUE `.o` files. |

## Acceptance Criteria

### AC1: The gate builds without UBA

**Given** the `project.ue-compile` provider
**When** it runs the engine build
**Then** the `Build.sh` arguments include `-NoUBA`, alongside the existing target, platform, configuration, `-Project=` and `-WaitMutex` arguments

### AC2: The documented gate command matches

**Given** `steering/snippets/project-tech.md`
**When** a contributor reads the `gate-ue-compile` row
**Then** it shows the build command with `-NoUBA` and says why

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | `steering/extensions/ue-compile.mjs` passes `-NoUBA` to `Build.sh`, with a comment explaining the shared UBA cache | Must |
| FR2 | `steering/snippets/project-tech.md` documents the flag in the `gate-ue-compile` row | Must |
| FR3 | A unit test asserts the provider's `Build.sh` arguments include `-NoUBA` (using a fake `Build.sh`) | Must |

## Out of Scope

- The UBT invocation in `scripts/run-ue-tests.sh`, which is not a registered gate.
- Changing which paths make `gate-ue-compile` apply, or its target, platform, configuration, or project.
- Running the real engine build or any Unreal Editor in tests.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #202 | 2026-11-11 | Initial defect report |
