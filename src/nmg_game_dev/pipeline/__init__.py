"""Pipeline composition core — variant-aware stage runner.

Single public entrypoint for all NMG asset-generation pipelines.  Every skill
that generates an asset (``new-prop``, ``new-character``, etc.) calls
``pipeline.run(...)`` rather than speaking MCP directly.

Stage order
-----------
``_STAGE_ORDER`` is the authoritative sequence and is importable by BDD steps
and unit tests so the order is never duplicated in the test suite::

    generate → texture → cleanup → variants → quality → import_ue

Source routing
--------------
Only the ``generate`` stage branches on ``source``:

- ``"blender"`` → ``stages.generate.generate_blender``
- ``"meshy"``   → ``stages.generate.generate_meshy``

All downstream stages are source-agnostic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from .cache import ArtifactCache
from .errors import PipelineError
from .prompt import Prompt
from .result import PipelineResult
from .stages._base import McpClients, Stage, StageArtifact, StageContext, StageName
from .stages.cleanup import cleanup
from .stages.generate import generate_blender, generate_meshy
from .stages.import_ue import import_ue
from .stages.quality import quality
from .stages.texture import texture
from .stages.variants import variants

Source = Literal["blender", "meshy"]

#: Authoritative stage execution order.  Import this in tests and BDD steps
#: rather than hard-coding the sequence a second time.
_STAGE_ORDER: tuple[StageName, ...] = (
    "generate",
    "texture",
    "cleanup",
    "variants",
    "quality",
    "import_ue",
)


def run(
    prompt: Prompt,
    source: Source,
    *,
    cache_dir: Path | None = None,
    mcp_clients: McpClients | None = None,
    stage_overrides: dict[StageName, Stage] | None = None,
) -> PipelineResult:
    """Compose generate → texture → cleanup → variants → quality → import_ue.

    Parameters
    ----------
    prompt:
        Validated asset-generation prompt.
    source:
        ``"blender"`` for Blender-first (default MCP: Blender).
        ``"meshy"`` for Meshy-supplement (generate via Meshy; all other
        stages via Blender + UE).
    cache_dir:
        Override the content-addressed cache root.  Defaults to
        ``${NMG_GAME_DEV_CACHE_DIR:-~/.cache/nmg-game-dev}``.
    mcp_clients:
        Pre-configured MCP client container.  When ``None``, raises
        ``PipelineError("pipeline.no_mcp_clients", ...)`` — the real
        ``.mcp.json``-based loader lands in a follow-up issue; for now
        construct ``McpClients`` manually or pass scripted fakes.
    stage_overrides:
        Optional mapping of stage name → ``Stage`` callable used to
        substitute specific stages (e.g. a fixture texture implementation
        in BDD tests).  This is a **test seam** — production callers should
        not need it.  Only the named stages in the dict are overridden;
        all others use the default implementations.

    Returns
    -------
    PipelineResult
        Desktop + Mobile variant paths plus per-stage execution bookkeeping.

    Raises
    ------
    PipelineError
        When any stage fails.  ``.code``/``.message``/``.remediation`` carry
        the failure detail.  No UE import is attempted after any failure.
        The error is re-raised unchanged — the orchestrator does NOT wrap it.
    """
    if mcp_clients is None:
        raise PipelineError(
            code="pipeline.no_mcp_clients",
            message="No MCP clients provided; pass mcp_clients= explicitly",
            remediation=(
                "Real .mcp.json-based loader lands in a follow-up issue — for now "
                "construct McpClients manually or pass fakes."
            ),
            stage="pipeline",
        )

    cache = ArtifactCache(cache_dir)
    resolved_cache_dir = cache.root
    overrides = stage_overrides or {}

    generate_fn: Stage = overrides.get(
        "generate",
        generate_blender if source == "blender" else generate_meshy,
    )
    stage_chain: list[tuple[StageName, Stage]] = [
        ("generate", generate_fn),
        ("texture", overrides.get("texture", texture)),
        ("cleanup", overrides.get("cleanup", cleanup)),
        ("variants", overrides.get("variants", variants)),
        ("quality", overrides.get("quality", quality)),
        ("import_ue", overrides.get("import_ue", import_ue)),
    ]

    prompt_hash = prompt.stable_hash()
    upstream_artifact: StageArtifact | None = None
    upstream_hash: str | None = None
    stages_executed: list[str] = []
    cache_hits: list[str] = []

    for stage_name, stage_fn in stage_chain:
        cache_key = cache.key(stage_name, prompt_hash, upstream_hash)

        cached = cache.get(cache_key)
        if cached is not None:
            cache_hits.append(stage_name)
            upstream_artifact = cached
            upstream_hash = cached.content_hash()
            continue

        ctx = StageContext(
            prompt=prompt,
            upstream_artifact=upstream_artifact,
            cache_dir=resolved_cache_dir,
            mcp_clients=mcp_clients,
        )
        # PipelineError propagates unchanged; no wrapping.
        artifact = stage_fn(ctx)
        cache.put(cache_key, artifact)
        stages_executed.append(stage_name)
        upstream_artifact = artifact
        upstream_hash = artifact.content_hash()

    if upstream_artifact is None:
        # Unreachable with a non-empty stage_chain; real safeguard, not asserted away under -O.
        raise PipelineError(
            code="pipeline.empty_chain",
            message="No stages executed — stage_chain was empty",
            remediation="Report this as a bug; the pipeline should always run at least import_ue.",
            stage="pipeline",
        )
    final_sidecar = upstream_artifact.sidecar or {}
    desktop_path_raw = final_sidecar.get("desktop_path", "")
    mobile_path_raw = final_sidecar.get("mobile_path", "")

    if not isinstance(desktop_path_raw, str) or not desktop_path_raw:
        raise PipelineError(
            code="pipeline.missing_desktop_path",
            message="import_ue artifact sidecar missing desktop_path",
            remediation="Check the import_ue stage implementation.",
            stage="import_ue",
        )
    if not isinstance(mobile_path_raw, str) or not mobile_path_raw:
        raise PipelineError(
            code="pipeline.missing_mobile_path",
            message="import_ue artifact sidecar missing mobile_path",
            remediation="Check the import_ue stage implementation.",
            stage="import_ue",
        )

    return PipelineResult(
        desktop_path=Path(desktop_path_raw),
        mobile_path=Path(mobile_path_raw),
        stages_executed=stages_executed,
        cache_hits=cache_hits,
    )
