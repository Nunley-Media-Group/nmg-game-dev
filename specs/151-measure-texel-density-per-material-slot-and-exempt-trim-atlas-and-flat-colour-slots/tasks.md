# Tasks: Measure texel density per material slot and exempt trim-atlas and flat-colour slots

**Issue**: #151
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley

## Implementation Tasks

### T001: Shared per-slot measurement

**File(s)**: `plugins/nmg-game-dev-blender-addon/contract_core/texel.py`
**Type**: Create
**Depends**: none
**Acceptance**:
- Defines `TRIM_ATLAS_PROPERTY = "nmg_trim_atlas"`, `FLAT_COLOUR_UV_AREA = 1e-8`, `DESKTOP_MIN = 256.0`, and `MOBILE_MIN = 128.0`.
- `slot_areas(obj, mesh)` groups polygons by material index, summing UV area and world-space area (after `obj.matrix_world`).
- `classify` returns, in order: `trim_atlas` (marker), `flat_colour` (UV area ≤ cut-off), `skipped` (zero world area), or `measured`.
- `density` = px × sqrt(uv / world).
- `slot_report` lists measured densities or exemption reasons.
- `classify` and `density` work on plain numbers (FR1–FR4, FR8).

### T002: Contract validation per slot

**File(s)**: `plugins/nmg-game-dev-blender-addon/contract_core/validate.py`, `plugins/nmg-game-dev-blender-addon/contract_core/report.py`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- `_texel_findings` emits one `texel.density` finding per failing measured slot, using that slot material's largest image. The message names the object, the material, the px/m, the minimum, and the variant.
- Exempt and skipped slots produce no finding.
- The report snapshot lists every slot with densities or its exemption (AC1–AC7).
- A single-slot mesh gives today's result (AC9).
- `RULES["texel.density"]` names both remedies (FR6, FR9, FR13).

### T003: Tiling bake per slot and marker carry-over

**File(s)**: `plugins/nmg-game-dev-blender-addon/bake_core/tiling.py`, `plugins/nmg-game-dev-blender-addon/bake_core/core.py`, `plugins/nmg-game-dev-blender-addon/bake_core/rewire.py`, `plugins/nmg-game-dev-blender-addon/bake_core/errors.py`, `plugins/nmg-game-dev-blender-addon/variants_core/textures.py`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- `check_density` measures slots of an evaluated copy through `contract_core/texel.py`.
- It raises `texel_density` for the first failing measured slot, naming the mesh, the material, the px/m, the variant, and the minimum.
- It returns per-slot entries, which `core.py` stores as `texel_density` in the bake report (AC1–AC3, AC7).
- The `texel_density` remediation names both remedies (FR9).
- The baked `M_<Name>_<Part>` gets `nmg_trim_atlas` when any of its source materials has it.
- The Mobile material copy keeps it (FR5, AC8).

### T004: Documentation and skill guidance

**File(s)**: `docs/asset-contract.md`, `docs/skills/bake-materials.md`, `docs/skills/model-asset.md`, `skills/model-asset/SKILL.md`
**Type**: Modify
**Depends**: T002, T003
**Acceptance**:
- The docs state the per-slot rule and the unchanged minimums.
- They define the flat-colour exemption with its cut-off, and the trim-atlas marker with how to set it in the UI and from a script.
- They describe the report fields (FR10).
- The `/model-asset` guidance tells authors to mark atlas materials on environment pieces (FR11).
- `claude plugin validate .` (`plugin.validate`) passes.

### T005: Tests

**File(s)**: `tests/unit/test_texel_classify.py`, `tests/blender/test_contract_validate.py`, `tests/blender/test_bake_tiling.py`, `tests/blender/test_variants_mobile.py`
**Type**: Create, Modify
**Depends**: T002, T003
**Acceptance**:
- No test launches or connects to a live Blender GUI session or Unreal editor. Blender tests run headless through `gate-blender-headless`.
- **Unit** (`repository.tests`): `classify` order and the cut-off boundary, and `density` arithmetic. `texel.py` is loaded by file path, as `test_blender_budgets.py` loads `budgets.py`, with its `bpy`-dependent function unused.
- **SCN001:** a three-slot mesh measures each slot from its own faces.
- **SCN002:** one passing tiling slot plus a marked atlas slot and a collapsed slot covering most of the area, with the whole-mesh aggregate below 256, gives no finding and no bake error.
- **SCN003:** two tiling slots, one failing, give one finding and one bake error naming the mesh and the failing material, with px/m, minimum, and variant.
- **SCN004:** a slot with all UVs collapsed is exempt as `flat_colour`, with no marker.
- **SCN005:** a marked low-density slot is exempt as `trim_atlas`.
- **SCN006:** an unmarked 0–1 mapped large surface fails, and the remediation names both remedies.
- **SCN007:** the validation snapshot and the bake report list every slot, with densities or the exemption reason.
- **SCN008:** after bake and variants, the baked material and its `_Mobile` copy carry the marker, and Mobile validation exempts the slot.
- **SCN009:** the existing single-slot passing and low-density cases keep their results, code, and reason.
- `repository.tests`, `repository.lint`, `repository.format`, `repository.types`, and `gate-blender-headless` pass.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #151 | 2026-11-11 | Initial feature tasks |
