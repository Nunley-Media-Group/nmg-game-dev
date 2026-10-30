"""Result models returned by ``pipeline.finalize`` and ``pipeline.run_step``.

``StepResult`` records one step's outcome and whether it was served from the cache.
``FinalizeResult`` lists every step and the UE content paths the run produced.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StepResult(BaseModel):
    """Outcome of one finalize step.

    Attributes:
        step: Step name: ``validate``, ``bake``, ``variants``, ``export``, ``reimport``, or
            ``import_ue``.
        cache_hit: ``True`` when the step was served from the content-addressed cache.
        outputs: Step-specific outputs.  Paths are strings.
        summary: One human-readable line.
    """

    model_config = ConfigDict(frozen=True)

    step: str
    cache_hit: bool
    outputs: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""


class FinalizeResult(BaseModel):
    """Outcome of a finalize run.

    Attributes:
        steps: One ``StepResult`` per requested step, in execution order.
        desktop_content_path: ``/Game/<Category>/<Name>/Desktop`` once ``import_ue`` ran or was
            served from cache, otherwise ``None``.
        mobile_content_path: ``/Game/<Category>/<Name>/Mobile`` under the same condition.
        loaded_back: ``True`` when the baked collections replaced the session's copies.
        result_blend: The last mutating step's ``.blend``, used for load-back.
    """

    model_config = ConfigDict(frozen=True)

    steps: list[StepResult]
    desktop_content_path: str | None = None
    mobile_content_path: str | None = None
    loaded_back: bool = False
    result_blend: str | None = None
