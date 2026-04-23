"""Unit tests for the generate stage (T017)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.pipeline.prompt import Prompt
from nmg_game_dev.pipeline.stages._base import McpClients, StageContext
from nmg_game_dev.pipeline.stages.generate import generate_blender, generate_meshy


@pytest.fixture()
def prompt() -> Prompt:
    return Prompt(
        category="Props",
        name="TestCrate",
        tier="standard",
        description="wooden supply crate",
    )


class TestGenerateBlender:
    def test_happy_path(
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
        artifact = generate_blender(ctx)
        assert artifact.stage == "generate"
        assert artifact.sidecar is not None
        assert artifact.sidecar["source"] == "blender"

    def test_mcp_error_raises_pipeline_error(
        self,
        prompt: Prompt,
        fake_blender: Any,
        fake_unreal: Any,
        tmp_path: Path,
    ) -> None:
        fake_blender.run_script_side_effect = RuntimeError("connection refused")
        clients = McpClients(blender=fake_blender, unreal=fake_unreal)
        ctx = StageContext(
            prompt=prompt,
            upstream_artifact=None,
            cache_dir=tmp_path / "cache",
            mcp_clients=clients,
        )
        with pytest.raises(PipelineError) as exc_info:
            generate_blender(ctx)
        assert exc_info.value.code == "mcp.blender.unreachable"
        assert exc_info.value.stage == "generate"

    def test_invalid_response_raises_pipeline_error(
        self,
        prompt: Prompt,
        fake_blender: Any,
        fake_unreal: Any,
        tmp_path: Path,
    ) -> None:
        # Override run_script to return no output_path.
        fake_blender.run_script_side_effect = None

        class BadBlender:
            def run_script(self, script: str, **kwargs: object) -> dict[str, object]:
                return {}  # no output_path

            def ping(self) -> bool:
                return True

        clients = McpClients(blender=BadBlender(), unreal=fake_unreal)
        ctx = StageContext(
            prompt=prompt,
            upstream_artifact=None,
            cache_dir=tmp_path / "cache",
            mcp_clients=clients,
        )
        with pytest.raises(PipelineError) as exc_info:
            generate_blender(ctx)
        assert exc_info.value.code == "mcp.blender.invalid_response"


class TestGenerateMeshy:
    def test_happy_path(
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
        artifact = generate_meshy(ctx)
        assert artifact.stage == "generate"
        assert artifact.sidecar is not None
        assert artifact.sidecar["source"] == "meshy"

    def test_none_meshy_raises_pipeline_error(
        self,
        prompt: Prompt,
        fake_mcp_clients_no_meshy: Any,
        tmp_path: Path,
    ) -> None:
        ctx = StageContext(
            prompt=prompt,
            upstream_artifact=None,
            cache_dir=tmp_path / "cache",
            mcp_clients=fake_mcp_clients_no_meshy,
        )
        with pytest.raises(PipelineError) as exc_info:
            generate_meshy(ctx)
        assert exc_info.value.code == "mcp.meshy.unreachable"

    def test_mcp_error_raises_pipeline_error(
        self,
        prompt: Prompt,
        fake_meshy: Any,
        fake_blender: Any,
        fake_unreal: Any,
        tmp_path: Path,
    ) -> None:
        fake_meshy.generate_side_effect = ConnectionError("timeout")
        clients = McpClients(blender=fake_blender, unreal=fake_unreal, meshy=fake_meshy)
        ctx = StageContext(
            prompt=prompt,
            upstream_artifact=None,
            cache_dir=tmp_path / "cache",
            mcp_clients=clients,
        )
        with pytest.raises(PipelineError) as exc_info:
            generate_meshy(ctx)
        assert exc_info.value.code == "mcp.meshy.unreachable"
        assert exc_info.value.stage == "generate"
