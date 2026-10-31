# Design: Drive asset work and Unreal scaffolding from a consumer project's markdown design docs

**Issue**: #112
**Date**: 2026-10-31
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/69-reshape-the-pipeline-to-finalize-an-authored-asset-instead-of-generating-from-a-prompt/

## Overview

A new package `src/nmg_game_dev/design/` parses design docs into a backlog, serves backlog lookups to finalize, and scaffolds non-asset entries in Unreal over the existing Unreal MCP client. A small C++ data asset class joins the runtime module. Onboarding installs a new contract document beside the asset contract.

## Architecture

| Module | Responsibility |
|--------|----------------|
| `design/paths.py` | `project_root(env, cwd)` (`CLAUDE_PROJECT_DIR`, else cwd), `design_dir(root)`, `backlog_path(root)` |
| `design/model.py` | `ENTITY_TYPES`, `ASSET_TYPES = {character, vehicle, prop, environment}`, `STATUSES`, `asset_name(name) -> str \| None`, a frozen `Entry` dataclass, and `DesignError(code, source, field, message)` |
| `design/parse.py` | `parse_file(path, root) -> Entry \| list[DesignError]`: splits a leading `---` … `---` block, runs `yaml.safe_load`, and validates per the contract table. `parse_tree(root) -> (entries, errors)` sorts `docs/design/**/*.md` paths (excluding nothing else), then checks duplicates and references across the set |
| `design/backlog.py` | `load(path)`, `merge(previous, parsed) -> list[Entry]` (keeps status; missing → `orphaned`; orphaned + present → `planned`), `dump(entries) -> str` (`json.dumps(..., indent=2, sort_keys=True)` + newline, entries sorted by `(type, asset_name)`), `write_atomic(path, text)` (temp file in the same dir + `os.replace`), `find_asset(path, asset_name)`, `mark(path, asset_name, status)` |
| `design/scaffold.py` | `build_scaffold_code(entry, design_root) -> str` (UE Python template like `unreal/import_asset.py`, one `NMG_RESULT` line), `scaffold(client, root) -> list[ReportLine]` |
| `design/__main__.py` | argparse `sync` / `scaffold` subcommands, report printing, exit codes |

`sync`: `parse_tree`. Any errors print every error and exit 1 without writing. Otherwise it merges with the existing backlog, writes atomically, prints the lines, and exits 0.

**Finalize fallback.** `finalize/mcp_tools.py` `_request` and `finalize/__main__.py` make `category` and `asset_class` optional. When either is `None`, `design.backlog.find_asset(backlog_path(project_root(...)), collection)` supplies the missing value from an asset-type entry. `FinalizeRequest` gains `backlog_path: Path | None = None`, set whenever a matching asset entry exists. `settings_hash` never reads it, so cache keys are unchanged. In `pipeline/jobs.py` `run_job`, after the `succeeded` update for a `finalize_asset` job (not `run_finalize_step`), `design.backlog.mark(request.backlog_path, request.collection, "finalized")` runs when `backlog_path` is set. An `OSError` or `ValueError` there appends `design.backlog_update_failed` to the result warnings. `mcp-servers/finalize/server.py` and `tools.json` make the two parameters optional.

**Scaffold (UE side).** One `execute_python_code` call per entry, through `UnrealMcpClient`, parsed with `nmg_game_dev.unreal.import_asset.parse_nmg_result`. Each call first checks `unreal.EditorAssetLibrary.does_asset_exist(path)` and reports `{"ok": true, "created": false}` without touching the asset when it already exists.
- **region:** remember the current level path. `LevelEditorSubsystem.new_level(path)`. Spawn a `StaticMeshActor` with `/Engine/BasicShapes/Plane` scaled `(100, 100, 1)` at the origin, a `PlayerStart` at `(0, 0, 100)`, a `DirectionalLight`, and a `SkyLight`. `save_current_level()`, then load the remembered level.
- **mission:** `AssetTools.create_asset("DA_<Name>", "/Game/Missions/<Name>", unreal.NmgMissionDefinition, unreal.DataAssetFactory())` with `data_asset_class` set. Set `mission_name`, `act` (0 when absent), `region` (the region's asset name or `None`), `depends_on` (asset names), and `design_doc_path` (the entry `source`), then save. A missing `unreal.NmgMissionDefinition` fails the item with a remediation to build the plugin.
- **system:** `BlueprintFactory` with `parent_class = unreal.ActorComponent`, `create_asset("BPC_<Name>", "/Game/Systems/<Name>", unreal.Blueprint, factory)`, then save.

Host side: when an item's `created` comes back true or false, `backlog.mark(..., "scaffolded")`; one atomic write follows after all items. An `ok: false` item becomes a `design.scaffold_failed` line. A `PipelineError` with code `mcp.unreal.unreachable` exits 2.

**UE runtime class.** `Source/NmgGameDevRuntime/Public/NmgMissionDefinition.h` + `Private/NmgMissionDefinition.cpp`: `UCLASS(BlueprintType) UNmgMissionDefinition : public UPrimaryDataAsset` with `UPROPERTY(EditAnywhere, BlueprintReadOnly)` `FString MissionName`, `int32 Act`, `FName Region`, `TArray<FName> DependsOn`, `FString DesignDocPath`. `GetPrimaryAssetId()` returns `FPrimaryAssetId("NmgMission", GetFName())`. No new module dependencies.

**Onboarding.** `runner.py` adds `DESIGN_CONTRACT_SRC = Path("docs/design-contract.md")` and `DESIGN_CONTRACT_DST = "docs/nmg-game-dev/design-contract.md"`. They are copied through the same helper and drift handling as the asset contract, and the source joins the framework check list. A new step `design_dir` creates `docs/design/` (`installed`) or reports `unchanged` without listing or modifying its contents. `instructions.py` `block_text()` adds a line linking `docs/nmg-game-dev/design-contract.md` and `docs/design/`.

**Dependencies.** `pyproject.toml` `dependencies` adds `pyyaml==6.0.3`. `uv.lock`, `mcp-servers/finalize/uv.lock`, and `mcp-servers/texture-gen/uv.lock` (and `mcp-servers/meshy/uv.lock` if present) are relocked so the existing lock-sync unit test passes.

## API / Interface Changes

| Interface | Input | Output / Error | Behavior |
|-----------|-------|----------------|----------|
| `python -m nmg_game_dev.design sync` | `--project DIR` | report lines; exit 0/1 | Writes `docs/design/backlog.json` |
| `python -m nmg_game_dev.design scaffold` | `--project DIR`, `--url URL` | report lines; exit 0/1/2 | Creates UE scaffolds, updates statuses |
| MCP `finalize_asset`, `run_finalize_step`; CLI `--category`, `--class` | `category`, `asset_class` now optional | `finalize.invalid_request` when unresolved | Backlog fallback; `finalize_asset` marks `finalized` |
| `UNmgMissionDefinition` | — | primary asset type `NmgMission` | Mission data asset class |

## Data / Storage Changes

`docs/design/backlog.json` in the consumer repo: `{"version": 1, "entries": [{"type", "name", "asset_name", "source", "fields", "status"}]}`, sorted, with no timestamps, so identical input gives identical bytes.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| PyYAML `safe_load` | Selected | Already locked at 6.0.3; full YAML in the frontmatter |
| Hand-written YAML subset parser | Rejected | Surprising failures on ordinary YAML |
| Mark `finalized` inside the MCP tool on poll | Rejected | Job may finish with no poll; the runner owns completion |
| Delete orphaned entries | Rejected | The issue requires keeping them |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #112 | 2026-10-31 | Initial feature design |
