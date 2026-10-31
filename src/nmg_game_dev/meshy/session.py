"""Meshy's operations in the open Blender session (#98 FR5, FR6).

Each operation runs ``scripts/blender/meshy_session.py`` through the shared session client, so the
Meshy text stays out of ``pipeline/``. ``mcp.blender.unreachable`` passes through unchanged. The
caller decides whether that is a warning (import, apply) or a stop (export, collection check).
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final, Protocol

from nmg_game_dev.meshy.errors import MeshyError

REPO_ROOT: Final = Path(__file__).resolve().parents[3]
MESHY_SESSION_SCRIPT: Final = REPO_ROOT / "scripts" / "blender" / "meshy_session.py"
STATES: Final = ("missing", "exists", "no_mesh")


class SessionClient(Protocol):
    """The part of ``BlenderSessionClient`` that Meshy needs."""

    def run_session_op(
        self,
        op: str,
        payload: Mapping[str, Any],
        *,
        script: Path,
    ) -> dict[str, Any]: ...


class MeshySession:
    """Reads and writes the open session for one Meshy collection at a time."""

    def __init__(self, client: SessionClient) -> None:
        self._client = client

    def collection_state(self, name: str) -> str:
        """Return ``missing``, ``exists`` (collection with ``SM_<Name>``), or ``no_mesh``."""
        result = self._run("collection_state", {"name": name})
        state = result.get("state")
        if not isinstance(state, str) or state not in STATES:
            raise MeshyError(
                "meshy.session_failed",
                f"The session reported an unknown collection state {state!r}.",
                "Check that the add-on is the nmg-game-dev build, then retry.",
            )
        return state

    def import_glb(self, name: str, path: Path) -> dict[str, Any]:
        """Import ``path`` as collection ``<name>`` with mesh ``SM_<name>``."""
        return self._run("import_glb", {"name": name, "path": str(path)})

    def export_glb(self, name: str, path: Path) -> dict[str, Any]:
        """Export the meshes of collection ``<name>`` to ``path`` as GLB."""
        return self._run("export_glb", {"name": name, "path": str(path)})

    def apply_maps(self, name: str, maps: Mapping[str, Path]) -> dict[str, Any]:
        """Wire the PBR maps into ``M_<name>_Body`` on ``SM_<name>``."""
        payload = {"name": name, "maps": {kind: str(path) for kind, path in maps.items()}}
        return self._run("apply_maps", payload)

    def _run(self, op: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        result = self._client.run_session_op(op, payload, script=MESHY_SESSION_SCRIPT)
        if result.get("ok") is True:
            return result
        error = result.get("error")
        if isinstance(error, dict):
            raise MeshyError(
                str(error.get("code", "meshy.session_failed")),
                str(error.get("message", f"The session {op} failed.")),
                str(error.get("remediation", "Check the Blender console, then retry.")),
            )
        raise MeshyError(
            "meshy.session_failed",
            f"The session {op} failed without an error description.",
            "Check the Blender console, then retry.",
        )
