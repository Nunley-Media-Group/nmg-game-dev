# Tasks: CHANGELOG release sections are duplicated, empty and out of order after parallel delivery

**Issue**: #223
**Date**: 2026-11-12
**Status**: Approved
**Author**: Rich Nunley

## Implementation Tasks

### T001: Reconcile the 0.21.2–0.25.0 CHANGELOG region

**File(s)**: `CHANGELOG.md`
**Type**: Modify
**Depends**: none
**Acceptance**:
- The region from `## [0.25.0]` down to `## [0.21.1]` is replaced with exactly the eight sections given in design.md's Fix Strategy (AC1, AC2, FR1).
- `## [Unreleased]`, the header, and `[0.21.1]` and older stay byte-identical to commit `353e275` (FR2).
- `diff <(git show 353e275:CHANGELOG.md | grep '^- ' | sort) <(grep '^- ' CHANGELOG.md | sort)` prints nothing (AC3, FR2).

### T002: Add the CHANGELOG structure test

**File(s)**: `tests/unit/test_changelog_structure.py`
**Type**: Create
**Depends**: T001
**Acceptance**:
- `changelog_problems(text, version)` behaves as specified in design.md (FR3).
- The checked-in `CHANGELOG.md` and stripped `VERSION` yield an empty problem list (AC1, AC2).
- Synthetic changelogs with a duplicate version, an ascending version pair, an empty release section, and a newest release different from the given version each yield at least one problem. The test fails when any of them yields none (AC4).
- Each of the 30 references listed in requirements.md AC3 appears in exactly one `- ` bullet of `CHANGELOG.md` (AC3).
- Passes `repository.tests` (`uv run pytest tests/unit tests/bdd -q`), `repository.lint`, `repository.format`, and `repository.types`. No Blender or Unreal process starts.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #223 | 2026-11-12 | Initial defect tasks |
