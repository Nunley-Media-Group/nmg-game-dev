# Design: Configure Git LFS for binary assets during consumer onboarding

**Issue**: #122
**Date**: 2026-11-01
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/7-consumer-onboarding-onboard-consumer-skill-asset-contract-install-and-onboarding-docs/

## Overview

A new module `src/nmg_game_dev/onboard/lfs.py` holds the LFS pattern list, the managed `.gitattributes` block, and the two step functions. `runner.py` calls them right after `ensure_gitignore_env` and adds a `git-lfs` check to `_check_prerequisites`. `report.py` gains a `skipped` status. All git commands go through the injected `Runner` using `git -C <consumer>` (the `Runner` signature has no cwd, matching `unreal.py`), so tests never need real git or git-lfs.

## Architecture

```
run_onboard
  ├─ _check_prerequisites: which("git") → onboard.git_missing
  │                        which("git-lfs") → onboard.git_lfs_missing   (new, before any write)
  ├─ … existing steps …
  ├─ ensure_gitignore_env("gitignore_env", target/.gitignore)
  ├─ ensure_gitattributes_lfs("gitattributes_lfs", target/.gitattributes, refresh=refresh)   (new)
  └─ ensure_lfs_hooks("git_lfs_hooks", target, run=run)                                     (new)
```

### `ensure_gitattributes_lfs(name, path, *, refresh) -> StepResult`

Modeled on `instructions.upsert_block` plus the drift/refresh semantics of `files.sync_file`.

- Read and write with `newline=""` (`path.open(..., newline="")` / `write_text(..., newline="")`) so CRLF and every byte outside the block are preserved.
- File missing → write `block_text() + "\n"`; `installed`, detail `created .gitattributes with the nmg-game-dev LFS block`.
- Both markers present (`BEGIN` index before `END` index) → slice `text[start:end+len(END)]`:
  - equal to `block_text()` → `unchanged`, detail `.gitattributes LFS block is current`.
  - differs, `refresh` false → `drift`, detail `.gitattributes LFS block differs from the framework block; content left unchanged`, remediation `REFRESH_REMEDIATION`.
  - differs, `refresh` true → replace only that slice; `refreshed`, detail `replaced the nmg-game-dev LFS block in .gitattributes`.
- Otherwise (no complete block) → append: a `\n` if the text lacks a final newline, a blank spacer line if the text is non-blank, then `block_text() + "\n"`; `installed`, detail `added the nmg-game-dev LFS block to .gitattributes`.

### `ensure_lfs_hooks(name, target, *, run) -> StepResult`

1. `run(["git", "-C", str(target), "rev-parse", "--is-inside-work-tree"], None)`; non-zero exit or stdout not `true` → `skipped`, detail `not a git repository`.
2. `run(["git", "-C", str(target), "rev-parse", "--git-path", "hooks"], None)`; resolve the stripped stdout against `target` when relative (handles worktrees and `core.hooksPath`).
3. `<hooks>/pre-push` exists and its text contains `git lfs` → `unchanged`, detail `LFS hooks present in <hooks dir relative or absolute>`.
4. Else `run(["git", "-C", str(target), "lfs", "install", "--local"], None)`; exit 0 → `installed`, detail `ran git lfs install --local`; non-zero → raise `OnboardError("onboard.git_lfs_hooks_failed", "git lfs install --local failed in <target>: <stderr>", "Check the repository's existing git hooks (git lfs install --local refuses to overwrite a custom pre-push), then re-run onboarding.")`.

## API / Interface Changes

| Interface | Input | Output / Error | Behavior |
|-----------|-------|----------------|----------|
| `nmg_game_dev.onboard.lfs.LFS_PATTERNS` | — | `tuple[str, ...]` of the 22 FR2 patterns | Single source for the block and the tests |
| `nmg_game_dev.onboard.lfs.BEGIN` / `END` | — | `"# nmg-game-dev:begin"` / `"# nmg-game-dev:end"` | Managed-block markers |
| `nmg_game_dev.onboard.lfs.block_text()` | — | `BEGIN`, one `<pattern> filter=lfs diff=lfs merge=lfs -text` line per pattern, `END`, joined by `\n`, no trailing newline | Framework block |
| `ensure_gitattributes_lfs(name, path, *, refresh)` | step name, `.gitattributes` path, refresh flag | `StepResult` (`installed`/`unchanged`/`drift`/`refreshed`) | AC1–AC4 |
| `ensure_lfs_hooks(name, target, *, run)` | step name, consumer root, `Runner` | `StepResult` (`installed`/`unchanged`/`skipped`) or `OnboardError onboard.git_lfs_hooks_failed` | AC5, AC7 |
| `_check_prerequisites` | `which` | `OnboardError onboard.git_lfs_missing`, message `git-lfs is not on PATH; binary assets cannot be tracked in Git LFS.`, remediation `Install Git LFS (brew install git-lfs), then re-run onboarding.` | AC6; runs after the git check |
| `report.Status` | — | `Literal["installed", "unchanged", "drift", "refreshed", "skipped"]` | `format_report` is unchanged: `skipped git_lfs_hooks: not a git repository` |

## State and UI Behavior

Report lines, in order after `gitignore_env`:

```
installed gitattributes_lfs: created .gitattributes with the nmg-game-dev LFS block
installed git_lfs_hooks: ran git lfs install --local
```

A drift line is followed by `  Remediation: re-run with --refresh`, as for other steps; the command still exits 0. Module and package docstrings in `runner.py`, `report.py`, and `onboard/__init__.py` that list the step order or status set are updated to include the new steps and `skipped`.

## Test seams

- `tests/onboard_fakes.py` `FakeRunner` gains a keyword `work_tree: bool = False`. Before its generic `"rev-parse" in args` branch it answers `rev-parse --is-inside-work-tree` (stdout `true` rc 0 when `work_tree`, else rc 128), `rev-parse --git-path hooks` (stdout `.git/hooks`), and `lfs install --local` (creates `<target>/.git/hooks/pre-push` containing `git lfs pre-push "$@"`, rc 0; rc 1 with stderr when `fail == "lfs-install"`). Existing tests keep the default `work_tree=False`, so `git_lfs_hooks` reports `skipped` there.
- `test_rerun_is_a_no_op` asserts every step is `unchanged` except `git_lfs_hooks`, which is `skipped`.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Extend `instructions.upsert_block` with a marker parameter | Rejected | `upsert_block` always rewrites a differing block (`refreshed`), but FR3 needs drift-without-refresh; a separate function keeps both behaviors simple |
| `sync_file` a whole framework `.gitattributes` | Rejected | Would overwrite consumer-authored lines (AC2) |
| Detect hooks by reading `.git/hooks` directly | Rejected | Breaks for worktrees and `core.hooksPath`; `git rev-parse --git-path hooks` resolves both |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #122 | 2026-11-01 | Initial feature design |
