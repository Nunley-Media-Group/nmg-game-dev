# THIS-REPO-ONLY — fixtures MUST NOT ship to consumers

This directory contains test fixtures used by `nmg-game-dev` contributors for local
smoke-testing of the launcher scripts and pipeline tooling.

**These files are NOT consumer-facing and MUST NOT be copied to a consumer game project
by `onboard-consumer` or any other distribution mechanism.**

See `specs/feature-scaffold-plugin-repo-session-start-hooks/requirements.md` § AC10
(no-leak requirement) for the full rationale.

## Contents

| File | Purpose |
|------|---------|
| `dogfood.uproject` | Minimal UE 5.8 project — gives `scripts/start-unreal-mcp.sh` a valid target when invoked from this repo without a consumer project present. Enables `ModelContextProtocol`, `EditorToolset` (Epic's native Unreal MCP), `VibeUE` (installed into `Plugins/`), and `nmg-game-dev`. |
| `Config/DefaultEditorPerProjectUserSettings.ini` | Turns on Epic's Unreal MCP server on `ServerPortNumber=8000` (`bAutoStartServer=True`) for editors opened by hand. `start-unreal-mcp.sh` also passes the launch flags, so either path serves `127.0.0.1:8000/mcp`. |
| `Config/DefaultEngine.ini`, `Config/DefaultInput.ini` | Tracked project settings so a fresh clone can build the `DogfoodEditor` target. |
| `Source/` | `Dogfood` game module plus `Dogfood.Target.cs` and `DogfoodEditor.Target.cs`. Tracked for the same reason as `Config/`. |
| `smoke/SM_SmokeCube.fbx` | 1 m cube exported from headless Blender per `docs/asset-contract.md` §7. `scripts/smoke-unreal-mcp.py` imports it into `/Game/__NmgSmoke` and removes it again. Rebuild it with `"$BLENDER_APP/Contents/MacOS/Blender" --background --factory-startup --python fixtures/smoke/make_smoke_fbx.py`. |
| `Plugins/VibeUE/` | Not tracked (see `.gitignore`). Fetched by `scripts/install-vibeue.sh`, which clones VibeUE's `5-8` branch at depth 1, or updates an existing clone to that branch's head, and prints the commit it checked out. |

Build output (`Binaries/`, `Intermediate/`, `Saved/`) stays untracked.

Set up the VibeUE plugin before opening the fixture:

```
scripts/install-vibeue.sh
scripts/start-unreal-mcp.sh
scripts/smoke-unreal-mcp.py
```

## Adding new fixtures

New fixtures belong here when they are:

- Used only inside `nmg-game-dev` development/testing workflows.
- Not part of a consumer game project's expected directory structure.

Consumer-facing templates belong in `templates/consumer/` instead.
