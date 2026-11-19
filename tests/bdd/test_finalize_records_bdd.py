"""pytest-bdd bindings for finalize_records.feature: SCN001-SCN013 of #247.

The steps share one ``records_state`` dict per scenario, and each step reads what the earlier steps
set.  ``CLAUDE_PROJECT_DIR`` points at the scenario's temporary consumer project, so the CLI and the
MCP tool default their export root to ``<consumer>/game/assets``.  Everything runs in-process with
the finalize fakes, so no Blender or Godot process starts.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable, Mapping
from io import StringIO
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenario, then, when

from nmg_game_dev.finalize import FinalizeService, check_finalized
from nmg_game_dev.finalize.__main__ import main
from nmg_game_dev.onboard.gitignore import ensure_gitignore_env
from nmg_game_dev.pipeline import FinalizeRequest
from nmg_game_dev.pipeline.records import check
from nmg_game_dev.pipeline.steps import STEP_ORDER
from tests.finalize_fakes import BatchRouter, Failure, batch_launcher
from tests.finalize_records_support import (
    PAST,
    RECORD_FIELDS,
    asset_request,
    hold_cache_lock,
    logs_of,
    manual_record,
    record_of,
    run_finalize,
    snapshot,
    up_to_date_asset,
    write_imports,
    write_record_file,
)

DOCS = Path(__file__).resolve().parents[2] / "docs" / "mcp" / "finalize.md"
SKILL = Path(__file__).resolve().parents[2] / "skills" / "finalize-asset" / "SKILL.md"


@pytest.fixture()
def records_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    return {"tmp": tmp_path, "cache": tmp_path / "cache"}


def _record(request: FinalizeRequest) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(record_of(request).read_text(encoding="utf-8"))
    return loaded


def _batch_service(
    cache: Path,
    requests: dict[str, FinalizeRequest],
    *,
    failures: Mapping[str, Mapping[str, Failure]] | None = None,
    on_step: Callable[[Path, str], None] | None = None,
) -> FinalizeService:
    project = next(iter(requests.values())).export_root.parent

    def make_router(_: dict[str, FinalizeRequest]) -> BatchRouter:
        return BatchRouter(requests, failures=failures, on_step=on_step)

    return FinalizeService(cache, launcher=batch_launcher(make_router, project=project))


# SCN001 - SCN004: records written by a finished run.


@scenario("finalize_records.feature", "A finished run writes a per-asset record")
def test_scn001_a_finished_run_writes_a_record() -> None:
    """SCN001: the record holds every field the spec names."""


@given(
    "a consumer project with game/project.godot and a finalize request for Props/Crate from "
    "Crate.blend"
)
def _consumer_and_request(records_state: dict[str, Any]) -> None:
    records_state["request"] = asset_request(records_state["tmp"], "Crate")


@when("the finalize job succeeds")
def _job_succeeds(records_state: dict[str, Any]) -> None:
    request = records_state.get("request") or asset_request(records_state["tmp"], "Crate")
    records_state["request"] = request
    records_state["status"] = run_finalize(records_state["cache"], request)


@then(
    '".nmg/finalize/Props/Crate.json" holds the state, times, version, full_run, steps with cache '
    "hits, source, imported res:// paths, content hash, logs, and a null error"
)
def _record_holds_every_field(records_state: dict[str, Any]) -> None:
    request = records_state["request"]
    status = records_state["status"]
    record = _record(request)
    assert set(record) == RECORD_FIELDS
    assert record["state"] == "succeeded" and record["ended_at"] >= record["started_at"]
    assert record["nmg_game_dev_version"]
    assert record["full_run"] is True
    assert [s["step"] for s in record["steps"]] == list(STEP_ORDER)
    assert all("cache_hit" in s for s in record["steps"])
    assert record["source"]["blend"] == str(request.blend)
    assert record["imported"] == [
        status["result"]["desktop_resource_path"],
        status["result"]["mobile_resource_path"],
    ]
    assert record["content_hash"] == "asset-hash-0"
    assert record["logs"]["job"] == "Crate.logs/job.log"
    assert record["error"] is None


@scenario("finalize_records.feature", "The run's logs are kept beside the record")
def test_scn002_the_logs_are_kept_beside_the_record() -> None:
    """SCN002: the log copies survive deletion of the job directory."""


@given("the same finished run")
def _the_same_finished_run(records_state: dict[str, Any]) -> None:
    request = asset_request(records_state["tmp"], "Crate")
    records_state["request"] = request
    records_state["status"] = run_finalize(records_state["cache"], request)


@when("the job directory under the cache root is deleted")
def _job_directory_deleted(records_state: dict[str, Any]) -> None:
    shutil.rmtree(records_state["cache"] / "jobs" / records_state["status"]["job_id"])


@then(
    '".nmg/finalize/Props/Crate.logs/" still holds job.log and each blender step log named in the '
    "record"
)
def _logs_still_hold_every_named_file(records_state: dict[str, Any]) -> None:
    request = records_state["request"]
    record = _record(request)
    assert (logs_of(request) / "job.log").is_file()
    assert "validate" in record["logs"]["steps"]
    for relative in record["logs"]["steps"].values():
        assert (record_of(request).parent / relative).is_file(), relative


@scenario("finalize_records.feature", "Each batch item gets its own record")
def test_scn003_each_batch_item_gets_its_own_record() -> None:
    """SCN003: a fail-fast batch writes each item's record before the next item starts."""


