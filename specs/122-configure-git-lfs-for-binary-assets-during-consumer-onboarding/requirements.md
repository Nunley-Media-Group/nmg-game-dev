# Requirements: Configure Git LFS for binary assets during consumer onboarding

**Issue**: #122
**Date**: 2026-11-01
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/7-consumer-onboarding-onboard-consumer-skill-asset-contract-install-and-onboarding-docs/

## User Story

**As an** NMG game developer onboarding a consumer project
**I want** `/onboard-consumer` to configure Git LFS for the binary asset types the pipeline produces
**So that** `.blend`, `.glb`, `.uasset`, texture, and audio files commit as LFS pointers instead of full blobs in git history

## Background

The pipeline writes large binaries into a consumer repo: Blender sources under `SourceArt/`, Meshy GLBs under `SourceArt/Meshy/`, generated textures, and finalized `.uasset` files under `Content/`. Today `run_onboard` in `src/nmg_game_dev/onboard/runner.py` ends with the `gitignore_env` step and nothing writes `.gitattributes` or installs LFS hooks. Preflight (`_check_prerequisites`) checks `git` but not `git-lfs`.

This feature adds a `gitattributes_lfs` step that owns a marker-delimited managed block in the consumer `.gitattributes`, a `git_lfs_hooks` step that installs the LFS hooks in the consumer repo, and a `git-lfs` preflight check. Both steps report with the existing `installed` / `unchanged` / `drift` / `refreshed` vocabulary, plus a new `skipped` status for a consumer that is not a git work tree.

## Acceptance Criteria

### AC1: Fresh consumer gets the LFS block

**Given** a consumer with no `.gitattributes` and `git-lfs` on PATH
**When** onboarding runs
**Then** `.gitattributes` is created containing a managed block delimited by `# nmg-game-dev:begin` and `# nmg-game-dev:end`, with one `<pattern> filter=lfs diff=lfs merge=lfs -text` line per pattern in FR2
**And** the report prints `installed gitattributes_lfs: ...`

### AC2: Consumer lines outside the block are preserved

**Given** a `.gitattributes` with consumer-authored lines and no managed block
**When** onboarding runs
**Then** the managed block is appended and every existing line is kept byte-for-byte

### AC3: Re-run is idempotent

**Given** a `.gitattributes` whose managed block matches the framework block
**When** onboarding runs again
**Then** the file is unchanged and the report prints `unchanged gitattributes_lfs: ...`

### AC4: Edited block reports drift and refresh restores it

**Given** a `.gitattributes` whose managed block differs from the framework block
**When** onboarding runs without `--refresh`
**Then** the file is unchanged and the report prints `drift gitattributes_lfs: ...` with remediation `re-run with --refresh`
**When** onboarding runs with `--refresh`
**Then** only the managed block is replaced, lines outside it are kept, and the report prints `refreshed gitattributes_lfs: ...`

### AC5: LFS hooks are installed in the consumer repo

**Given** a consumer git work tree with `git-lfs` on PATH and no LFS `pre-push` hook in its hooks directory
**When** onboarding runs
**Then** `git -C <consumer> lfs install --local` runs and the report prints `installed git_lfs_hooks: ...`
**And** on a re-run with the hook present, no `git lfs install` runs and the report prints `unchanged git_lfs_hooks: ...`

### AC6: Missing git-lfs fails preflight

**Given** `git-lfs` is not on PATH
**When** onboarding runs
**Then** it raises `onboard.git_lfs_missing` with remediation `Install Git LFS (brew install git-lfs), then re-run onboarding.`
**And** no consumer file is written

### AC7: Consumer that is not a git repo

**Given** a consumer directory that is not inside a git work tree
**When** onboarding runs
**Then** `.gitattributes` is still written as in AC1, `git_lfs_hooks` reports `skipped` with detail `not a git repository`, and onboarding continues

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | Add a `gitattributes_lfs` step to `run_onboard` that maintains a marker-delimited managed block (`# nmg-game-dev:begin` … `# nmg-game-dev:end`) in the consumer `.gitattributes`, creating the file when missing and never changing bytes outside the block. | Must |
| FR2 | The managed block tracks these patterns in LFS, in this order: `*.blend`, `*.glb`, `*.fbx`, `*.obj`, `*.abc`, `*.usd`, `*.usdz`, `*.uasset`, `*.umap`, `*.png`, `*.jpg`, `*.jpeg`, `*.tga`, `*.tif`, `*.tiff`, `*.exr`, `*.hdr`, `*.psd`, `*.wav`, `*.mp3`, `*.ogg`, `*.mp4`. The list lives in one constant that the step and the tests both read. | Must |
| FR3 | A managed block that differs from the framework block reports `drift` (remediation `re-run with --refresh`) and leaves the file unchanged without `--refresh`; with `--refresh` it is replaced in place and reports `refreshed`. | Must |
| FR4 | Preflight raises `onboard.git_lfs_missing` when `git-lfs` is not on PATH, after the `git` check and before the first consumer write. | Must |
| FR5 | Add a `git_lfs_hooks` step that, when the consumer is a git work tree and its hooks directory has no `pre-push` containing `git lfs`, runs `git -C <consumer> lfs install --local` and reports `installed`; reports `unchanged` when the hook is present; reports `skipped` with detail `not a git repository` outside a git work tree; raises `onboard.git_lfs_hooks_failed` when the install command exits non-zero. | Must |
| FR6 | Add `skipped` to the onboarding report status vocabulary. | Must |
| FR7 | Both new steps run immediately after `gitignore_env`, `gitattributes_lfs` first, so the order of existing steps is unchanged. | Must |
| FR8 | Update `skills/onboard-consumer/references/install-steps.md` (preflight and step tables), `skills/onboard-consumer/SKILL.md` (status list in flow step 3 and failure modes), and `docs/onboarding/index.md` for both steps, both new error codes, and how to convert files already committed as blobs (`git add --renormalize .`). | Must |

## Out of Scope

- Running `git add --renormalize .` or `git lfs migrate` from onboarding; docs describe the commands only.
- `.gitignore` changes beyond the existing `gitignore_env` step.
- LFS file locking (`lockable`) for `.uasset` / `.umap`.
- Changing where `finalize-asset` or `texture-gen` write their outputs.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #122 | 2026-11-01 | Initial feature spec |
