"""MeshySession maps script results to codes and passes unreachable through (#98 FR5)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from nmg_game_dev.meshy.errors import MeshyError
from nmg_game_dev.meshy.session import MESHY_SESSION_SCRIPT, MeshySession
from nmg_game_dev.pipeline.errors import PipelineError
from tests.meshy_fakes import FakeSession


class _Scripted:
    """A session client that answers with one fixed result and records its arguments."""

    def __init__(self, result: dict[str, Any]) -> None:
        self._result = result
        self.calls: list[tuple[str, dict[str, Any], Path]] = []

    def run_session_op(self, op: str, payload: Any, *, script: Path) -> dict[str, Any]:
        self.calls.append((op, dict(payload), script))
        return self._result


def test_every_operation_runs_the_meshy_session_script() -> None:
    client = FakeSession(collections=["Crate"])
    session = MeshySession(client)
    session.collection_state("Crate")
    session.export_glb("Crate", Path("/tmp/x.glb"))
    assert set(client.scripts) == {MESHY_SESSION_SCRIPT}
    assert MESHY_SESSION_SCRIPT.name == "meshy_session.py"


@pytest.mark.parametrize("state", ["missing", "exists", "no_mesh"])
def test_collection_state_returns_the_reported_state(state: str) -> None:
    assert MeshySession(_Scripted({"ok": True, "state": state})).collection_state("Crate") == state


def test_an_unknown_state_is_a_session_failure() -> None:
    with pytest.raises(MeshyError) as info:
        MeshySession(_Scripted({"ok": True, "state": "maybe"})).collection_state("Crate")
    assert info.value.code == "meshy.session_failed"


def test_a_script_error_keeps_its_code_and_remediation() -> None:
    result = {
        "ok": False,
        "error": {
            "code": "meshy.collection_exists",
            "message": "already there",
            "remediation": "rename it",
        },
    }
    with pytest.raises(MeshyError) as info:
        MeshySession(_Scripted(result)).import_glb("Crate", Path("/tmp/x.glb"))
    assert (info.value.code, info.value.message, info.value.remediation) == (
        "meshy.collection_exists",
        "already there",
        "rename it",
    )


def test_a_result_without_an_error_description_is_a_session_failure() -> None:
    with pytest.raises(MeshyError) as info:
        MeshySession(_Scripted({"ok": False})).export_glb("Crate", Path("/tmp/x.glb"))
    assert info.value.code == "meshy.session_failed"


def test_unreachable_blender_passes_through_as_a_pipeline_error() -> None:
    client = FakeSession(down={"apply_maps"})
    with pytest.raises(PipelineError) as info:
        MeshySession(client).apply_maps("Crate", {"base_color": Path("/tmp/b.png")})
    assert info.value.code == "mcp.blender.unreachable"


def test_apply_maps_sends_string_paths() -> None:
    client = _Scripted({"ok": True, "material": "M_Crate_Body", "maps": ["base_color"]})
    MeshySession(client).apply_maps("Crate", {"base_color": Path("/tmp/b.png")})
    (op, payload, _script) = client.calls[0]
    assert op == "apply_maps"
    assert payload == {"name": "Crate", "maps": {"base_color": "/tmp/b.png"}}
