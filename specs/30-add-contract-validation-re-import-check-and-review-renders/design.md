# Design: Contract validation, re-import check, and review renders

**Issue**: #30
**Date**: 2026-10-29
**Status**: Approved
**Author**: Rich Nunley

## Overview

Blender-side logic lives in a new add-on package, `plugins/nmg-game-dev-blender-addon/contract_core/`, next to #33's `variants_core/`. Three thin operators wrap it. A Python package on the host side, `src/nmg_game_dev/contract/`, launches headless Blender for CLI use. `src/nmg_game_dev/quality/contract.py` holds the report models and the gate. Reports are plain JSON, so the Blender side and the host side share a schema without importing each other.

## Architecture

```
Agent (execute_blender_code) ─┐
Operators nmggamedev.*  ──────┼─► contract_core.validate_asset / reimport_check / render_review / render_texture_proof
python -m nmg_game_dev.contract ─► blender --background [--factory-startup] --python scripts/blender/contract_entry.py -- <args>
                                         └─► contract_core (same functions) ─► JSON report / PNGs
Finalize (#69) ─► nmg_game_dev.quality.contract.load_report + gate(report, kind)
```

`reimport_check` must run in a fresh process. When called inside a session (the operator or `execute_blender_code`), `contract_core.reimport.run_isolated()` spawns `[bpy.app.binary_path, "--background", "--factory-startup", "--python", <contract_entry.py>, "--", "reimport", ...]` and reads the JSON it writes. Inside that process, `reimport_check` itself runs in-process.

### Modules

