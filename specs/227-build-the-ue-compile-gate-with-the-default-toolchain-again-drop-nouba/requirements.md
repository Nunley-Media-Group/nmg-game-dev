# Defect Report: gate-ue-compile builds with -NoUBA instead of the default UE 5.8 toolchain

**Issue**: #227
**Date**: 2026-11-12
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/202-build-the-ue-compile-gate-without-uba-so-parallel-worktrees-don-t-corrupt-each-other-s-objects/

## Reproduction

1. Run `uv run pytest tests/unit/test_ue_compile_gate.py -q` on macOS. The test calls the `project.ue-compile` provider in `steering/extensions/ue-compile.mjs` with a fake `Build.sh` that logs its arguments.
2. The logged arguments end with `-NoUBA`, and the test asserts that they do.
3. Read the `gate-ue-compile` row in `steering/snippets/project-tech.md`. It documents `-NoUBA` and justifies it with concurrent builds from parallel worktrees.
4. Run `uv run pytest tests/unit/test_build_master_material.py -q`. `scripts/unreal/build_master_material.py --headless` also passes `-NoUBA` to the fake `Build.sh`, and the test asserts that it does.

## Expected vs Actual

| | Description |
|---|-------------|
| **Expected** | The gate and the headless master-material build both invoke `Build.sh` with the default toolchain arguments `<target> Mac Development -Project=<abs project> -WaitMutex`. The docs describe that build. |
| **Actual** | Both append `-NoUBA`, which turns off the Unreal Build Accelerator. The documentation and both unit tests require the flag. |

## Acceptance Criteria

### AC1: The gate builds with the default toolchain

**Given** the `project.ue-compile` provider
**When** it runs the engine build
**Then** the `Build.sh` arguments are exactly the target, `Mac`, `Development`, `-Project=<absolute project path>`, and `-WaitMutex`, with no `-NoUBA`

### AC2: Docs match

**Given** `steering/snippets/project-tech.md`
**When** a contributor reads the `gate-ue-compile` row
**Then** it describes `Build.sh DogfoodEditor Mac Development -WaitMutex` and no longer mentions `-NoUBA`, the Unreal Build Accelerator, or parallel worktrees

### AC3: The argument test guards the default build

**Given** `tests/unit/test_ue_compile_gate.py`
**When** it runs against the fake `Build.sh`
**Then** it asserts the exact default argument list, and that `-NoUBA` is absent from both the logged arguments and the gate's command evidence

### AC4: The headless master-material build uses the default toolchain

**Given** `scripts/unreal/build_master_material.py --headless` with a fake engine under `UE_ROOT`
**When** it builds `DogfoodEditor` before it starts the editor
**Then** `Build.sh` receives exactly `DogfoodEditor`, `Mac`, `Development`, `-Project=<dogfood project>`, and `-WaitMutex`, and `tests/unit/test_build_master_material.py` asserts that list and that `-NoUBA` is absent

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | Remove `-NoUBA` and its explanatory comment from `steering/extensions/ue-compile.mjs` | Must |
| FR2 | Revert the `gate-ue-compile` row in `steering/snippets/project-tech.md` so that it no longer mentions `-NoUBA`, the Unreal Build Accelerator, or parallel worktrees | Must |
| FR3 | Update `tests/unit/test_ue_compile_gate.py` as AC3 describes, and assert the reverted documentation row as AC2 describes | Must |
| FR4 | Remove `-NoUBA` from the `Build.sh` arguments in `_build_headless()` in `scripts/unreal/build_master_material.py`. Update `tests/unit/test_build_master_material.py` to assert the default argument list and that `-NoUBA` is absent. | Must |

## Out of Scope

- Any other change to `scripts/unreal/build_master_material.py`: its editor arguments, live-MCP mode, or exit codes.
- Any other change to the `gate-ue-compile` provider: its macOS check, `UE_ROOT` resolution, error parsing, or evidence format.
- Registering `gate-ue-compile` differently in `steering/manifest.json`.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #227 | 2026-11-12 | Initial defect report |
