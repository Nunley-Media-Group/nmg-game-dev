# Verification Report: Let one .blend hold several rigged characters that share clip names

**Date**: 2026-11-19
**Issue**: #233
**Reviewer**: Claude (nmg-sdlc verify worker, gate phase)
**Scope**: Implementation verification against spec

**Verification head**: 5a4064ba62391e1f25d9aa9f136ea0abfeea5a29

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 5 |
| Security | 5 |
| Performance | 5 |
| Testability | 4 |
| Error Handling | 4 |
| **Overall** | 4.7 |

### Implementation Status: Pass
**Total Issues**: 5 (all `info`; none blocking, major or minor)

The review of source head `2703969` passed with no finding above `info`. The gate ran once at the
merge-queue head `5a4064b`, which has the default branch integrated and the version prepared. All 8
applicable registered validations passed. The 3 that do not apply were recorded as skipped. Coverage
is complete (11 declared, 11 recorded).

---

## Issue Scope

- Active issue: #233
- Spec: `specs/233-let-one-blend-hold-several-rigged-characters-that-share-clip-names`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1-AC9]; FR [FR1-FR8]; tasks [T001-T007]; scenarios [SCN001-SCN009]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":233,"specPath":"specs/233-let-one-blend-hold-several-rigged-characters-that-share-clip-names","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6","AC7","AC8","AC9"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6","FR7","FR8"],"tasks":["T001","T002","T003","T004","T005","T006","T007"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006","SCN007","SCN008","SCN009"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

- Artifact: `.nmg-sdlc/verification/233.json` (pre-merge tier; no tiers declared, so every applicable required validation ran)
- Identity: head `5a4064ba62391e1f25d9aa9f136ea0abfeea5a29`, clean tree
- Ceiling: none
- Coverage: declared 11, recorded 11, complete `true`, no missing, duplicate or unknown entries

---

## Acceptance Criteria Verification

The evidence below comes from the passed review record `.nmg-sdlc/verification/233-review.json`.

| AC | Description | Status | Exercised | Evidence |
|----|-------------|--------|-----------|----------|
| AC1 | An @-suffixed action exports under its bare clip name | Pass | real entry point | `finalize_core/anims.py:81-156,265-282`; `tests/blender/test_finalize_anims.py`, `tests/blender/test_shared_clip_names_bdd.py::test_scn001_*` |
| AC2 | Two characters in one file each export their own clip | Pass | real entry point | per-collection own suffix in `resolve()` (`anims.py:92`); `test_scn002_*` re-imports both GLBs and checks they differ |
| AC3 | Unsuffixed action names keep working | Pass | real entry point | `clip_hash` payload is unchanged for unsuffixed actions (`anims.py:187-208`); existing unsuffixed tests are unchanged and pass |
| AC4 | A suffix naming another rig stops the export | Pass | **mocked** (host side) | `finalize.clip_rig_mismatch` is raised in Blender (`anims.py:230-238`) and on the host (`src/nmg_game_dev/pipeline/anims.py:284-299`). The host test uses `FakeStepRunner` in place of the Blender probe |
| AC5 | Two actions giving one clip name stop the export | Pass | **mocked** (host side) | `finalize.clip_name_duplicate` is raised in Blender (`anims.py:239-251`) and on the host (`pipeline/anims.py:300-314`). The host test uses `FakeStepRunner` |
| AC6 | The bare clip name is still validated | Pass | **mocked** (host side) | `valid_clip_name(bare)` (`anims.py:144`); the Blender test is real and the host BDD SCN006 uses `FakeStepRunner` |
| AC7 | Importing a clip onto one character leaves the others alone | Pass | real entry point | `rig_core/retarget.py:386-398` names the action `<clip>@SK_<Name>`; `test_scn007_*` |
| AC8 | Re-importing a clip replaces only that rig's action | Pass | real entry point | `retarget.py:394-397`; `test_scn008_*` (no `.001` actions) |
| AC9 | The rule is documented | Pass | real entry point | `docs/asset-contract.md`, `docs/mcp/finalize.md`, `skills/finalize-asset/SKILL.md`, `docs/rigging-and-animation.md`; BDD SCN009 |

Criteria whose tests mock the path under test: **AC4, AC5, AC6**. In each case the host-side refusal
is tested against a faked Blender probe. The Blender-side refusal is tested in real Blender.

FR1-FR8, design paths DP1-DP7 and consumers CN1-CN8 all passed in the review record.

---

## Task Completion

| Task | Description | Status |
|------|-------------|--------|
| T001 | Resolve and probe clips by bare clip name | Complete |
| T002 | Fail the export on host for mismatched and duplicate clips | Complete |
| T003 | Import clips as per-rig actions | Complete |
| T004 | Document the clip naming rule and the new failures | Complete |
| T005 | Blender tests for resolution, export, and import | Complete |
| T006 | Host unit tests and the fake probe | Complete |
| T007 | BDD scenarios for every acceptance criterion | Complete |

---

## Architecture Assessment

| Area | Score (1-5) | Notes |
|------|-------------|-------|
| SOLID | 5 | The Blender core resolves and exports, and the host pipeline refuses. Probe output is only extended, and the new constructor arguments are optional |
| Security | 5 | No new inputs from outside the system, credentials or subprocess surfaces |
| Performance | 5 | Resolution is linear in actions per collection, and the cache key is unchanged for unsuffixed clips |
| Testability | 4 | Real-Blender proofs cover AC1-3, 7 and 8. Host refusals use a fake probe (F3 and F4 are `info` gaps) |
| Error Handling | 4 | Every refusal happens before any write, and the refusals are ordered mismatch, then duplicate, then invalid. One defensive message is worded imprecisely (F2) |

The layers stay separate. `finalize_core` and `rig_core` hold the Blender logic, and
`src/nmg_game_dev/pipeline/anims.py` composes the steps and refuses. Structured `PipelineError`
codes reach the MCP envelope through the existing path, which needed no change.

---

## Test Results (pre-merge gate)

| Validation | Tier | Selection | Status | Evidence |
|------------|------|-----------|--------|----------|
| `repository.tests` | — | — | Pass | `uv run pytest tests/unit tests/bdd -q` exited 0 |
| `repository.lint` | — | — | Pass | `uv run ruff check .` exited 0 |
| `repository.format` | — | — | Pass | `uv run ruff format --check .` exited 0 |
| `repository.types` | — | — | Pass | `uv run mypy src tests` exited 0 |
| `gate-blender-headless` | — | — | Pass | `scripts/run-blender-tests.sh` exited 0 |
| `gate-godot-headless` | — | — | Pass | `scripts/run-godot-tests.sh` exited 0 |
| `gate-mcp-schema` | — | — | Skipped (not applicable) | the change touches no `mcp-servers/**` |
| `gate-shellcheck` | — | — | Skipped (not applicable) | the change touches no `scripts/**.sh` |
| `gate-ship-smoke` | — | — | Skipped (not applicable) | the change touches no ship paths |
| `plugin.validate` | — | — | Pass | `claude plugin validate .` exited 0 |
| `plugin.session-smoke` | — | — | Pass | plugin loaded through `--plugin-dir`, and `nmg-game-dev:blender` connected |

**Gate Summary**: 8/8 applicable gates passed, 0 failed, 0 incomplete. 3 were not applicable.

The project declares no `nmg-sdlc-smoke` validation. `plugin.session-smoke` is the registered
session smoke, and it passed.

---

## Fixes Applied

None in the gate phase. The review passed with no finding above `info`.

## Remaining Issues

All remaining items are `info`. None blocks the merge.

| Severity | Category | Location | Issue | Reason Not Fixed |
|----------|----------|----------|-------|------------------|
| info | Error Handling | `plugins/nmg-game-dev-blender-addon/finalize_core/anims.py` | F1: the risk that the glTF animation is named after the suffixed action does not hold, because both exports carry `Animation`. A test could pin this | Optional hardening |
| info | Error Handling | `plugins/nmg-game-dev-blender-addon/finalize_core/anims.py` | F2: the defensive `clip_name_invalid` message says "action" but shows the bare clip name. Only reachable if the host check is bypassed | Cosmetic; the host message is correct |
| info | Testing | `tests/blender/test_finalize_anims.py` | F3: AC3 hash stability is compared with a hash the new code computes, not a pinned pre-change hash | The payload is unchanged by construction |
| info | Testing | `tests/blender/test_shared_clip_names_bdd.py` | F4: the SCN001 Blender proof asserts the record name, not `nmg-animations.json` | Covered by composition with host unit tests |
| info | Error Handling | `plugins/nmg-game-dev-blender-addon/rig_core/retarget.py` | F5: a legacy unsuffixed action held on the NLA can trigger `clip_name_duplicate` after an upgrade | Accepted in `design.md`, and the docs explain it |

---

## Recommendation

**Ready for PR.** Every acceptance criterion, functional requirement and task is met. All applicable
registered gates passed at `5a4064ba62391e1f25d9aa9f136ea0abfeea5a29`, and steering coverage is
complete.
