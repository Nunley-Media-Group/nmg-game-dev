"""pytest-bdd bindings for reduce_to_budget.feature: the host-side scenarios of #139.

The host runs the reduce job through the in-process fakes in ``tests/finalize_fakes.py``, so no
Blender runs here.  Scenarios that change the Blender scene (SCN001, SCN004, SCN007, SCN008) are
covered by ``tests/blender/test_reduce.py`` and ``tests/blender/test_reduce_finalize.py``.

The steps share one ``state`` dict per scenario.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, scenario, then, when

from nmg_game_dev.finalize import FinalizeService, reduce_asset
from nmg_game_dev.finalize.__main__ import main as finalize_main
from nmg_game_dev.pipeline import FinalizeClients, PipelineError, jobs
from nmg_game_dev.pipeline.reduce import build_request, execute_reduce
from tests.finalize_fakes import FakeBlenderSession, FakeReduceRunner, default_reduce_result

_FEATURE = "reduce_to_budget.feature"


@pytest.fixture()
def state(tmp_path: Path) -> dict[str, Any]:
    return {
        "tmp": tmp_path,
        "asset_class": "standard_prop",
        "runner": FakeReduceRunner(),
        "session": FakeBlenderSession(hash_value="asset-hash-0"),
        "result": None,
        "error": None,
        "job": None,
        "job_error": None,
        "results": {},
    }


def _dead_pid() -> int:
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait()
    return process.pid


def _service(state: dict[str, Any], key: str) -> FinalizeService:
    """A service whose job runs now, against the state's runner and session."""
    cache = state["tmp"] / f"cache-{key}"

    def launch(job_dir: Path) -> int:
        jobs.run_job(
            job_dir,
            clients=FinalizeClients(blender=state["session"]),
            runner=state["runner"],
        )
        return _dead_pid()

    return FinalizeService(cache, launcher=launch)


# SCN009 ---------------------------------------------------------------------------------------


@scenario(_FEATURE, "An asset already in budget is left alone")
def test_within_budget_is_left_alone() -> None:
    """SCN009: within_budget, and nothing is loaded back."""


@given("an asset within its Desktop budget and no <Name>_High")
def _in_budget(state: dict[str, Any]) -> None:
    within = {
        **default_reduce_result(),
        "state": "within_budget",
        "summary": "Crate is within its Desktop budget; nothing changed",
    }
    state["runner"] = FakeReduceRunner(result=within)


@when("the reduce step runs")
def _run_reduce(state: dict[str, Any]) -> None:
    request = build_request(collection="Crate", asset_class=state["asset_class"])
    try:
        state["result"] = execute_reduce(
            request,
            job_dir=state["tmp"] / "job",
            clients=FinalizeClients(blender=state["session"]),
            runner=state["runner"],
        )
    except PipelineError as error:
        state["error"] = error


@then("the result state is within_budget and the scene is unchanged")
def _within_budget_result(state: dict[str, Any]) -> None:
    assert state["error"] is None
    assert state["result"]["state"] == "within_budget"
    assert state["result"]["loaded_back"] is False
    assert state["session"].load_backs == []


# SCN010 ---------------------------------------------------------------------------------------


@scenario(_FEATURE, "A rigged asset or the terrain class is refused")
def test_refused_asset_or_class() -> None:
    """SCN010: terrain is refused by Blender, and nothing is loaded back."""


@given("an asset with an armature, or a request for class terrain")
def _refused_request(state: dict[str, Any]) -> None:
    state["asset_class"] = "terrain"
    state["runner"] = FakeReduceRunner(
        failure=(
            "reduce.class_unsupported",
            "terrain has no Desktop budget to reduce to.",
            "Reduce a prop or character class, or leave terrain alone.",
        )
    )


@then("it fails with reduce.rigged or reduce.class_unsupported and the scene is unchanged")
def _refused_result(state: dict[str, Any]) -> None:
    error = state["error"]
    assert isinstance(error, PipelineError)
    assert error.code in {"reduce.rigged", "reduce.class_unsupported"}
    assert state["session"].load_backs == []


# SCN011 ---------------------------------------------------------------------------------------


