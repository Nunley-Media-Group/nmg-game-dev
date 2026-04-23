"""Import UE stage — imports Desktop + Mobile assets into the UE content tree.

Calls the VibeUE MCP bridge (``ctx.mcp_clients.unreal``) to import each
variant into ``Content/<Category>/<Name>/{Desktop,Mobile}/``.  The desktop
and mobile paths are read from the variants artifact sidecar (written by the
variants stage and preserved through the quality artifact).

The stage sidecar records the final ``desktop_path`` and ``mobile_path`` that
``PipelineResult`` returns to the caller.
"""

from __future__ import annotations

from pathlib import Path

from ..errors import PipelineError
from ._base import StageArtifact, StageContext
from ._mcp import translate_mcp_errors

_STAGE = "import_ue"


def import_ue(ctx: StageContext) -> StageArtifact:
    """Import Desktop + Mobile assets into the UE content tree via VibeUE MCP.

    Args:
        ctx: Stage execution context.  ``ctx.upstream_artifact`` is the
            quality stage artifact, whose sidecar retains the ``desktop_path``
            and ``mobile_path`` written by the variants stage.

    Returns:
        A ``StageArtifact`` whose sidecar carries ``desktop_path`` and
        ``mobile_path`` — the final UE content tree paths returned to the
        skill caller via ``PipelineResult``.

    Raises:
        PipelineError: On VibeUE MCP connectivity or import failure.
    """
    upstream = ctx.upstream_artifact
    if upstream is None:
        raise PipelineError(
            code="import_ue.no_upstream",
            message="import_ue stage requires an upstream artifact from quality",
            remediation="Ensure the quality stage ran successfully before import_ue.",
            stage=_STAGE,
        )

    # The variants stage writes desktop_path / mobile_path; the quality stage
    # preserves them via its own sidecar. A stage substitute that omits either
    # field is the only way to reach the guard below.
    sidecar = upstream.sidecar or {}
    desktop_path_raw = sidecar.get("desktop_path")
    mobile_path_raw = sidecar.get("mobile_path")

    if desktop_path_raw is None or mobile_path_raw is None:
        raise PipelineError(
            code="import_ue.missing_paths",
            message=(
                "import_ue stage could not find desktop_path/mobile_path in the "
                "upstream artifact sidecar.  Ensure the variants stage wrote them."
            ),
            remediation=(
                "Re-run the pipeline from the variants stage.  The variants stage "
                "is responsible for writing desktop_path and mobile_path to its sidecar."
            ),
            stage=_STAGE,
        )

    desktop_source = str(desktop_path_raw)
    mobile_source = str(mobile_path_raw)

    # Compute UE destination paths — ``Content/<Category>/<Name>/{Desktop,Mobile}/``
    ue_desktop_dest = f"Content/{ctx.prompt.category}/{ctx.prompt.name}/Desktop/"
    ue_mobile_dest = f"Content/{ctx.prompt.category}/{ctx.prompt.name}/Mobile/"

    with translate_mcp_errors(server="unreal", stage=_STAGE):
        desktop_result = ctx.mcp_clients.unreal.import_asset(
            source_path=desktop_source,
            destination_path=ue_desktop_dest,
        )
        mobile_result = ctx.mcp_clients.unreal.import_asset(
            source_path=mobile_source,
            destination_path=ue_mobile_dest,
        )

    imported_desktop = desktop_result.get("imported_path", desktop_source)
    imported_mobile = mobile_result.get("imported_path", mobile_source)

    if not isinstance(imported_desktop, str):
        imported_desktop = desktop_source
    if not isinstance(imported_mobile, str):
        imported_mobile = mobile_source

    out_sidecar: dict[str, object] = {
        "desktop_path": imported_desktop,
        "mobile_path": imported_mobile,
    }
    return StageArtifact(
        stage=_STAGE,
        blob_path=Path(imported_desktop),
        sidecar=out_sidecar,
    )