@given(
    "a fail-fast batch of Crate, Barrel, and Lamp where Barrel fails and Lamp has an earlier record"
)
def _fail_fast_batch_with_an_earlier_lamp(records_state: dict[str, Any]) -> None:
    tmp = records_state["tmp"]
    requests = {name: asset_request(tmp, name) for name in ("Crate", "Barrel", "Lamp")}
    earlier = manual_record(requests["Lamp"], job_id="earlier-lamp")
    records_state["lamp_path"] = write_record_file(requests["Lamp"], earlier)
    records_state["lamp_before"] = records_state["lamp_path"].read_bytes()
    records_state["requests"] = requests
    records_state["failures"] = {
        "Barrel": {"validate": ("quality.contract_failed", "bad", "fix it")}
    }
    records_state["fail_fast"] = True
    records_state["observed"] = []
    crate_record = record_of(requests["Crate"])

    def on_step(item_dir: Path, step: str) -> None:
        if "Barrel" in item_dir.name and step == "validate":
            records_state["observed"].append(crate_record.is_file())

    records_state["on_step"] = on_step


@when("the batch runs")
def _the_batch_runs(records_state: dict[str, Any]) -> None:
    requests = records_state["requests"]
    service = _batch_service(
        records_state["cache"],
        requests,
        failures=records_state.get("failures"),
        on_step=records_state["on_step"],
    )
    records_state["batch"] = service.run_batch(
        list(requests.values()),
        fail_fast=records_state.get("fail_fast", False),
        skip_up_to_date=records_state.get("skip", False),
    )


@then("Crate's record is written before Barrel starts")
def _crate_record_before_barrel(records_state: dict[str, Any]) -> None:
    assert records_state["observed"] == [True]


@then('Barrel\'s record has state "failed"')
def _barrel_record_failed(records_state: dict[str, Any]) -> None:
    barrel = _record(records_state["requests"]["Barrel"])
    assert barrel["state"] == "failed"


@then("Lamp's earlier record is unchanged")
def _lamp_record_unchanged(records_state: dict[str, Any]) -> None:
    assert records_state["lamp_path"].read_bytes() == records_state["lamp_before"]


@scenario("finalize_records.feature", "A new run replaces the last record")
def test_scn004_a_new_run_replaces_the_last_record() -> None:
    """SCN004: the record and the logs describe only the latest run."""


@given("Props/Crate has a record and logs from an earlier run")
def _earlier_run(records_state: dict[str, Any]) -> None:
    request = asset_request(records_state["tmp"], "Crate")
    records_state["request"] = request
    records_state["first"] = run_finalize(records_state["cache"], request)
    (logs_of(request) / "left-from-the-earlier-run.log").write_text("old", encoding="utf-8")


@when("Props/Crate is finalized again")
def _finalized_again(records_state: dict[str, Any]) -> None:
    records_state["second"] = run_finalize(records_state["cache"], records_state["request"])