@scenario(_FEATURE, "The MCP job loads the result back only into an unchanged session")
def test_job_loads_back_only_into_an_unchanged_session() -> None:
    """SCN011: loaded back when unchanged; reduce.session_changed with the .blend when changed."""


@given("a reduce_asset job started on the open session")
def _job_on_session(state: dict[str, Any]) -> None:
    state["runner"] = FakeReduceRunner()
    state["session"] = FakeBlenderSession(hash_value="asset-hash-0")


@when("the background run finishes and the session's <Name> is unchanged")
def _unchanged_run(state: dict[str, Any]) -> None:
    response = reduce_asset(
        collection="Crate",
        asset_class=state["asset_class"],
        wait_seconds=5,
        service=_service(state, "unchanged"),
    )
    state["job"] = response


@then("<Name> and <Name>_High are loaded back")
def _loaded_back(state: dict[str, Any]) -> None:
    assert state["job"]["status"] == "succeeded"
    assert state["job"]["result"]["loaded_back"] is True
    load = state["session"].load_backs[-1]
    assert load["suffixes"] == ["", "_High"]
    assert load["expected_hash"] == "asset-hash-0"


@then(
    "when the session changed, the job fails with reduce.session_changed and the result .blend path"
)
def _session_changed(state: dict[str, Any]) -> None:
    changed = FakeBlenderSession(
        hash_value="asset-hash-0",
        load_result={"ok": True, "loaded": False, "hash": "moved-on"},
    )
    response = reduce_asset(
        collection="Crate",
        asset_class=state["asset_class"],
        wait_seconds=5,
        service=FinalizeService(
            state["tmp"] / "cache-changed",
            launcher=lambda job_dir: _run_with_session(job_dir, changed, state["runner"]),
        ),
    )
    assert response["status"] == "failed"
    assert response["error"]["code"] == "reduce.session_changed"
    result_blend = response["error"]["message"].rsplit("The result is at ", 1)[-1].rstrip(".")
    assert result_blend.endswith("reduce.blend")


def _run_with_session(job_dir: Path, session: FakeBlenderSession, runner: FakeReduceRunner) -> int:
    jobs.run_job(job_dir, clients=FinalizeClients(blender=session), runner=runner)
    return _dead_pid()


# SCN012 ---------------------------------------------------------------------------------------


@scenario(_FEATURE, "All entry points share one implementation and result shape")
def test_all_entry_points_share_one_result_shape() -> None:
    """SCN012: the CLI, the MCP tool, and the job return the same result fields."""


@given("the panel operator, run_for_mcp, the CLI reduce command, and the reduce_asset tool")
def _entry_points(state: dict[str, Any]) -> None:
    # The panel operator and run_for_mcp run in Blender; tests/blender/test_reduce.py checks them.
    state["runner"] = FakeReduceRunner()


@when("each runs the same request")
def _each_entry_point(state: dict[str, Any]) -> None:
    results: dict[str, dict[str, Any]] = {}

    out = io.StringIO()
    err = io.StringIO()
    code = finalize_main(
        ["reduce", "--collection", "Crate", "--class", "standard_prop"],
        service=_service(state, "cli"),
        stdout=out,
        stderr=err,
    )
    assert code == 0, err.getvalue()
    results["cli"] = json.loads(out.getvalue())["result"]

    response = reduce_asset(
        collection="Crate",
        asset_class="standard_prop",
        wait_seconds=5,
        service=_service(state, "mcp"),
    )
    results["mcp"] = response["result"]

    service = _service(state, "job")
    job_id = service.start_reduce(build_request(collection="Crate", asset_class="standard_prop"))
    results["job"] = service.status(job_id)["result"]
    state["results"] = results


@then("each returns the same result fields")
def _same_fields(state: dict[str, Any]) -> None:
    results: dict[str, dict[str, Any]] = state["results"]
    fields = {name: set(result) for name, result in results.items()}
    assert fields["cli"] == fields["mcp"] == fields["job"]
    assert {"state", "parts", "total_tris", "textures", "summary", "loaded_back"} <= fields["cli"]
