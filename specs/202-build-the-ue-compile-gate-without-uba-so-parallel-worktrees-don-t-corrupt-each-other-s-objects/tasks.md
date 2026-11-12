# Tasks: gate-ue-compile builds through UBA, so parallel worktrees corrupt each other's objects

**Issue**: #202
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/123-register-the-project-verification-gates-and-a-ue-compile-extension-in-steering/

## Implementation Tasks

### T001: Build the gate without UBA

**File(s)**: `steering/extensions/ue-compile.mjs`
**Type**: Modify
**Depends**: none
**Acceptance**:
- `compile()` passes `Build.sh` the arguments `[target, "Mac", "Development", "-Project=<abs project>", "-WaitMutex", "-NoUBA"]` (AC1, FR1).
- A comment next to the argument list explains that UBA keeps one shared session and file cache per user, so concurrent builds from parallel worktrees corrupt each other's object files (FR1).
- The `command` evidence summary records the full command, including `-NoUBA`. The provider id `project.ue-compile`, the frozen `extension` export, and the passed/failed/incomplete rules don't change, and the module still imports only Node built-ins.

### T002: Document the flag in the gate row

**File(s)**: `steering/snippets/project-tech.md`
**Type**: Modify
**Depends**: none
**Acceptance**:
- The `gate-ue-compile` row of the Verification Gates table shows the build command `Build.sh DogfoodEditor Mac Development -WaitMutex -NoUBA` (AC2, FR2).
- The same row says that `-NoUBA` turns off the Unreal Build Accelerator, whose per-user shared cache lets concurrent builds from parallel worktrees corrupt each other's object files (AC2, FR2).
- The row's "Applies when" paths and host prerequisites don't change.

### T003: Cover the build arguments and the documented row

**File(s)**: `tests/unit/test_ue_compile_gate.py`
**Type**: Create
**Depends**: T001, T002
**Acceptance**:
- AC1, FR3: a test writes a fake executable `Engine/Build/BatchFiles/Mac/Build.sh` under a temporary `UE_ROOT`. The fake writes each argument it receives on its own line to a log file named by an environment variable, prints `Result: Succeeded`, and exits 0. The test also writes a placeholder `.uproject` under `tmp_path`. It runs the real provider from `steering/extensions/ue-compile.mjs` through `node` with `projectRoot` set to `tmp_path` and `config` naming that project and target `DogfoodEditor`. It asserts the logged arguments equal `["DogfoodEditor", "Mac", "Development", "-Project=<abs placeholder project>", "-WaitMutex", "-NoUBA"]`, the result status is `passed`, and the `command` evidence summary contains `-NoUBA`.
- The provider test is skipped when `sys.platform != "darwin"`, because the provider returns `incomplete` off macOS. It starts no real `Build.sh`, Unreal Editor, or Blender process.
- AC2: a test reads `steering/snippets/project-tech.md`, finds the table row that starts with ``| `gate-ue-compile` |``, and asserts it contains `-NoUBA` and `Unreal Build Accelerator`.
- The test fails without T001 and T002 and passes with them. It passes under `repository.tests` (`uv run pytest tests/unit tests/bdd -q`) and passes `repository.lint`, `repository.format`, and `repository.types`.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #202 | 2026-11-11 | Initial defect tasks |
