# File: tests/bdd/features/scaffold-plugin-repo-session-start-hooks.feature
#
# Generated from: specs/feature-scaffold-plugin-repo-session-start-hooks/requirements.md
# Issue: #1 (updated for the Godot engine by #249)

Feature: Scaffold plugin + repo + session-start hooks
  As an internal NMG game developer
  I want a fresh clone of nmg-game-dev to self-assemble into a working Claude Code plugin
    whose Blender launcher script is ready for consumer-game adoption, whose Godot add-on
    is versioned with the plugin, and whose Python/MCP scaffolding is in place
  So that every downstream v1 issue (#2–#7) can assume the skeleton is wired and
    so the same plugin installs correctly into consumer games at either user or project scope

  Background:
    Given the repo root of nmg-game-dev is the working directory

  # --- Plugin manifest ---

  Scenario: Plugin manifest is valid (AC1)
    Given `.claude-plugin/plugin.json` exists at the repo root
    When the plugin manifest is validated against Claude Code's plugin schema
    Then validation passes with no errors
    And the manifest declares "name", "version", "description", and "author" fields
    And skills are discovered from the default `skills/` folder
    And this repo carries no marketplace file, because the `nmg-plugins` marketplace lists it

  # --- Directory layout ---

  Scenario: Directory layout matches steering/snippets/project-structure.md (AC2)
    Given the layout declared in `steering/snippets/project-structure.md` § Project Layout
    When `ls` probes every top-level directory listed there
    Then every declared directory exists
    And empty directories carry a `.gitkeep`
    And the Python package `src/nmg_game_dev/` is importable with submodules `godot/`, `pipeline/`, `variants/`, `quality/`, `ship/`

  # --- Launcher script — happy path ---

  Scenario: The Blender launcher detaches when invoked manually (AC3)
    Given a developer, working inside the nmg-game-dev repo, invokes `scripts/start-blender-mcp.sh` directly from the shell
    And `BLENDER_BIN` resolves to an installed Blender binary
    When the script runs
    Then Blender is detached with the MCP add-on enabled on `BLENDER_MCP_PORT` (default 9876)
    And the script exits 0 while the process it started is still running
    And the script returns control to the shell in under two seconds
    And the script does not block waiting for Blender to finish booting

  # --- Launcher detach judged by process state (#215) ---

  Scenario: A launcher that waits for its child fails the detach check (AC2)
    Given a synthetic launcher that starts a fake child and waits for it to exit
    When the launcher runs with a fake child that exits after 1 second
    Then the detach check fails because the child is gone

  Scenario: A launcher that does not return fails the detach check (AC2)
    Given a synthetic launcher that starts a fake child and waits for it to exit
    When the launcher runs with a fake child that keeps running under a 3 second bound
    Then the detach check fails because the launcher did not return

  Scenario: A slow launcher fails the detach check (AC2)
    Given a synthetic launcher that sleeps 2.5 seconds before detaching a fake child
    When the launcher runs with a fake child that keeps running
    Then the detach check fails because the launcher took longer than two seconds
    And the launcher finished its 2.5 second delay before detaching

  # --- Launcher script — idempotency ---

  Scenario: The launcher is idempotent when the port is already bound (AC4)
    Given the Blender MCP port is already in `LISTEN` state (simulated by a bound socket in the test harness)
    When `scripts/start-blender-mcp.sh` is re-invoked
    Then the script exits 0 without launching a second Blender process
    And no duplicate process appears in the process table

  # --- Launcher script — actionable failure ---

  Scenario: Launcher fails with a one-line remediation when the binary is missing (AC5)
    Given `BLENDER_BIN` is unset
    And `BLENDER_APP` points at a non-existent path
    When `scripts/start-blender-mcp.sh` runs
    Then the script exits non-zero
    And stderr contains a one-line remediation hint naming `BLENDER_BIN`/`BLENDER_APP` and the default path it checked

  # --- Consumer SessionStart template ---

  Scenario: Consumer SessionStart template ships under templates/consumer/ (AC5b)
    Given `templates/consumer/.claude/settings.json` exists in this repo
    When a reader inspects it
    Then it declares a `SessionStart` hook command invoking `scripts/start-blender-mcp.sh`
    And no other launcher runs at session start, because Godot only runs headless on demand
    And no `.claude/settings.json` exists at this repo's root
    And `templates/consumer/README.md` documents that `onboard-consumer` (future v1 issue) copies this template into downstream projects

  # --- Python package ---

  Scenario: Python package bootstraps (AC6)
    Given `pyproject.toml` declares the `nmg_game_dev` package and dev deps
    When `pip install -e .[dev]` runs in a fresh virtualenv
    Then the install succeeds with exit code 0
    And `python -c "import nmg_game_dev"` exits 0
    And `ruff check .` exits 0
    And `pytest` on the empty scaffold exits 0

  # --- Versioning files ---

  Scenario: VERSION and CHANGELOG are seeded (AC7)
    When a developer reads `VERSION` and `CHANGELOG.md`
    Then `VERSION` contains exactly one `X.Y.Z` semver followed by a newline
    And `CHANGELOG.md` has an `## [Unreleased]` section
    And `.claude-plugin/plugin.json`'s `version` field equals `VERSION`
    And `pyproject.toml` declares `project.version` dynamic, sourced from `VERSION`

  # --- Godot runtime add-on ---

  Scenario: The Godot runtime add-on ships with a manifest at the plugin version (#249)
    Given the add-on folder `plugins/nmg-game-dev-godot-addon/addons/nmg_game_dev/`
    When its `plugin.cfg` is read
    Then the `[plugin]` section names `nmg-game-dev` with the script `plugin.gd`
    And its `version` equals `VERSION`
    And the add-on holds `nmg_assets.gd`, `nmg_mission_definition.gd`, and the headless runner `tests/run_tests.gd`

  # --- MCP config ---

  Scenario: MCP server config tracks latest and is dual-purpose (AC8)
    Given `.mcp.json` at the repo root
    When the file is parsed
    Then it declares the `blender` (mcp-for-blender), `finalize`, `texture-gen`, and `meshy` server entries and no engine server
    And every server entry tracks the latest release with no version constraint other than `@latest`
    And the file contains no this-repo-specific absolute paths (usable verbatim by `onboard-consumer` in a consumer project)

  # --- Entry-point pointer ---

  Scenario: CLAUDE.md points at steering + SDLC entry (AC9)
    Given `CLAUDE.md` at the repo root
    When a new contributor opens the repo
    Then `CLAUDE.md` references `steering/snippets/project-product.md`, `steering/snippets/project-tech.md`, and `steering/snippets/project-structure.md`
    And it mentions `/sdlc-draft-issue` as the SDLC entry point
    And it does not duplicate content from any steering document

  # --- No-leak guard ---

  Scenario: Nothing this-repo-specific leaks into consumer-facing deliverables (AC10)
    Given the consumer-facing artifacts: `.claude-plugin/plugin.json`, `scripts/start-blender-mcp.sh`, `templates/consumer/.claude/settings.json`, `.mcp.json`, `pyproject.toml`
    When these artifacts are grep-scanned for repo-specific absolute paths, in-repo fixture project references, this-repo-only module imports, and credentials
    Then no banned substring is found
    And every path resolution in the launcher script uses either env-var overrides or documented defaults a consumer can override without editing the script

  # --- Install-scope invariance ---

  Scenario: Install-scope invariance (AC11)
    Given the plugin is installed through Claude Code at either user scope or project scope inside a consumer game repo
    And `onboard-consumer` (future v1 issue) has run against that consumer
    When a developer opens the consumer project in Claude Code
    Then the consumer-side outcome is identical regardless of the plugin's install scope — same skills, same `scripts/` contents, same MCP config, same `.claude/settings.json` `SessionStart` entries
    And no artifact shipped in this issue encodes or depends on a specific install scope