| Path | Contents |
|------|----------|
| `contract_core/__init__.py` | Re-exports the four functions |
| `contract_core/report.py` | `Finding` / report dict builders; `RULES` (rule id → default remediation) |
| `contract_core/validate.py` | Rule checks below; snapshot per object (`name`, `parent`, `tris`, `dimensions`, `location`, `rotation`, `scale`, `uv_maps`, `materials`, `images`) |
| `contract_core/geometry.py` | bmesh checks on evaluated copies (never mutates the scene): loose, zero-area (`area < 1e-8`), doubles (`find_doubles` 1e-5), normals (count of faces flipped by `recalc_face_normals` on a copy) |
| `contract_core/uv.py` | UV overlap by rasterizing triangle interiors onto a 512×512 grid; overlap when > 0.5% of covered cells are hit by two or more faces |
| `contract_core/reimport.py` | `reimport_check`, `run_isolated` |
| `contract_core/render.py` | `render_review`, `render_texture_proof`, the camera/light rig, proof sheet compositing |
| `operators/validate_contract.py`, `operators/reimport_check.py`, `operators/render_review.py` | Operators; results stored on `scene.nmg_game_dev.last_result` (property added by #33) |
| `scripts/blender/contract_entry.py` | Argument parsing inside Blender; enables the add-on; opens `--blend` when given; calls `contract_core`; writes `--report` JSON |
| `src/nmg_game_dev/contract/__main__.py`, `src/nmg_game_dev/contract/blender.py` | CLI; Blender resolution `BLENDER_BIN` → `BLENDER_APP/Contents/MacOS/Blender` → `/Applications/Blender.app/...`, the same order as `scripts/run-blender-tests.sh` |
| `src/nmg_game_dev/quality/contract.py` | `Finding`, `ContractReport` (pydantic), `load_report`, `gate` |

## API / Interface Changes

| Interface | Input | Output / Error | Behavior |
|-----------|-------|----------------|----------|
| `validate_asset(collection, asset_class, budgets_path=None)` | collection name, class id | report dict | AC1, AC2 |
| `reimport_check(variant_dir, pre_report)` | folder with `SM_<Name>.fbx` + PNGs, report dict/path | report dict | AC3 |
| `render_review(collection, out_dir, resolution=1024)` | | `{"files": [...]}` | AC4 |
| `render_texture_proof(variant_dir, out_dir, pre_bake=None, collection=None)` | | `{"proof": path}` | AC5 |
| `nmggamedev.validate_contract` | `collection_name`, `asset_class`, `budgets_path`, `report_path` | `FINISHED` (pass) / `CANCELLED` (fail, error report shown) | AC7 |
| `nmggamedev.reimport_check` | `variant_dir`, `pre_report_path`, `report_path` | same | AC7 |
| `nmggamedev.render_review` | `collection_name`, `out_dir`, `resolution`, `proof_variant_dir`, `pre_bake_path` | `FINISHED` | AC7 |
| `python -m nmg_game_dev.contract validate --blend B --collection N --class C --report R` | | exit 0 / 1 / 2 | AC7 |
| `python -m nmg_game_dev.contract reimport --variant-dir D --pre-report R --report OUT` | | exit 0 / 1 / 2 | AC7 |
| `python -m nmg_game_dev.contract render --blend B --collection N --out O [--proof-variant-dir D] [--pre-bake P]` | | exit 0 / 2 | AC7 |
| `gate(report: ContractReport, kind: Literal["contract","reimport"])` | | `None` or `PipelineError` | AC6 |

## Data / Storage Changes

Report JSON (shared schema):

```json
{"kind": "contract", "asset": "Crate", "class": "standard_prop", "passed": false,
 "findings": [{"rule": "budget.tris", "target": "SM_Crate_Mobile_LOD0", "message": "SM_Crate_Mobile_LOD0 has 4000 triangles; standard_prop Mobile budget is 3000", "remediation": "Re-run nmggamedev.optimize_mobile or lower the Mobile mesh detail"}],
 "snapshot": {"SM_Crate": {"tris": 4000, "dimensions": [1,1,1], "location": [0,0,0], "rotation": [0,0,0], "scale": [1,1,1], "uv_maps": ["UVMap"], "materials": ["M_Crate_Body"], "images": ["T_Crate_Body_BC", "T_Crate_Body_N", "T_Crate_Body_ORM"]}}}
```

Budget checks: Desktop objects (collection `<Name>`) use the class's Desktop budget; objects in `<Name>_Mobile` use the Mobile budget via `resolve_budget` (from `utils/budgets.py`). For Mobile LOD groups, LOD0 is what gets checked.

Texel density for `environment_piece`: `max_texture_px * sqrt(uv_area / world_area)` per mesh must be ≥ 256 (Desktop) or 128 (Mobile) px/m; otherwise `texel.density`.

Rule ids:

- `scene.collection`, `scene.units`
- `naming.root`, `naming.part`, `naming.material`, `naming.texture`
- `transform.root_applied`, `transform.part_applied`
- `pivot.bottom_center` (tolerance 1 mm)
- `geometry.loose`, `geometry.zero_area`, `geometry.duplicates`, `geometry.normals`
- `uv.single_map`, `uv.overlap`
- `material.node_types`, `material.uv_coordinates`
- `texture.power_of_two`
- `budget.tris`, `budget.materials`, `budget.texture_size`, `texel.density`
- `variants.names_match`
- `reimport.texture_missing`, `reimport.orm_missing`, `reimport.uv_missing`, `reimport.name_mismatch`, `reimport.dimensions`, `reimport.pivot`, `reimport.tris`

Render output: `<out>/<variant>/<Name>_{front,back,side,three_quarter}.png` and `<out>/<variant>/<Name>_proof.png`.

## State and UI Behavior

Review renders run in a temporary scene `__nmg_review`. The asset collections are linked into it, along with:

- a 50 mm camera on a fixed-elevation (20°) orbit at a distance that fits the bounding-box radius with 10% margin;
- views at azimuth −Y (front), +Y (back), +X (side), and −Y+X 45° (three-quarter);
- a three-sun rig with a gray world;
- EEVEE, 16 samples.

The scene is deleted afterward, so user scenes and the active scene are unchanged. The proof sheet is composited by placing the PNGs side by side into a new image via pixel buffers, with the labels "pre-bake", "baked", and "re-imported".

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Logic in the add-on, host CLI launches headless Blender | Selected | One implementation reachable from MCP sessions, operators, and the CLI |
| Re-import inside the running session | Rejected | The issue requires a fresh process; session state could hide missing files |
| Cycles for review renders | Rejected | EEVEE is fast enough for routine self-review |
| Wire the gate into the current pipeline `quality` stage | Rejected | The pipeline is being reshaped in #69, which owns finalize wiring |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #30 | 2026-10-29 | Initial feature design |
