# Design: Block commits and builds that contain API keys in consumer projects

**Issue**: #255
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley

## Overview

A new package `src/nmg_game_dev/secrets/` holds `scan.py`, a stdlib-only module that is also runnable as a script, plus `__main__.py`. Onboarding copies `scan.py` into the consumer as `scripts/nmg_secret_scan.py` and installs a `pre-commit` hook that runs it on staged blobs. `/ship` imports the same module and scans the consumer's tracked files before any Godot command. Matches are always masked.

## Architecture

```
git commit ─► .git/hooks/pre-commit (marker "# nmg-game-dev secret scan")
               └─ python3 <toplevel>/scripts/nmg_secret_scan.py --staged   (copy of secrets/scan.py)

/ship ─► run_ship ─► _scan_secrets(consumer_root) ─► scan.scan_tracked(root) ─► ship.secret_found

python -m nmg_game_dev.secrets scan [--staged|--tracked] [--root PATH]  (same functions)
```

### Scanner (`src/nmg_game_dev/secrets/scan.py`, stdlib only)

- `PATTERNS: tuple[tuple[str, re.Pattern[str]], ...]`, in order:
  - `anthropic` `\bsk-ant-[A-Za-z0-9_-]{20,}`
  - `openai` `\bsk-(?!ant-)(?:proj-)?[A-Za-z0-9_-]{20,}`
  - `elevenlabs` `\bsk_[0-9a-f]{48}\b`
  - `meshy` `\bmsy_[A-Za-z0-9_-]{16,}`
  - `github` `\b(?:ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{22,})`
  - `aws` `\bAKIA[0-9A-Z]{16}\b`
  - `private-key` `-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----`
  - `env-file`: a staged or tracked path whose basename is exactly `.env`, reported as line 0 with the path as its value.
- `Match(path, line, pattern, value)`.
- `mask(value) = value[:4] + "…"`.
- `fingerprint(value) = "sha256:" + sha256(value.encode()).hexdigest()`.
- `Match.render() = f"{path}:{line}: {pattern} {mask(value)} ({fingerprint})"`. The raw value is never rendered or logged.
- `scan_text(path, data: bytes) -> list[Match]`:
  - Skip binary data, meaning a NUL byte in the first 8000 bytes.
  - Skip Git LFS pointers, meaning data starting with `version https://git-lfs.github.com/spec/v1`.
  - Otherwise decode as UTF-8 with `errors="replace"` and match each pattern line by line.
- Allow file: `load_allow(root) -> Allow` reads `<root>/.nmg/secret-scan-allow`. Each line is `sha256:<hex>` or `<path>:<pattern>`; blank lines and `#` comments are ignored, and a missing file means an empty allow list. `Allow.permits(match)` checks both forms.
- Sources:
  - `staged_files(root, run)`: `git -C root diff --cached --name-only -z --diff-filter=ACMR`, then each blob from `git -C root show :<path>` as bytes.
  - `tracked_files(root, run)`: `git -C root ls-files -z` with working-tree bytes. When `git -C root rev-parse --is-inside-work-tree` is not `true`, it walks every regular file under `root` instead, skipping `.git/`, `game/.godot/`, and `release/`.
- `scan_staged(root, run=subprocess.run) -> list[Match]` and `scan_tracked(root, run=...) -> list[Match]` return the unallowed matches sorted by path and line.
- `main(argv)`, used by the script and the CLI, takes `--staged` (default) or `--tracked`, and `--root` (default: `git rev-parse --show-toplevel`, else cwd). With matches it prints `secret scan: <n> match(es) blocked` and one rendered line each to stderr, then the remediation "Remove the key (keep keys in .env), or allow a false positive in .nmg/secret-scan-allow", and exits 1. With none it prints nothing and exits 0. A git failure prints an error and exits 2.

### CLI (`src/nmg_game_dev/secrets/__main__.py`)

`python -m nmg_game_dev.secrets scan [--staged|--tracked] [--root PATH]` delegates to `scan.main`.

### Onboarding (`src/nmg_game_dev/onboard/secrets_hook.py`, `runner.py`, `report.py`)

- `report.Status` gains `"conflict"`. `format_report` prints its remediation like drift, and onboarding still exits 0.
- `ensure_secret_scanner(name, framework, target, refresh)` calls `sync_file(<framework>/src/nmg_game_dev/secrets/scan.py, target, "scripts/nmg_secret_scan.py", ...)`, so the existing installed / unchanged / drift / refreshed states apply.
- `ensure_precommit_hook(name, target, *, run)`:
  - Not a work tree: `skipped`.
  - It resolves the hooks folder like `ensure_lfs_hooks`.
  - No `pre-commit`: write `HOOK_TEXT` and `chmod 0o755`, giving `installed`.
  - An existing hook containing `HOOK_MARKER`: `unchanged`.
  - A foreign hook: `StepResult(name, "conflict", "onboard.precommit_hook_conflict: a pre-commit hook already exists at <path>; it was left unchanged", remediation=f"Add this line to it: {CALL_LINE}")`.
  - `HOOK_TEXT`:
    ```sh
    #!/bin/sh
    # nmg-game-dev secret scan
    python3 "$(git rev-parse --show-toplevel)/scripts/nmg_secret_scan.py" --staged || exit 1
    ```
- `runner.py` appends `secret_scanner` and `precommit_hook` after `git_lfs_hooks`.

### Ship gate (`src/nmg_game_dev/ship/runner.py`)

`_scan_secrets(ship)` runs right after preflight and before `_import_project` (and before any other gate), on the consumer root `project_dir.parent`. Matches raise `ShipError(code="ship.secret_found", stage="secrets", message=f"{n} secret(s) found: " + "; ".join(m.render() for m in matches), remediation="Remove each key from the repository (keep keys in .env) or allow a false positive in .nmg/secret-scan-allow, then rerun the ship.")`. The gate runs in a dry run too, and appends `secrets: no matches` to `ship.gate_lines`.

## API / Interface Changes

| Interface | Input | Output / Error | Behavior |
|-----------|-------|----------------|----------|
| `python -m nmg_game_dev.secrets scan` / `scripts/nmg_secret_scan.py` | `--staged` \| `--tracked`, `--root` | exit 0 silent; exit 1 with masked lines; exit 2 on git failure | scans staged blobs or tracked files |
| `.nmg/secret-scan-allow` | `sha256:<hex>` or `<path>:<pattern>` lines | — | suppresses matches |
| `.git/hooks/pre-commit` | — | blocks the commit on exit 1 | installed by onboarding |
| onboarding steps `secret_scanner`, `precommit_hook` | — | installed / unchanged / drift / refreshed / conflict / skipped | never overwrites a foreign hook |
| `/ship` | — | `ship.secret_found` | first gate, also in dry run |

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Copy a stdlib scanner into the consumer's `scripts/` | Selected | The hook runs without the plugin, uv, or a versioned plugin cache path |
| Hook calling `uv run --project <plugin path>` | Rejected | Plugin cache paths change on every upgrade, so the hook would break |
| Failing onboarding on a foreign hook | Rejected | Onboarding reports problems as steps and exits 0; the conflict step names the line to add |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #255 | 2026-11-18 | Initial feature design |
