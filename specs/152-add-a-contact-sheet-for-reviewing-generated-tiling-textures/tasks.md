# Tasks: Contact sheet for reviewing generated tiling textures

**Issue**: #152
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/7-consumer-onboarding-onboard-consumer-skill-asset-contract-install-and-onboarding-docs/

## Implementation Tasks

### T001: Contact sheet builder

**File(s)**: `src/nmg_game_dev/texture/contact_sheet.py`
**Type**: Create
**Depends**: none
**Acceptance**:
- `collect` and `build` behave as in design.md: cells come from manifest `images` entries only, are located by file name in the set folder, and are ordered by set name, backend, then seed (AC2, FR1, FR2, FR4).
- Each cell is the albedo at 192 px tiled 2x2 into 384 px, under a two-line label with the set name and then `<backend> seed <seed>` (AC2, FR3).
- Pages hold 24 cells (6 × 4) and are named `contact_sheet_NNN.png` at the root. Stale higher-numbered pages are deleted (AC5, FR4).
- Missing or unreadable albedos and unreadable manifests go to `skipped` with `path` and `reason` (AC6, FR8).
- `build(..., require_sets=True)` on a missing or empty root raises `texture.no_texture_sets` with a remediation (AC7, FR9).
- The module imports nothing from `registry`, `hardware`, `batch`, `worker`, or mflux (AC8, FR10).

### T002: Refresh the sheet after generate

**File(s)**: `src/nmg_game_dev/texture/generate.py`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- `run` calls `build(base, require_sets=False)` after writing `textures.json`. `TextureResult` gains a `contact_sheet` field, and `as_json()` includes `contact_sheet: {pages, cells, skipped}` (AC1, FR5).
- An `OSError` from building the sheet is reported in `contact_sheet.skipped` and does not fail the run (AC6, FR8).
- The job's succeeded `result` carries `contact_sheet` with no change to `jobs.py` beyond what `as_json()` provides (AC1).

### T003: `sheet` CLI subcommand

**File(s)**: `src/nmg_game_dev/texture/__main__.py`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- `sheet [--root PATH]` defaults to `paths.output_root(os.environ, Path.cwd())`, prints `ContactSheet.as_json()` as indented, sorted JSON, and exits 0 (AC3, FR6).
- `texture.no_texture_sets` prints the existing `ERROR [code]` and `Remediation:` lines and exits 1. Argument errors still exit 2 (AC7).
- The module docstring lists `sheet`.

### T004: `texture_contact_sheet` MCP tool

**File(s)**: `mcp-servers/texture-gen/src/texture_gen_mcp/server.py`, `mcp-servers/texture-gen/tools.json`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- `texture_contact_sheet()` returns `build(output_root(os.environ, Path.cwd()), require_sets=True).as_json()`, or `_error(error)` for a `TextureGenError` (AC4, AC7, FR7, FR9).
- `tools.json` declares `texture_contact_sheet` with a description and an empty-object `inputSchema`. `gate-mcp-schema` (`uv run python scripts/validate-mcp-tools.py`) passes (AC4).

### T005: Document the contact sheet

**File(s)**: `docs/onboarding/texture-models.md`
**Type**: Modify
**Depends**: T002, T003, T004
**Acceptance**:
- A "Contact sheet" section covers the `contact_sheet_NNN.png` pages at the output root, the 2x2 tiled cells and their labels, the 24-per-page paging, the refresh after each generate, `python -m nmg_game_dev.texture sheet [--root PATH]`, the `texture_contact_sheet` tool, `skipped`, and `texture.no_texture_sets` (FR11).
- The "Output folder" list mentions the contact sheet pages.

### T006: Unit tests

**File(s)**: `tests/unit/texture/test_contact_sheet.py`, `tests/unit/texture/test_cli.py`, `tests/unit/texture/test_mcp_server.py`, `tests/unit/texture/test_generate.py`
**Type**: Create
**Depends**: T001, T002, T003, T004
**Acceptance**:
- Builder tests use synthetic sets written with `tests/texture_fakes.py` `save_png` and hand-written manifests:
  - cell order (AC2);
  - a page is 6 × 384 + gutters wide and one row tall for ≤ 6 cells (AC2);
  - the pixels of a cell's top-left tile equal those of its bottom-right tile (2x2 tiling) (AC2);
  - `_N`, `_R`, and `_compare.png` files present but not counted as cells (AC2);
  - 25 albedos give two pages, and a stale `contact_sheet_003.png` is removed (AC5);
  - a missing albedo, a non-image `.png`, and an invalid `textures.json` land in `skipped` while the other cells render (AC6);
  - a missing or empty root raises `texture.no_texture_sets` (AC7);
  - a moved root still builds (FR2).
- `test_generate.py`: a fake-worker generate run into a root with one existing set returns `contact_sheet.cells` covering both sets, and its pages exist (AC1). A run whose sheet build raises `OSError` still succeeds (AC6).
- `test_cli.py`: `main(["sheet", "--root", tmp])` exits 0 and prints the JSON keys (AC3). An empty root exits 1 with `ERROR [texture.no_texture_sets]` and `Remediation:` on stderr (AC7).
- `test_mcp_server.py`: `texture_contact_sheet` is in `mcp.list_tools()` and in `tools.json` (AC4). With `NMG_GAME_DEV_TEXTURE_DIR` set it returns pages, and on an empty root it returns the structured error (AC4, AC7).
- With `TEXTURE_GEN_MODELS_DIR` unset and `generate.probe`/`hardware.probe` monkeypatched to raise, `sheet` and the MCP tool still succeed (AC8).
- Evidence: `uv run pytest tests/unit/texture -q`; `repository.tests`, `repository.lint`, `repository.format`, `repository.types`; `gate-mcp-schema`.

### T007: BDD scenarios

**File(s)**: `tests/bdd/features/texture_contact_sheet.feature`, `tests/bdd/test_texture_contact_sheet_bdd.py`
**Type**: Create
**Depends**: T006
**Acceptance**:
- The feature file holds the AC1–AC8 scenarios from `feature.gherkin`, bound with pytest-bdd as in `tests/bdd/test_texture_bdd.py`, using synthetic PNGs and the fake worker (`tests/texture_fakes.py`). No model, editor, or network is used.
- Evidence: `uv run pytest tests/bdd/test_texture_contact_sheet_bdd.py -q` and `repository.tests`.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #152 | 2026-11-11 | Initial feature tasks |
