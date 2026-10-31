# Verification Report: Optional Meshy model generation and retexturing

**Date**: 2026-10-31
**Issue**: #98
**Reviewer**: Claude (nmg-sdlc verify worker, architecture-reviewer inline)
**Scope**: Implementation verification against spec
**Verification head**: 353c5b69d55c76604ff44c53f1a58db5fd87afc8

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 4.6 |
| Security | 5 |
| Performance | 4 |
| Testability | 5 |
| Error Handling | 5 |
| **Overall** | 4.8 |

### Implementation Status: Pass
**Total Issues**: 3 (all Low, none blocking)

All 14 acceptance criteria and 12 tasks are implemented and covered by unit, BDD, and headless Blender tests. Every manifest-registered validation passed at the verification head with complete coverage (5 declared, 5 recorded). The real plugin session smoke loaded the plugin through `--plugin-dir` and showed `plugin:nmg-game-dev:meshy` connected with 3 tools beside the existing servers.

---

## Issue Scope

- Active issue: #98
- Spec: `specs/98-add-optional-meshy-model-generation-and-retexturing-through-the-meshy-api`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1–AC14]; FR [FR1–FR12]; tasks [T001–T012]; scenarios [SCN001–SCN014]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":98,"specPath":"specs/98-add-optional-meshy-model-generation-and-retexturing-through-the-meshy-api","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6","AC7","AC8","AC9","AC10","AC11","AC12","AC13","AC14"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6","FR7","FR8","FR9","FR10","FR11","FR12"],"tasks":["T001","T002","T003","T004","T005","T006","T007","T008","T009","T010","T011","T012"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006","SCN007","SCN008","SCN009","SCN010","SCN011","SCN012","SCN013","SCN014"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

`node sdlc-verify-steering.mjs --project . --issue 98 --spec specs/98-… --base main --controller-run-id 9eeadb71-…` → `.nmg-sdlc/verification/98.json`: `ok: true`, `ceiling: null`, coverage `declared: 5, recorded: 5, complete: true` (no missing, duplicate, or unknown ids). All results carry identity head `353c5b69…`, tree `clean`.

| Validation | Required | Status | Evidence |
|------------|----------|--------|----------|
| `repository.tests` | yes | passed | `uv run pytest tests/unit tests/bdd -q` → 788 passed, 4 skipped |
| `repository.lint` | yes | passed | `uv run ruff check .` → All checks passed |
| `repository.types` | yes | passed | `uv run mypy src tests` → no issues in 169 files |
| `plugin.validate` | yes | passed | `claude plugin validate .` → passed with warnings (pre-existing directory warnings: LICENSE, icon, privacy URL) |
| `plugin.session-smoke` | yes | passed | Ephemeral project, `claude --plugin-dir`; `/mcp` shows blender, finalize, **meshy (3 tools)**, texture-gen, unreal all connected |

Ceiling: none. Pass is permitted.

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Prompt-only generation lands in the session | Pass | `jobs._generate_text` (preview → refine with `enable_pbr: true`, `client.create_text_refine`); `_run_generate` saves `SourceArt/Meshy/<Name>/<Name>.glb` (`paths.glb_path`) and imports via `meshy_session._import_glb` (collection, `SM_<Name>`, `M_<Name>_Body`); SCN001, `tests/blender/test_meshy_session.py::test_import_creates_the_collection…` |
| AC2 | Images alone shape the model | Pass | `request.route`, `client.create_image_to_3d` (`image_url`) / `create_multi_image_to_3d` (`image_urls`), `request.image_data_uri` MIME map; `texture_prompt` added only when a prompt exists (`_add_optional`); SCN002 outline |
| AC3 | Images plus prompt | Pass | `_generate_images` passes `clean_prompt` as `texture_prompt` in the same request; SCN003 |
| AC4 | Optional pose | Pass | `pose_mode` added only when not None on preview/image/multi-image bodies; refine body has none; SCN004 |
| AC5 | Untextured generation | Pass | `_generate_text` returns after preview when `texture=False`; image bodies set `should_texture`/`enable_pbr` to `texture`; SCN005 |
| AC6 | Session unreachable at import keeps the file | Pass | `_run_generate` catches `mcp.blender.unreachable` → warning, `loaded_into_session: false`, GLB kept; SCN006 |
| AC7 | Retexture an authored mesh | Pass | `start_retexture` → `export_glb`; `_run_retexture` posts `model_url` data URI, downloads maps to `SourceArt/Textures/Meshy/<Name>/`; `meshy_session._apply_maps` wires sRGB base color, Non-Color others, Normal Map node, replaces material slots; SCN007 + Blender tests `test_apply_maps_*` |
| AC8 | Key from env or project `.env` | Pass | `config.api_key` (env first, then `<project>/.env`, `CLAUDE_PROJECT_DIR` root); SCN008, `tests/unit/meshy/test_config.py` |
| AC9 | Missing key fails fast | Pass | `start_*` call `config.api_key` before `_new_job_dir`, session calls, or HTTP; remediation names `MESHY_API_KEY=<key>` and git-ignored `.env`; SCN009 |
| AC10 | Structured API failures, no key leak | Pass | `client._http_error` 401/402/429 mapping; `_task_failed` for FAILED/CANCELED/EXPIRED with `task_error.message`; `redact` on messages; key never in `request.json`/`status.json`; SCN010 scans job dir |
| AC11 | Invalid requests rejected before Meshy | Pass | `GenerateRequest.validate` / `RetextureRequest.validate` implement every design rule; `collection_exists` from `collection_state`; `collection_not_found` from `export_glb`; job dir removed on failure; SCN011 outline |
| AC12 | Shared CLI and MCP implementation | Pass | `__main__.py` and `meshy_mcp/server.py` both call `jobs.start_generate`/`start_retexture`/`status`; SCN012, `tests/unit/meshy/test_cli.py`, `test_mcp_server.py` |
| AC13 | Config, guards, steering, docs | Pass | `.mcp.json` `meshy` entry via `uv run --project …/mcp-servers/meshy meshy-mcp`, no key text; other entries unchanged; `validate-mcp-tools.py` exit 0; `tools.json` pose guidance; `test_no_meshy.py` scoped to `pipeline/` and `finalize/`; product steering adds "Optional Meshy source"; `docs/mcp/meshy.md` and onboarding docs updated; SCN013 |
| AC14 | `.env` git-ignored | Pass | `.gitignore` adds `.env` (`git check-ignore .env` → `.env`); `onboard/gitignore.py` `ensure_gitignore_env` installed/unchanged, accepts `/.env`, never writes `.env`; wired in `runner.py`; SCN014, `tests/unit/onboard/test_gitignore.py` |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Errors, key, paths, validation, routing | Complete | `meshy/{errors,config,paths,request}.py` |
| T002 | REST client, injectable transport | Complete | `meshy/client.py`; downloads omit auth |
| T003 | Session script + `script=` parameter | Complete | `scripts/blender/meshy_session.py`, `pipeline/clients/blender_session.py` (no Meshy text), `meshy/session.py` |
| T004 | Background jobs | Complete | `meshy/jobs.py`; atomic status writes, 30 min timeout |
| T005 | CLI | Complete | `meshy/__main__.py` |
| T006 | MCP server + `.mcp.json` | Complete | `mcp-servers/meshy/*`; lockfile test passes |
| T007 | `.gitignore` + onboarding step | Complete | |
| T008 | Narrowed guards | Complete | `test_no_meshy.py`, `test_scaffold_guards.py`, `_scaffold_contract.py` |
| T009 | Steering and docs | Complete | |
| T010 | Fakes and unit tests | Complete | `tests/meshy_fakes.py`, `tests/unit/meshy/*` |
| T011 | BDD scenarios | Complete | `tests/bdd/features/meshy.feature` SCN001–SCN014 |
| T012 | Headless Blender tests | Complete | 10 tests in `tests/blender/test_meshy_session.py` |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 5 | Request validation, key resolution, HTTP, session ops, and job lifecycle live in separate modules |
| Open/Closed | 4 | Routing is a small closed set by design (spec Out of Scope excludes other services) |
| Liskov Substitution | 5 | `Transport` and `SessionClient` protocols are honored by real and fake implementations |
| Interface Segregation | 5 | `SessionClient` protocol requires only `run_session_op` |
| Dependency Inversion | 4 | Transport, session, spawn, sleep, and clock are injected; `meshy` depends on `pipeline.errors`/session client, never the reverse |

### Layer Separation

The MCP server and CLI are thin wrappers over `nmg_game_dev.meshy.jobs`. Blender work goes through the shared session client with a Meshy-owned script, so `pipeline/` and `finalize/` contain no Meshy code (guarded by `test_no_meshy.py`). Long Meshy work runs in a detached child, matching the long-running-work rule in tech steering.

### Dependency Flow

`meshy → pipeline.errors, pipeline.clients.blender_session`. Pipeline does not import meshy. The MCP server depends on the root package through an editable path source, the same as `texture-gen`.

---

## Security Assessment

- [x] Authentication: Bearer key only in request headers; asset downloads carry no auth header
- [x] Authorization: N/A (single-user local tool)
- [x] Input validation: name regex, image suffix/existence/size, prompt length, pose enum, job id path traversal check in `jobs.status`
- [x] Injection prevention: session payloads embedded as JSON string literals (`session_code`), never as Python source
- [x] Data protection: key not persisted in job files; `redact` on error messages; `.env` git-ignored here and in consumers; onboarding never writes `.env`

---

## Performance Assessment

- [x] Async patterns: Meshy work runs detached; MCP calls return a job id at once
- [x] Caching: N/A
- [x] Resource management: log handle closed after spawn; temp files cleaned on failed atomic writes; job dir removed when start fails
- [x] Query optimization: 5 s polling interval, 30 min cap. Images and the retexture GLB are base64-inlined in request bodies (per design); large inputs mean large request bodies, bounded by the 20 MB image limit

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1–AC14 | Yes (SCN001–SCN014) | Yes (`tests/bdd/test_meshy_bdd.py`) | Yes |

### Coverage Summary

- Feature files: 14 scenarios (2 outlines) in `tests/bdd/features/meshy.feature`
- Step definitions: Implemented
- Unit tests: meshy/onboard/pipeline subset 243 passed; full unit + BDD 788 passed, 4 skipped
- Headless Blender: `scripts/run-blender-tests.sh` (BLENDER_APP on Fast Brick, Blender 5.2) → 136 passed, exit 0, including 10 meshy session tests

---

## Exercise Test Results

| Field | Value |
|-------|-------|
| **Reason** | No nmg-sdlc plugin workflows or agents changed (`workflows/`, `agents/` untouched). The shipped plugin surface was exercised by the registered `plugin.session-smoke`, which loaded this checkout with `--plugin-dir` in an ephemeral project and confirmed `meshy` connected with 3 tools |
| **Recommendation** | A live Meshy call with a real key is outside automated verification (paid API); manual follow-up recommended |

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` (registered) | Pass | 788 passed, 4 skipped |
| `repository.lint` (registered) | Pass | ruff: All checks passed |
| `repository.types` (registered) | Pass | mypy: no issues in 169 files |
| `plugin.validate` (registered) | Pass | Validation passed with warnings |
| `plugin.session-smoke` (registered) | Pass | meshy, blender, finalize, texture-gen, unreal connected |
| `gate-mcp-schema` (prose, supplementary) | Pass | `scripts/validate-mcp-tools.py` → "MCP tools match tools.json for every server", exit 0 |
| `gate-blender-headless` (prose, supplementary) | Pass | `scripts/run-blender-tests.sh` → 136 passed, exit 0 |
| `gate-shellcheck` (prose) | Not applicable | No `*.sh` in the diff |

**Gate Summary**: 7/7 applicable gates passed, 0 failed, 0 incomplete

---

## Fixes Applied

| Severity | Category | Location | Original Issue | Fix Applied | Routing |
|----------|----------|----------|----------------|-------------|---------|
| — | — | — | None required | — | — |

## Remaining Issues

### Critical Issues
None.

### High Priority
None.

### Medium Priority
None.

### Low Priority

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Error Handling |
| **Location** | `scripts/blender/meshy_session.py` (`_import_glb`) |
| **Issue** | After joining several imported meshes, only the first material slot is renamed `M_<Name>_Body`; any further Meshy materials keep their GLB names |
| **Impact** | Meshy GLBs normally carry one material, so the contract name holds in practice |
| **Reason Not Fixed** | Spec scopes a single body material; multi-part assets are Out of Scope |

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Error Handling |
| **Location** | `scripts/blender/meshy_session.py` (`_export_glb`) |
| **Issue** | Export uses `use_selection=True`; meshes hidden in the view layer cannot be selected and would be left out of the retexture export |
| **Impact** | Only affects collections with hidden mesh objects |
| **Reason Not Fixed** | Edge case outside the approved ACs; publication scope for this step is the report only |

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Documentation |
| **Location** | `steering/snippets/project-product.md` (Won't Have) |
| **Issue** | Won't Have still names Meshy, as the exception to "any cloud-hosted or paid generation service" |
| **Impact** | None: Meshy is no longer a Won't Have item and is described under Must Have as optional, opt-in, and paid (AC13 satisfied, SCN013 passes) |
| **Reason Not Fixed** | Wording choice, not a defect |

---

## Positive Observations

- Strict validation → key → session → write ordering in `start_*` keeps failed requests side-effect free.
- Every external edge (HTTP transport, Blender session, spawn, sleep, clock) is injectable, so no test touches the network.
- Atomic `status.json` writes and a catch-all `meshy.job_crashed` guarantee a terminal state for pollers.
- The generic `script=` parameter on the session client keeps Meshy out of `pipeline/` without duplicating the MCP transport.

---

## Recommendations Summary

### Before PR (Must)
- None.

### Short Term (Should)
- Run one live Meshy generate and retexture with a real key on a consumer project.

### Long Term (Could)
- Rename every imported material slot, or join materials, when a Meshy GLB has several.
- Temporarily unhide collection meshes during `export_glb`.

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `src/nmg_game_dev/meshy/*.py` | 0 | |
| `scripts/blender/meshy_session.py` | 2 (Low) | |
| `mcp-servers/meshy/*` | 0 | |
| `src/nmg_game_dev/pipeline/clients/blender_session.py` | 0 | Backward-compatible `script=` default |
| `src/nmg_game_dev/onboard/{gitignore,runner}.py` | 0 | |
| `.mcp.json`, `.gitignore` | 0 | |
| `steering/snippets/project-product.md` | 1 (Low) | |
| `docs/mcp/meshy.md`, `docs/onboarding/*.md`, `skills/onboard-consumer/references/install-steps.md` | 0 | |
| `tests/**` (meshy, onboard, guards) | 0 | |

---

## Recommendation

**Ready for PR**

Every acceptance criterion, task, and scenario is implemented and tested. All five registered validations passed at `353c5b69d55c76604ff44c53f1a58db5fd87afc8` with complete coverage, and the supplementary MCP schema and headless Blender gates pass. The three remaining findings are low-severity and outside the approved scope.
