"""The reduce MCP tool and CLI return the same result shape, and refuse bad input (#139, AC14).

Both call ``FinalizeService`` with an in-process launcher, so no Blender runs.  The CLI and the
tool tests share the fake reduce runner from ``tests/finalize_fakes.py``.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from nmg_game_dev.finalize import FinalizeService, reduce_asset
from nmg_game_dev.finalize.__main__ import build_parser, main
from nmg_game_dev.pipeline import FinalizeClients, jobs
from tests.finalize_fakes import FakeBlenderSession, FakeReduceRunner


def _dead_pid() -> int:
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait()
    return process.pid


def _run_now(job_dir: Path, runner: FakeReduceRunner) -> int:
    jobs.run_job(
        job_dir,
        clients=FinalizeClients(blender=FakeBlenderSession()),
        runner=runner,
    )
    return _dead_pid()


def _service(tmp_path: Path, runner: FakeReduceRunner | None = None) -> FinalizeService:
    fake = runner if runner is not None else FakeReduceRunner()
    return FinalizeService(tmp_path / "cache", launcher=lambda job_dir: _run_now(job_dir, fake))


def _deferred(tmp_path: Path) -> FinalizeService:
    """A service whose job never runs, so it stays queued and can be polled."""
    return FinalizeService(tmp_path / "cache", launcher=lambda _job_dir: os.getpid())


def test_the_tool_returns_a_job_id_and_the_result_when_it_finishes(tmp_path: Path) -> None:
    response = reduce_asset(
        collection="Crate",
        asset_class="standard_prop",
        wait_seconds=5,
        service=_service(tmp_path),
    )

    assert response["status"] == "succeeded"
    assert response["job_id"]
    assert response["result"]["kind"] == "reduce"
    assert response["result"]["state"] == "reduced"
    assert response["result"]["loaded_back"] is True


def test_the_tool_returns_at_once_for_a_job_that_is_still_running(tmp_path: Path) -> None:
    response = reduce_asset(
        collection="Crate",
        asset_class="standard_prop",
        service=_deferred(tmp_path),
    )

    assert response["status"] in {"queued", "running"}
    assert "result" not in response
    assert "error" not in response


def test_the_tool_reports_a_refused_class_from_blender(tmp_path: Path) -> None:
    runner = FakeReduceRunner(
        failure=(
            "reduce.class_unsupported",
            "terrain has no Desktop budget to reduce to.",
            "Reduce a prop or character class, or leave terrain alone.",
        )
    )
    response = reduce_asset(
        collection="Crate",
        asset_class="terrain",
        wait_seconds=5,
        service=_service(tmp_path, runner),
    )

    assert response["status"] == "failed"
    assert response["error"]["code"] == "reduce.class_unsupported"


def test_the_tool_refuses_a_bad_override_before_any_job_starts(tmp_path: Path) -> None:
    response = reduce_asset(
        collection="Crate",
        asset_class="standard_prop",
        parts={"Wall": {"share": 0.4, "tris": 900}},
        service=_deferred(tmp_path),
    )

    assert response["error"]["code"] == "reduce.invalid_override"
    assert not (tmp_path / "cache" / "jobs").exists()


def test_the_tool_refuses_a_bad_collection_name(tmp_path: Path) -> None:
    response = reduce_asset(
        collection="crate",
        asset_class="standard_prop",
        service=_deferred(tmp_path),
    )

    assert response["error"]["code"] == "reduce.invalid_request"


def _run_cli(argv: list[str], service: FinalizeService) -> tuple[int, dict[str, Any], str]:
    out = io.StringIO()
    err = io.StringIO()
    code = main(argv, service=service, stdout=out, stderr=err)
    text = out.getvalue()
    status: dict[str, Any] = json.loads(text) if text.strip() else {}
    return code, status, err.getvalue()


def test_the_cli_prints_the_job_status_and_the_same_result_shape(tmp_path: Path) -> None:
    code, status, err = _run_cli(
        ["reduce", "--collection", "Crate", "--class", "standard_prop"],
        _service(tmp_path),
    )

    assert code == 0
    assert err == ""
    assert status["state"] == "succeeded"
    assert status["result"]["kind"] == "reduce"
    assert status["result"]["state"] == "reduced"
    assert "job_id" in status


def test_the_cli_reports_a_failed_reduce_with_its_code(tmp_path: Path) -> None:
    runner = FakeReduceRunner(
        failure=(
            "reduce.bake_misses",
            "Part Body has 4.2% unbaked texels, above the 1% threshold.",
            "Raise max_ray_distance, then rerun.",
        )
    )
    code, status, err = _run_cli(
        ["reduce", "--collection", "Crate", "--class", "standard_prop"],
        _service(tmp_path, runner),
    )

    assert code == 1
    assert status["state"] == "failed"
    assert "ERROR [reduce.bake_misses]" in err


def test_the_cli_refuses_malformed_parts_json(tmp_path: Path) -> None:
    code, status, err = _run_cli(
        ["reduce", "--collection", "Crate", "--class", "standard_prop", "--parts", "{nope"],
        _service(tmp_path),
    )

    assert code == 1
    assert status == {}  # refused before a job starts, so nothing is printed on stdout
    assert "ERROR [reduce.invalid_request]" in err


def test_the_cli_passes_parts_and_distances_through_to_the_request(tmp_path: Path) -> None:
    runner = FakeReduceRunner()
    code, status, _err = _run_cli(
        [
            "reduce",
            "--collection",
            "Crate",
            "--class",
            "standard_prop",
            "--cage",
            "0.05",
            "--ray",
            "0.2",
            "--miss-threshold",
            "0.02",
            "--parts",
            '{"Body": {"tris": 1500}}',
        ],
        _service(tmp_path, runner),
    )

    assert code == 0
    request = json.loads(
        (tmp_path / "cache" / "jobs" / status["job_id"] / "request.json").read_text("utf-8")
    )
    assert request["cage_extrusion"] == 0.05
    assert request["max_ray_distance"] == 0.2
    assert request["miss_threshold"] == 0.02
    assert request["parts"] == {
        "Body": {"share": None, "tris": 1500, "cage_extrusion": None, "max_ray_distance": None}
    }


def test_the_cli_knows_the_reduce_command() -> None:
    parser = build_parser()
    args = parser.parse_args(["reduce", "--collection", "Crate", "--class", "hero_prop"])
    assert args.command == "reduce"
    assert args.asset_class == "hero_prop"
