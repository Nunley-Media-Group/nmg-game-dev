"""Unit tests for the PipelineResult model (T016)."""

from __future__ import annotations

from pathlib import Path

from nmg_game_dev.pipeline.result import PipelineResult


class TestPipelineResult:
    def test_constructs_with_required_fields(self) -> None:
        r = PipelineResult(
            desktop_path=Path("/content/Props/TestCrate/Desktop"),
            mobile_path=Path("/content/Props/TestCrate/Mobile"),
            stages_executed=["generate", "texture"],
            cache_hits=["cleanup"],
        )
        assert r.desktop_path == Path("/content/Props/TestCrate/Desktop")
        assert r.mobile_path == Path("/content/Props/TestCrate/Mobile")
        assert r.stages_executed == ["generate", "texture"]
        assert r.cache_hits == ["cleanup"]

    def test_round_trip_json(self) -> None:
        r = PipelineResult(
            desktop_path=Path("/content/Props/TestCrate/Desktop"),
            mobile_path=Path("/content/Props/TestCrate/Mobile"),
            stages_executed=["generate"],
            cache_hits=[],
        )
        json_str = r.model_dump_json()
        r2 = PipelineResult.model_validate_json(json_str)
        assert r2.desktop_path == r.desktop_path
        assert r2.mobile_path == r.mobile_path
        assert r2.stages_executed == r.stages_executed
        assert r2.cache_hits == r.cache_hits

    def test_empty_lists(self) -> None:
        r = PipelineResult(
            desktop_path=Path("/d"),
            mobile_path=Path("/m"),
            stages_executed=[],
            cache_hits=[],
        )
        assert r.stages_executed == []
        assert r.cache_hits == []
