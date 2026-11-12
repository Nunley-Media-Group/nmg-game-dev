# Root Cause Analysis: gate-ue-compile builds through UBA, so parallel worktrees corrupt each other's objects

**Issue**: #202
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/123-register-the-project-verification-gates-and-a-ue-compile-extension-in-steering/

## Root Cause

`compile()` in `steering/extensions/ue-compile.mjs` builds its argument list as `[target, "Mac", "Development", "-Project=<abs>", "-WaitMutex"]`. Nothing turns off UBA, so UE 5.8's UnrealBuildTool runs the build through the Unreal Build Accelerator by default. UBA keeps one session and file cache per user, not per checkout. When two worktrees run the gate at once, both builds share that cache, and one build's VibeUE object outputs are overwritten or truncated while the other is linking. `-WaitMutex` serializes UBT only within one engine invocation's mutex scope and does not isolate the UBA cache. Building with `-NoUBA` makes UBT compile locally into each checkout's own `Intermediate/`.

## Affected Code

| File | Symbol / Area | Role |
|------|---------------|------|
| `steering/extensions/ue-compile.mjs` | `compile()` — the `args` array passed to `run(buildSh, args, …)` | Builds the `Build.sh` command line without `-NoUBA` |
| `steering/snippets/project-tech.md` | Verification Gates table, `gate-ue-compile` row | Documents the gate command |

## Fix Strategy

Append `-NoUBA` to the provider's `Build.sh` arguments, so they become `[target, "Mac", "Development", "-Project=<abs>", "-WaitMutex", "-NoUBA"]`. Put a comment above the array explaining that UBA's per-user shared session and cache let concurrent builds from parallel worktrees corrupt each other's object files. Because the evidence `summary` already prints `${buildSh} ${args.join(" ")}`, the recorded command shows the flag with no further change. Update the tech snippet's `gate-ue-compile` row to show the flag and give the reason.

## Changes

| File | Change | Behavioral reason |
|------|--------|-------------------|
| `steering/extensions/ue-compile.mjs` | Add `"-NoUBA"` after `"-WaitMutex"` in `args`, with an explanatory comment | AC1, FR1 |
| `steering/snippets/project-tech.md` | `gate-ue-compile` "Runs" cell becomes: extension `project.ue-compile`: the engine `Build.sh DogfoodEditor Mac Development -WaitMutex -NoUBA` for `fixtures/dogfood.uproject`, which compiles the UE plugin and its automation specs. `-NoUBA` turns off the Unreal Build Accelerator, whose per-user shared cache lets concurrent builds from parallel worktrees corrupt each other's object files | AC2, FR2 |
| `tests/unit/test_ue_compile_gate.py` | New: runs the real provider through `node` against a fake `Build.sh`, and reads the tech snippet row | AC1, AC2, FR3 |

## Blast Radius

Only `gate-ue-compile` runs this provider. Its pass, fail, and incomplete rules, the provider id, the extension id, and its manifest registration don't change. Builds lose UBA's distributed and cache acceleration and compile locally, so cold builds may take longer. The module still imports only Node built-ins.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Pass `-NoUBA` to `Build.sh` | Selected | The issue's local build with `-NoUBA` compiled each checkout on its own. It is a one-argument change |
| Point each worktree at its own UBA root through environment or BuildConfiguration.xml | Rejected | Needs per-host configuration outside the provider, and isolation of the UBA session is not proven |
| Serialize all gate runs with a cross-worktree lock | Rejected | Removes parallel verification across worktrees, and keeps UBA's shared cache as a hazard for other builds |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #202 | 2026-11-11 | Initial defect design |
