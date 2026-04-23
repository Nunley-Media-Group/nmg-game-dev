"""Unit tests for quality.check_mobile_budget (T016)."""

from __future__ import annotations

from pathlib import Path

from nmg_game_dev.pipeline.stages._base import StageArtifact
from nmg_game_dev.quality import MobileBudget, check_mobile_budget

_BUDGET = MobileBudget(poly_budget=10_000, texture_byte_budget=2 * 1024 * 1024)


def _artifact(poly_mobile: int, tex_mobile: int) -> StageArtifact:
    return StageArtifact(
        stage="variants",
        blob_path=Path("/fake/mesh.fbx"),
        sidecar={
            "poly_count_mobile": poly_mobile,
            "texture_bytes_mobile": tex_mobile,
            "poly_count_desktop": 20_000,
            "texture_bytes_desktop": 5_000_000,
            "desktop_path": "/fake/Desktop/mesh.fbx",
            "mobile_path": "/fake/Mobile/mesh.fbx",
        },
    )


class TestCheckMobileBudget:
    def test_within_budget_passes(self) -> None:
        report = check_mobile_budget(_artifact(5_000, 1_000_000), _BUDGET)
        assert report.passed is True
        assert report.reasons == []
        assert report.variant == "mobile"

    def test_poly_over_budget_fails(self) -> None:
        report = check_mobile_budget(_artifact(15_000, 1_000_000), _BUDGET)
        assert report.passed is False
        assert len(report.reasons) == 1
        assert "poly count" in report.reasons[0].lower()

    def test_texture_over_budget_fails(self) -> None:
        report = check_mobile_budget(_artifact(5_000, 3 * 1024 * 1024), _BUDGET)
        assert report.passed is False
        assert len(report.reasons) == 1
        assert "texture" in report.reasons[0].lower()

    def test_both_over_budget_two_reasons(self) -> None:
        report = check_mobile_budget(_artifact(20_000, 5 * 1024 * 1024), _BUDGET)
        assert report.passed is False
        assert len(report.reasons) == 2

    def test_exact_budget_passes(self) -> None:
        report = check_mobile_budget(_artifact(10_000, 2 * 1024 * 1024), _BUDGET)
        assert report.passed is True

    def test_missing_poly_field_defaults_zero(self) -> None:
        artifact = StageArtifact(
            stage="variants",
            blob_path=Path("/fake/mesh.fbx"),
            sidecar={"texture_bytes_mobile": 100},
        )
        report = check_mobile_budget(artifact, _BUDGET)
        assert report.poly_count == 0
        assert report.passed is True

    def test_none_sidecar_defaults_zero(self) -> None:
        artifact = StageArtifact(stage="variants", blob_path=Path("/fake/mesh.fbx"), sidecar=None)
        report = check_mobile_budget(artifact, _BUDGET)
        assert report.poly_count == 0
        assert report.texture_bytes == 0

    def test_report_carries_budget_values(self) -> None:
        report = check_mobile_budget(_artifact(5_000, 1_000_000), _BUDGET)
        assert report.poly_budget == 10_000
        assert report.texture_budget == 2 * 1024 * 1024

    def test_remediation_mentions_mobile_poly_budget(self) -> None:
        report = check_mobile_budget(_artifact(20_000, 100), _BUDGET)
        assert not report.passed
        reason = report.reasons[0]
        # Should mention the overage
        assert "10,000" in reason or "polygons" in reason.lower()
