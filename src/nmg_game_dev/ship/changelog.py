"""The player changelog section a ship requires before it gates (#254 FR3, AC3).

``changelog_section`` finds the heading ``## X.Y.Z`` (also ``## [X.Y.Z]``, with optional trailing
text such as a date) in the consumer's root ``CHANGELOG.md`` and returns the section's text, up to
the next ``## `` heading. A missing file, a missing heading, or a section with no non-blank line
raises ``ship.changelog_missing`` before any Godot command runs.

See: the #254 design
(§ Changelog)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

from nmg_game_dev.ship.errors import ShipError

CHANGELOG_NAME: Final = "CHANGELOG.md"


def changelog_section(path: Path, version: str) -> str:
    """Return the text of the ``## version`` section in ``path``, without its surrounding blanks."""
    if not path.is_file():
        raise _missing(path, version, "does not exist")
    heading = re.compile(rf"^##\s+\[?{re.escape(version)}\]?(\s.*)?$")
    lines = path.read_text(encoding="utf-8").splitlines()
    start = next((index + 1 for index, line in enumerate(lines) if heading.match(line)), None)
    if start is None:
        raise _missing(path, version, f"has no '## {version}' section")
    body: list[str] = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        body.append(line.rstrip())
    while body and not body[0].strip():
        body.pop(0)
    while body and not body[-1].strip():
        body.pop()
    if not body:
        raise _missing(path, version, f"has a '## {version}' section with no text")
    return "\n".join(body)


def _missing(path: Path, version: str, detail: str) -> ShipError:
    return ShipError(
        code="ship.changelog_missing",
        message=f"{path} {detail}; a ship of {version} needs a section with player-facing text.",
        remediation=f"Add a `## {version}` section with at least one line for players to "
        "CHANGELOG.md, then rerun the ship.",
        stage="preflight",
    )
