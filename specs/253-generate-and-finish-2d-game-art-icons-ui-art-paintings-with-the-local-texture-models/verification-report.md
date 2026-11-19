# Verification Report: Generate and finish 2D game art (icons, UI art, paintings) with the local texture models

**Date**: 2026-11-19
**Issue**: #253
**Reviewer**: Claude (nmg-sdlc verify worker, gate phase)
**Scope**: Implementation verification against spec
**Verification head**: 724b7d4a0348a3b002c2bd343789a03bd064dde0

---

## Executive Summary

The review phase passed at head `4b54ad28ea44cb958e11c99f14a4744bc730a5b2`. Every acceptance criterion, functional requirement, design path and consumer row passed, and the only finding is `info`. This gate ran once at the merge-queue head `724b7d4`, which has the default branch integrated and version 0.31.0 prepared. It ran every pre-merge validation registered in `steering/manifest.json`. Coverage is complete (11 declared, 11 recorded). All 9 applicable required validations passed. The other 2 did not apply to the changed paths.

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 5 |
| Security | 5 |
| Performance | 4 |
| Testability | 5 |
| Error Handling | 5 |
| **Overall** | 4.8 |

### Implementation Status: Pass
**Total Issues**: 1 (info)

---

## Deterministic Steering Artifact and Ceiling

- Artifact: `.nmg-sdlc/verification/253.json`
- Identity: head `724b7d4a0348a3b002c2bd343789a03bd064dde0`, tree clean, steering `sha256:77bdf5578f21e673b6f758ef4c8931030f7637f4d45c8f1fdcfd42f58a5277d6`, spec `sha256:b44aa4e17295612c2b522ca75cc176836b90087bc4f8546757911cb97bdb68fc`
- Ceiling: none
- Coverage: declared 11, recorded 11, complete true; none missing, duplicated or unknown

---

## Issue Scope

