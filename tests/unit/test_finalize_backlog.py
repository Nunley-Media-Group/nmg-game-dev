"""Unit tests for the finalize fallback to the design backlog (#112 AC4, FR5).

A project's ``docs/design/backlog.json`` supplies a missing ``category`` or ``asset_class``.  A
successful full ``finalize_asset`` job marks the matching entry ``finalized``.
``run_finalize_step`` never marks.  A backlog write failure is a warning, not a failed job.
"""

from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Any

import pytest

from nmg_game_dev.design import backlog as design_backlog
from nmg_game_dev.design.__main__ import main as design_main
from nmg_game_dev.design.paths import backlog_path
from nmg_game_dev.finalize import FinalizeService, finalize_asset, run_finalize_step
from nmg_game_dev.finalize.__main__ import main as finalize_main
from nmg_game_dev.pipeline import FinalizeClients, FinalizeRequest, jobs
from nmg_game_dev.pipeline.steps import settings_hash
from tests.finalize_fakes import FakeBlenderSession, FakeStepRunner, FakeUnrealRunner


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project whose backlog holds one prop, Crate, planned and synced."""
    root = tmp_path / "project"
    props = root / "docs" / "design" / "props"
    props.mkdir(parents=True)
    (props / "crate.md").write_text(
        "---\ntype: prop\nname: Crate\ncategory: Props\nasset_class: standard_prop\n---\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    assert design_main(["sync"], stdout=io.StringIO(), stderr=io.StringIO()) == 0
    return root


def _args(tmp_path: Path, collection: str = "Crate") -> dict[str, Any]:
    blend = tmp_path / f"{collection.lower()}.blend"
    blend.write_bytes(b"authored")
    return {
        "collection": collection,
        "export_root": str(tmp_path / "export"),
        "blend": str(blend),
    }


def _deferred(cache: Path) -> FinalizeService:
    """A service whose launcher leaves the job queued, so the test can run it itself."""
    return FinalizeService(cache, launcher=lambda job_dir: os.getpid())


def _run_job(cache: Path, job_id: str) -> None:
    job_dir = cache / "jobs" / job_id
    request = FinalizeRequest.model_validate_json(
        (job_dir / "request.json").read_text(encoding="utf-8")
    )
    jobs.run_job(
        job_dir,
        clients=FinalizeClients(blender=FakeBlenderSession(), unreal=FakeUnrealRunner()),
        runner=FakeStepRunner(request),
    )


def _request_json(cache: Path, job_id: str) -> dict[str, object]:
    text = (cache / "jobs" / job_id / "request.json").read_text(encoding="utf-8")
    return dict(FinalizeRequest.model_validate_json(text).model_dump(mode="json"))


def _status(project: Path, asset_name: str) -> str:
    entries = design_backlog.load(backlog_path(project))
    return next(entry.status for entry in entries if entry.asset_name == asset_name)


def test_mcp_finalize_takes_category_and_class_from_the_backlog(
    project: Path, tmp_path: Path
) -> None:
    cache = tmp_path / "cache"
    response = finalize_asset(**_args(tmp_path), service=_deferred(cache))

    request = _request_json(cache, str(response["job_id"]))
    assert request["category"] == "Props"
    assert request["asset_class"] == "standard_prop"
    assert request["backlog_path"] == str(backlog_path(project))


def test_explicit_arguments_win_over_the_backlog(project: Path, tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    response = finalize_asset(
        **_args(tmp_path),
        category="Weapons",
        service=_deferred(cache),
    )

    request = _request_json(cache, str(response["job_id"]))
    assert request["category"] == "Weapons"
    assert request["asset_class"] == "standard_prop"


def test_a_successful_full_run_marks_the_entry_finalized(project: Path, tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    service = _deferred(cache)
    job_id = str(finalize_asset(**_args(tmp_path), service=service)["job_id"])

    _run_job(cache, job_id)

    assert service.status(job_id)["state"] == "succeeded"
    assert _status(project, "Crate") == "finalized"


def test_run_finalize_step_never_marks_the_entry(project: Path, tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    service = _deferred(cache)
    response = run_finalize_step(
        step="validate",
        **_args(tmp_path),
        service=service,
    )

    _run_job(cache, str(response["job_id"]))

    assert service.status(str(response["job_id"]))["state"] == "succeeded"
    assert _status(project, "Crate") == "planned"


def test_a_backlog_write_failure_warns_without_failing_the_job(
    project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(*_args: object, **_kwargs: object) -> bool:
        raise OSError("read-only backlog")

    monkeypatch.setattr(design_backlog, "mark", refuse)
    cache = tmp_path / "cache"
    service = _deferred(cache)
    job_id = str(finalize_asset(**_args(tmp_path), service=service)["job_id"])

    _run_job(cache, job_id)

    status = service.status(job_id)
    assert status["state"] == "succeeded"
    warnings = status["result"]["warnings"]
    assert [warning["code"] for warning in warnings] == ["design.backlog_update_failed"]


def test_a_missing_argument_with_no_entry_names_the_argument_and_the_backlog(
    project: Path, tmp_path: Path
) -> None:
    response = finalize_asset(
        **_args(tmp_path, collection="Barrel"),
        service=_deferred(tmp_path / "cache"),
    )

    error = response["error"]
    assert error["code"] == "finalize.invalid_request"
    assert "category" in error["message"]
    assert str(backlog_path(project)) in error["message"]


def test_cli_reports_the_missing_argument_and_exits_1(project: Path, tmp_path: Path) -> None:
    err = io.StringIO()
    code = finalize_main(
        [
            "all",
            "--collection",
            "Barrel",
            "--export-root",
            str(tmp_path / "export"),
        ],
        stdout=io.StringIO(),
        stderr=err,
    )

    assert code == 1
    assert "ERROR [finalize.invalid_request] category is required" in err.getvalue()


def test_the_backlog_path_never_changes_the_cache_settings(tmp_path: Path) -> None:
    base = FinalizeRequest(
        collection="Crate",
        category="Props",
        asset_class="standard_prop",
        export_root=tmp_path / "export",
    )
    linked = base.model_copy(update={"backlog_path": tmp_path / "backlog.json"})

    for step in ("validate", "bake", "variants", "export", "reimport", "import_ue"):
        assert settings_hash(step, base, "") == settings_hash(step, linked, "")