@then("the record names the new job id and the logs directory holds only the new run's logs")
def _record_names_the_new_run(records_state: dict[str, Any]) -> None:
    request = records_state["request"]
    second = records_state["second"]
    assert _record(request)["job_id"] == second["job_id"] != records_state["first"]["job_id"]
    assert not (logs_of(request) / "left-from-the-earlier-run.log").exists()
    assert (logs_of(request) / "job.log").read_text(encoding="utf-8") == (
        f"job {second['job_id']}\n"
    )


# SCN005 - SCN006: the CLI and the MCP tool answer the check.


@scenario("finalize_records.feature", "The CLI answers whether an asset is up to date")
def test_scn005_the_cli_answers_whether_an_asset_is_up_to_date() -> None:
    """SCN005: the check subcommand prints the JSON result and exits 0."""


@given("Props/Crate has an up-to-date record")
def _up_to_date_crate(records_state: dict[str, Any]) -> None:
    records_state["request"] = up_to_date_asset(records_state["tmp"], "Crate")


@when(parsers.parse('"{command}" runs'))
def _command_runs(records_state: dict[str, Any], command: str) -> None:
    tokens = command.split()
    argv = tokens[tokens.index("check") :]
    out, err = StringIO(), StringIO()
    records_state["exit"] = main(argv, stdout=out, stderr=err)
    records_state["out"] = out.getvalue()


@then('it prints up_to_date true with reason "up_to_date" and exits 0')
def _cli_prints_up_to_date(records_state: dict[str, Any]) -> None:
    payload = json.loads(records_state["out"])
    assert payload["up_to_date"] is True
    assert payload["reason"] == "up_to_date"
    assert records_state["exit"] == 0


@scenario("finalize_records.feature", "The MCP tool answers for a list of assets")
def test_scn006_the_mcp_tool_answers_for_a_list_of_assets() -> None:
    """SCN006: check_finalized reports each asset, with no record summary for a missing one."""


@given("Props/Crate is up to date and Props/Barrel has no record")
def _crate_up_to_date_and_barrel_missing(records_state: dict[str, Any]) -> None:
    up_to_date_asset(records_state["tmp"], "Crate")
    asset_request(records_state["tmp"], "Barrel")


@when("check_finalized is called with both assets")
def _check_finalized_both(records_state: dict[str, Any]) -> None:
    records_state["rows"] = {
        row["collection"]: row
        for row in check_finalized(
            assets=[
                {"category": "Props", "collection": "Crate"},
                {"category": "Props", "collection": "Barrel"},
            ]
        )["assets"]
    }


@then(
    'Crate reports up_to_date true and Barrel reports reason "no_record" with a null record summary'
)
def _crate_true_barrel_no_record(records_state: dict[str, Any]) -> None:
    rows = records_state["rows"]
    assert rows["Crate"]["up_to_date"] is True
    assert rows["Barrel"]["reason"] == "no_record"
    assert rows["Barrel"]["record"] is None


# SCN007 - SCN009: the check's rule, its reasons, and its side effects.


@scenario("finalize_records.feature", "A clean full run newer than the source is up to date")
def test_scn007_a_clean_full_run_is_up_to_date() -> None:
    """SCN007: a succeeded full run whose source is older and whose imports exist is up to date."""


@given(
    "a succeeded full-run record whose .blend is older than its start and whose imported files and "
    ".import files exist"
)
def _clean_record(records_state: dict[str, Any]) -> None:
    request = asset_request(records_state["tmp"], "Crate")
    records_state["request"] = request
    write_imports(request)
    write_record_file(request, manual_record(request))


def _run_the_check(records_state: dict[str, Any]) -> None:
    request = records_state["request"]
    root = records_state.get("export_root", request.export_root)
    records_state["result"] = check(request.category, request.collection, root)


@when("the check runs")
def _the_check_runs(records_state: dict[str, Any]) -> None:
    _run_the_check(records_state)


@when("the check runs for Props/Crate")
def _the_check_runs_for_props_crate(records_state: dict[str, Any]) -> None:
    _run_the_check(records_state)


@then("it reports up_to_date true")
def _reports_up_to_date_true(records_state: dict[str, Any]) -> None:
    assert records_state["result"].up_to_date is True


