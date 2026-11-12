# Root Cause Analysis: gate-ue-compile builds with -NoUBA instead of the default UE 5.8 toolchain

**Issue**: #227
**Date**: 2026-11-12
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/202-build-the-ue-compile-gate-without-uba-so-parallel-worktrees-don-t-corrupt-each-other-s-objects/

## Root Cause

#202 appended `"-NoUBA"` to the `args` array in `compile()` in `steering/extensions/ue-compile.mjs`, with a comment explaining it. It also rewrote the `gate-ue-compile` row in `steering/snippets/project-tech.md` to document the flag. Finally, it added `tests/unit/test_ue_compile_gate.py`, which pins the flag in both places. #204 copied the same argument list, `-NoUBA` included, into `_build_headless()` in `scripts/unreal/build_master_material.py`, and pinned it in `tests/unit/test_build_master_material.py`. Both builds therefore compile with the Unreal Build Accelerator turned off, a build configuration the default UE 5.8 toolchain does not use.

## Affected Code

| File | Symbol / Area | Role |
|------|---------------|------|
| `steering/extensions/ue-compile.mjs` | `compile()`: the `-NoUBA` comment block and the `args` array | Passes the non-default flag to `Build.sh` |
| `steering/snippets/project-tech.md` | Verification Gates table, `gate-ue-compile` row | Documents the flag and the parallel-worktree reason |
| `tests/unit/test_ue_compile_gate.py` | Module docstring, `test_gate_passes_no_uba_to_build_sh`, `test_documented_gate_row_shows_no_uba_and_why` | Require the flag and its documentation |
| `scripts/unreal/build_master_material.py` | `_build_headless()`: the `Build.sh` argument list | Passes the non-default flag |
| `tests/unit/test_build_master_material.py` | `test_headless_builds_dogfood_then_runs_the_graph_in_a_separate_editor` | Requires the flag |

## Fix Strategy

1. **Provider (FR1).** Delete the three comment lines that start `// -NoUBA turns off the Unreal Build Accelerator`. Set `args` to `[target, "Mac", "Development", `-Project=${project}`, "-WaitMutex"]`. The rest of `compile()` is unchanged.
2. **Documentation (FR2).** In the `gate-ue-compile` row, the "Runs" cell becomes: extension `project.ue-compile`: the engine `Build.sh DogfoodEditor Mac Development -WaitMutex` for `fixtures/dogfood.uproject`, which compiles the UE plugin and its automation specs. The sentence about `-NoUBA`, the Unreal Build Accelerator, and parallel worktrees is removed. The "Applies when" and "Host prerequisite" cells are unchanged.
3. **Tests (FR3).**
   - The module docstring cites #227 and says the gate passes the default toolchain arguments to `Build.sh`.
   - `test_gate_passes_no_uba_to_build_sh` is renamed `test_gate_passes_default_arguments_to_build_sh`. It asserts the logged arguments equal `["DogfoodEditor", "Mac", "Development", f"-Project={project}", "-WaitMutex"]`, that `"-NoUBA"` is not among them, and that the first command evidence summary does not contain `-NoUBA`. The test still requires `result["status"] == "passed"`.
   - `test_documented_gate_row_shows_no_uba_and_why` is renamed `test_documented_gate_row_shows_default_build`. It asserts that the single row contains `Build.sh DogfoodEditor Mac Development -WaitMutex`, and that it contains none of `-NoUBA`, `Unreal Build Accelerator`, or `parallel worktrees`.
4. **Headless master-material build (FR4).**
   - In `_build_headless()`, the `subprocess.run` argument list loses its `"-NoUBA"` entry and keeps `[<Build.sh>, "DogfoodEditor", "Mac", "Development", f"-Project={DOGFOOD_PROJECT}", "-WaitMutex"]`.
   - In `test_headless_builds_dogfood_then_runs_the_graph_in_a_separate_editor`, the expected `fake.build_args()` list loses `"-NoUBA"`, and the test adds `assert "-NoUBA" not in fake.build_args()`.
   - The editor-argument assertions are unchanged.

## Changes

| File | Change | Behavioral reason |
|------|--------|-------------------|
| `steering/extensions/ue-compile.mjs` | Remove the `-NoUBA` comment and argument | AC1, FR1 |
| `steering/snippets/project-tech.md` | Revert the `gate-ue-compile` "Runs" cell | AC2, FR2 |
| `tests/unit/test_ue_compile_gate.py` | Assert the default arguments, the absence of `-NoUBA`, and the reverted row | AC1, AC2, AC3, FR3 |
| `scripts/unreal/build_master_material.py` | Remove `-NoUBA` from the headless `Build.sh` arguments | AC4, FR4 |
| `tests/unit/test_build_master_material.py` | Assert the default arguments and that `-NoUBA` is absent | AC4, FR4 |

## Blast Radius

The change reaches the `gate-ue-compile` provider, its documentation row, and its unit test. It also reaches the `Build.sh` call in headless master-material mode and its unit test. Other `steering/manifest.json` registrations and the other extension, `plugin-session-smoke.mjs`, are unchanged, and so are the master-material editor launch and live-MCP mode. The gate still runs only on macOS and still reports evidence in the same shape.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Remove `-NoUBA` from the gate and the headless master-material build | Selected | Both carry the same flag, so both return to the default toolchain build |
| Make `-NoUBA` an opt-in through provider config | Rejected | The gate would keep a non-default build path the issue removes |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #227 | 2026-11-12 | Initial defect design |
