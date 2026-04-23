"""Unit tests for the texture stage placeholder (T017)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.pipeline.prompt import Prompt
from nmg_game_dev.pipeline.stages._base import StageContext
from nmg_game_dev.pipeline.stages.texture import texture


@pytest.fixture()
def prompt() -> Prompt:
    return Prompt(
        category="Props",
        name="TestCrate",
        tier="standard",
        description="wooden supply crate",
    )


class TestTexturePlaceholder:
    def test_always_raises_not_implemented(
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
            texture(ctx)
        assert exc_info.value.code == "texture.not_implemented"

    def test_error_stage_is_texture(
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
            texture(ctx)
        assert exc_info.value.stage == "texture"

    def test_remediation_mentions_issue_5(
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
            texture(ctx)
        assert "#5" in exc_info.value.remediation