- Active issue: #253
- Spec: `specs/253-generate-and-finish-2d-game-art-icons-ui-art-paintings-with-the-local-texture-models`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1, AC2, AC3, AC4, AC5, AC6, AC7]; FR [FR1, FR2, FR3, FR4, FR5, FR6, FR7]; tasks [T001, T002, T003, T004, T005, T006, T007, T008]; scenarios [SCN001, SCN002, SCN003, SCN004, SCN005, SCN006, SCN007]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":253,"specPath":"specs/253-generate-and-finish-2d-game-art-icons-ui-art-paintings-with-the-local-texture-models","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6","AC7"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6","FR7"],"tasks":["T001","T002","T003","T004","T005","T006","T007","T008"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006","SCN007"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Acceptance Criteria Verification

All criteria come from the review record `.nmg-sdlc/verification/253-review.json`. Each one is exercised through its real entry point: the `python -m nmg_game_dev.texture art` / `art-finish` CLI, the texture-gen MCP tools, or the finishing core. A fake model worker and synthetic images stand in for the hardware-bound backend. No criterion's tests mock the path under test.

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | 2D art generates without tiling | Pass | `art.py` run() writes raw takes with no seamless or derived maps, plus a manifest and contact sheet. The CLI and MCP `generate_art` paths go through `jobs.start`. BDD SCN001 checks that the bytes are unchanged and that exactly 5 files are written. |
| AC2 | Kinds set framing and size | Pass | `art.py` validate_request refuses any aspect/resolution pair more than 5% off the ratio and names the nearest valid resolutions. `test_art.py` is parametrized over every allowed resolution and aspect. |
| AC3 | The project style is shared | Pass | `style.py` project_style is used by both art and texture generation and recorded in their manifests. BDD SCN003 and `test_style.py` cover it. |
| AC4 | Existing takes are skipped | Pass | `art.missing_seeds` skips existing takes. When nothing is missing, no backend check or worker runs (BDD SCN004). |
| AC5 | Icons and UI art are cut out | Pass | `art_finish.py` does a corner flood fill, feathers the edge, crops, then applies the margin and baseline. Output is deterministic. BDD SCN005 checks a byte-identical rerun, and `test_art_finish.py` checks the geometry. |
| AC6 | A non-flat background is rejected | Pass | `art.background_not_flat` and `art.subject_cropped` are raised before any write (BDD SCN006). |
| AC7 | Paintings are finished without a cut-out | Pass | `_painting` resizes with LANCZOS to RGB 1920x1080 by default (BDD SCN007). |

Functional requirements FR1 to FR7, design paths DP1 to DP9, consumers CN1 to CN6 and the REPAIR row all passed in the review.

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Read the project style and record it in texture manifests | Complete | `style.py`, `generate.py` |
| T002 | Pass width and height through batches and the worker | Complete | ImageItem width/height (CN3) |
| T003 | Add art generation | Complete | `art.py` |
| T004 | Add art finishing | Complete | `art_finish.py` |
| T005 | Add the CLI commands and MCP tools | Complete | `__main__.py`, `server.py`, `tools.json` |
| T006 | Unit tests | Complete | `tests/unit/texture/test_art*.py`, `test_style.py` |
| T007 | BDD scenarios | Complete | `tests/bdd/test_game_art_bdd.py` SCN001-SCN007 |
| T008 | Document the art flow | Complete | `docs/onboarding/texture-models.md`, `docs/mcp/texture-gen.md`, steering tech snippet, CHANGELOG |

---

## Architecture Assessment

| Area | Score (1-5) | Notes |
|------|-------------|-------|
| SOLID | 5 | Generation (`art.py`), finishing (`art_finish.py`) and style (`style.py`) are separate modules. The MCP server and CLI only wrap them. |
| Security | 5 | Names and paths are validated, and there are no new credentials or network calls. |
| Performance | 4 | Existing takes are skipped and no backend starts when nothing is missing. Finishing uses NumPy flood fill. |
| Testability | 5 | Fake worker and synthetic images. Parametrized refusal tests would fail on off-ratio sizes. |
| Error Handling | 5 | Structured `texture.*` and `art.*` errors carry a remediation. All validation runs before any write, and writes go through temp file plus `os.replace`. |

Layer separation follows the structure steering: the texture-gen MCP server wraps the core without adding logic.

---

## Test Results

The steering verification runner ran each validation once at head `724b7d4`. No validation declares a `tier`, so every result records `tier: null` and `selection: null`. None is marked heavy.

| Validation | Applicable | Status | Evidence |
|------------|-----------|--------|----------|
| repository.tests | yes | Pass | `uv run pytest tests/unit tests/bdd -q`: 2227 passed, 24 skipped |
| repository.lint | yes | Pass | `uv run ruff check .`: All checks passed |
| repository.format | yes | Pass | `uv run ruff format --check .`: 455 files already formatted |
| repository.types | yes | Pass | `uv run mypy src tests`: no issues in 299 source files |
| gate-blender-headless | yes | Pass | `scripts/run-blender-tests.sh`: 436 passed, 4 skipped |
| gate-godot-headless | yes | Pass | `scripts/run-godot-tests.sh`: 28 passed, 0 failed |
| gate-mcp-schema | yes | Pass | `scripts/validate-mcp-tools.py` exited 0 |
| gate-shellcheck | no | Skipped (not applicable) | No `scripts/**.sh` changed |
| gate-ship-smoke | no | Skipped (not applicable) | No ship paths changed |
| plugin.validate | yes | Pass | `claude plugin validate .` exited 0 |
| plugin.session-smoke | yes | Pass | Plugin loaded via `--plugin-dir`; nmg-game-dev:blender connected |

**Gate Summary**: 9/9 applicable passed, 0 failed, 0 incomplete; 2 not applicable.

Smoke: `plugin.session-smoke` (extension `project.plugin-session-smoke`) passed for real after the required local command validations passed.

---

## Fixes Applied

None in this gate. The review's earlier findings (aspect tolerance, MCP empty seeds, docs, steering and `.mcp.json` text, jobs docstring) were repaired in implement before the review passed.

## Remaining Issues

| Severity | Category | Location | Issue | Reason Not Fixed |
|----------|----------|----------|-------|------------------|
| Info | Error Handling | `mcp-servers/texture-gen/tools.json` | The `generate_art` `resolution` schema does not describe the allowed values: a multiple of 64 from 256 to 2048, refused when it misses a 16:9 or 3:2 aspect by more than 5%. | Info only. The structured error's remediation names valid resolutions, so callers recover. |

## Recommendation

**Ready for PR.** All acceptance criteria are met, and every applicable required validation passed at the exact merge-queue head.
