---
name: design
description: Sync the game's docs/design markdown into a backlog, then scaffold its regions, missions, and systems in Unreal
required_mcp: [unreal]
required_env: [UE_MCP_PORT?]
unattended_safe: true
---

# Design

Reads the game's design docs under `docs/design/` into `docs/design/backlog.json`, then creates the
Unreal starting points for its regions, missions, and systems. Use it when the developer adds or
edits a design doc, or asks to sync or scaffold the design. `sync` reads only the repo. `scaffold`
needs the Unreal editor open with its MCP endpoint reachable. Asset entries (`character`, `vehicle`,
`prop`, `environment`) are finalized with the `finalize-asset` skill, not here. The file format is
in `docs/design-contract.md`.

## Flow

1. Run sync:
   `uv run --project "${CLAUDE_PLUGIN_ROOT}" python -m nmg_game_dev.design sync`
   Relay every line it prints, verbatim and in order. If it exits 1, the error lines name each file
   and field. Relay them, then stop. Do not run scaffold against the old backlog. Fix the files
   named, then rerun sync.
2. Run scaffold:
   `uv run --project "${CLAUDE_PLUGIN_ROOT}" python -m nmg_game_dev.design scaffold`
   Relay every line it prints, verbatim and in order, including `unchanged` and `skipped` lines.
3. Report the outcome from the exit code. Exit 0: every item was created, unchanged, or skipped. Exit
   1: name each `error design.scaffold_failed` line, then stop. Exit 2: see below.

Add `--project <dir>` to either command only when the developer names another project directory. The
default root is `CLAUDE_PROJECT_DIR`. Add `--url <url>` to scaffold only when the developer names an
Unreal MCP endpoint. Otherwise it uses `http://127.0.0.1:$UE_MCP_PORT/mcp`.

Report line formats are in `docs/design-contract.md` (section 6). Never reword a line. Do not
retry a failed item, and do not edit `backlog.json` by hand.

## Failure modes and remediation

- `design.frontmatter_missing`: the named file does not start with a `---` frontmatter block. Add the
  block, then rerun sync.
- `design.frontmatter_invalid`: the frontmatter is not valid YAML. Fix the YAML in the named file,
  then rerun sync.
- `design.unknown_type`: `type` is not one of the seven listed in the contract. Correct it, then rerun
  sync.
- `design.missing_field`: a required field is absent. The line names the field. Add it, then rerun
  sync.
- `design.invalid_field`: a field value breaks its rule, such as an unknown `asset_class` or a
  `category` that is not PascalCase. Correct the value, then rerun sync.
- `design.duplicate_name`: two files derive the same asset name. Rename the `name` in one of them,
  then rerun sync.
- `design.invalid_name`: the `name` yields no valid asset name. Change the `name` so its words form a
  PascalCase name that starts with a letter, then rerun sync.
- `design.unknown_reference`: a `depends_on` or `region` names no entry. Fix the name, or add the
  missing design file, then rerun sync.
- `design.dir_missing`: `docs/design/` does not exist. Run `/onboard-consumer` to create it, or create
  the folder, add the design docs, then rerun sync.
- `design.scaffold_failed`: the Unreal work for one item failed. The line names the asset and the UE
  error. Fix the cause, then rerun scaffold. Items that were created on the earlier run report
  `unchanged`, and the failed item runs again. If the error says `UNmgMissionDefinition` is missing,
  the nmg-game-dev runtime plugin is not built in the editor. Build it, then rerun.
- `mcp.unreal.unreachable` (scaffold exits 2): the Unreal editor is not reachable. Run
  `scripts/start-unreal-mcp.sh`, then rerun scaffold. Sync does not need to run again.

`design.backlog_update_failed` is a warning from finalize, not from this skill. See `finalize-asset`.

## Test fixtures

- `tests/bdd/features/design.feature` (SCN001 to SCN007), bound in `tests/bdd/test_design_bdd.py`.
- `tests/unit/design/test_cli.py`: the report lines and exit codes for sync and scaffold.
