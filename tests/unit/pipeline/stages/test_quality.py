"""Unit tests for the quality stage (T017)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.pipeline.prompt import Prompt
from nmg_game_dev.pipeline.stages._base import StageArtifact, StageContext
from nmg_game_dev.pipeline.stages.quality import quality


@pytest.fixture()
def prompt() -> Prompt:
    return Prompt(
        category="Props",
        name="TestCrate",
        tier="standard",
        description="wooden supply crate",
    )


def _variants_artifact(
    tmp_path: Path,
    poly_mobile: int = 2_000,
    tex_mobile: int = 500_000,
) -> StageArtifact:
    blob = tmp_path / "desktop.fbx"
    blob.write_bytes(b"FAKE_DESKTOP")
    return StageArtifact(
        stage="variants",
        blob_path=blob,
        sidecar={
            "desktop_path": str(tmp_path / "Desktop" / "SM_TestCrate.fbx"),
            "mobile_path": str(tmp_path / "Mobile" / "SM_TestCrate.fbx"),
            "poly_count_desktop": 10_000,
            "poly_count_mobile": poly_mobile,
            "texture_bytes_desktop": 2_000_000,
            "texture_bytes_mobile": tex_mobile,
            "variant": "desktop",
        },
    )


class TestQualityStage:
    def test_happy_path_passes(
        self,
        prompt: Prompt,
        fake_mcp_clients: Any,
        tmp_path: Path,
    ) -> None:
        ctx = StageContext(
            prompt=prompt,
            upstream_artifact=_variants_artifact(tmp_path),
            cache_dir=tmp_path / "cache",
            mcp_clients=fake_mcp_clients,
        )
        artifact = quality(ctx)
        assert artifact.stage == "quality"
        assert artifact.sidecar is not None
        assert artifact.sidecar["passed"] is True

    def test_mobile_budget_exceeded_raises(
        self,
        prompt: Prompt,
        fake_mcp_clients: Any,
        tmp_path: Path,
    ) -> None:
        # Way over budget poly count.
        ctx = StageContext(
            prompt=prompt,
            upstream_artifact=_variants_artifact(tmp_path, poly_mobile=999_999),
            cache_dir=tmp_path / "cache",
            mcp_clients=fake_mcp_clients,
        )
        with pytest.raises(PipelineError) as exc_info:
            quality(ctx)
        assert exc_info.value.code == "quality.mobile_budget_exceeded"
        assert exc_info.value.stage == "quality"

    def test_budget_exceeded_remediation_mentions_poly(
        self,
        prompt: Prompt,
        fake_mcp_clients: Any,
        tmp_path: Path,
    ) -> None:
        ctx = StageContext(
            prompt=prompt,
            upstream_artifact=_variants_artifact(tmp_path, poly_mobile=999_999),
            cache_dir=tmp_path / "cache",
            mcp_clients=fake_mcp_clients,
        )
        with pytest.raises(PipelineError) as exc_info:
            quality(ctx)
        remediation = exc_info.value.remediation.lower()
        assert "poly" in remediation or "mobile" in remediation

    def test_manifest_malformed_raises(
        self,
        prompt: Prompt,
        fake_mcp_clients: Any,
        tmp_path: Path,
    ) -> None:
        blob = tmp_path / "desktop.fbx"
        blob.write_bytes(b"FAKE")
        # Artifact with missing manifest fields.
        bad_artifact = StageArtifact(
            stage="variants",
            blob_path=blob,
            sidecar={"poly_count_mobile": 100, "texture_bytes_mobile": 100},
        )
        ctx = StageContext(
            prompt=prompt,
            upstream_artifact=bad_artifact,
            cache_dir=tmp_path / "cache",
            mcp_clients=fake_mcp_clients,
        )
        with pytest.raises(PipelineError) as exc_info:
            quality(ctx)
        assert exc_info.value.code == "quality.manifest_malformed"

    def test_no_upstream_raises(
        self,
        prompt: Prompt,
        fake_mcp_clients: Any,
        tmp_path: Path,
    ) -> None:
        ctx = StageContext(
            prompt=prompt,
            upstream_artifact=None,
            cache_dir=tmp_path / "cache",
            mcp_clients=fake_mcp_clients,
        )
        with pytest.raises(PipelineError) as exc_info:
            quality(ctx)
        assert exc_info.value.code == "quality.no_upstream"

    def test_no_mcp_calls_made(
        self,
        prompt: Prompt,
        fake_blender: Any,
        fake_unreal: Any,
        fake_meshy: Any,
        tmp_path: Path,
    ) -> None:
        from nmg_game_dev.pipeline.stages._base import McpClients

        clients = McpClients(blender=fake_blender, unreal=fake_unreal, meshy=fake_meshy)
        ctx = StageContext(
            prompt=prompt,
            upstream_artifact=_variants_artifact(tmp_path),
            cache_dir=tmp_path / "cache",
            mcp_clients=clients,
        )
        quality(ctx)
        assert fake_blender.call_count == 0
        assert fake_unreal.call_count == 0
        assert fake_meshy.call_count == 0
