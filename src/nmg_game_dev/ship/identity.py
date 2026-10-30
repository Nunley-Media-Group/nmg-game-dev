"""macOS signing identity resolution (#6, FR8, AC9).

The identity comes from ``MACOS_SIGNING_IDENTITY`` when set. Otherwise it is the first
``Developer ID Application`` identity whose team matches ``NOTARIZATION_TEAM_ID``, read from
``security find-identity``. The lookup runs under the ship's explicit environment, so a test can
put a shim first on ``PATH``. A dry run returns a placeholder and runs nothing.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable, Mapping
from typing import Final

from nmg_game_dev.ship.errors import ShipError

Runner = Callable[..., subprocess.CompletedProcess[str]]

_IDENTITY_LINE: Final = re.compile(r'"(Developer ID Application: [^"]*\(([A-Z0-9]+)\))"')


def resolve_signing_identity(
    env: Mapping[str, str],
    run: Runner = subprocess.run,
    dry_run: bool = False,
) -> str:
    """Return the codesign identity for the team, or raise ``ship.signing_identity_missing``."""
    explicit = env.get("MACOS_SIGNING_IDENTITY", "")
    if explicit:
        return explicit
    team = env.get("NOTARIZATION_TEAM_ID", "")
    if dry_run:
        return f"<Developer ID Application for team {team}>"
    result = run(
        ["security", "find-identity", "-v", "-p", "codesigning"],
        env=dict(env),
        capture_output=True,
        text=True,
        check=False,
    )
    for line in result.stdout.splitlines():
        match = _IDENTITY_LINE.search(line)
        if match and match.group(2) == team:
            return match.group(1)
    raise ShipError(
        code="ship.signing_identity_missing",
        message=f"No Developer ID Application identity matches team {team}.",
        remediation=(
            "Install the Developer ID Application certificate for that team in the login "
            "keychain, or set MACOS_SIGNING_IDENTITY to its name."
        ),
        stage="sign",
    )
