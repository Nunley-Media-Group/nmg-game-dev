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
- Add a `CHANGELOG.md` at the project root, the folder above `game/`. Give it a `## X.Y.Z` section
  for the version you will ship, with at least one line that tells players what changed. The ship
  refuses to run without that section, and it copies the section into the release notes.
- Choose the first version. The project has no `application/config/version` until you ship one, so
  the first ship takes `--version X.Y.Z` (for example `--version 1.0.0`); later ships can take
  `--bump` instead. The version appears in the game through `NmgVersionLabel`.

## 1. Dry run

Ask the agent to plan the release for a target (`macos`, `ios`, `android`, `windows`, `web`,
`desktop`, `mobile`, or `all`). The dry run prints each planned command with a `DRY-RUN:` prefix and
writes `release/<platform>/DRY-RUN.txt`. Godot does not run, and nothing is exported or signed. The
mobile budget gate still runs, so an over-budget Mobile asset shows up here.

## 2. Ship

Ask the agent to ship the target, and name the version when you have one to set: `--version X.Y.Z`
on the first ship, or `--bump major|minor|patch` after that. Without either flag, the current version
ships. The ship checks the version and the `CHANGELOG.md` section before it runs any Godot command,
then runs the gates: `godot --import` (so a fresh
clone has its class cache), `godot --check-only` on every script, your `game/tests/run_tests.gd`
when it exists, and a headless smoke run: the game starts with autoplay for 600 frames and the ship
stops with `ship.smoke_failed` if it prints a script error or does not finish. Then the mobile budget
gate runs for iOS, Android, and web. Then it exports each platform headless with its Godot preset,
signs and notarizes the macOS app, and writes each artifact to `release/<platform>/`.
`release/RELEASE-NOTES.md` lists every artifact with its SHA-256. To run the game yourself, or to
capture a screenshot of it, see [run-and-capture.md](run-and-capture.md).

## 3. Check the result

- Every platform folder holds one artifact and the release notes name it. The web build is the whole
  `release/web/` folder.
- The SHA-256 in the notes matches the artifact.
- A web build over 38 MB prints `WARNING [ship.web_pack_large]`; it still ships.
- A failing gate names the rule and a remediation. Fix that and ship again. Re-running is safe.

Skill reference: `skills/ship/SKILL.md`. Full reference: `docs/skills/ship.md`.
