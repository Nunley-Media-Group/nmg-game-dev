# Design: Measure texel density per material slot and exempt trim-atlas and flat-colour slots

**Issue**: #151
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley

## Overview

A new module, `contract_core/texel.py`, owns both the slot measurement and the classification. Contract validation and the tiling bake both call it, so they measure the same faces the same way (FR8). They differ only in texture size:
- validation uses the slot material's largest image;
- the bake uses the class's Desktop and Mobile sizes.

A slot is one of:
- exempt as **flat-colour** when its total UV area is at or below `FLAT_COLOUR_UV_AREA`;
- exempt as **trim-atlas** when its material carries `nmg_trim_atlas = True`;
- otherwise **measured** and compared on its own.

## Architecture

### `plugins/nmg-game-dev-blender-addon/contract_core/texel.py` (new)

**Constants:**
- `TRIM_ATLAS_PROPERTY = "nmg_trim_atlas"`;
- `FLAT_COLOUR_UV_AREA = 1e-8` (UV units², summed over the slot);
- `DESKTOP_MIN = 256.0` and `MOBILE_MIN = 128.0` (moved here; `validate.TEXEL_DENSITY_MIN` and the `tiling` constants re-export them, FR13).

**`slot_areas(obj, mesh) -> list[SlotArea]`:**
- Reads `mesh`, which is the evaluated copy, and walks each polygon once.
- Groups polygons by `material_index`. It keeps per slot the slot index, the material (`obj.material_slots[i].material`, or `None`), the summed UV area (render-active UV layer, else layer 0, fan triangulation as today), and the summed world area (polygon area after `obj.matrix_world`).
- Slots with no faces are omitted.

**`classify(slot) -> "trim_atlas" | "flat_colour" | "measured" | "skipped"`:**
- `trim_atlas` when the material has the property truthy;
- otherwise `flat_colour` when the UV area is at or below the cut-off;
- otherwise `skipped` when the world area is 0;
- otherwise `measured`.

**`density(slot, px) = px * sqrt(uv / world)`.**

**`slot_report(obj, slots, desktop_px, mobile_px)` returns per-slot dicts:**
- measured slots give `{slot, material, desktop, mobile}`, rounded to 1 place;
- exempt slots give `{slot, material, exempt: reason}`.

**Pure helpers.** `classify` and `density` take plain numbers and a marker flag, so they unit-test under CPython. The `bpy` reading stays in `slot_areas`.

### Contract validation (`contract_core/validate.py`)

- `_texel_findings(obj, copy, variant)` uses `texel.slot_areas(obj, copy)`.
- For each measured slot, `px` is the largest image size on that slot's material. A material with no images gives no measurement, as today.
- One `texel.density` finding is emitted per slot below `TEXEL_DENSITY_MIN[variant]` (FR6, AC3).
  - `target` is the object name.
  - The message reads "`<obj>` slot `<material>` reaches `<d>` px/m; environment pieces need at least `<min>` px/m on `<variant>`".
- The validation report snapshot gains `texel: {<obj>: [slot entries]}` for environment pieces (AC7).
- **Equivalence with today (AC9).**
  - For a single-slot mesh, the slot measure equals today's measure when the object transform is identity. The contract requires applied root transforms, and validation already checks that.
  - The texture size of a single-material mesh is the same image set as today.

### Tiling bake (`bake_core/tiling.py`, `bake_core/core.py`)

- `check_density(meshes, desktop_px, mobile_px)` measures each mesh's slots through `texel.slot_areas(obj, evaluated copy)` and `classify`.
- **Failure.** It raises `BakeError("texel_density", "Mesh '<obj>' slot '<material>' has <d> px/m at <variant> size; the minimum is <min>.", target=obj.name)` for the first failing measured slot, in mesh then slot order (FR6).
- **Report.** It returns `{<obj>: [slot entries]}`. `core.py` stores it in the bake report as `texel_density` (AC7). The value was discarded before, so no existing consumer reads it.
- **Same faces in both paths.** The bake measures an evaluated copy, made with the same helper validation uses, and removes it after measuring. Both paths therefore see the same faces (FR8).

### Marker carry-over (FR5, AC8)

- **Baked material.** `bake_core/rewire.build_material` gains `trim_atlas: bool`. In `core.py`, each item's flag is true when any of `item.sources` carries the marker, and the flag sets `nmg_trim_atlas` on the baked `M_<Name>_<Part>`.
- **Mobile material.** `variants_core/textures.py::mobile_material_copy` keeps the property. A test asserts it, because `Material.copy()` already carries ID properties.

### Remediation and docs

- `contract_core/report.py` `RULES["texel.density"]` and `bake_core/errors.py` `texel_density` both state the per-slot rule (FR9, AC6). Each names both remedies:
  - raise the slot's density with more texture resolution or less UV area per meter;
  - or set `nmg_trim_atlas` on the material if it is a trim atlas.
- `docs/asset-contract.md` sections 4 and 6 and `docs/skills/bake-materials.md` cover (FR10):
  - the per-slot rule and the minimums;
  - the flat-colour exemption, with the cut-off;
  - the trim-atlas marker: its name and how to set it in Material Properties > Custom Properties or from a script with `material["nmg_trim_atlas"] = True`;
  - the new report fields.
- The `/model-asset` guidance (`skills/model-asset/SKILL.md` and `docs/skills/model-asset.md`) tells authors to mark the atlas materials of environment pieces (FR11).

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Custom property `nmg_trim_atlas` on the material | Selected | Settable in the UI and from a script, survives `Material.copy()`, and is visible in the material panel |
| Name prefix such as `M_Trim*` | Rejected | Collides with contract naming `M_<Name>_<Part>` |
| Detect atlas UV layouts automatically | Rejected | Out of scope |
| Relative flat-colour cut-off (UV/world ratio) | Rejected | Would also exempt legitimately sparse tiling slots; the issue asks for "effectively zero" UV area |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #151 | 2026-11-11 | Initial feature design |
