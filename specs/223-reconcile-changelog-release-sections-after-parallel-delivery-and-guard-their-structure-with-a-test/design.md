# Root Cause Analysis: CHANGELOG release sections are duplicated, empty and out of order after parallel delivery

**Issue**: #223
**Date**: 2026-11-12
**Status**: Approved
**Author**: Rich Nunley

## Root Cause

Each issue branch prepared its own version and CHANGELOG section before delivery. When branches were reconciled with main, `CHANGELOG.md` was merged by line union while `VERSION` took main's value. As a result:

- sections from different branches interleaved;
- some headings lost their bullets;
- `0.22.0` was written twice;
- headings stayed for three branch-local versions (`0.21.6`, `0.22.1`, `0.23.1`) that main's `VERSION` never carried;
- bullets from 0.21.2 to 0.25.0 ended up under versions other than the one main carried when they merged.

No test reads the release structure, so the damage passed every gate.

## Affected Code

| File | Symbol / Area | Role |
|------|---------------|------|
| `CHANGELOG.md` | Sections from `## [0.25.0]` down to, not including, `## [0.21.1]` | Damaged release history |
| `tests/unit/` | No CHANGELOG structure test | Missing guard |

## Fix Strategy

Replace the damaged region with this exact content. Bullet text is unchanged, and each bullet keeps its current subsection type:

    ## [0.25.0] - 2026-11-12

    ### Changed

    - Add a terrain asset class that finalizes Blender heightfields into Unreal Landscapes (#154)

    ## [0.24.0] - 2026-11-12

    ### Added

    - Export and import rigged-character animation clips through finalize (#138)

    ### Changed

    - Add a reduce-to-budget step that bakes a generated high-poly asset onto an in-budget mesh (#139)
    - Add batch finalize with lock wait, Unreal MCP timeout retry, and a PIE preflight (#149)

    ### Fixed

    - Rebuild the committed M_NmgORM master material headlessly so it carries the Tint parameter (#204)
    - Judge launcher detach in the scaffold scenarios by process state, not a 2-second wall clock (#215)

    ## [0.23.0] - 2026-11-11

    ### Added

    - Let one finalized asset declare several material variants (#148)

    ### Changed

    - Report sample locations in geometry contract findings (#153)
    - Add a built-in procedural clip library to import_animations (#136)

    ### Fixed

    - Fail import_ue when Unreal refuses to rename or consolidate an imported asset (#203)
    - Fix texture job queue: duplicate batch outputs, orphaned running jobs, and runner log location (#211)

    ## [0.22.0] - 2026-11-11

    ### Changed

    - Add optional ElevenLabs sound-effect and music generation that imports into Unreal (#155)
    - Make texture generation work from the plugin root and queue or batch texture jobs (#143)

    ### Fixed

    - Fix naming collisions that pass validate and fail after the bake (#142)
    - Fix contract UV overlap validation hanging for hours on stacked UVs (#133)
    - Build the UE compile gate without UBA so parallel worktrees don't corrupt each other's objects (#202)

    ## [0.21.5] - 2026-11-11

    ### Fixed

    - Fix geometry.normals rejecting correctly facing open surfaces on environment pieces (#144)
    - Fix the Blender test runner repointing the user's Blender add-on link and racing across worktrees (#189)

    ## [0.21.4] - 2026-11-11

    ### Changed

    - Add a contact sheet for reviewing generated tiling textures (#152)

    ### Fixed

    - Fix plugin.session-smoke failing when the Herdr window is too short to show every /mcp server (#193)
    - Fix import_ue failing multi-part static imports because UE 5.8 reports only the first mesh on the import task (#141)

    ## [0.21.3] - 2026-11-11

    ### Changed

    - Add estimate_landmarks to propose rig_humanoid landmarks from the mesh (#137)
    - Measure texel density per material slot and exempt trim-atlas and flat-colour slots (#151)

    ### Fixed

    - Fix import_ue failing the Mobile variant of static assets that export as an LOD group (#146)
    - Fix the tiling seam check rejecting high-frequency textures that tile correctly (#147)

    ## [0.21.2] - 2026-11-11

    ### Fixed

    - The `variants` step cleans every Mobile mesh it produces with the same routine Desktop cleanup uses, so decimated LODs no longer fail the contract's zero-area, loose, normals, and pivot rules or the re-import triangle count. Desktop cleanup also removes non-manifold-edge and duplicate faces, and the Mobile variant is re-seated on the world origin after decimation (#140)
    - Fix Meshy a-pose arm raise destroying legs on stylized characters (#135)
    - Fix import_ue importing static meshes at 1/100 scale on UE 5.8 (#145)
    - Honour nmg-budgets.json Desktop overrides in contract validation (#134)
    - Fix start-unreal-mcp.sh rebuilding plugins on every launch and failing to relaunch the editor after a config change (#150)

After this region come a blank line and the untouched `## [0.21.1] - 2026-11-02` section. `## [Unreleased]` and the file header stay as they are. Every bullet is copied byte-for-byte from commit `353e275`, which the T001 diff enforces.

Add `tests/unit/test_changelog_structure.py` with a pure function `changelog_problems(text: str, version: str) -> list[str]` that:

- requires `## [Unreleased]` to be the first `## ` heading;
- requires every later `## ` heading to match `^## \[(\d+)\.(\d+)\.(\d+)\] - \d{4}-\d{2}-\d{2}$`;
- reports a duplicate version, any version not strictly lower than the one above it (integer tuple comparison), any release section with no line starting `- `, and a first release that differs from `version`.

Tests:

- The checked-in `CHANGELOG.md` with stripped `VERSION` yields no problems.
- Parametrized synthetic changelogs (a duplicate version, an ascending pair, an empty section, newest ≠ VERSION) each yield at least one problem.
- Each of the 30 reconciled references appears in exactly one bullet of the checked-in file.

## Changes

| File | Change | Behavioral reason |
|------|--------|-------------------|
| `CHANGELOG.md` | Replace the region from `[0.25.0]` down to `[0.21.1]` with the content above | AC1, AC2, AC3, FR1, FR2 |
| `tests/unit/test_changelog_structure.py` | New structure checker and tests | AC3, AC4, FR3 |

## Blast Radius

Only `CHANGELOG.md` text and one new test module change. Existing tests that read CHANGELOG look up `## [Unreleased]`, or the section that holds (#127) or (#7):

- `tests/unit/test_model_asset_skill.py`
- `tests/unit/onboard/test_docs_and_skill.py`
- `tests/bdd/steps/test_scaffold.py`

All of those sections stay untouched. Later version preparation adds a new top section and bumps `VERSION` together, which keeps the new test passing.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Rebuild 0.21.2–0.25.0 from main's first-parent `VERSION` history | Selected | Places every bullet in the window by one rule, and only versions main shipped get headings |
| Rebuild only the region above `[0.21.5]` | Rejected | Leaves bullets in 0.21.2–0.21.5 under versions they did not ship in |
| Keep `0.21.6`, `0.22.1` and `0.23.1` as releases | Rejected | Main's `VERSION` never carried them, and no merge produced them |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #223 | 2026-11-12 | Initial defect design |
