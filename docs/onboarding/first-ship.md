# Your first ship

This guide walks through the `ship` skill on a fixture project. Run it once on the fixture before you
ship your own game, so you know what each step prints.

## Before you start

- Onboard the project ([index.md](index.md)).
- Have the target platform's toolchain and secrets in place. The ship names any missing variable and
  stops before it builds. It never prints a secret value.

## 1. Dry run

Ask the agent to plan the release for a target (`macos`, `ios`, `android`, `windows`, `desktop`,
`mobile`, or `all`). The dry run prints each planned command with a `DRY-RUN:` prefix and writes
`release/<platform>/DRY-RUN.txt`. Nothing is built or signed.

## 2. Ship

Ask the agent to ship the target. The ship runs the gates first: cook manifest, mobile budgets, and
the UE Automation tests. Then it packages, signs, and notarizes each platform, and writes each artifact
to `release/<platform>/`. `release/RELEASE-NOTES.md` lists every artifact with its SHA-256.

## 3. Check the result

- Every platform folder holds one artifact and the release notes name it.
- The SHA-256 in the notes matches the file.
- A failing gate names the rule and a remediation. Fix that and ship again. Re-running is safe.

Skill reference: `skills/ship/SKILL.md`.
