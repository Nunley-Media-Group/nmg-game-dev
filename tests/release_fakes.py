"""Helpers for the release-tooling tests (#95): the Blender gate driver and Blender resolution.

``resolved_blender`` mirrors scripts/run-blender-tests.sh: BLENDER_BIN, then BLENDER_APP, then the
default app bundle. ``run_gate`` runs the gate from the repo root with the caller's environment.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
GATE: Final[Path] = REPO_ROOT / "scripts" / "run-blender-tests.sh"


def resolved_blender() -> str | None:
    """Return the Blender binary the gate would run, or None when none resolves."""
    candidates = []
    if os.environ.get("BLENDER_BIN"):
        candidates.append(Path(os.environ["BLENDER_BIN"]))
    app = Path(os.environ.get("BLENDER_APP", "/Applications/Blender.app"))
    candidates.append(app / "Contents" / "MacOS" / "Blender")
    for candidate in candidates:
        if os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def write_suite(root: Path, body: str) -> Path:
    """Write one pytest file with body into root/suite and return that folder."""
    suite = root / "suite"
    suite.mkdir(parents=True)
    (suite / "test_gate.py").write_text(body, encoding="utf-8")
    return suite


def run_gate(extra_env: Mapping[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    """Run the Blender gate from the repo root, with extra_env layered over the environment."""
    env = {**os.environ, **extra_env}
    return subprocess.run(
        [str(GATE), *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
