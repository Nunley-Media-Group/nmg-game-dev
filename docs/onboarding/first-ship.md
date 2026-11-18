# Your first ship

This guide walks through the `ship` skill on your Godot project. Run a dry run first, so you know
what each step prints. To see a full dry run before your own project is ready, run
`scripts/ship-smoke.sh`: it dry-runs `all` against the fixture project in `tests/godot/fixture/`.

## Before you start

- Onboard the project ([index.md](index.md)). Onboarding writes `game/project.godot` and
  `game/export_presets.cfg` with one preset per platform.
- Install Godot 4 (latest stable), or set `GODOT_BIN`, and install the export templates for each
  platform you ship (Editor > Manage Export Templates).
- Have the target platform's signing secrets in place. Windows and web need none. The ship names any
  missing variable and stops before it exports. It never prints a secret value.

## 1. Dry run

Ask the agent to plan the release for a target (`macos`, `ios`, `android`, `windows`, `web`,
`desktop`, `mobile`, or `all`). The dry run prints each planned command with a `DRY-RUN:` prefix and
writes `release/<platform>/DRY-RUN.txt`. Godot does not run, and nothing is exported or signed. The
mobile budget gate still runs, so an over-budget Mobile asset shows up here.

## 2. Ship

Ask the agent to ship the target. The ship runs the gates first: `godot --check-only` on every
script, your `game/tests/run_tests.gd` when it exists, and the mobile budget gate for iOS, Android,
and web. Then it exports each platform headless with its Godot preset, signs and notarizes the macOS
app, and writes each artifact to `release/<platform>/`. `release/RELEASE-NOTES.md` lists every
artifact with its SHA-256.

## 3. Check the result

- Every platform folder holds one artifact and the release notes name it. The web build is the whole
  `release/web/` folder.
- The SHA-256 in the notes matches the artifact.
- A web build over 38 MB prints `WARNING [ship.web_pack_large]`; it still ships.
- A failing gate names the rule and a remediation. Fix that and ship again. Re-running is safe.

Skill reference: `skills/ship/SKILL.md`. Full reference: `docs/skills/ship.md`.
