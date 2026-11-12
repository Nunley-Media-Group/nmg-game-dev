# Tasks: The committed M_NmgORM master material drifts from its builder because it can only be rebuilt in a live editor

**Issue**: #204
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/148-let-one-finalized-asset-declare-several-material-variants/

## Implementation Tasks

### T001: Add a headless mode to the master-material builder

**File(s)**: `scripts/unreal/build_master_material.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- `--headless`, mutually exclusive with `--url`, runs `Build.sh DogfoodEditor Mac Development -Project=<abs fixtures/dogfood.uproject> -WaitMutex -NoUBA`. It then writes `_MATERIAL_CODE` unchanged to a temporary `.py` file and runs `UnrealEditor-Cmd <abs fixtures/dogfood.uproject> -ExecutePythonScript=<abs temp file> -DisablePlugins=ModelContextProtocol,EditorToolset,VibeUE -EnablePlugins=PythonScriptPlugin -unattended -nopause -nosplash -nullrhi -stdout -FullStdOutLogOutput`, with both binaries resolved under `UE_ROOT` (default `/Users/Shared/Epic Games/UE_5.8`) (AC1, FR1).
- Headless mode never constructs `UnrealMcpClient` and never opens a network connection (FR4).
- It reads the `NMG_RESULT` line from the process output even when UE prefixes it with a log category such as `LogPython: `. On `ok: true` it prints `Built /nmg-game-dev/Materials/M_NmgORM` and exits 0. On a UE error, or no result line, it exits 1. A missing `Build.sh`, `UnrealEditor-Cmd`, or project exits 3 with `master_material.headless_unavailable`, naming the path and `UE_ROOT`. A failed build exits 3 with `master_material.build_failed`. The temporary script is removed.
- The default MCP mode, its `--url` flag, and its exit codes 0/1/2 are unchanged. The module docstring documents both commands and exit code 3.

### T002: Rebuild and commit M_NmgORM with the Tint parameter

**File(s)**: `plugins/nmg-game-dev-ue-plugin/Content/Materials/M_NmgORM.uasset`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- With #148's `Tint` graph in `_MATERIAL_CODE` and `fixtures/Plugins/` populated by `scripts/install-vibeue.sh`, `uv run --group dev python scripts/unreal/build_master_material.py --headless` exits 0. The regenerated `M_NmgORM.uasset` is committed (AC2, FR2).
- The rebuild runs only that separate headless process. It doesn't connect to or restart any running editor, and nothing binds the MCP port.
- The only tracked file the rebuild changes is `M_NmgORM.uasset`. Engine output stays in the git-ignored `fixtures/` folders.

### T003: Unit tests for the headless mode and the committed asset

**File(s)**: `tests/unit/test_build_master_material.py`
**Type**: Modify
**Depends**: T001, T002
**Acceptance**:
- AC1, FR1: with `UE_ROOT` pointed at a temporary tree, a fake executable `Build.sh` and a fake executable `UnrealEditor-Cmd` each log their arguments. The fake editor also copies the file named by `-ExecutePythonScript=` and prints `LogPython: NMG_RESULT {"asset": "/nmg-game-dev/Materials/M_NmgORM", "error": null, "ok": true}`. `main(["--headless"])` returns 0. The `Build.sh` arguments are exactly `DogfoodEditor Mac Development -Project=<abs dogfood.uproject> -WaitMutex -NoUBA`. The editor arguments start with the absolute `fixtures/dogfood.uproject` path and include `-ExecutePythonScript=`, `-DisablePlugins=ModelContextProtocol,EditorToolset,VibeUE`, `-EnablePlugins=PythonScriptPlugin`, and `-unattended`. The copied script equals `_MATERIAL_CODE`, and the temporary script no longer exists afterward.
- FR4: in the same run, `UnrealMcpClient` is replaced with a stub that fails the test if constructed, and the stub is never called.
- A fake editor that prints `LogPython: NMG_RESULT {"ok": false, "error": "RuntimeError: x", "asset": "/nmg-game-dev/Materials/M_NmgORM"}` makes `main(["--headless"])` return 1. A missing `UnrealEditor-Cmd` returns 3 and names its path. A fake `Build.sh` exiting 2 returns 3 with `master_material.build_failed`.
- AC2, FR3: the committed `M_NmgORM.uasset` contains a serialized name entry (`struct.pack("<i", len(name) + 1) + name.encode() + b"\0"`) for each of `Tint`, `BaseColor`, `Normal`, and `ORM`.
- AC3: the committed asset contains the package name `/nmg-game-dev/Materials/M_NmgORM` and the name entry `M_NmgORM`. `rebuild_clears_in_place` still holds for `_MATERIAL_CODE`, and the existing #101 checks for the default textures and `bUsedWithSkeletalMesh` still pass.
- No test starts a real Unreal, Blender, or MCP process.

### T004: BDD scenarios for AC1–AC3

**File(s)**: `tests/bdd/features/master_material.feature`, `tests/bdd/test_master_material_bdd.py`
**Type**: Modify
**Depends**: T003
**Acceptance**:
- The feature gains SCN004–SCN006 from this spec's `feature.gherkin`. They are bound in `tests/bdd/test_master_material_bdd.py`, reusing the T003 helpers, the fake `Build.sh` and `UnrealEditor-Cmd`, and the name-table check. SCN001–SCN003 stay as they are.
- Passes under `repository.tests` (`uv run pytest tests/unit tests/bdd -q`), and the changed files pass `repository.lint`, `repository.format`, and `repository.types`.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #204 | 2026-11-11 | Initial defect tasks |
