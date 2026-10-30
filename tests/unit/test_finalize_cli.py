"""Unit tests for the ``python -m nmg_game_dev.finalize`` CLI (AC3, #69).

The CLI runs through the real job layer.  An in-process launcher runs the job body with the fake
step runner, so no Blender or Unreal process is started.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from io import StringIO
from pathlib import Path

import pytest

from nmg_game_dev.finalize import FinalizeService, build_request, default_budgets_path
from nmg_game_dev.finalize.__main__ import EXIT_FAILED, EXIT_OK, EXIT_PREREQUISITE, main
from nmg_game_dev.pipeline import FinalizeClients, FinalizeRequest, PipelineError, jobs
from tests.finalize_fakes import FakeBlenderSession, FakeStepRunner, FakeUnrealRunner


def _dead_pid() -> int:
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait()
    return process.pid


def _inproc_service(
    cache_root: Path,
    make_runner: Callable[[FinalizeRequest], object],
    clients: FinalizeClients | None = None,
) -> FinalizeService:
    def launch(job_dir: Path) -> int:
        request = FinalizeRequest.model_validate_json((job_dir / "request.json").read_text())
        jobs.run_job(
            job_dir,
            clients=clients
            or FinalizeClients(blender=FakeBlenderSession(), unreal=FakeUnrealRunner()),
            runner=make_runner(request),  # type: ignore[arg-type]
        )
        return _dead_pid()

    return FinalizeService(cache_root, launcher=launch)


def _argv(tmp_path: Path, *extra: str, command: str = "all") -> list[str]:
    blend = tmp_path / "crate.blend"
    blend.write_bytes(b"authored")
    return [
        command,
        "--collection",
        "Crate",
        "--category",
        "Props",
        "--class",
        "standard_prop",
        "--export-root",
        str(tmp_path / "export"),
        "--blend",
        str(blend),
        *extra,
    ]


class _Streams:
    def __init__(self) -> None:
        self.out = StringIO()
        self.err = StringIO()


@pytest.fixture()
def streams() -> _Streams:
    return _Streams()


def _run(argv: list[str], service: FinalizeService, streams: _Streams) -> int:
    return main(argv, service=service, stdout=streams.out, stderr=streams.err)


def test_all_runs_every_step_and_prints_the_content_paths(
    tmp_path: Path, streams: _Streams
) -> None:
    service = _inproc_service(
        tmp_path / "cache",
        lambda request: FakeStepRunner(request),
    )
    code = _run(_argv(tmp_path), service, streams)

    assert code == EXIT_OK
    out = streams.out.getvalue()
    assert "validate:" in out
    assert "import_ue:" in out
    assert "Desktop: /Game/Props/Crate/Desktop" in out
    assert "Mobile: /Game/Props/Crate/Mobile" in out


def test_json_flag_prints_the_result_as_json(tmp_path: Path, streams: _Streams) -> None:
    service = _inproc_service(tmp_path / "cache", lambda request: FakeStepRunner(request))
    code = _run(_argv(tmp_path, "--json"), service, streams)

    assert code == EXIT_OK
    result = json.loads(streams.out.getvalue())
    assert result["desktop_content_path"] == "/Game/Props/Crate/Desktop"
    assert [step["step"] for step in result["steps"]][-1] == "import_ue"


def test_a_single_step_runs_its_prerequisites_only(tmp_path: Path, streams: _Streams) -> None:
    service = _inproc_service(tmp_path / "cache", lambda request: FakeStepRunner(request))
    code = _run(_argv(tmp_path, command="variants"), service, streams)

    assert code == EXIT_OK
    out = streams.out.getvalue()
    assert "variants:" in out
    assert "import_ue" not in out


def test_failed_step_exits_one_with_error_and_remediation(
    tmp_path: Path, streams: _Streams
) -> None:
    service = _inproc_service(
        tmp_path / "cache",
        lambda request: FakeStepRunner(
            request,
            failures={"bake": ("texture.bake_failed", "Alpha is linked.", "Set Alpha to 1.")},
        ),
    )
    code = _run(_argv(tmp_path), service, streams)

    assert code == EXIT_FAILED
    err = streams.err.getvalue()
    assert "ERROR [bake.texture.bake_failed] Alpha is linked." in err
    assert "Remediation: Set Alpha to 1." in err


def test_missing_blender_exits_two_as_a_prerequisite(tmp_path: Path, streams: _Streams) -> None:
    class _NoBlender:
        def run_step(self, step: str, **_: object) -> dict[str, object]:
            raise PipelineError(
                code="finalize.blender_not_found",
                message="Blender was not found.",
                remediation="Set BLENDER_APP.",
                stage="finalize",
            )

        def hash(self, **_: object) -> str:
            return "h"

    service = _inproc_service(tmp_path / "cache", lambda request: _NoBlender())
    code = _run(_argv(tmp_path), service, streams)

    assert code == EXIT_PREREQUISITE
    assert "finalize.blender_not_found" in streams.err.getvalue()


def test_invalid_class_is_refused_before_any_step(tmp_path: Path, streams: _Streams) -> None:
    argv = _argv(tmp_path)
    argv[argv.index("standard_prop")] = "not_a_class"
    service = _inproc_service(tmp_path / "cache", lambda request: FakeStepRunner(request))
    code = _run(argv, service, streams)

    assert code == EXIT_FAILED
    assert "finalize.invalid_request" in streams.err.getvalue()


def test_project_budget_file_is_used_when_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "nmg-budgets.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    assert default_budgets_path() == tmp_path / "nmg-budgets.json"

    request = build_request(
        collection="Crate",
        category="Props",
        asset_class="standard_prop",
        export_root=tmp_path / "export",
    )
    assert request.budgets_path == tmp_path / "nmg-budgets.json"


def test_no_budget_file_means_contract_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path / "empty"))
    assert default_budgets_path() is None
    request = build_request(
        collection="Crate",
        category="Props",
        asset_class="standard_prop",
        export_root=tmp_path / "export",
    )
    assert request.budgets_path is None


def test_explicit_budgets_flag_wins_over_the_project_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "nmg-budgets.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    explicit = tmp_path / "custom.json"
    request = build_request(
        collection="Crate",
        category="Props",
        asset_class="standard_prop",
        export_root=tmp_path / "export",
        budgets_path=explicit,
    )
    assert request.budgets_path == explicit
