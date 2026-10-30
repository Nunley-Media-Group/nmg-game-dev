"""Mobile budget gate for the ship flow (#6): each Mobile variant checked against asset-contract §6.

A ``Content/<Category>/<Name>/Mobile/`` folder must hold ``nmg-asset.json``, the per-asset report
finalize writes. ``check_mobile_budgets`` compares it with the mobile defaults, merged per metric
with an optional project-root ``nmg-budgets.json``. It reads files and runs no tool, so the ship
flow may call it in a dry run.

See: specs/6-ship-skills-per-platform-build-sign-notarize-package/design.md
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

AssetClass = Literal["small_prop", "standard_prop", "hero_prop", "character", "environment_piece"]

ASSET_CLASSES: Final[tuple[str, ...]] = (
    "small_prop",
    "standard_prop",
    "hero_prop",
    "character",
    "environment_piece",
)
BUDGET_METRICS: Final[tuple[str, ...]] = ("tris", "max_texture_px", "materials")

# asset-contract.md §6, Mobile column.
DEFAULT_MOBILE_BUDGETS: Final[dict[str, dict[str, int]]] = {
    "small_prop": {"tris": 500, "max_texture_px": 512, "materials": 1},
    "standard_prop": {"tris": 3000, "max_texture_px": 1024, "materials": 1},
    "hero_prop": {"tris": 10000, "max_texture_px": 2048, "materials": 2},
    "character": {"tris": 15000, "max_texture_px": 2048, "materials": 2},
    "environment_piece": {"tris": 10000, "max_texture_px": 1024, "materials": 3},
}

REPORT_NAME: Final = "nmg-asset.json"
OVERRIDES_NAME: Final = "nmg-budgets.json"

CODE_EXCEEDED: Final = "ship.mobile_budget_exceeded"
CODE_REPORT_MISSING: Final = "ship.budget_report_missing"
CODE_REPORT_INVALID: Final = "ship.budget_report_invalid"
CODE_OVERRIDE_INVALID: Final = "ship.budget_override_invalid"

# The gate reports the first code in this order: configuration errors before asset errors.
GATE_CODE_ORDER: Final[tuple[str, ...]] = (
    CODE_OVERRIDE_INVALID,
    CODE_REPORT_INVALID,
    CODE_REPORT_MISSING,
    CODE_EXCEEDED,
)


class BudgetFinding(BaseModel):
    """One failed budget check.

    Attributes:
        code: Stable gate code, e.g. ``ship.mobile_budget_exceeded``.
        subject: The asset as ``Category/Name``, or ``nmg-budgets.json`` for an override file.
        message: What failed, on one line.
        remediation: The next action that fixes it.
    """

    code: str
    subject: str
    message: str
    remediation: str


class MobileBudgetAudit(BaseModel):
    """Result of checking every Mobile variant under a project's ``Content/`` folder.

    Attributes:
        passed: ``True`` when no check failed.
        assets: Each Mobile variant checked, as ``Category/Name``, in sorted order.
        findings: One entry per failed check; empty when ``passed`` is ``True``.
    """

    passed: bool
    assets: list[str]
    findings: list[BudgetFinding]


class _AssetReport(BaseModel):
    """The per-asset report shape. Extra keys are ignored; metric values must be integers."""

    model_config = ConfigDict(populate_by_name=True)

    asset_class: AssetClass = Field(alias="class")
    tris: int = Field(strict=True, ge=0)
    max_texture_px: int = Field(strict=True, ge=0)
    materials: int = Field(strict=True, ge=0)


def check_mobile_budgets(project_root: Path) -> MobileBudgetAudit:
    """Check every ``Content/**/Mobile/`` folder under ``project_root`` against its budget.

    A missing or malformed report, and an invalid ``nmg-budgets.json``, are findings too. Budgets
    are the defaults with each valid override applied per metric. An invalid override file leaves
    the defaults in place and fails the audit.
    """
    budgets, findings = _effective_budgets(project_root)
    content = project_root / "Content"
    assets: list[str] = []
    for mobile_dir in _mobile_folders(content):
        subject = mobile_dir.parent.relative_to(content).as_posix()
        assets.append(subject)
        report_path = mobile_dir / REPORT_NAME
        if not report_path.is_file():
            findings.append(_missing_report(subject))
            continue
        try:
            report = _AssetReport.model_validate_json(report_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            findings.append(_invalid_report(subject, error))
            continue
        findings.extend(_over_budget(subject, report, budgets[report.asset_class]))
    return MobileBudgetAudit(passed=not findings, assets=assets, findings=findings)


def _mobile_folders(content: Path) -> list[Path]:
    if not content.is_dir():
        return []
    return sorted(
        folder for folder in content.rglob("Mobile") if folder.is_dir() and folder.parent != content
    )


def _effective_budgets(
    project_root: Path,
) -> tuple[dict[str, dict[str, int]], list[BudgetFinding]]:
    budgets = {cls: dict(metrics) for cls, metrics in DEFAULT_MOBILE_BUDGETS.items()}
    path = project_root / OVERRIDES_NAME
    if not path.is_file():
        return budgets, []
    try:
        overrides = _read_overrides(path)
    except (OSError, ValueError) as error:
        finding = BudgetFinding(
            code=CODE_OVERRIDE_INVALID,
            subject=OVERRIDES_NAME,
            message=f"{OVERRIDES_NAME} cannot be applied: {_reason(error)}",
            remediation=(
                f"Fix {OVERRIDES_NAME} so each key is an asset class ({', '.join(ASSET_CLASSES)}), "
                f"each metric is one of {', '.join(BUDGET_METRICS)}, and each value is a "
                "non-negative integer. Or delete it to use the defaults."
            ),
        )
        return budgets, [finding]
    for cls, metrics in overrides.items():
        budgets[cls].update(metrics)
    return budgets, []


def _read_overrides(path: Path) -> dict[str, dict[str, int]]:
    """Parse ``nmg-budgets.json``; raise ``ValueError`` naming the first invalid entry."""
    data: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("it must be a JSON object keyed by asset class")
    overrides: dict[str, dict[str, int]] = {}
    for asset_class, metrics in data.items():
        if asset_class not in ASSET_CLASSES:
            raise ValueError(f"unknown asset class {asset_class!r}")
        if not isinstance(metrics, dict):
            raise ValueError(f"{asset_class} must map metric names to integers")
        overrides[asset_class] = {}
        for metric, value in metrics.items():
            if metric not in BUDGET_METRICS:
                raise ValueError(f"unknown metric {metric!r} for {asset_class}")
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{asset_class}.{metric} must be a non-negative integer")
            overrides[asset_class][metric] = value
    return overrides


def _over_budget(subject: str, report: _AssetReport, budget: dict[str, int]) -> list[BudgetFinding]:
    values = {
        "tris": report.tris,
        "max_texture_px": report.max_texture_px,
        "materials": report.materials,
    }
    findings: list[BudgetFinding] = []
    for metric, value in values.items():
        limit = budget[metric]
        if value <= limit:
            continue
        line = f"{subject}: {metric} {value} > {limit} (+{value - limit})"
        findings.append(
            BudgetFinding(
                code=CODE_EXCEEDED,
                subject=subject,
                message=line,
                remediation=(
                    f"{line}. Reduce the Mobile {metric} to {limit} or fewer and finalize "
                    f"{subject} again, or raise {report.asset_class}.{metric} in "
                    f"{OVERRIDES_NAME} for this project."
                ),
            )
        )
    return findings


def _missing_report(subject: str) -> BudgetFinding:
    return BudgetFinding(
        code=CODE_REPORT_MISSING,
        subject=subject,
        message=f"{subject}: Mobile/ has no {REPORT_NAME}",
        remediation=f"finalize {subject} to write Mobile/{REPORT_NAME}, then rerun the ship.",
    )


def _invalid_report(subject: str, error: Exception) -> BudgetFinding:
    return BudgetFinding(
        code=CODE_REPORT_INVALID,
        subject=subject,
        message=f"{subject}: Mobile/{REPORT_NAME} is malformed ({_reason(error)})",
        remediation=(
            f"Rewrite {subject}'s Mobile/{REPORT_NAME} with class, tris, max_texture_px, and "
            f"materials, or finalize {subject} to write it again."
        ),
    )


def _reason(error: Exception) -> str:
    if isinstance(error, ValidationError):
        return "; ".join(
            f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
            for item in error.errors()
        )
    text = str(error).strip()
    return text.splitlines()[0] if text else type(error).__name__
