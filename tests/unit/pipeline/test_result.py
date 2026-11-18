"""Unit tests for the finalize result models (AC1, #69)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from nmg_game_dev.pipeline import FinalizeResult, StepResult


def test_step_result_is_frozen() -> None:
    result = StepResult(step="bake", cache_hit=False, outputs={"blend": "/x"}, summary="ok")
    with pytest.raises(ValidationError):
        result.cache_hit = True


def test_finalize_result_lists_steps_and_resource_paths() -> None:
    step = StepResult(step="import_godot", cache_hit=True)
    result = FinalizeResult(
        steps=[step],
        desktop_resource_path="res://assets/Props/Crate/Desktop/Crate.glb",
        mobile_resource_path="res://assets/Props/Crate/Mobile/Crate.glb",
    )
    assert result.steps == [step]
    assert result.desktop_resource_path == "res://assets/Props/Crate/Desktop/Crate.glb"
    assert result.mobile_resource_path == "res://assets/Props/Crate/Mobile/Crate.glb"
    assert result.loaded_back is False
    assert result.result_blend is None


def test_finalize_result_round_trips_through_json() -> None:
    result = FinalizeResult(
        steps=[StepResult(step="validate", cache_hit=False, outputs={"report": "/r.json"})],
        loaded_back=True,
        result_blend="/job/variants.blend",
    )
    restored = FinalizeResult.model_validate_json(result.model_dump_json())
    assert restored == result
