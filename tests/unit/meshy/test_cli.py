"""The CLI prints the same JSON as the MCP tools and fails with codes (#98 AC12, SCN012)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from nmg_game_dev.meshy import __main__ as cli
from nmg_game_dev.meshy import jobs
from tests.meshy_fakes import (
    ENV,
    TEST_KEY,
    FakeClock,
    FakeMeshy,
    FakeSession,
    RecordingSpawn,
    make_png,
    run_job,
)


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Run the CLI in a temp project with the fake session; detached jobs are recorded, not run."""
    monkeypatch.setenv("MESHY_API_KEY", TEST_KEY)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(jobs, "BlenderSessionClient", lambda: FakeSession())
    monkeypatch.setattr(jobs, "default_spawn", RecordingSpawn())
    return tmp_path


def _inline_spawn(session: FakeSession, meshy: FakeMeshy) -> Any:
    def spawn(job_dir: Path, env: Any, cwd: Path) -> None:
        clock = FakeClock()
        run_job(job_dir, meshy=meshy, session=session, clock=clock, env=ENV)

    return spawn


def test_parser_accepts_repeated_images_and_no_texture() -> None:
    args = cli._build_parser().parse_args(
        ["generate", "--name", "Ghost", "--image", "a.png", "--image", "b.jpg", "--no-texture"]
    )
    assert args.images == ["a.png", "b.jpg"]
    assert args.texture is False


def test_generate_prints_the_job_id(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["generate", "--name", "Crate", "--prompt", "crate"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert set(printed) == {"job_id"}
    assert jobs.status(printed["job_id"], env=ENV, cwd=project)["state"] == "queued"


def test_status_prints_exactly_what_get_meshy_job_returns(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli.main(["generate", "--name", "Crate", "--prompt", "crate"])
    job_id = json.loads(capsys.readouterr().out)["job_id"]
    assert cli.main(["status", job_id]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed == jobs.status(job_id, env=ENV, cwd=project)


def test_wait_prints_the_final_status(
    project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    session, meshy = FakeSession(), FakeMeshy()
    monkeypatch.setattr(jobs, "default_spawn", _inline_spawn(session, meshy))
    monkeypatch.setattr(jobs, "BlenderSessionClient", lambda: session)
    assert cli.main(["generate", "--name", "Crate", "--prompt", "crate", "--wait"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["state"] == "succeeded"
    assert printed["result"]["loaded_into_session"] is True


def test_a_refused_request_prints_the_code_and_remediation_and_exits_1(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["generate", "--name", "crate", "--prompt", "x"]) == 1
    err = capsys.readouterr().err
    assert "ERROR [meshy.invalid_request]:" in err
    assert "Remediation:" in err


def test_a_missing_collection_fails_retexture_with_its_code(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["retexture", "--name", "Crate", "--prompt", "mossy"]) == 1
    assert "ERROR [meshy.collection_not_found]:" in capsys.readouterr().err


def test_an_unreachable_session_fails_retexture_with_the_blender_code(
    project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        jobs,
        "BlenderSessionClient",
        lambda: FakeSession(collections=["Crate"], down={"export_glb"}),
    )
    assert cli.main(["retexture", "--name", "Crate", "--prompt", "mossy"]) == 1
    assert "ERROR [mcp.blender.unreachable]:" in capsys.readouterr().err


def test_status_of_an_unknown_job_exits_1(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["status", "nope"]) == 1
    assert "ERROR [meshy.job_not_found]:" in capsys.readouterr().err


def test_run_job_prints_the_final_document(
    project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(jobs, "run_job", lambda job_dir: {"job_id": "x", "state": "succeeded"})
    assert cli.main(["run-job", str(project)]) == 0
    assert json.loads(capsys.readouterr().out) == {"job_id": "x", "state": "succeeded"}


def test_a_reference_image_path_is_validated_by_the_cli_too(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    gif = project / "ref.gif"
    gif.write_bytes(b"GIF89a")
    assert cli.main(["generate", "--name", "Lamp", "--image", str(gif)]) == 1
    assert "ERROR [meshy.invalid_request]:" in capsys.readouterr().err
    make_png(project / "ref.png")
    assert cli.main(["generate", "--name", "Lamp", "--image", str(project / "ref.png")]) == 0
