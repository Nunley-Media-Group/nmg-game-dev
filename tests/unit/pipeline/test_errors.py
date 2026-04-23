"""Unit tests for PipelineError (T016)."""

from __future__ import annotations

import pytest

from nmg_game_dev.pipeline.errors import PipelineError


class TestPipelineError:
    def test_all_four_fields_accessible(self) -> None:
        err = PipelineError(
            code="quality.mobile_budget_exceeded",
            message="poly count too high",
            remediation="reduce mesh complexity",
            stage="quality",
        )
        assert err.code == "quality.mobile_budget_exceeded"
        assert err.message == "poly count too high"
        assert err.remediation == "reduce mesh complexity"
        assert err.stage == "quality"

    def test_is_exception(self) -> None:
        err = PipelineError("c", "m", "r", "s")
        assert isinstance(err, Exception)

    def test_str_is_message(self) -> None:
        err = PipelineError("c", "my message", "r", "s")
        assert str(err) == "my message"

    def test_can_be_raised_and_caught(self) -> None:
        with pytest.raises(PipelineError) as exc_info:
            raise PipelineError(
                "mcp.blender.unreachable", "unreachable", "restart blender", "generate"
            )
        assert exc_info.value.code == "mcp.blender.unreachable"
        assert exc_info.value.stage == "generate"

    def test_all_fields_are_str(self) -> None:
        err = PipelineError("a", "b", "c", "d")
        assert isinstance(err.code, str)
        assert isinstance(err.message, str)
        assert isinstance(err.remediation, str)
        assert isinstance(err.stage, str)
