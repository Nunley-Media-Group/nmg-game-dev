# Tasks: gate-ue-compile builds with -NoUBA instead of the default UE 5.8 toolchain

**Issue**: #227
**Date**: 2026-11-12
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/202-build-the-ue-compile-gate-without-uba-so-parallel-worktrees-don-t-corrupt-each-other-s-objects/

## Implementation Tasks

### T001: Build with the default toolchain arguments and document them

**File(s)**: `steering/extensions/ue-compile.mjs`, `steering/snippets/project-tech.md`
**Type**: Modify
**Depends**: none
**Acceptance**:
- AC1, FR1: `compile()` in `steering/extensions/ue-compile.mjs` passes exactly `[target, "Mac", "Development", "-Project=<absolute project>", "-WaitMutex"]` to `Build.sh`. The file no longer contains `NoUBA` or `Unreal Build Accelerator`.
- AC2, FR2: the single `gate-ue-compile` row in `steering/snippets/project-tech.md` contains `Build.sh DogfoodEditor Mac Development -WaitMutex` and contains none of `-NoUBA`, `Unreal Build Accelerator`, or `parallel worktrees`. Its "Applies when" and "Host prerequisite" cells are unchanged.

### T002: Guard the default build in the gate unit test

**File(s)**: `tests/unit/test_ue_compile_gate.py`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- AC1, AC3, FR3: `test_gate_passes_default_arguments_to_build_sh` runs the real provider through node against the fake `Build.sh`. It asserts that the logged arguments equal `["DogfoodEditor", "Mac", "Development", f"-Project={project}", "-WaitMutex"]`, that `-NoUBA` is absent from both the arguments and the command evidence summary, and that the status is `passed`. It stays skipped off macOS.
- AC2, FR3: `test_documented_gate_row_shows_default_build` asserts the row content described in T001.
- Evidence: `uv run pytest tests/unit/test_ue_compile_gate.py -q` passes.

### T003: Build the headless master material with the default toolchain

**File(s)**: `scripts/unreal/build_master_material.py`, `tests/unit/test_build_master_material.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- AC4, FR4: `_build_headless()` passes exactly `DogfoodEditor`, `Mac`, `Development`, `-Project=<DOGFOOD_PROJECT>`, and `-WaitMutex` to `Build.sh`. `scripts/unreal/build_master_material.py` no longer contains `NoUBA`.
- AC4, FR4: `test_headless_builds_dogfood_then_runs_the_graph_in_a_separate_editor` asserts that exact list and `"-NoUBA" not in fake.build_args()`. Its editor-argument assertions are unchanged.
- Evidence: `uv run pytest tests/unit/test_build_master_material.py tests/unit/test_ue_compile_gate.py -q` passes. `repository.tests` (`uv run pytest tests/unit tests/bdd -q`), `repository.lint`, `repository.format`, and `repository.types` pass.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #227 | 2026-11-12 | Initial defect tasks |
