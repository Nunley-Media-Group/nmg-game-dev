"""Quality gate stage — pure-local budget + manifest checks.

No MCP calls.  Reads the variants artifact sidecar and delegates to
``nmg_game_dev.quality.check_mobile_budget`` and ``check_manifest``.
Raises ``PipelineError`` on any failure so the orchestrator never invokes the
``import_ue`` stage when quality has not been verified.

The quality result is itself cached so a re-run after a successful run hits
cache instead of re-checking (satisfying AC3).
"""

from __future__ import annotations

import nmg_game_dev.quality as quality_helpers
from nmg_game_dev.quality import MobileBudget

from ..errors import PipelineError
from ._base import StageArtifact, StageContext

_STAGE = "quality"

# Default mobile budgets.  These are conservative starting points; consumer
# projects can inject a different ``MobileBudget`` via the stage context in a
# future iteration when budget configuration surfaces to skills.
_DEFAULT_MOBILE_BUDGET = MobileBudget(
    poly_budget=15_000,
    texture_byte_budget=4 * 1024 * 1024,  # 4 MiB
)


def quality(ctx: StageContext) -> StageArtifact:
    """Run budget + manifest quality checks on the variants artifact.

    Args:
        ctx: Stage execution context.  ``ctx.upstream_artifact`` is the
            artifact produced by the variants stage.

    Returns:
        A ``StageArtifact`` whose sidecar carries the ``BudgetReport`` and
        ``ManifestReport`` for downstream observability.

    Raises:
        PipelineError: With code ``"quality.mobile_budget_exceeded"`` or
            ``"quality.manifest_malformed"`` when a check fails.
    """
    upstream = ctx.upstream_artifact
    if upstream is None:
        raise PipelineError(
            code="quality.no_upstream",
            message="quality stage requires an upstream artifact from variants",
            remediation="Ensure the variants stage ran successfully before quality.",
            stage=_STAGE,
        )

    budget_report = quality_helpers.check_mobile_budget(upstream, _DEFAULT_MOBILE_BUDGET)
    manifest_report = quality_helpers.check_manifest(upstream)

    if not budget_report.passed:
        reasons_text = " | ".join(budget_report.reasons)
        raise PipelineError(
            code="quality.mobile_budget_exceeded",
            message=f"Mobile variant exceeds budget: {reasons_text}",
            remediation=(
                f"Reduce the mobile variant's polygon count and/or texture size. "
                f"Current mobile poly count: {budget_report.poly_count:,} "
                f"(budget: {budget_report.poly_budget:,}). "
                f"Current mobile texture: {budget_report.texture_bytes:,} bytes "
                f"(budget: {budget_report.texture_budget:,} bytes). "
                f"Re-run the variants stage with more aggressive decimation."
            ),
            stage=_STAGE,
        )

    if not manifest_report.passed:
        reasons_text = " | ".join(manifest_report.reasons)
        raise PipelineError(
            code="quality.manifest_malformed",
            message=f"Variant artifact sidecar is missing required manifest fields: {reasons_text}",
            remediation=(
                "Ensure the variants stage writes all required sidecar fields: "
                "desktop_path, mobile_path, poly_count_desktop, poly_count_mobile, "
                "texture_bytes_desktop, texture_bytes_mobile."
            ),
            stage=_STAGE,
        )

    upstream_sidecar = upstream.sidecar or {}
    sidecar: dict[str, object] = {
        "budget_report": budget_report.model_dump(),
        "manifest_report": manifest_report.model_dump(),
        "passed": True,
        # Pass through variant paths so import_ue can find them without
        # reaching back to the variants artifact directly.
        "desktop_path": upstream_sidecar.get("desktop_path", ""),
        "mobile_path": upstream_sidecar.get("mobile_path", ""),
    }
    return StageArtifact(
        stage=_STAGE,
        blob_path=upstream.blob_path,
        sidecar=sidecar,
    )
