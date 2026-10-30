"""pytest-bdd bindings for finalize.feature: AC1, AC3, AC4, and AC6 of #69.

The steps share one ``state`` dict per scenario.  Each step reads what the earlier steps set.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenario, then, when

from nmg_game_dev.finalize import FinalizeService, run_finalize_step
from nmg_game_dev.pipeline import (
    STEP_ORDER,
    FinalizeClients,
    FinalizeRequest,
    PipelineError,
    finalize,
    jobs,
)
from tests.finalize_fakes import FakeBlenderSession, FakeStepRunner, FakeUnrealRunner


@pytest.fixture()
def state(tmp_path: Path) -> dict[str, Any]:
    return {"tmp": tmp_path, "failing": frozenset(), "request": None}


@scenario("finalize.feature", "Finalize runs the six steps from an authored collection")
def test_six_steps_in_order() -> None:
    """AC1: validate → import_ue in order, with the UE content paths in the result."""


@scenario("finalize.feature", "A single step runs through the same implementation")
def test_single_step_through_the_tool() -> None:
    """AC3: a step tool returns step, cache_hit, outputs, and summary."""


@scenario("finalize.feature", "An unchanged finalized asset is served from cache")
def test_unchanged_asset_is_cached() -> None:
    """AC4: a rerun is all cache hits; a material change reruns from the first affected step."""


@scenario("finalize.feature", "A failing step stops the run before UE import")
def test_failing_step_stops_the_run() -> None:
    """AC6: a failing contract report stops the run and nothing reaches UE."""


def _make_request(state: dict[str, Any], collection: str, asset_class: str, category: str) -> None:
    tmp: Path = state["tmp"]
    blend = tmp / f"{collection.lower()}.blend"
    blend.write_bytes(b"authored")
    state["request"] = FinalizeRequest(
        collection=collection,
        category=category,
        asset_class=asset_class,  # type: ignore[arg-type]
        export_root=tmp / "export",
        blend=blend,
    )


@given(
    parsers.parse(
        'an authored collection "{collection}" of class "{asset_class}" in category "{category}"'
    )
)
def _authored(state: dict[str, Any], collection: str, asset_class: str, category: str) -> None:
    _make_request(state, collection, asset_class, category)


@given('"Crate" fails contract validation')
def _failing(state: dict[str, Any]) -> None:
    _make_request(state, "Crate", "standard_prop", "Props")
    state["failing"] = frozenset({"validate"})


@given('an authoring session holding "Crate"')
def _session(state: dict[str, Any]) -> None:
    _make_request(state, "Crate", "standard_prop", "Props")


@given('"Crate" was finalized and loaded back')
def _finalized(state: dict[str, Any]) -> None:
    _make_request(state, "Crate", "standard_prop", "Props")
    state["cache"] = state["tmp"] / "cache"
    finalize_once(state, "first", FakeStepRunner(state["request"]))


def finalize_once(state: dict[str, Any], job: str, runner: FakeStepRunner) -> Any:
    """Run finalize for the state's request with ``runner``, storing the unreal fake."""
    unreal = FakeUnrealRunner()
    state["unreal"] = unreal
    return finalize(
        state["request"],
        cache_dir=state.get("cache", state["tmp"] / "cache"),
        runner=runner,
        job_dir=state["tmp"] / job,
        clients=FinalizeClients(unreal=unreal),
    )


@when("finalize runs")
def _run(state: dict[str, Any]) -> None:
    events: list[str] = []
    runner = FakeStepRunner(state["request"], failing_reports=state["failing"], events=events)
    unreal = FakeUnrealRunner(events=events)
    state["runner"] = runner
    state["unreal"] = unreal
    state["events"] = events
    try:
        state["result"] = finalize(
            state["request"],
            cache_dir=state["tmp"] / "cache",
            runner=runner,
            job_dir=state["tmp"] / "job",
            clients=FinalizeClients(unreal=unreal),
        )
    except PipelineError as error:
        state["error"] = error


@when("finalize runs again without changes")
def _rerun(state: dict[str, Any]) -> None:
    runner = FakeStepRunner(state["request"])
    state["runner"] = runner
    state["result"] = finalize_once(state, "second", runner)


@when('the agent calls run_finalize_step with step "validate" and wait_seconds 60')
def _single_step(state: dict[str, Any]) -> None:
    request: FinalizeRequest = state["request"]
    cache = state["tmp"] / "cache"

    def launch(job_dir: Path) -> int:
        run_request = FinalizeRequest.model_validate_json(
            (job_dir / "request.json").read_text(encoding="utf-8")
        )
        jobs.run_job(
            job_dir,
            clients=FinalizeClients(blender=FakeBlenderSession(), unreal=FakeUnrealRunner()),
            runner=FakeStepRunner(run_request),
        )
        return _finished_process_id()

    state["response"] = run_finalize_step(
        step="validate",
        collection=request.collection,
        category=request.category,
        asset_class=request.asset_class,
        export_root=str(request.export_root),
        blend=str(request.blend),
        wait_seconds=60,
        service=FinalizeService(cache, launcher=launch),
    )


@then("the steps validate, bake, variants, export, reimport, and import_ue run in that order")
def _order(state: dict[str, Any]) -> None:
    assert state["events"] == [*STEP_ORDER[:-1], "import_ue", "import_ue"]


@then("the result lists each step and the UE content paths under /Game/Props/Crate/")
def _content(state: dict[str, Any]) -> None:
    result = state["result"]
    assert [step.step for step in result.steps] == list(STEP_ORDER)
    assert result.desktop_content_path == "/Game/Props/Crate/Desktop"
    assert result.mobile_content_path == "/Game/Props/Crate/Mobile"


@then('it receives a result with step "validate", cache_hit, outputs, and summary')
def _single_result(state: dict[str, Any]) -> None:
    response = state["response"]
    assert response["status"] == "succeeded"
    step = response["result"]["steps"][0]
    assert step["step"] == "validate"
    assert "cache_hit" in step
    assert "outputs" in step
    assert "summary" in step


@then("every step reports cache_hit true and nothing is reimported into UE")
def _all_hits(state: dict[str, Any]) -> None:
    assert all(step.cache_hit for step in state["result"].steps)
    assert state["unreal"].codes == []


@then("after a material change the bake step and every later step run again")
def _rerun_after_change(state: dict[str, Any]) -> None:
    runner = FakeStepRunner(state["request"], hash_value="asset-hash-changed")
    finalize_once(state, "changed", runner)
    assert runner.steps_run() == ["validate", "bake", "variants", "export", "reimport"]


@then(parsers.parse('it raises PipelineError "{code}" with a remediation'))
def _raises(state: dict[str, Any], code: str) -> None:
    error = state.get("error")
    assert isinstance(error, PipelineError)
    assert error.code == code
    assert error.remediation


@then("no later step runs and nothing is imported into UE")
def _stopped(state: dict[str, Any]) -> None:
    assert state["runner"].steps_run() == ["validate"]
    assert state["unreal"].codes == []


def _finished_process_id() -> int:
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait()
    return process.pid
