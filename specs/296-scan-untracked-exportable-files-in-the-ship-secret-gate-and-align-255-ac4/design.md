# Design: Scan untracked exportable files in the /ship secret gate

**Issue**: #296
**Date**: 2026-11-19
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/255-block-commits-and-builds-that-contain-api-keys-in-consumer-projects/

## Overview

Add a ship-specific file source to `src/nmg_game_dev/secrets/scan.py`: in a git work tree it yields the tracked files (as today) followed by the untracked, unignored files under the Godot project folder; outside a work tree it yields the existing walk. `/ship`'s `_scan_secrets` calls the new `scan_shippable` instead of `scan_tracked`. The module stays stdlib-only, so `/onboard-consumer` keeps copying it byte-for-byte to `scripts/nmg_secret_scan.py`.

## Architecture

```
/ship ─► run_ship ─► _scan_secrets(project_dir)
                       └─ scan.scan_shippable(consumer=project_dir.parent, project=project_dir.name)
                            ├─ not a work tree ─► _walk_files(root)                     (unchanged, #255)
                            └─ work tree ─► _tracked_from_index(git ls-files -z)
                                          + _tracked_from_index(git ls-files -z --others
                                                --exclude-standard -- <project>/)
                                            minus paths under <project>/.godot/
                       └─ _scan_files ─► _unallowed(load_allow(root)) ─► ship.secret_found
```

`--others` and the tracked list are disjoint, so no path is read twice. `_tracked_from_index` already skips symbolic links and non-regular paths (a nested repository is listed as `dir/` and is skipped). `--exclude-standard` applies `.gitignore`, `.git/info/exclude`, and the global excludes file.

## API / Interface Changes

| Interface | Input | Output / Error | Behavior |
|-----------|-------|----------------|----------|
| `scan.shippable_files(root, project, run=subprocess.run)` | consumer root `Path`, project folder name relative to root (`"game"`) | iterator of `(posix path, bytes)` | Work tree: tracked files then untracked unignored files under `<project>/`, excluding `<project>/.godot/`. Otherwise `_walk_files(root)`. Raises `GitError` when a git command fails inside a work tree |
| `scan.scan_shippable(root, project, run=subprocess.run)` | same | sorted unallowed `list[Match]` | `_unallowed(_scan_files(shippable_files(...)), load_allow(root))` |
| `ship.runner._scan_secrets(project_dir)` | Godot project folder | `None` or `ShipError` | Calls `scan_shippable(project_dir.parent, project_dir.name)`. `ship.secret_found` unchanged. `ship.secret_scan_failed` message reads "could not list the files to scan"; remediation still names `git -C <consumer> ls-files` |

`scan_tracked`, `tracked_files`, `scan_staged`, and `main` keep their signatures and behaviour.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Untracked unignored files under the project folder | Selected | Matches what Godot can export from a git consumer and keeps ignored local files (build output, scratch) from blocking ships |
| Walk all of `game/` regardless of `.gitignore` | Rejected | Contradicts AC2; ignored files under `game/` would fail the ship |
| Parse `export_presets.cfg` include/exclude filters | Rejected | Filters are per preset and globbed; the untracked list is the bounded, preset-independent superset |
| Add the untracked files to `scan_tracked` | Rejected | `scan_tracked` also backs the `--tracked` CLI, whose behaviour is out of scope |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #296 | 2026-11-19 | Initial feature design |