@scenario("finalize_records.feature", "Every other case is not up to date, with a reason")
def test_scn008_every_other_case_is_not_up_to_date() -> None:
    """SCN008: each case gives up_to_date false and its own reason."""


def _set_up_case(case: str, records_state: dict[str, Any]) -> None:
    tmp = records_state["tmp"]
    request = asset_request(tmp, "Crate", blend=case != "the run had no source .blend")
    records_state["request"] = request
    if case == "no record exists":
        write_imports(request)
    elif case == "the record is not valid JSON":
        write_imports(request)
        write_record_file(request, "{not json")
    elif case == "the last run failed":
        write_imports(request)
        write_record_file(request, manual_record(request, state="failed"))
    elif case == "the last run was one step":
        write_imports(request)
        write_record_file(request, manual_record(request, full_run=False))
    elif case == "the run had no source .blend":
        write_imports(request)
        write_record_file(request, manual_record(request))
    elif case == "the .blend was deleted":
        write_imports(request)
        write_record_file(request, manual_record(request))
        assert request.blend is not None
        request.blend.unlink()
    elif case == "the .blend changed after the run began":
        write_imports(request)
        write_record_file(request, manual_record(request, started_at=PAST))
    elif case == "the Mobile .glb.import is missing":
        write_imports(request)
        write_record_file(request, manual_record(request))
        (request.export_root / "Props" / "Crate" / "Mobile" / "Crate.glb.import").unlink()
    elif case == "no project.godot can be found":
        write_imports(request)
        write_record_file(request, manual_record(request))
        records_state["export_root"] = tmp / "loose" / "assets"
    else:  # pragma: no cover - the outline's Examples cover every case
        raise AssertionError(f"unknown case {case!r}")


@given(parsers.parse("a record set up so that {case}"))
def _a_record_set_up_so_that(records_state: dict[str, Any], case: str) -> None:
    _set_up_case(case, records_state)


@then(parsers.parse('it reports up_to_date false with reason "{reason}"'))
def _reports_not_up_to_date(records_state: dict[str, Any], reason: str) -> None:
    result = records_state["result"]
    assert result.up_to_date is False
    assert result.reason == reason


@scenario("finalize_records.feature", "The check is cheap and has no side effects")
def test_scn009_the_check_is_cheap_and_has_no_side_effects() -> None:
    """SCN009: the check answers while another job holds the lock and writes nothing."""


@given("another finalize job holds the cache lock")
def _another_job_holds_the_lock(records_state: dict[str, Any]) -> None:
    records_state["request"] = up_to_date_asset(records_state["tmp"], "Crate")
    hold_cache_lock(records_state["cache"])
    records_state["before"] = snapshot(records_state["tmp"])


@then("it answers and the project and cache trees are unchanged")
def _answers_and_trees_unchanged(records_state: dict[str, Any]) -> None:
    assert records_state["result"].up_to_date is True
    assert snapshot(records_state["tmp"]) == records_state["before"]


# SCN010 - SCN011: a record that cannot be written, and batch skips.


@scenario("finalize_records.feature", "Record writing never changes a run's result")
def test_scn010_record_writing_never_changes_a_run() -> None:
    """SCN010: an unwritable records folder adds a warning and leaves the run succeeded."""


@given('".nmg/finalize" is a file, so no record can be written')
def _records_folder_is_a_file(records_state: dict[str, Any]) -> None:
    tmp = records_state["tmp"]
    records_state["request"] = asset_request(tmp, "Crate")
    (tmp / ".nmg").mkdir(exist_ok=True)
    (tmp / ".nmg" / "finalize").write_text("a file", encoding="utf-8")


@then('its state is "succeeded" and its result carries a "finalize.record_not_written" warning')
def _succeeded_with_a_warning(records_state: dict[str, Any]) -> None:
    status = records_state["status"]
    assert status["state"] == "succeeded"
    assert [w["code"] for w in status["result"]["warnings"]] == ["finalize.record_not_written"]


@scenario("finalize_records.feature", "Batches can skip up-to-date assets")
def test_scn011_batches_can_skip_up_to_date_assets() -> None:
    """SCN011: an up-to-date item runs no step and keeps its record; the other item runs."""


