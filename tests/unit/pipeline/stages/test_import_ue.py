"""Unit tests for the import_ue stage (T017)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.pipeline.prompt import Prompt
from nmg_game_dev.pipeline.stages._base import McpClients, StageArtifact, StageContext
from nmg_game_dev.pipeline.stages.import_ue import import_ue


@pytest.fixture()
def prompt() -> Prompt:
    return Prompt(
        category="Props",
        name="TestCrate",
        tier="standard",
        description="wooden supply crate",
    )


def _quality_artifact(tmp_path: Path) -> StageArtifact:
    blob = tmp_path / "desktop.fbx"
    blob.write_bytes(b"FAKE_DESKTOP")
    return StageArtifact(
        stage="quality",
        blob_path=blob,
        sidecar={
            "desktop_path": str(tmp_path / "Desktop" / "SM_TestCrate.fbx"),
            "mobile_path": str(tmp_path / "Mobile" / "SM_TestCrate.fbx"),
        },
    )


class TestImportUeStage:
    def test_happy_path(
        self,
        prompt: Prompt,
        fake_mcp_clients: Any,
        tmp_path: Path,
    ) -> None:
        ctx = StageContext(
            prompt=prompt,
            upstream_artifact=_quality_artifact(tmp_path),
            cache_dir=tmp_path / "cache",
            mcp_clients=fake_mcp_clients,
        )
        artifact = import_ue(ctx)
        assert artifact.stage == "import_ue"
        assert artifact.sidecar is not None
        assert "desktop_path" in artifact.sidecar
        assert "mobile_path" in artifact.sidecar

    def test_calls_unreal_twice_desktop_and_mobile(
        self,
        prompt: Prompt,
        fake_blender: Any,
        fake_unreal: Any,
        tmp_path: Path,
    ) -> None:
        clients = McpClients(blender=fake_blender, unreal=fake_unreal)
        ctx = StageContext(
            prompt=prompt,
            upstream_artifact=_quality_artifact(tmp_path),
            cache_dir=tmp_path / "cache",
            mcp_clients=clients,
        )
        import_ue(ctx)
        assert fake_unreal.call_count == 2

    def test_destination_paths_match_convention(
        self,
        prompt: Prompt,
        fake_blender: Any,
        fake_unreal: Any,
        tmp_path: Path,
    ) -> None:
        clients = McpClients(blender=fake_blender, unreal=fake_unreal)
        ctx = StageContext(
            prompt=prompt,
            upstream_artifact=_quality_artifact(tmp_path),
            cache_dir=tmp_path / "cache",
            mcp_clients=clients,
        )
        import_ue(ctx)
        calls = fake_unreal.import_asset_calls
        dest_paths = [c[1] for c in calls]
        assert any("Desktop" in d for d in dest_paths)
        assert any("Mobile" in d for d in dest_paths)

    def test_unreal_error_raises_pipeline_error(
        self,
        prompt: Prompt,
        fake_blender: Any,
        fake_unreal: Any,
        tmp_path: Path,
    ) -> None:
        fake_unreal.import_asset_side_effect = RuntimeError("UE MCP unreachable")
        clients = McpClients(blender=fake_blender, unreal=fake_unreal)
        ctx = StageContext(
            prompt=prompt,
            upstream_artifact=_quality_artifact(tmp_path),
            cache_dir=tmp_path / "cache",
            mcp_clients=clients,
        )
        with pytest.raises(PipelineError) as exc_info:
            import_ue(ctx)
        assert exc_info.value.code == "mcp.unreal.unreachable"
        assert exc_info.value.stage == "import_ue"

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
            import_ue(ctx)
        assert exc_info.value.code == "import_ue.no_upstream"

    def test_missing_paths_in_sidecar_raises(
        self,
        prompt: Prompt,
        fake_mcp_clients: Any,
        tmp_path: Path,
    ) -> None:
        blob = tmp_path / "desktop.fbx"
        blob.write_bytes(b"X")
        artifact = StageArtifact(stage="quality", blob_path=blob, sidecar={"passed": True})
        ctx = StageContext(
            prompt=prompt,
            upstream_artifact=artifact,
            cache_dir=tmp_path / "cache",
            mcp_clients=fake_mcp_clients,
        )
        with pytest.raises(PipelineError) as exc_info:
            import_ue(ctx)
        assert exc_info.value.code == "import_ue.missing_paths"
