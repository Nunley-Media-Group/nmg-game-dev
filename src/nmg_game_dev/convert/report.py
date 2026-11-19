"""The conversion report: ``godot-conversion-report.md`` at the consumer root (#249 FR11, AC12).

Sections, in order: Converted (every item done so far, including earlier runs), Failed (item, code,
remediation), Manual port (path, reason), and Deletions (the removed paths, "failed: <error>"
when removing them failed, or "kept: N item(s) failed").
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from nmg_game_dev.convert.plan import ManualPort

REPORT_NAME: Final = "godot-conversion-report.md"


@dataclass(frozen=True)
class Failure:
    """One item that did not convert, with its error code and remediation."""

    item: str
    code: str
    message: str
    remediation: str


def _cell(text: str) -> str:
    return " ".join(text.replace("|", "\\|").split())


def render_report(
    converted: Sequence[str],
    failures: Sequence[Failure],
    manual_port: Sequence[ManualPort],
    deletions: Sequence[str],
    *,
    deleted: bool,
    deletion_error: str | None = None,
) -> str:
    """Return the report text."""
    lines = ["# Godot conversion report", "", "## Converted", ""]
    lines.extend([f"- `{key}`" for key in converted] or ["None."])
    lines.extend(["", "## Failed", ""])
    if failures:
        lines.extend(["| Item | Code | Remediation |", "|------|------|-------------|"])
        lines.extend(f"| `{f.item}` | `{f.code}` | {_cell(f.remediation)} |" for f in failures)
    else:
        lines.append("None.")
    lines.extend(["", "## Manual port", ""])
    if manual_port:
        lines.extend(["| Path | Reason |", "|------|--------|"])
        lines.extend(f"| `{row.path}` | {_cell(row.reason)} |" for row in manual_port)
    else:
        lines.append("None.")
    lines.extend(["", "## Deletions", ""])
    if deletion_error is not None:
        lines.append(f"failed: {_cell(deletion_error)}")
    elif deleted:
        lines.append(
            "done: " + (", ".join(f"`{path}`" for path in deletions) or "nothing to delete")
        )
    else:
        count = len(failures)
        lines.append(f"kept: {count} item{'' if count == 1 else 's'} failed")
    return "\n".join(lines) + "\n"


def write_report(root: Path, text: str) -> Path:
    """Write the report to ``<root>/godot-conversion-report.md`` and return its path."""
    path = root / REPORT_NAME
    path.write_text(text, encoding="utf-8")
    return path
