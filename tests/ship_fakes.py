"""Fakes for the ship tests: a temp consumer project and PATH shims that record their argv.

Every tool the ship scripts call (RunUAT.sh, codesign, security, xcrun, ditto, ssh, scp) becomes a
shell wrapper in the sandbox's ``bin/`` folder. The wrappers run ``tests/ship_shim.py``, which logs
argv and returns canned output. The environment is built from scratch rather than inherited, so no
real ``NOTARIZATION_*`` or keystore value reaches a script. Every credential here is a placeholder.
Nothing contacts Apple, Google, a store, or a keychain.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

SHIM: Final[Path] = Path(__file__).resolve().parent / "ship_shim.py"
REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
SCRIPTS: Final[Path] = REPO_ROOT / "scripts"
WRAPPED_TOOLS: Final[tuple[str, ...]] = ("codesign", "security", "xcrun", "ditto", "ssh", "scp")


@dataclass
class ShipSandbox:
    """A consumer project with fake tools on PATH.

    Attributes:
        project: The ``.uproject`` path, inside ``consumer/``.
        ue_root: A fake engine root holding ``Engine/Build/BatchFiles/RunUAT.sh``.
        bin_dir: Folder of wrappers that come first on PATH.
        log: JSON-lines file where every fake tool records its argv.
        env: The complete environment every ship run uses. It is never inherited.
    """

    project: Path
    ue_root: Path
    bin_dir: Path
    log: Path
    env: dict[str, str] = field(default_factory=dict)

    @property
    def release_dir(self) -> Path:
        return self.project.parent / "release"

    def calls(self, tool: str | None = None) -> list[list[str]]:
        """Return the argv of every recorded call, optionally only for one tool."""
        if not self.log.is_file():
            return []
        out: list[list[str]] = []
        for line in self.log.read_text(encoding="utf-8").splitlines():
            record: dict[str, Any] = json.loads(line)
            if tool is None or record["tool"] == tool:
                out.append([str(arg) for arg in record["argv"]])
        return out

    def invoked(self, tool: str) -> bool:
        return bool(self.calls(tool))


def make_sandbox(root: Path, *, project_name: str = "Dogfood") -> ShipSandbox:
    """Build a consumer project, a fake engine, and PATH shims under ``root``."""
    project_dir = root / "consumer"
    (project_dir / "Content" / "Shared").mkdir(parents=True)
    project = project_dir / f"{project_name}.uproject"
    project.write_text("{}", encoding="utf-8")
    (project_dir / "Content" / "Shared" / "Common.uasset").write_bytes(b"common")

    ue_root = root / "UE_5.8"
    runuat_dir = ue_root / "Engine" / "Build" / "BatchFiles"
    runuat_dir.mkdir(parents=True)
    _write_wrapper(runuat_dir / "RunUAT.sh", "RunUAT.sh")

    bin_dir = root / "bin"
    bin_dir.mkdir()
    for tool in WRAPPED_TOOLS:
        _write_wrapper(bin_dir / tool, tool)

    key = root / "builder.key"
    key.write_text("placeholder-key", encoding="utf-8")
    log = root / "calls.jsonl"
    env = {
        "PATH": os.pathsep.join([str(bin_dir), "/usr/bin", "/bin", "/usr/sbin", "/sbin"]),
        "HOME": str(root),
        "LANG": "C",
        "UE_ROOT": str(ue_root),
        "NMG_SHIP_FAKE_LOG": str(log),
        "NOTARIZATION_APPLE_ID": "ship-test@example.invalid",
        "NOTARIZATION_APP_SPECIFIC_PASSWORD": "placeholder-app-password",
        "NOTARIZATION_TEAM_ID": "SMOKE00000",
        "IOS_PROVISIONING_PROFILE": str(root / "Dogfood.mobileprovision"),
        "ANDROID_KEYSTORE": str(root / "upload.keystore"),
        "ANDROID_KEYSTORE_PASSWORD": "placeholder-keystore-password",
        "WINDOWS_BUILD_HOST": "win-build.example.invalid",
        "WINDOWS_BUILD_USER": "builder",
        "WINDOWS_BUILD_SSH_KEY": str(key),
        "WINDOWS_REMOTE_PROJECT_PATH": "C:\\build\\Dogfood\\Dogfood.uproject",
    }
    return ShipSandbox(
        project=project,
        ue_root=ue_root,
        bin_dir=bin_dir,
        log=log,
        env=env,
    )


def run_script(
    sandbox: ShipSandbox,
    name: str,
    *args: str,
    extra_env: dict[str, str] | None = None,
    without: tuple[str, ...] = (),
) -> subprocess.CompletedProcess[str]:
    """Run ``scripts/<name>`` under the sandbox environment, minus any ``without`` variables."""
    merged = {**sandbox.env, **(extra_env or {})}
    env = {key: value for key, value in merged.items() if key not in without}
    return subprocess.run(
        [str(SCRIPTS / name), *args],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def parse_frontmatter(text: str) -> dict[str, str]:
    """Return the ``key: value`` lines between the leading ``---`` fences of a SKILL.md."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip()
    return fields


def _write_wrapper(path: Path, tool: str) -> None:
    path.write_text(
        f"#!/bin/sh\nexec '{sys.executable}' '{SHIM}' '{tool}' \"$@\"\n",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
