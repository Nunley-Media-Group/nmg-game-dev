"""AC1 to AC3 for #227: gate-ue-compile passes the default toolchain arguments to Build.sh.

The #202 flag -NoUBA is gone. The provider test runs the real steering/extensions/ue-compile.mjs
through node against a fake Build.sh that logs its arguments, so no engine build or Unreal Editor
process starts. The provider returns incomplete off macOS, so that test is skipped elsewhere. The
snippet test reads the checked-in Verification Gates row.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
from typing import Any

import pytest

# Imports the provider module by path and calls its compile function with the request from argv.
_DRIVER = """
import { pathToFileURL } from "node:url";
const [modulePath, projectRoot, configJson] = process.argv.slice(1);
const { extension } = await import(pathToFileURL(modulePath).href);
const compile = extension.providers["project.ue-compile"];
const config = JSON.parse(configJson);
const identity = { id: "gate-ue-compile" };
process.stdout.write(JSON.stringify(await compile({ projectRoot, config, identity })));
"""

# Writes each argument on its own line to the file named by FAKE_BUILD_LOG, then reports success.
_FAKE_BUILD_SH = r"""#!/bin/sh
printf '%s\n' "$@" > "$FAKE_BUILD_LOG"
echo "Result: Succeeded"
exit 0
"""


@pytest.mark.skipif(sys.platform != "darwin", reason="gate-ue-compile returns incomplete off macOS")
def test_gate_passes_default_arguments_to_build_sh(
    tmp_path: pathlib.Path, repo_root: pathlib.Path
) -> None:
    ue_root = tmp_path / "UE_5.8"
    build_sh = ue_root / "Engine" / "Build" / "BatchFiles" / "Mac" / "Build.sh"
    build_sh.parent.mkdir(parents=True)
    build_sh.write_text(_FAKE_BUILD_SH, encoding="utf-8")
    build_sh.chmod(0o755)
    project = tmp_path / "fixtures" / "dogfood.uproject"
    project.parent.mkdir(parents=True)
    project.write_text("{}\n", encoding="utf-8")
    build_log = tmp_path / "build-args.txt"
    provider = repo_root / "steering" / "extensions" / "ue-compile.mjs"
    config = {"project": "fixtures/dogfood.uproject", "target": "DogfoodEditor"}
    env = {**os.environ, "UE_ROOT": str(ue_root), "FAKE_BUILD_LOG": str(build_log)}

    completed = subprocess.run(
        [
            "node",
            "--input-type=module",
            "-e",
            _DRIVER,
            str(provider),
            str(tmp_path),
            json.dumps(config),
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
    )

    assert completed.returncode == 0, completed.stderr
    result: dict[str, Any] = json.loads(completed.stdout)
    assert build_log.read_text(encoding="utf-8").splitlines() == [
        "DogfoodEditor",
        "Mac",
        "Development",
        f"-Project={project}",
        "-WaitMutex",
    ]
    assert result["status"] == "passed"
    commands = [item for item in result["evidence"] if item["kind"] == "command"]
    assert commands and "-NoUBA" not in commands[0]["summary"]


def test_documented_gate_row_shows_default_build(repo_root: pathlib.Path) -> None:
    snippet = (repo_root / "steering" / "snippets" / "project-tech.md").read_text(encoding="utf-8")
    rows = [line for line in snippet.splitlines() if line.startswith("| `gate-ue-compile` |")]
    assert len(rows) == 1
    row = rows[0]
    assert "Build.sh DogfoodEditor Mac Development -WaitMutex" in row
    for phrase in ("-NoUBA", "Unreal Build Accelerator", "parallel worktrees"):
        assert phrase not in row
