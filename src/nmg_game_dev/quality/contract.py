"""Contract and re-import report models, and the gate that stops finalize on a failing report.

The Blender side (``contract_core``) writes these reports as plain JSON, so this module parses
them without importing ``bpy``. ``gate`` raises ``PipelineError`` for the finalize pipeline (#69)
to surface; it never inspects the asset itself.

See: specs/30-add-contract-validation-re-import-check-and-review-renders/design.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from nmg_game_dev.pipeline.errors import PipelineError

ReportKind = Literal["contract", "reimport"]

_STAGE: Final = "quality"
_GATE_CODES: Final[dict[ReportKind, str]] = {
    "contract": "quality.contract_failed",
    "reimport": "quality.reimport_mismatch",
}


class Finding(BaseModel):
    """One violated rule.

    Attributes:
        rule: Stable rule id, e.g. ``transform.root_applied``.
        target: The object, material, or image the rule failed on.
        message: What was found.
        remediation: The next action that fixes the finding.
    """

    rule: str
    target: str
    message: str
    remediation: str


class ContractReport(BaseModel):
    """A validation or re-import report, as written by the Blender side.

    Extra keys in the JSON are ignored, so the Blender side can add fields without breaking
    the host.

    Attributes:
        kind: ``contract`` for a validation report, ``reimport`` for a re-import report.
        asset: The asset name, e.g. ``Crate``.
        asset_class: The asset class, read from the JSON key ``class``.
        passed: ``True`` when no rule failed.
        findings: One entry per violated rule; empty when ``passed`` is ``True``.
        snapshot: Per-object measurements the checks read.
    """

    model_config = ConfigDict(populate_by_name=True)

    kind: ReportKind
    asset: str
    asset_class: str = Field(alias="class")
    passed: bool
    findings: list[Finding] = Field(default_factory=list)
    snapshot: dict[str, Any] = Field(default_factory=dict)


class ContractGateError(PipelineError):
    """A failing report raised by ``gate``. The parsed report rides along as ``report``."""

    def __init__(self, code: str, message: str, remediation: str, report: ContractReport) -> None:
        super().__init__(code=code, message=message, remediation=remediation, stage=_STAGE)
        self.report = report


def load_report(path: Path) -> ContractReport:
    """Parse a report JSON file; raise ``quality.report_unreadable`` if it cannot be read."""
    try:
        return ContractReport.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise PipelineError(
            code="quality.report_unreadable",
            message=f"Contract report is missing or malformed: {path} ({error})",
            remediation="Rerun the contract or re-import check so it writes a valid report, "
            "then retry.",
            stage=_STAGE,
        ) from error


def gate(report: ContractReport, kind: ReportKind) -> None:
    """Return when the report passed; otherwise raise ``ContractGateError``.

    ``kind`` selects the error code: ``quality.contract_failed`` for ``contract``, or
    ``quality.reimport_mismatch`` for ``reimport``.
    """
    if report.passed:
        return
    details = " | ".join(
        f"{finding.rule} {finding.target}: {finding.message}" for finding in report.findings
    )
    remediations = " | ".join(dict.fromkeys(finding.remediation for finding in report.findings))
    raise ContractGateError(
        code=_GATE_CODES[kind],
        message=f"{report.asset} failed the {kind} check: {details or 'no findings recorded'}",
        remediation=remediations
        or f"Rerun the {kind} check on {report.asset} and read its report.",
        report=report,
    )
