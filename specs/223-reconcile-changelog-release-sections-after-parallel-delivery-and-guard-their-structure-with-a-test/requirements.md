# Defect Report: CHANGELOG release sections are duplicated, empty and out of order after parallel delivery

**Issue**: #223
**Date**: 2026-11-12
**Status**: Approved
**Author**: Rich Nunley

## Reproduction

1. Read the `## [x.y.z] - date` headings of `CHANGELOG.md` at commit `353e275` (VERSION 0.25.0).
2. Observe the order `[0.25.0]`, `[0.23.1]`, `[0.24.0]` (no bullets), `[0.22.1]`, `[0.22.0] - 2026-11-12`, `[0.23.0]`, `[0.21.6]`, `[0.22.0] - 2026-11-11` (no bullets), `[0.21.5]`, `[0.21.4]`, …
3. Compare each bullet's section with `VERSION` on `origin/main` right after its PR merged (`git log --first-parent`): many bullets sit under a different version, and no unit test checks the release structure.

## Expected vs Actual

| | Description |
|---|-------------|
| **Expected** | Each version that main's `VERSION` carried appears once, newest first, with at least one bullet. Each bullet sits under the version main carried right after its PR merged, and the newest release equals `VERSION` |
| **Actual** | `0.22.0` appears twice, `0.24.0` and one `0.22.0` are empty, versions are out of order, headings exist for versions main never carried (`0.21.6`, `0.22.1`, `0.23.1`), and bullets from 0.21.2 to 0.25.0 sit under the wrong versions |

## Acceptance Criteria

### AC1: Each released version appears once, newest first

**Given** `CHANGELOG.md`
**When** its `## [x.y.z] - YYYY-MM-DD` headings are read
**Then** every version appears exactly once, in strictly descending semver order, after `## [Unreleased]`, and the first released version equals the contents of `VERSION`

### AC2: No empty release sections

**Given** `CHANGELOG.md`
**When** each release section is read
**Then** every release section contains at least one `- ` bullet

### AC3: No entry is lost

**Given** the bullets of `CHANGELOG.md` at commit `353e275`
**When** the file is reconciled
**Then** every bullet line from that commit is still present with identical text, the reconciliation adds and duplicates no bullet line, and each of (#133), (#134), (#135), (#136), (#137), (#138), (#139), (#140), (#141), (#142), (#143), (#144), (#145), (#146), (#147), (#148), (#149), (#150), (#151), (#152), (#153), (#154), (#155), (#189), (#193), (#202), (#203), (#204), (#211), (#215) appears in exactly one bullet

### AC4: The structure is enforced by a test

**Given** the unit test suite
**When** `uv run pytest tests/unit` runs
**Then** a test fails if AC1 or AC2 is violated. This is shown by the checker rejecting synthetic changelogs with a duplicate version, an out-of-order version, an empty release section, and a newest release that differs from `VERSION`

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | Rewrite the part of `CHANGELOG.md` from `## [0.25.0]` down to, but not including, `## [0.21.1]` into one section per version main's `VERSION` carried: 0.25.0 and 0.24.0 dated 2026-11-12; 0.23.0, 0.22.0, 0.21.5, 0.21.4, 0.21.3 and 0.21.2 dated 2026-11-11. Each section uses Keep a Changelog subsections in the order Added, Changed, Fixed. Remove the `[0.23.1]`, `[0.22.1]` and `[0.21.6]` headings and the duplicate or empty headings. Place each bullet under the version main carried right after its PR merged | Must |
| FR2 | Preserve every bullet's text and keep each reconciled `(#N)` reference exactly once. Leave `## [Unreleased]`, the file header, and `[0.21.1]` and older unchanged | Must |
| FR3 | Add a unit test that checks unique, strictly descending, non-empty release sections below `## [Unreleased]`, and that the newest release equals `VERSION` | Must |

## Out of Scope

- Re-bucketing or re-dating `[0.21.1]` and older sections
- Changing how version preparation writes CHANGELOG sections
- Checking release dates or subsection names in the test

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #223 | 2026-11-12 | Initial defect report |
