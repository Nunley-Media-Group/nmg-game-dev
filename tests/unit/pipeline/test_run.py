"""Unit tests for pipeline.run() orchestrator (T017)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from nmg_game_dev.pipeline import _STAGE_ORDER, run
from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.pipeline.prompt import Prompt
from nmg_game_dev.pipeline.stages._base import McpClients, StageArtifact, StageContext


@pytest.fixture()
def prompt() -> Prompt:
    return Prompt(
        category="Props",
        name="TestCrate",
        tier="standard",
        description="wooden supply crate",
    )


def _fake_texture(ctx: StageContext) -> StageArtifact:
    """Test-fixture texture stage that passes through the upstream blob."""
    upstream = ctx.upstream_artifact
    blob = upstream.blob_path if upstream is not None else ctx.cache_dir / "texture_out.fbx"
    if not blob.exists():
        blob.parent.mkdir(parents=True, exist_ok=True)
        blob.write_bytes(b"FAKE_TEXTURE")
    return StageArtifact(stage="texture", blob_path=blob, sidecar={"textured": True})


class TestStageOrder:
    def test_stage_order_tuple_exported(self) -> None:
        assert isinstance(_STAGE_ORDER, tuple)

    def test_stage_order_six_elements(self) -> None:
        assert len(_STAGE_ORDER) == 6

    def test_stage_order_correct_sequence(self) -> None:
        assert _STAGE_ORDER == (
            "generate",
            "texture",
            "cleanup",
            "variants",
            "quality",
            "import_ue",
        )


class TestRunNullMcpClients:
    def test_none_mcp_clients_raises_pipeline_error(self, prompt: Prompt, tmp_path: Path) -> None:
        with pytest.raises(PipelineError) as exc_info:
            run(prompt, "blender", cache_dir=tmp_path / "cache", mcp_clients=None)
        assert exc_info.value.code == "pipeline.no_mcp_clients"


class TestRunHappyPath:
    def test_blender_source_full_chain(
        self,
        prompt: Prompt,
        fake_mcp_clients: Any,
        tmp_path: Path,
    ) -> None:
        result = run(
            prompt,
            "blender",
            cache_dir=tmp_path / "cache",
            mcp_clients=fake_mcp_clients,
            stage_overrides={"texture": _fake_texture},
        )
        assert "Props" in str(result.desktop_path)
        assert "TestCrate" in str(result.desktop_path)
        assert result.stages_executed == list(_STAGE_ORDER)
        assert result.cache_hits == []

    def test_meshy_source_routing(
        self,
        prompt: Prompt,
        fake_mcp_clients: Any,
        fake_meshy: Any,
        tmp_path: Path,
    ) -> None:
        result = run(
            prompt,
            "meshy",
            cache_dir=tmp_path / "cache",
            mcp_clients=fake_mcp_clients,
            stage_overrides={"texture": _fake_texture},
        )
        # Meshy generate should have been called once.
        assert fake_meshy.call_count == 1
        assert "Props" in str(result.desktop_path)

    def test_result_contains_all_six_stages_executed(
        self,
        prompt: Prompt,
        fake_mcp_clients: Any,
        tmp_path: Path,
    ) -> None:
        result = run(
            prompt,
            "blender",
            cache_dir=tmp_path / "cache",
            mcp_clients=fake_mcp_clients,
            stage_overrides={"texture": _fake_texture},
        )
        assert set(result.stages_executed) == set(_STAGE_ORDER)


class TestRunCacheShortCircuit:
    def test_second_run_hits_cache(
        self,
        prompt: Prompt,
        fake_mcp_clients: Any,
        tmp_path: Path,
    ) -> None:
        cache_dir = tmp_path / "cache"
        # First run.
        result1 = run(
            prompt,
            "blender",
            cache_dir=cache_dir,
            mcp_clients=fake_mcp_clients,
            stage_overrides={"texture": _fake_texture},
        )
        assert result1.stages_executed == list(_STAGE_ORDER)
        assert result1.cache_hits == []

        # Second run with same prompt and new fakes — blender should not be called.
        class NonCalledBlender:
            def run_script(self, script: str, **kwargs: object) -> dict[str, object]:
                raise AssertionError("Blender should not be called on a fully-cached run!")

            def ping(self) -> bool:
                return True

        class NonCalledUnreal:
            def import_asset(
                self, source_path: str, destination_path: str, **kwargs: object
            ) -> dict[str, object]:
                raise AssertionError("Unreal should not be called on a fully-cached run!")

            def ping(self) -> bool:
                return True

        second_clients = McpClients(blender=NonCalledBlender(), unreal=NonCalledUnreal())
        result2 = run(
            prompt,
            "blender",
            cache_dir=cache_dir,
            mcp_clients=second_clients,
            stage_overrides={"texture": _fake_texture},
        )
        assert result2.cache_hits == list(_STAGE_ORDER)
        assert result2.stages_executed == []


class TestRunErrorReRaise:
    def test_pipeline_error_reraises_unchanged(
        self,
        prompt: Prompt,
        fake_blender: Any,
        fake_unreal: Any,
        tmp_path: Path,
    ) -> None:
        fake_blender.run_script_side_effect = RuntimeError("blender down")
        clients = McpClients(blender=fake_blender, unreal=fake_unreal)
        with pytest.raises(PipelineError) as exc_info:
            run(
                prompt,
                "blender",
                cache_dir=tmp_path / "cache",
                mcp_clients=clients,
                stage_overrides={"texture": _fake_texture},
            )
        # The error should propagate with its original code, not wrapped.
        assert exc_info.value.code == "mcp.blender.unreachable"
        assert exc_info.value.stage == "generate"

    def test_downstream_stages_not_called_after_error(
        self,
        prompt: Prompt,
        fake_blender: Any,
        fake_unreal: Any,
        tmp_path: Path,
    ) -> None:
        fake_blender.run_script_side_effect = RuntimeError("blender down")
        clients = McpClients(blender=fake_blender, unreal=fake_unreal)
        with pytest.raises(PipelineError):
            run(
                prompt,
                "blender",
                cache_dir=tmp_path / "cache",
                mcp_clients=clients,
                stage_overrides={"texture": _fake_texture},
            )
        # Unreal should never be called because the pipeline stopped at generate.
        assert fake_unreal.call_count == 0
