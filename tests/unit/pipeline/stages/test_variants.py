"""Unit tests for the variants stage (T017)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.pipeline.prompt import Prompt
from nmg_game_dev.pipeline.stages._base import McpClients, StageArtifact, StageContext
from nmg_game_dev.pipeline.stages.variants import variants


@pytest.fixture()
def prompt() -> Prompt:
    return Prompt(
        category="Props",
        name="TestCrate",
        tier="standard",
        description="wooden supply crate",
    )


@pytest.fixture()
def upstream(tmp_path: Path) -> StageArtifact:
    blob = tmp_path / "cleaned.fbx"
    blob.write_bytes(b"FAKE_CLEANED")
    return StageArtifact(stage="cleanup", blob_path=blob, sidecar=None)


class TestVariantsStage:
    def test_happy_path_returns_artifact(
        self,
        prompt: Prompt,
        upstream: StageArtifact,
        fake_mcp_clients: Any,
        tmp_path: Path,
    ) -> None:
        ctx = StageContext(
            prompt=prompt,
            upstream_artifact=upstream,
            cache_dir=tmp_path / "cache",
            mcp_clients=fake_mcp_clients,
        )
        artifact = variants(ctx)
        assert artifact.stage == "variants"
        assert artifact.sidecar is not None

    def test_sidecar_has_required_manifest_fields(
        self,
        prompt: Prompt,
        upstream: StageArtifact,
        fake_mcp_clients: Any,
        tmp_path: Path,
    ) -> None:
        ctx = StageContext(
            prompt=prompt,
            upstream_artifact=upstream,
            cache_dir=tmp_path / "cache",
            mcp_clients=fake_mcp_clients,
        )
        artifact = variants(ctx)
        assert artifact.sidecar is not None
        for field in [
            "desktop_path",
            "mobile_path",
            "poly_count_desktop",
            "poly_count_mobile",
            "texture_bytes_desktop",
            "texture_bytes_mobile",
        ]:
            assert field in artifact.sidecar, f"Missing sidecar field: {field}"

    def test_mcp_error_raises_pipeline_error(
        self,
        prompt: Prompt,
        upstream: StageArtifact,
        fake_blender: Any,
        fake_unreal: Any,
        tmp_path: Path,
    ) -> None:
        fake_blender.run_script_side_effect = RuntimeError("blender crash")
        clients = McpClients(blender=fake_blender, unreal=fake_unreal)
        ctx = StageContext(
            prompt=prompt,
            upstream_artifact=upstream,
            cache_dir=tmp_path / "cache",
            mcp_clients=clients,
        )
        with pytest.raises(PipelineError) as exc_info:
            variants(ctx)
        assert exc_info.value.code == "mcp.blender.unreachable"
        assert exc_info.value.stage == "variants"
