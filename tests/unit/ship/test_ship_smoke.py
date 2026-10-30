"""AC10: scripts/ship-smoke.sh runs a dry-run "all" ship of the fixture and exits 0.

The smoke sets its own placeholder credentials and runs no tool that touches a service. This test
gives the script a minimal environment, so no real NOTARIZATION_* or keystore value is inherited.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.ship_fakes import REPO_ROOT, SCRIPTS


def test_ship_smoke_dry_run_of_all_exits_zero() -> None:
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is required to run scripts/ship-smoke.sh")
    env = {
        "PATH": os.pathsep.join([str(Path(uv).parent), "/usr/bin", "/bin", "/usr/sbin", "/sbin"]),
        "HOME": os.environ.get("HOME", str(REPO_ROOT)),
        "LANG": "C",
    }
    result = subprocess.run(
        [str(SCRIPTS / "ship-smoke.sh")],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "DRY-RUN" in result.stdout
    assert "Release notes:" in result.stdout
