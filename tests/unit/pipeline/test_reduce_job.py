"""Host tests for the reduce job (#139, AC14): kind and status, load-back, and the refusals.

No live Blender is involved.  The reduce step is a fake in-process runner, and the session is a
fake that records its load-back calls.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from nmg_game_dev.pipeline import (
    FinalizeClients,
    PipelineError,
    ReduceRequest,
    ReduceSessionChangedError,
    jobs,
)
from nmg_game_dev.pipeline.reduce import (
    LOAD_BACK_SUFFIXES,
    build_request,
    execute_reduce,
    parts_from_json,
)
from tests.finalize_fakes import FakeBlenderSession, FakeReduceRunner, default_reduce_result


def _request(**overrides: Any) -> ReduceRequest:
    values: dict[str, Any] = {"collection": "Crate", "asset_class": "standard_prop"}
    values.update(overrides)
    return build_request(**values)


def _dead_pid() -> int:
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait()
    return process.pid


def _run_now(
    job_dir: Path,
    *,
    session: FakeBlenderSession | None,
    runner: FakeReduceRunner,
) -> int:
    jobs.run_job(
        job_dir,
        clients=FinalizeClients(blender=session),
        runner=runner,
    )
    return _dead_pid()


def test_a_reduce_job_is_kind_reduce_and_succeeds_with_the_result(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    session = FakeBlenderSession(hash_value="asset-hash-0")
    runner = FakeReduceRunner()
    job_id = jobs.start_reduce(
        _request(),
        cache_root=cache,
        launcher=lambda job_dir: _run_now(job_dir, session=session, runner=runner),
    )

    status = jobs.status(job_id, cache_root=cache)
    assert status["state"] == "succeeded"
    assert status["result"]["kind"] == "reduce"
    assert status["result"]["state"] == "reduced"
    assert status["result"]["loaded_back"] is True
    assert status["result"]["total_tris"] == 2990
    job = (cache / "jobs" / job_id / "job.json").read_text(encoding="utf-8")
    assert '"kind": "reduce"' in job
    assert not (cache / "jobs" / "lock").exists()


def test_the_session_load_back_replaces_name_and_high(tmp_path: Path) -> None:
    session = FakeBlenderSession(hash_value="asset-hash-0")
    runner = FakeReduceRunner()
    result = execute_reduce(
        _request(),
        job_dir=tmp_path / "job",
        clients=FinalizeClients(blender=session),
        runner=runner,
    )

    assert result["loaded_back"] is True
    assert len(session.load_backs) == 1
    load = session.load_backs[0]
    assert load["suffixes"] == list(LOAD_BACK_SUFFIXES) == ["", "_High"]
    assert load["expected_hash"] == "asset-hash-0"
    assert load["collection"] == "Crate"


def test_a_within_budget_result_loads_nothing(tmp_path: Path) -> None:
    within = {**default_reduce_result(), "state": "within_budget", "summary": "in budget"}
    session = FakeBlenderSession(hash_value="asset-hash-0")
    result = execute_reduce(
        _request(),
        job_dir=tmp_path / "job",
        clients=FinalizeClients(blender=session),
        runner=FakeReduceRunner(result=within),
    )

    assert result["state"] == "within_budget"
    assert result["loaded_back"] is False
    assert session.load_backs == []


def test_a_hash_mismatch_fails_with_reduce_session_changed_and_the_blend(tmp_path: Path) -> None:
    session = FakeBlenderSession(
        hash_value="asset-hash-0",
        load_result={"ok": True, "loaded": False, "hash": "moved-on"},
    )
    with pytest.raises(ReduceSessionChangedError) as raised:
        execute_reduce(
            _request(),
            job_dir=tmp_path / "job",
            clients=FinalizeClients(blender=session),
            runner=FakeReduceRunner(),
        )

    error = raised.value
    assert error.code == "reduce.session_changed"
    assert error.stage == "reduce"
    assert error.result["loaded_back"] is False
    assert error.result["result_blend"] in error.message
    assert error.result["result_blend"].endswith("reduce.blend")


def test_a_session_changed_job_is_failed_and_keeps_the_result(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    session = FakeBlenderSession(
        hash_value="asset-hash-0",
        load_result={"ok": True, "loaded": False, "hash": "moved-on"},
    )
    runner = FakeReduceRunner()
    job_id = jobs.start_reduce(
        _request(),
        cache_root=cache,
        launcher=lambda job_dir: _run_now(job_dir, session=session, runner=runner),
    )

    status = jobs.status(job_id, cache_root=cache)
    assert status["state"] == "failed"
    assert status["error"]["code"] == "reduce.session_changed"
    assert status["result"]["state"] == "reduced"
    assert status["result"]["loaded_back"] is False


def test_a_refused_blender_step_surfaces_its_own_code(tmp_path: Path) -> None:
    runner = FakeReduceRunner(
        failure=(
            "reduce.bake_misses",
            "Part Body has 4.2% unbaked texels, above the 1% threshold.",
            "Raise max_ray_distance or cage_extrusion, then rerun.",
        )
    )
    with pytest.raises(PipelineError) as raised:
        execute_reduce(
            _request(),
            job_dir=tmp_path / "job",
            clients=FinalizeClients(blender=FakeBlenderSession()),
            runner=runner,
        )

    assert raised.value.code == "reduce.bake_misses"
    assert raised.value.stage == "reduce"
    assert "4.2%" in raised.value.message


def test_a_saved_blend_is_reduced_without_a_session_or_load_back(tmp_path: Path) -> None:
    blend = tmp_path / "crate.blend"
    blend.write_bytes(b"authored")
    session = FakeBlenderSession()
    runner = FakeReduceRunner()
    result = execute_reduce(
        _request(blend=blend),
        job_dir=tmp_path / "job",
        clients=FinalizeClients(blender=session),
        runner=runner,
    )

    assert session.checkpoints == []
    assert session.load_backs == []
    assert result["loaded_back"] is False
    assert result["state"] == "reduced"


def test_the_runner_gets_the_checkpoint_and_the_request_file(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    runner = FakeReduceRunner()
    execute_reduce(
        _request(cage_extrusion=0.05),
        job_dir=job_dir,
        clients=FinalizeClients(blender=FakeBlenderSession()),
        runner=runner,
    )

    reduce_calls = [call for call in runner.calls if call["step"] == "reduce"]
    assert len(reduce_calls) == 1
    assert reduce_calls[0]["in_blend"] == str(job_dir / "checkpoint.blend")
    request_text = (job_dir / "request.json").read_text(encoding="utf-8")
    assert '"cage_extrusion": 0.05' in request_text
    assert '"collection": "Crate"' in request_text


def test_an_invalid_per_part_override_is_reduce_invalid_override() -> None:
    with pytest.raises(PipelineError) as raised:
        _request(parts={"Wall": {"share": 0.4, "tris": 900}})
    assert raised.value.code == "reduce.invalid_override"


def test_an_out_of_range_share_is_reduce_invalid_override() -> None:
    with pytest.raises(PipelineError) as raised:
        _request(parts={"Wall": {"share": 1.5}})
    assert raised.value.code == "reduce.invalid_override"


def test_a_non_pascal_collection_is_reduce_invalid_request() -> None:
    with pytest.raises(PipelineError) as raised:
        _request(collection="crate")
    assert raised.value.code == "reduce.invalid_request"


def test_a_nonpositive_cage_distance_is_refused() -> None:
    with pytest.raises(PipelineError) as raised:
        _request(cage_extrusion=0)
    assert raised.value.code == "reduce.invalid_request"


def test_terrain_is_accepted_by_the_host_and_refused_by_blender() -> None:
    # The host passes the class through so Blender refuses it with reduce.class_unsupported.
    request = _request(asset_class="terrain")
    assert request.asset_class == "terrain"


def test_parts_from_json_reads_an_object_and_refuses_the_rest() -> None:
    assert parts_from_json('{"Wall": {"share": 0.4}}') == {"Wall": {"share": 0.4}}
    assert parts_from_json(None) == {}
    with pytest.raises(PipelineError) as bad_json:
        parts_from_json("{not json")
    assert bad_json.value.code == "reduce.invalid_request"
    with pytest.raises(PipelineError) as not_object:
        parts_from_json("[1, 2]")
    assert not_object.value.code == "reduce.invalid_request"


def test_a_reduce_request_is_frozen() -> None:
    request = _request()
    with pytest.raises(ValidationError):
        request.collection = "Other"
