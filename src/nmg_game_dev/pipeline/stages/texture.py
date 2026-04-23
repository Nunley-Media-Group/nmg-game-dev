"""Texture stage — abstract placeholder awaiting the #5 spike pick.

This module defines the ``texture`` function that satisfies the ``Stage``
Protocol but immediately raises ``PipelineError("texture.not_implemented",
...)`` because the concrete texture-generation tool is chosen by the
separately-scoped issue #5 spike.

The ``pipeline.run()`` entrypoint accepts a ``stage_overrides`` keyword
argument that lets callers (including BDD test fixtures) substitute a
real or scripted implementation without modifying this module::

    pipeline.run(prompt, source="blender", stage_overrides={"texture": my_texture_fn})

See: requirements.md FR3, steering/tech.md § Texture-gen tool interface (TBD).
"""

from __future__ import annotations

from ..errors import PipelineError
from ._base import StageArtifact, StageContext

_STAGE = "texture"


def texture(ctx: StageContext) -> StageArtifact:  # noqa: ARG001
    """Placeholder texture stage — always raises until #5 lands.

    Args:
        ctx: Stage execution context (ignored by this placeholder).

    Raises:
        PipelineError: Always — with code ``"texture.not_implemented"`` and
            remediation pointing at issue #5.
    """
    raise PipelineError(
        code="texture.not_implemented",
        message="texture stage awaits the #5 spike pick",
        remediation=(
            "Track issue #5 — the concrete texture-generation tool is selected "
            "there.  This stage is a placeholder in #4.  To run the pipeline "
            "in tests, pass stage_overrides={'texture': your_fixture_fn} to "
            "pipeline.run()."
        ),
        stage=_STAGE,
    )