@given("a batch of Crate and Barrel with skip_up_to_date where only Crate is up to date")
def _batch_where_only_crate_is_up_to_date(records_state: dict[str, Any]) -> None:
    tmp = records_state["tmp"]
    crate = asset_request(tmp, "Crate")
    barrel = asset_request(tmp, "Barrel")
    records_state["requests"] = {"Crate": crate, "Barrel": barrel}
    records_state["skip"] = True
    run_finalize(records_state["cache"], crate)
    write_imports(crate)
    records_state["crate_before"] = record_of(crate).read_bytes()
    records_state["ran"] = []

    def on_step(item_dir: Path, step: str) -> None:
        records_state["ran"].append(item_dir.name)

    records_state["on_step"] = on_step


@then('Crate\'s item state is "up_to_date", no step ran for it, and its record is unchanged')
def _crate_item_up_to_date(records_state: dict[str, Any]) -> None:
    items = {
        item["collection"]: item for item in records_state["batch"]["result"]["batch"]["items"]
    }
    assert items["Crate"]["state"] == "up_to_date"
    assert not any("Crate" in name for name in records_state["ran"])
    assert (
        record_of(records_state["requests"]["Crate"]).read_bytes() == records_state["crate_before"]
    )


@then("Barrel runs every step")
def _barrel_runs_every_step(records_state: dict[str, Any]) -> None:
    items = {
        item["collection"]: item for item in records_state["batch"]["result"]["batch"]["items"]
    }
    assert items["Barrel"]["state"] == "succeeded"
    barrel_steps = {name for name in records_state["ran"] if "Barrel" in name}
    assert barrel_steps, "Barrel must run its steps"
    barrel = _record(records_state["requests"]["Barrel"])
    assert [s["step"] for s in barrel["steps"]] == list(STEP_ORDER)


# SCN012 - SCN013: the docs and the onboarding ignore line.


@scenario("finalize_records.feature", "The record and the check are documented")
def test_scn012_the_record_and_the_check_are_documented() -> None:
    """SCN012: the MCP reference and the skill describe the record, the logs, and the check."""


@given("docs/mcp/finalize.md and skills/finalize-asset/SKILL.md")
def _the_two_documents(records_state: dict[str, Any]) -> None:
    records_state["docs"] = DOCS.read_text(encoding="utf-8")
    records_state["skill"] = SKILL.read_text(encoding="utf-8")


@when("a reader looks up finalize records")
def _a_reader_looks_up_records(records_state: dict[str, Any]) -> None:
    records_state["lookup"] = records_state["docs"] + records_state["skill"]


@then(
    "they describe the record path and fields, the logs, check and check_finalized, the reasons, "
    "skip_up_to_date, and the modification-time caveat"
)
def _they_describe_the_record(records_state: dict[str, Any]) -> None:
    text = records_state["lookup"]
    for needle in (
        "<consumer>/.nmg/finalize/<Category>/<Name>.json",
        "schema_version",
        "<Name>.logs/",
        "nmg_game_dev.finalize check",
        "check_finalized",
        "no_record",
        "skip_up_to_date",
        "modification times",
    ):
        assert needle in text, needle


@scenario("finalize_records.feature", "Onboarding ignores the records")
def test_scn013_onboarding_ignores_the_records() -> None:
    """SCN013: the gitignore_env step adds .nmg/ to a consumer .gitignore."""


@given('a consumer .gitignore without ".nmg/"')
def _gitignore_without_records(records_state: dict[str, Any]) -> None:
    path = records_state["tmp"] / ".gitignore"
    path.write_text(".env\ngame/.godot/\n", encoding="utf-8")
    records_state["gitignore"] = path


@when("the gitignore_env onboarding step runs")
def _the_gitignore_step_runs(records_state: dict[str, Any]) -> None:
    records_state["step"] = ensure_gitignore_env("gitignore_env", records_state["gitignore"])


@then('the .gitignore contains ".nmg/"')
def _gitignore_contains_records(records_state: dict[str, Any]) -> None:
    lines = records_state["gitignore"].read_text(encoding="utf-8").splitlines()
    assert ".nmg/" in lines
    assert records_state["step"].status == "installed"
