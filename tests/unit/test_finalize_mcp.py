"""Unit tests for the three ``finalize`` MCP tools (AC3, #69).

The tool functions are tested directly, so the MCP SDK is not needed.  The server module only
registers them.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from nmg_game_dev.finalize import (
    FinalizeService,
    finalize_asset,
    get_finalize_job,
    run_finalize_step,
)
from nmg_game_dev.finalize.service import clamp_wait
from nmg_game_dev.pipeline import FinalizeClients, FinalizeRequest, jobs
from tests.finalize_fakes import FakeBlenderSession, FakeStepRunner, FakeUnrealRunner


def _dead_pid() -> int:
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait()
    return process.pid


def _deferred(cache_root: Path) -> FinalizeService:
    """A service whose launcher records the job without running it, so it stays queued."""
    return FinalizeService(cache_root, launcher=lambda job_dir: _live_pid())


def _live_pid() -> int:
    import os

    return os.getpid()


def _args(tmp_path: Path) -> dict[str, object]:
    blend = tmp_path / "crate.blend"
    blend.write_bytes(b"authored")
    return {
        "collection": "Crate",
        "category": "Props",
        "asset_class": "standard_prop",
        "export_root": str(tmp_path / "export"),
        "blend": str(blend),
    }


def test_wait_seconds_is_clamped_to_zero_through_one_fifty() -> None:
    assert clamp_wait(999) == 150
    assert clamp_wait(-5) == 0
    assert clamp_wait(30) == 30


def test_finalize_asset_returns_a_job_id_immediately_when_not_waiting(tmp_path: Path) -> None:
    response = finalize_asset(**_args(tmp_path), service=_deferred(tmp_path / "cache"))  # type: ignore[arg-type]

    assert response["job_id"]
    assert response["status"] == "queued"
    assert "result" not in response


def test_get_finalize_job_reports_the_status_and_then_the_result(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    service = _deferred(cache)
    response = finalize_asset(**_args(tmp_path), service=service)  # type: ignore[arg-type]
    job_id = str(response["job_id"])

    assert get_finalize_job(job_id, service=service)["state"] == "queued"

    request = FinalizeRequest.model_validate_json(
        (cache / "jobs" / job_id / "request.json").read_text(encoding="utf-8")
    )
    jobs.run_job(
        cache / "jobs" / job_id,
        clients=FinalizeClients(blender=FakeBlenderSession(), unreal=FakeUnrealRunner()),
        runner=FakeStepRunner(request),
    )

    finished = get_finalize_job(job_id, service=service)
    assert finished["state"] == "succeeded"
    assert finished["result"]["desktop_content_path"] == "/Game/Props/Crate/Desktop"


def test_run_finalize_step_names_the_step_it_ran(tmp_path: Path) -> None:
    response = run_finalize_step(
        step="validate",
        **_args(tmp_path),  # type: ignore[arg-type]
        service=_deferred(tmp_path / "cache"),
    )
    assert response["status"] == "queued"


def test_unknown_step_is_a_structured_error(tmp_path: Path) -> None:
    response = run_finalize_step(
        step="generate",
        **_args(tmp_path),  # type: ignore[arg-type]
        service=_deferred(tmp_path / "cache"),
    )
    assert response["error"]["code"] == "finalize.unknown_step"
    assert response["error"]["stage"] == "finalize"


def test_unknown_job_is_finalize_job_not_found(tmp_path: Path) -> None:
    response = get_finalize_job("no-such-job", service=_deferred(tmp_path / "cache"))
    assert response["error"]["code"] == "finalize.job_not_found"


def test_invalid_arguments_are_a_structured_error(tmp_path: Path) -> None:
    args = _args(tmp_path)
    args["asset_class"] = "generated"
    response = finalize_asset(**args, service=_deferred(tmp_path / "cache"))  # type: ignore[arg-type]
    assert response["error"]["code"] == "finalize.invalid_request"


def test_a_failed_job_reports_its_error_when_waited_on(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    service = FinalizeService(cache, launcher=lambda job_dir: _dead_pid())
    response = finalize_asset(
        **_args(tmp_path),  # type: ignore[arg-type]
        service=service,
        wait_seconds=5,
    )
    assert response["status"] == "failed"
    assert response["error"]["code"] == "finalize.job_crashed"
