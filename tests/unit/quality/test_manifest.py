"""Unit tests for quality.check_manifest (T016)."""

from __future__ import annotations

from pathlib import Path

from nmg_game_dev.pipeline.stages._base import StageArtifact
from nmg_game_dev.quality import ManifestReport, check_manifest


def _full_sidecar() -> dict[str, object]:
    return {
        "desktop_path": "/Content/Props/TestCrate/Desktop/SM_TestCrate.fbx",
        "mobile_path": "/Content/Props/TestCrate/Mobile/SM_TestCrate.fbx",
        "poly_count_desktop": 20_000,
        "poly_count_mobile": 5_000,
        "texture_bytes_desktop": 4_000_000,
        "texture_bytes_mobile": 1_000_000,
    }


def _artifact(sidecar: dict[str, object] | None) -> StageArtifact:
    return StageArtifact(stage="variants", blob_path=Path("/fake/mesh.fbx"), sidecar=sidecar)


class TestCheckManifest:
    def test_full_sidecar_passes(self) -> None:
        report = check_manifest(_artifact(_full_sidecar()))
        assert report.passed is True
        assert report.reasons == []

    def test_missing_desktop_path_fails(self) -> None:
        sidecar = _full_sidecar()
        del sidecar["desktop_path"]
        report = check_manifest(_artifact(sidecar))
        assert report.passed is False
        assert any("desktop_path" in r for r in report.reasons)

    def test_missing_mobile_path_fails(self) -> None:
        sidecar = _full_sidecar()
        del sidecar["mobile_path"]
        report = check_manifest(_artifact(sidecar))
        assert report.passed is False
        assert any("mobile_path" in r for r in report.reasons)

    def test_wrong_type_poly_count_fails(self) -> None:
        sidecar = _full_sidecar()
        sidecar["poly_count_desktop"] = "not-an-int"
        report = check_manifest(_artifact(sidecar))
        assert report.passed is False
        assert any("poly_count_desktop" in r for r in report.reasons)

    def test_none_sidecar_fails_all_fields(self) -> None:
        report = check_manifest(_artifact(None))
        assert report.passed is False
        # All 6 required fields should be reported missing
        assert len(report.reasons) == 6

    def test_empty_sidecar_fails_all_fields(self) -> None:
        report = check_manifest(_artifact({}))
        assert report.passed is False
        assert len(report.reasons) == 6

    def test_returns_manifest_report_type(self) -> None:
        report = check_manifest(_artifact(_full_sidecar()))
        assert isinstance(report, ManifestReport)
