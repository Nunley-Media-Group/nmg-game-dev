"""StepResult and the text report that onboarding prints (#7 FR9).

Each step reports one of ``installed``, ``unchanged``, ``drift``, ``refreshed``, or ``skipped``.
Drift leaves the item unchanged and carries the remediation ``re-run with --refresh``. ``skipped``
means the step does not apply to this consumer (for example, no git work tree), and its detail says
why. The command still exits 0.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

Status = Literal["installed", "unchanged", "drift", "refreshed", "skipped"]

REFRESH_REMEDIATION = "re-run with --refresh"


@dataclass(frozen=True)
class StepResult:
    """One step's outcome: what it is, what happened, and what to do about drift."""

    name: str
    status: Status
    detail: str
    remediation: str | None = None

    def as_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "remediation": self.remediation,
        }


def format_report(results: list[StepResult]) -> str:
    """One ``<status> <step>: <detail>`` line per step, with a ``Remediation:`` line for drift."""
    lines: list[str] = []
    for result in results:
        lines.append(f"{result.status} {result.name}: {result.detail}")
        if result.remediation is not None:
            lines.append(f"  Remediation: {result.remediation}")
    return "\n".join(lines)
