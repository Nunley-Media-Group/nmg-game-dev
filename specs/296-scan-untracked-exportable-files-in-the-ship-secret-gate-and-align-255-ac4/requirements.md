# Requirements: Scan untracked exportable files in the /ship secret gate

**Issue**: #296
**Date**: 2026-11-19
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/255-block-commits-and-builds-that-contain-api-keys-in-consumer-projects/

## User Story

**As a** consumer project maintainer shipping a Godot build
**I want** `/ship`'s secret gate to scan every file under `game/` that Godot could export
**So that** an API key in an untracked file never ends up inside a shipped build

## Background

#255 added a `/ship` gate that scans the consumer for API keys before any Godot command. In a git work tree it scans only git-tracked files (`scan_tracked`). Godot exports the files under `game/` that the export preset includes whether or not git tracks them, so a key in an untracked, unignored file under `game/` passes the gate and ships.

Outside a git work tree the gate walks every regular file under the consumer root. It skips `.env` and `.env.*` files, `.claude/settings.local.json`, and the `.git/`, `release/`, `game/.godot/`, `.venv/`, and `node_modules/` folders. Keys are meant to live in `.env` and `.claude/settings.local.json`, and without git the scan cannot tell those local stores from committed files, so scanning them would block every ship. This spec states that behaviour; #255 AC4's "any regular file" wording predates it.

## Acceptance Criteria

### AC1: Untracked files that would be exported are scanned

**Given** a consumer git repository with an untracked file under `game/` that `.gitignore` does not cover and that contains an API key
**When** `/ship <target>` runs its secret gate, including with `--dry-run`
**Then** it stops with `ship.secret_found` before any Godot command, listing the match masked as `path:line: pattern xxxx… (sha256:…)`, the same as for a tracked file, and the unmasked value appears in no output

### AC2: Ignored and non-exported untracked files are not scanned

**Given** a consumer git repository whose only key is in an untracked file that `.gitignore` covers, an untracked file outside `game/`, or an untracked file under `game/.godot/`
**When** `/ship <target> --dry-run` runs its secret gate
**Then** the gate passes (`secrets: no matches`)

### AC3: Outside git, local secret stores are skipped and every other file is scanned

**Given** a consumer root that is not a git work tree
**When** `/ship <target> --dry-run` runs its secret gate
**Then** a key in `.env`, `.env.<suffix>`, `.claude/settings.local.json`, or under a `.venv/` or `node_modules/` folder does not stop the ship, and a key in any other regular file under the root (outside `.git/`, `release/`, and `game/.godot/`) stops it with `ship.secret_found`

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | In a git work tree, the `/ship` secret gate scans the tracked files plus the untracked files under the Godot project folder that `git ls-files --others --exclude-standard` lists, with the same patterns, `.env` rule, masking, and `.nmg/secret-scan-allow` handling as tracked files | Must |
| FR2 | Untracked files under the project's `.godot/` folder, symbolic links, and non-regular paths are not scanned | Must |
| FR3 | Outside a git work tree the gate keeps the #255 walk and its exclusions unchanged | Must |
| FR4 | The scanner stays standard-library only, and `--staged` / `--tracked` CLI behaviour is unchanged | Must |
| FR5 | `docs/skills/ship.md` and `docs/onboarding/index.md` describe the untracked-file scan and the non-git exclusions | Must |

## Out of Scope

- The pre-commit hook, which scans staged files
- The `--tracked` CLI mode of `scripts/nmg_secret_scan.py`
- Reading Godot export preset include/exclude filters to narrow the scan

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #296 | 2026-11-19 | Initial feature spec |
