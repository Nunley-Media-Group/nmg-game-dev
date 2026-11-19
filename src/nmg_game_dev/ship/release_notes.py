"""``release/RELEASE-NOTES.md``: the version, changelog section, gate results, and artifacts (#6).

Each artifact is listed with its SHA-256 (#254 FR4).

The heading names the version (``# Release notes — 1.3.0``). ``## Changes`` carries the consumer's
``CHANGELOG.md`` section for that version, verbatim. ``## Gates`` lists each gate that ran with its
result. ``## Artifacts`` is the SHA-256 table. A dry run is marked in the notes and lists no
artifacts, because none were produced.
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
    *,
    version: str | None = None,
    changes: str = "",
    gates: Sequence[tuple[str, str]] = (),
) -> Path:
    """Write ``release/RELEASE-NOTES.md`` and return its path.

    ``gates`` holds ``(gate, result)`` pairs in the order the gates ran.
    """
    release_dir.mkdir(parents=True, exist_ok=True)
    title = f"# Release notes — {version}" if version else "# Release notes"
    lines = [
        title,
        "",
        f"- Target: `{target}`",
        f"- Platforms: {', '.join(platforms) or 'none'}",
        f"- Mode: {'dry run' if dry_run else 'release'}",
    ]
    if version:
        lines.append(f"- Version: {version}")
    lines.append("")
    if dry_run:
        lines += [
            "> **DRY RUN.** No export, signing, notarization, or packaging ran, and no artifact "
            "was produced. Each platform's `DRY-RUN.txt` lists the planned commands.",
            "",
        ]
    if changes:
        lines += ["## Changes", "", changes, ""]
    if gates:
        lines += ["## Gates", ""]
        lines += [f"- {gate}: {result}" for gate, result in gates]
        lines.append("")
    lines += ["## Artifacts", "", "| Platform | Artifact | SHA-256 |", "| --- | --- | --- |"]
    if entries:
        lines += [f"| {entry.platform} | `{entry.path}` | `{entry.sha256}` |" for entry in entries]
    else:
        lines.append("| - | none | - |")
    path = release_dir / RELEASE_NOTES_NAME
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
