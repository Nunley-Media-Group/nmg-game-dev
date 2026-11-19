# Requirements: Block commits and builds that contain API keys in consumer projects

**Issue**: #255
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley

## User Story

**As a** game developer whose project uses Meshy, ElevenLabs, and other API keys
**I want** a commit or a build that contains a key to be stopped
**So that** keys never reach git history or a shipped game

## Background

Consumer projects keep API keys in a git-ignored `.env`. A key can still reach a commit through a pasted script, a log, or a config file, and nothing checks for this. Onboarding already installs Git LFS hooks and refuses to overwrite a foreign hook; `/ship` has no secret check.

## Acceptance Criteria

### AC1: A commit containing a key is blocked

**Given** a consumer project onboarded by `/onboard-consumer`
**When** a commit stages a file containing:
- a Meshy key (`msy_…`);
- an ElevenLabs key (`sk_` + 48 hex);
- an Anthropic key (`sk-ant-…`);
- an OpenAI key (`sk-…`, including `sk-proj-…`);
- a GitHub key (`ghp_…`, `github_pat_…`);
- an AWS key (`AKIA…`);
- a PEM private-key header;
- or it stages a file named `.env`.

**Then** the pre-commit hook exits 1 and prints one line per match. Each line gives the file, the line number (0 for `.env`), the pattern name, the value masked to its first 4 characters followed by `…`, and the match's fingerprint. The unmasked value appears nowhere in the output.

### AC2: A clean commit passes silently

**Given** staged changes with no match
**When** the hook runs
**Then** it exits 0 with no output

### AC3: False positives can be allowed

**Given** `.nmg/secret-scan-allow` lists a match's fingerprint (`sha256:<hex of the matched value>`) or a `<path>:<pattern-name>` pair (blank lines and `#` comments ignored)
**When** the scan runs
**Then** that match is not reported, and other matches still are

### AC4: `/ship` refuses to build with a key in tracked files

**Given** a tracked file in the consumer repository contains a match, or (when the consumer root is not a git work tree) any regular file under the root does
**When** `/ship <target>` runs its gates, including with `--dry-run`
**Then** it stops with `ship.secret_found` before any Godot command, listing the masked matches; with no match the gate passes and no secret value is printed

### AC5: Onboarding installs the hook safely

**Given** onboarding runs in a git work tree
**When** there is no pre-commit hook, the nmg hook, or a foreign pre-commit hook
**Then** it installs the hook and `scripts/nmg_secret_scan.py` (`installed`), reports `unchanged`, or reports a `conflict` step whose detail names `onboard.precommit_hook_conflict` and whose remediation names the line to add to the existing hook (`python3 "$(git rev-parse --show-toplevel)/scripts/nmg_secret_scan.py" --staged || exit 1`); it never overwrites a foreign hook, and outside a git work tree the hook step is `skipped`

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | Add `python -m nmg_game_dev.secrets scan [--staged \| --tracked]` (stdlib-only scanner) with the AC1 patterns and the allow file | Must |
| FR2 | Onboarding copies the scanner to `scripts/nmg_secret_scan.py` and installs a `pre-commit` hook that runs it with `--staged`, following the LFS hook pattern | Must |
| FR3 | `/ship` runs the tracked-file scan as its first gate | Must |
| FR4 | Never print or log an unmasked match | Must |
| FR5 | Tests cover each pattern, masking, allow entries, binary and LFS-pointer skips, the hook install states, and the ship gate | Must |
| FR6 | Document the hook and the allow file in the onboarding docs | Should |

## Out of Scope

- Scanning git history or rewriting it.
- Revoking or rotating keys.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #255 | 2026-11-18 | Initial feature spec |
