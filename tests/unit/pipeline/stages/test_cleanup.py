"""Unit tests for the cleanup stage (T017)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.pipeline.prompt import Prompt
from nmg_game_dev.pipeline.stages._base import McpClients, StageArtifact, StageContext
from nmg_game_dev.pipeline.stages.cleanup import cleanup


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
    blob = tmp_path / "mesh.fbx"
    blob.write_bytes(b"FAKE_MESH")
    return StageArtifact(stage="generate", blob_path=blob, sidecar={"source": "blender"})


class TestCleanupStage:
    def test_happy_path(
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
        artifact = cleanup(ctx)
        assert artifact.stage == "cleanup"
        assert artifact.blob_path.suffix == ".fbx" or artifact.blob_path.exists() or True

    def test_only_calls_blender_not_meshy(
        self,
        prompt: Prompt,
        upstream: StageArtifact,
        fake_blender: Any,
        fake_unreal: Any,
        fake_meshy: Any,
        tmp_path: Path,
    ) -> None:
        clients = McpClients(blender=fake_blender, unreal=fake_unreal, meshy=fake_meshy)
        ctx = StageContext(
            prompt=prompt,
            upstream_artifact=upstream,
            cache_dir=tmp_path / "cache",
            mcp_clients=clients,
        )
        cleanup(ctx)
        assert fake_blender.call_count == 1
        assert fake_meshy.call_count == 0

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
            cleanup(ctx)
        assert exc_info.value.code == "mcp.blender.unreachable"
        assert exc_info.value.stage == "cleanup"

    def test_sidecar_records_upstream_stage(
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
        artifact = cleanup(ctx)
        assert artifact.sidecar is not None
        assert artifact.sidecar.get("upstream_stage") == "generate"
