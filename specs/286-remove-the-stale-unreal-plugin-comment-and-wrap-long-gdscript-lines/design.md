# Design: Remove the stale Unreal plugin comment and wrap long GDScript lines

**Issue**: #286
**Date**: 2026-11-19
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/251-add-launch-options-a-headless-autoplay-smoke-run-and-on-demand-game-screenshots-for-godot-games/

## Overview

Two source cleanups, each with a guard test so it cannot come back.

## Architecture

- `tests/blender/_runner.py`: the comment becomes, in substance: "The add-on source directory is hyphenated (nmg-game-dev-blender-addon), like the other directories under plugins/, but Python/Blender require the snake_case module id ``nmg_game_dev_blender_addon``. Bridge the gap ..." The rest of the comment and the code stay unchanged.
- `tests/unit/test_no_unreal_references.py`: `INSENSITIVE` becomes `re.compile(r"unreal|vibeue|ue-plugin|\.uproject|\.uasset", re.IGNORECASE)`, the module docstring lists `ue-plugin`, and `test_matcher_whole_word_abbreviation_and_any_case_engine_name` asserts `references_engine("nmg-game-dev-ue-plugin")`. The repository has no other non-exempt `ue-plugin` text once `_runner.py` is fixed (`git grep` outside `specs/` and `CHANGELOG.md` finds only that line).
- `plugins/nmg-game-dev-godot-addon/addons/nmg_game_dev/nmg_launch.gd`: reflow the `##` doc-comment paragraph at lines 12-14 to 100 columns, with the same words.
- `.../tests/test_nmg_launch.gd:7`: `const AutoplaySceneScript: GDScript = preload(` followed by the path string on a tab-indented continuation line, then `)`. GDScript continues lines inside parentheses.
- `.../tests/test_nmg_variant_scene.gd:46-47`: split each `check_eq(` call so its arguments sit on tab-indented continuation lines inside the parentheses.
- `tests/unit/test_godot_addon_line_length.py` (new): walk `REPO_ROOT / "plugins" / "nmg-game-dev-godot-addon"` with `rglob("*.gd")`, read each file as UTF-8, and collect `path:line: length` for every `splitlines()` line whose `len` is over 100. Assert the list is empty, and assert at least one `.gd` file was found, so the test cannot pass vacuously. Use `REPO_ROOT` from `tests._scaffold_contract`, as the neighboring guards do.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Extend the existing retired-engine guard with `ue-plugin` | Selected | One guard owns the retired-engine vocabulary |
| Add a separate `_runner.py`-only test | Rejected | Narrower than the guard that already scans every tracked file |
| Measure tabs as 4 columns | Rejected | The issue and the scan measure characters; at 4 columns the limit is stricter than the style the add-on keeps |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #286 | 2026-11-19 | Initial feature design |
