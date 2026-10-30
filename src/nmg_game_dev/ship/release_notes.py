"""``release/RELEASE-NOTES.md``: the target, its platforms, and each artifact with its SHA-256 (#6).

A dry run is marked in the notes and lists no artifacts, because none were produced.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Final

from nmg_game_dev.ship.artifacts import ReleaseEntry

RELEASE_NOTES_NAME: Final = "RELEASE-NOTES.md"


def write_release_notes(
    release_dir: Path,
    target: str,
    entries: Sequence[ReleaseEntry],
    dry_run: bool,
    platforms: Sequence[str] = (),
) -> Path:
    """Write ``release/RELEASE-NOTES.md`` and return its path."""
    release_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Release notes",
        "",
        f"- Target: `{target}`",
        f"- Platforms: {', '.join(platforms) or 'none'}",
        f"- Mode: {'dry run' if dry_run else 'release'}",
        "",
    ]
    if dry_run:
        lines += [
            "> **DRY RUN.** No build, signing, notarization, or packaging ran, and no artifact "
            "was produced. Each platform's `DRY-RUN.txt` lists the planned commands.",
            "",
        ]
    lines += ["| Platform | Artifact | SHA-256 |", "| --- | --- | --- |"]
    if entries:
        lines += [f"| {entry.platform} | `{entry.path}` | `{entry.sha256}` |" for entry in entries]
    else:
        lines.append("| - | none | - |")
    path = release_dir / RELEASE_NOTES_NAME
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
