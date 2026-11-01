# Tasks: Register the project verification gates and a UE compile extension in steering

**Issue**: #123
**Date**: 2026-11-01
**Status**: Approved
**Author**: Rich Nunley

## Implementation Tasks

### T001: Register the validations and extension

**File(s)**: `steering/manifest.json`
**Type**: Modify
**Depends**: none
**Acceptance**:
- AC1, FR1: the six validations are registered as required with the conditions and commands in the tech table.
- FR2: the `project.ue-compile` extension is registered under `extensions`.

### T002: Add the UE compile extension

**File(s)**: `steering/extensions/ue-compile.mjs`
**Type**: Create
**Depends**: none
**Acceptance**:
- AC2, FR2: the module exports `extension` with provider `project.ue-compile` and returns `passed` / `failed` / `incomplete` as specified, importing only Node built-ins.

### T003: Mirror the manifest in the tech steering

**File(s)**: `steering/snippets/project-tech.md`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- AC3, FR3: `## Verification Gates` lists every registered validation id, condition, command, and host prerequisite; the `verify-skip` rule is gone; UE Automation and E2E are listed under "Not gated yet".

### T004: Verify the steering changes

**File(s)**: `specs/123-register-the-project-verification-gates-and-a-ue-compile-extension-in-steering/verification-report.md`
**Type**: Create
**Depends**: T001, T002, T003
**Acceptance**:
- AC1–AC3 are checked against `steering/manifest.json`, `steering/extensions/ue-compile.mjs`, and `steering/snippets/project-tech.md`, and the registered `repository.*` validations pass.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #123 | 2026-11-01 | Initial feature tasks |
