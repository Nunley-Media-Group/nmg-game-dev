# Design: Version each game build in /ship, show the version in game, and require a player changelog entry

**Issue**: #254
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/249-replace-unreal-engine-with-godot-4-and-convert-existing-consumer-projects/

## Overview

A new `src/nmg_game_dev/ship/version.py` resolves, validates, and writes the build version, and `ship/changelog.py` finds the changelog section. `run_ship` resolves the version and checks the changelog before any Godot command, records each gate's result, writes the version keys after the gates and before the first export, and passes the version, changes, and gate results to `write_release_notes`. The add-on gains `nmg_build.gd` (`class_name NmgBuild`) and `nmg_version_label.gd` (`class_name NmgVersionLabel`).

## Architecture

```
run_ship(target, project, release_dir, dry_run, env, *, bump=None, version=None, ...)
  preflight (existing)
  plan = version.resolve(project_godot, bump, version)        # ship.version_* errors, no writes
  changes = changelog.section(consumer_root / "CHANGELOG.md", plan.new)   # ship.changelog_missing
  gates (existing) -> ship.gate_results: list[GateResult]
  version.write(plan, project_dir, presets) unless dry_run or plan unchanged   # DRY-RUN lines otherwise
  exports (existing)
  write_release_notes(..., version=plan.new, changes=changes, gates=ship.gate_results)
```

### Version (`src/nmg_game_dev/ship/version.py`)

- `SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")`.
- `VersionPlan(current: str | None, new: str, changed: bool)`.
- `resolve(project_file, bump, version) -> VersionPlan`:
  - The current version is read with `read_config` as `("application", "config/version")` and unquoted.
  - Both flags together, or an invalid `--version` or invalid current value, raise `ship.version_invalid`.
  - `--version` must be greater than the current version (tuple compare; an absent current counts as `0.0.0`). Otherwise it raises `ship.version_not_increased`.
  - `--bump` increments the named part and zeroes the lower ones.
  - With no flag, the current version is used unchanged. When there is none, it raises `ship.version_missing` with the remediation "Pass --version X.Y.Z (or --bump) for the first ship."
- `PRESET_KEYS`:
  - `macos`, `ios`: `application/short_version` and `application/version` = `X.Y.Z`.
  - `android`: `version/name` = `X.Y.Z`, plus `version/code` = previous integer + 1 (absent or non-integer counts as 0).
  - `windows`: `application/file_version` and `application/product_version` = `X.Y.Z.0`.
  - `web`: none.
- `planned_edits(plan, project_dir, preset_indexes) -> list[(path, key description, value)]` lists every edit for every preset in `export_presets.cfg` whose platform is one of the five `PRESETS`, not only the shipped targets, so all presets match.
- `write(plan, project_dir, preset_indexes)`:
  - `project.godot` sets `config/version` in `[application]` by replacing that line, or inserting it after the `[application]` header. Only that line changes.
  - `export_presets.cfg` gets `runner.patch_preset_options` per preset, which writes `version/code` as an unquoted integer and the other values as Godot strings.
  - Both files are written through a temp sibling and `os.replace`.

### Changelog (`src/nmg_game_dev/ship/changelog.py`)

`section(path, version) -> str` reads `CHANGELOG.md`, finds the first line matching `^##\s+\[?<version>\]?(\s.*)?$`, and returns the stripped lines up to the next line starting with `## `. A missing file, a missing section, or an all-blank section raises `ship.changelog_missing` with the message naming the path and version and the remediation "Add a `## X.Y.Z` section with at least one line for players to CHANGELOG.md, then rerun the ship."

### Gate results and release notes

- `_Ship.gate_results: list[tuple[str, str]]` collects `(gate, result)`:
  - `version`: `1.2.3 -> 1.3.0`, or `1.3.0 (unchanged)`.
  - `changelog`: `## 1.3.0 found`.
  - `import`: `passed`.
  - `scripts`: `<n> scripts passed`.
  - `tests`: the last line of `run_tests.gd` output matching `^\d+ passed, \d+ failed$`, else `passed`; `not present` when there is no test runner.
  - `mobile budgets`: `passed`, or `not applicable` when no mobile or web platform ships.
  - A dry run records `planned (dry run)` for the Godot gates.
- `write_release_notes(release_dir, target, entries, dry_run, platforms, *, version, changes, gates)` writes:
  - the heading `# Release notes — <version>`;
  - the existing bullet list, plus `- Version: <version>`;
  - `## Changes` with the changelog section text verbatim;
  - `## Gates` with `- <gate>: <result>` per gate in order;
  - `## Artifacts` with the existing SHA-256 table.

### CLI and skill

`python -m nmg_game_dev.ship <target> --project … [--bump {major,minor,patch}] [--version X.Y.Z] [--dry-run]`. argparse makes the two flags mutually exclusive (exit 2). `run_ship` gains keyword parameters `bump: str | None = None` and `version: str | None = None`. `skills/ship/SKILL.md` passes `--bump` / `--version` through from the invocation.

### Add-on

- `addons/nmg_game_dev/nmg_build.gd`: `class_name NmgBuild extends RefCounted` with `const VERSION_SETTING: String = "application/config/version"` and `static func version() -> String: return str(ProjectSettings.get_setting(VERSION_SETTING, ""))`.
- `addons/nmg_game_dev/nmg_version_label.gd`: `class_name NmgVersionLabel extends Label` with `@export var prefix: String = "v"` and `_ready()` setting `text = prefix + NmgBuild.version()` (empty text when there is no version). It has no per-frame hook.

### Fixtures

- `tests/godot/fixture/project.godot` gains `config/version="1.0.0"`.
- A new `tests/godot/CHANGELOG.md` has `## 1.0.0` and one line, so the `gate-ship-smoke` dry run passes.
- `tests/ship_fakes.make_sandbox` writes a version and a `CHANGELOG.md` for the sandbox consumer.

## API / Interface Changes

| Interface | Input | Output / Error | Behavior |
|-----------|-------|----------------|----------|
| `python -m nmg_game_dev.ship` / `/ship` | `--bump`, `--version` | `ship.version_invalid`, `ship.version_not_increased`, `ship.version_missing`, `ship.changelog_missing` | sets the version, gates on the changelog |
| `game/project.godot` | — | `application/config/version` | only that line changes |
| `game/export_presets.cfg` | — | per-preset version keys | only those keys change |
| `release/RELEASE-NOTES.md` | — | version heading, Changes, Gates, Artifacts | |
| `NmgBuild.version()` | — | String | `application/config/version` |
| `NmgVersionLabel` | `prefix` | Label text | `prefix + version` |

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Edit only version keys as text | Selected | Keeps the rest of `project.godot` and `export_presets.cfg` byte-identical; `patch_preset_options` already does it for iOS |
| An `NmgBuild` autoload | Rejected | A static method needs no `project.godot` change or onboarding drift |
| Skipping the changelog check in a dry run | Rejected | The dry run already runs the budget gate; checking keeps it a faithful rehearsal |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #254 | 2026-11-18 | Initial feature design |
