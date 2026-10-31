"""The session client takes an alternative session script; the default is unchanged (#98 FR5)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from nmg_game_dev.pipeline.clients import blender_session as session_module
from nmg_game_dev.pipeline.clients.blender_session import (
    SESSION_SCRIPT,
    BlenderSessionClient,
    session_code,
)


def _embedded_payload(code: str) -> dict[str, Any]:
    line = next(line for line in code.splitlines() if line.startswith("NMG_PAYLOAD = "))
    literal = line.split("_json.loads(", 1)[1].rsplit(")", 1)[0]
    parsed: dict[str, Any] = json.loads(json.loads(literal))
    return parsed


def test_default_script_is_finalize_session() -> None:
    code = session_code("checkpoint", {"collection": "Crate"})
    assert str(SESSION_SCRIPT) in code
    assert SESSION_SCRIPT.name == "finalize_session.py"
    assert 'NMG_OP = "checkpoint"' in code


def test_an_alternative_script_replaces_only_the_exec_target(tmp_path: Path) -> None:
    script = tmp_path / "other_session.py"
    code = session_code("import_glb", {"name": "Crate"}, script=script)
    assert str(script) in code
    assert str(SESSION_SCRIPT) not in code
    assert _embedded_payload(code)["name"] == "Crate"
    assert "addon_dir" in _embedded_payload(code)


def test_run_session_op_forwards_the_script_to_the_code_it_executes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sent: list[str] = []
    client = BlenderSessionClient(port=1)

    def record(code: str) -> dict[str, Any]:
        sent.append(code)
        return {"ok": True}

    monkeypatch.setattr(client, "execute", record)
    script = tmp_path / "meshy_session.py"
    client.run_session_op("collection_state", {"name": "Crate"}, script=script)
    assert str(script) in sent[0]
    client.run_session_op("checkpoint", {"collection": "Crate", "path": "x"})
    assert str(SESSION_SCRIPT) in sent[1]


def test_the_default_session_script_is_still_the_finalize_script() -> None:
    assert session_module.SESSION_SCRIPT == SESSION_SCRIPT
