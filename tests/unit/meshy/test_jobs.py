"""Background jobs: start, route, import, retexture, failures, and redaction (#98 FR4–FR7)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from nmg_game_dev.meshy import jobs
from nmg_game_dev.meshy.errors import MeshyError
from nmg_game_dev.meshy.paths import glb_path, jobs_root, maps_dir
from nmg_game_dev.meshy.request import GenerateRequest, RetextureRequest
from nmg_game_dev.pipeline.errors import PipelineError
from tests.meshy_fakes import (
    ENV,
    GLB_BYTES,
    IMPORT_NORMALIZATION,
    MAP_BYTES,
    MAP_NAMES,
    TEST_KEY,
    FakeClock,
    FakeMeshy,
    FakeSession,
    all_job_text,
    generate_and_run,
    make_png,
    retexture_and_run,
    run_job,
    start_generate,
    start_retexture,
)

UNREACHABLE = "mcp.blender.unreachable"


def _jobs_exist(project: Path) -> bool:
    return jobs_root(project).exists() and any(jobs_root(project).iterdir())


def _posts_by_path(meshy: FakeMeshy) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for path, body in meshy.posts():
        grouped.setdefault(path, []).append(body)
    return grouped


# --- start: order of checks and nothing written before them -------------------------------


def test_invalid_request_is_refused_before_the_key_is_read(tmp_path: Path) -> None:
    with pytest.raises(MeshyError) as info:
        start_generate(GenerateRequest(name="crate", prompt="x"), tmp_path, env={})
    assert info.value.code == "meshy.invalid_request"
    assert not _jobs_exist(tmp_path)


def test_missing_key_fails_before_any_write_or_spawn(tmp_path: Path) -> None:
    session = FakeSession()
    with pytest.raises(MeshyError) as info:
        start_generate(GenerateRequest(name="Crate", prompt="x"), tmp_path, env={}, session=session)
    assert info.value.code == "meshy.api_key_missing"
    assert not _jobs_exist(tmp_path)
    assert session.ops == []


def test_existing_collection_is_refused_before_a_job_starts(tmp_path: Path) -> None:
    session = FakeSession(collections=["Crate"])
    with pytest.raises(MeshyError) as info:
        start_generate(GenerateRequest(name="Crate", prompt="x"), tmp_path, session=session)
    assert info.value.code == "meshy.collection_exists"
    assert not _jobs_exist(tmp_path)


def test_an_unreachable_session_at_start_does_not_block_generation(tmp_path: Path) -> None:
    session = FakeSession(down={"collection_state"})
    job_id, spawn = start_generate(
        GenerateRequest(name="Crate", prompt="x"), tmp_path, session=session
    )
    assert len(spawn.jobs) == 1
    assert jobs.status(job_id, env=ENV, cwd=tmp_path)["state"] == "queued"


def test_a_queued_job_is_visible_and_its_files_hold_no_key(tmp_path: Path) -> None:
    job_id, spawn = start_generate(GenerateRequest(name="Crate", prompt="crate"), tmp_path)
    assert jobs.status(job_id, env=ENV, cwd=tmp_path)["state"] == "queued"
    assert TEST_KEY not in all_job_text(spawn.jobs[0])


def test_status_rejects_unknown_and_path_like_ids(tmp_path: Path) -> None:
    for job_id in ("missing", "../escape", "", "."):
        with pytest.raises(MeshyError) as info:
            jobs.status(job_id, env=ENV, cwd=tmp_path)
        assert info.value.code == "meshy.job_not_found"


def test_a_failed_spawn_leaves_no_job_directory(tmp_path: Path) -> None:
    def broken_spawn(job_dir: Path, env: Any, cwd: Path) -> None:
        raise RuntimeError("cannot start")

    with pytest.raises(RuntimeError):
        jobs.start_generate(
            GenerateRequest(name="Crate", prompt="x"),
            env=ENV,
            cwd=tmp_path,
            session=FakeSession(),
            spawn=broken_spawn,
        )
    assert not _jobs_exist(tmp_path)


# --- generation routing and import ---------------------------------------------------------


def test_prompt_only_generation_runs_preview_then_refine_and_lands_in_the_session(
    tmp_path: Path,
) -> None:
    job_id, final, meshy, session = generate_and_run(
        GenerateRequest(name="Crate", prompt="weathered wooden crate"), tmp_path
    )
    assert final["state"] == "succeeded"
    result = final["result"]
    assert result["route"] == "text" and result["loaded_into_session"] is True
    assert result["collection"] == "Crate" and result["mesh"] == "SM_Crate"
    assert result["material"] == "M_Crate_Body" and result["warnings"] == []
    assert glb_path(tmp_path, "Crate").read_bytes() == GLB_BYTES
    preview, refine = _posts_by_path(meshy)["/openapi/v2/text-to-3d"]
    assert preview == {"mode": "preview", "prompt": "weathered wooden crate"}
    assert refine["mode"] == "refine" and refine["enable_pbr"] is True
    assert session.ops_named("import_glb") == [
        {"name": "Crate", "path": str(glb_path(tmp_path, "Crate"))}
    ]
    assert jobs.status(job_id, env=ENV, cwd=tmp_path) == final


def test_untextured_prompt_runs_only_the_preview(tmp_path: Path) -> None:
    _job, final, meshy, _session = generate_and_run(
        GenerateRequest(name="Crate", prompt="crate", texture=False), tmp_path
    )
    assert final["state"] == "succeeded"
    assert [body["mode"] for _path, body in meshy.posts()] == ["preview"]


def test_one_image_uses_image_to_3d_without_a_texture_prompt(tmp_path: Path) -> None:
    image = str(make_png(tmp_path / "lamp.png"))
    _job, final, meshy, _session = generate_and_run(
        GenerateRequest(name="Lamppost", image_paths=(image,)), tmp_path
    )
    assert final["result"]["route"] == "image"
    (body,) = _posts_by_path(meshy)["/openapi/v1/image-to-3d"]
    assert body["image_url"].startswith("data:image/png;base64,")
    assert "texture_prompt" not in body
    assert body["should_texture"] is True and body["enable_pbr"] is True


def test_several_images_use_multi_image_with_each_mime_and_the_prompt_as_texture(
    tmp_path: Path,
) -> None:
    images = (
        str(make_png(tmp_path / "a.png")),
        str(make_png(tmp_path / "b.jpg")),
        str(make_png(tmp_path / "c.webp")),
    )
    _job, final, meshy, _session = generate_and_run(
        GenerateRequest(name="Ghost", image_paths=images, prompt="pale translucent cloth"),
        tmp_path,
    )
    assert final["result"]["route"] == "multi_image"
    (body,) = _posts_by_path(meshy)["/openapi/v1/multi-image-to-3d"]
    prefixes = [uri.split(";", 1)[0] for uri in body["image_urls"]]
    assert prefixes == ["data:image/png", "data:image/jpeg", "data:image/webp"]
    assert body["texture_prompt"] == "pale translucent cloth"


def test_pose_is_sent_on_the_geometry_request_only_when_given(tmp_path: Path) -> None:
    image = str(make_png(tmp_path / "knight.png"))
    _job, _final, posted, _session = generate_and_run(
        GenerateRequest(name="Knight", image_paths=(image,), pose="a-pose"), tmp_path
    )
    (with_pose,) = _posts_by_path(posted)["/openapi/v1/image-to-3d"]
    assert with_pose["pose_mode"] == "a-pose"

    _job, _final, plain, _session = generate_and_run(
        GenerateRequest(name="Plain", image_paths=(image,)), tmp_path
    )
    (without_pose,) = _posts_by_path(plain)["/openapi/v1/image-to-3d"]
    assert "pose_mode" not in without_pose


def test_untextured_images_send_should_texture_false(tmp_path: Path) -> None:
    image = str(make_png(tmp_path / "rock.png"))
    _job, final, meshy, _session = generate_and_run(
        GenerateRequest(name="Rock", image_paths=(image,), texture=False), tmp_path
    )
    assert final["state"] == "succeeded"
    (body,) = _posts_by_path(meshy)["/openapi/v1/image-to-3d"]
    assert body["should_texture"] is False and body["enable_pbr"] is False


def test_an_unreachable_session_at_import_keeps_the_glb_and_warns(tmp_path: Path) -> None:
    _job, final, _meshy, _session = generate_and_run(
        GenerateRequest(name="Crate", prompt="crate"),
        tmp_path,
        session=FakeSession(down={"import_glb"}),
    )
    assert final["state"] == "succeeded"
    result = final["result"]
    assert result["loaded_into_session"] is False
    assert result["warnings"][0]["code"] == UNREACHABLE
    assert result["warnings"][0]["remediation"]
    assert glb_path(tmp_path, "Crate").read_bytes() == GLB_BYTES


def test_a_loaded_generate_job_copies_the_import_normalization(tmp_path: Path) -> None:
    _job, final, _meshy, _session = generate_and_run(
        GenerateRequest(name="Crate", prompt="crate"), tmp_path
    )
    result = final["result"]
    assert result["merged_vertices"] == IMPORT_NORMALIZATION["merged_vertices"]
    assert result["origin_offset"] == IMPORT_NORMALIZATION["origin_offset"]


def test_an_unreachable_import_adds_no_normalization_keys(tmp_path: Path) -> None:
    _job, final, _meshy, _session = generate_and_run(
        GenerateRequest(name="Crate", prompt="crate"),
        tmp_path,
        session=FakeSession(down={"import_glb"}),
    )
    assert "merged_vertices" not in final["result"]
    assert "origin_offset" not in final["result"]


def test_a_meshy_job_without_a_glb_fails_with_task_failed(tmp_path: Path) -> None:
    _job, final, _meshy, _session = generate_and_run(
        GenerateRequest(name="Crate", prompt="crate", texture=False),
        tmp_path,
        meshy=FakeMeshy(glb_url=None),
    )
    assert final["state"] == "failed"
    assert final["error"]["code"] == "meshy.task_failed"


# --- task failures, timeouts, and status codes --------------------------------------------


@pytest.mark.parametrize("state", ["FAILED", "CANCELED", "EXPIRED"])
def test_terminal_failures_carry_meshys_message(tmp_path: Path, state: str) -> None:
    _job, final, _meshy, _session = generate_and_run(
        GenerateRequest(name="Crate", prompt="crate"),
        tmp_path,
        meshy=FakeMeshy(task_states=[state], task_error="prompt was refused"),
    )
    assert final["state"] == "failed"
    assert final["error"]["code"] == "meshy.task_failed"
    assert "prompt was refused" in final["error"]["message"]
    assert final["error"]["remediation"]


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"create_status": 401}, "meshy.auth_failed"),
        ({"poll_status": 401}, "meshy.auth_failed"),
        ({"create_status": 402}, "meshy.insufficient_credits"),
        ({"poll_status": 429}, "meshy.rate_limited"),
    ],
)
def test_http_status_failures_fail_the_job_with_their_code(
    tmp_path: Path, kwargs: dict[str, int], code: str
) -> None:
    _job, final, _meshy, _session = generate_and_run(
        GenerateRequest(name="Crate", prompt="crate"),
        tmp_path,
        meshy=FakeMeshy(**kwargs),  # type: ignore[arg-type]
    )
    assert final["state"] == "failed"
    assert final["error"]["code"] == code
    assert final["error"]["remediation"]


def test_a_task_that_never_finishes_times_out(tmp_path: Path) -> None:
    clock = FakeClock()
    job_id, spawn = start_generate(
        GenerateRequest(name="Crate", prompt="crate", texture=False), tmp_path
    )
    final = run_job(
        spawn.jobs[0],
        meshy=FakeMeshy(task_states=["IN_PROGRESS"]),
        session=FakeSession(),
        clock=clock,
        timeout=60.0,
    )
    assert final["state"] == "failed"
    assert final["error"]["code"] == "meshy.task_timeout"
    assert clock.now >= 60.0
    assert jobs.status(job_id, env=ENV, cwd=tmp_path)["state"] == "failed"


def test_progress_is_recorded_while_the_task_runs(tmp_path: Path) -> None:
    job_id, spawn = start_generate(
        GenerateRequest(name="Crate", prompt="crate", texture=False), tmp_path
    )
    observed: list[dict[str, Any]] = []

    class _Watch(FakeMeshy):
        def send(
            self, method: str, url: str, headers: Any, body: bytes | None
        ) -> tuple[int, bytes]:
            if method == "GET":
                observed.append(jobs.status(job_id, env=ENV, cwd=tmp_path))
            return super().send(method, url, headers, body)

    run_job(
        spawn.jobs[0], meshy=_Watch(task_states=["IN_PROGRESS", "SUCCEEDED"]), session=FakeSession()
    )
    running = [doc for doc in observed if doc["state"] == "running"]
    assert any(doc["stage"] == "preview" and doc["progress"] == 40 for doc in running)


def test_a_crash_is_recorded_as_job_crashed(tmp_path: Path) -> None:
    class _Broken:
        def send(
            self, method: str, url: str, headers: Any, body: bytes | None
        ) -> tuple[int, bytes]:
            raise RuntimeError("socket exploded")

    _job, final, _meshy, _session = generate_and_run(
        GenerateRequest(name="Crate", prompt="crate"),
        tmp_path,
        meshy=_Broken(),  # type: ignore[arg-type]
    )
    assert final["state"] == "failed"
    assert final["error"]["code"] == "meshy.job_crashed"
    assert "socket exploded" in final["error"]["message"]


def test_the_detached_child_resolves_the_key_from_the_dotenv(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("MESHY_API_KEY=key-from-dotenv\n", encoding="utf-8")
    job_id, spawn = start_generate(GenerateRequest(name="Crate", prompt="crate"), tmp_path, env={})
    meshy = FakeMeshy()
    final = run_job(spawn.jobs[0], meshy=meshy, session=FakeSession(), env={})
    assert final["state"] == "succeeded"
    assert meshy.sent[0].headers["Authorization"] == "Bearer key-from-dotenv"


def test_environment_key_wins_in_the_child_too(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("MESHY_API_KEY=key-from-dotenv\n", encoding="utf-8")
    _job, spawn = start_generate(GenerateRequest(name="Crate", prompt="crate"), tmp_path, env={})
    meshy = FakeMeshy()
    run_job(
        spawn.jobs[0], meshy=meshy, session=FakeSession(), env={"MESHY_API_KEY": "key-from-env"}
    )
    assert meshy.sent[0].headers["Authorization"] == "Bearer key-from-env"


def test_the_key_never_reaches_a_job_file_or_an_error(tmp_path: Path) -> None:
    failing = FakeMeshy(task_states=["FAILED"], task_error=f"rejected key {TEST_KEY}")
    _job, final, _meshy, _session = generate_and_run(
        GenerateRequest(name="Crate", prompt="crate"), tmp_path, meshy=failing
    )
    assert final["state"] == "failed"
    assert TEST_KEY not in final["error"]["message"]
    assert "***" in final["error"]["message"]
    job_dir = jobs_root(tmp_path) / final["job_id"]
    assert TEST_KEY not in all_job_text(job_dir)


def test_the_key_is_absent_from_a_successful_job_directory(tmp_path: Path) -> None:
    _job, final, _meshy, _session = generate_and_run(
        GenerateRequest(name="Crate", prompt="crate"), tmp_path
    )
    assert final["state"] == "succeeded"
    assert TEST_KEY not in all_job_text(jobs_root(tmp_path) / final["job_id"])


def test_wait_returns_the_final_status(tmp_path: Path) -> None:
    job_id, final, _meshy, _session = generate_and_run(
        GenerateRequest(name="Crate", prompt="crate"), tmp_path
    )
    assert jobs.wait(job_id, env=ENV, cwd=tmp_path, sleep=lambda _s: None) == final


# --- retexture -----------------------------------------------------------------------------


def test_retexture_exports_downloads_maps_and_applies_them(tmp_path: Path) -> None:
    session = FakeSession(collections=["Crate"])
    job_id, final, meshy = retexture_and_run(
        RetextureRequest(name="Crate", prompt="mossy stone"), tmp_path, session=session
    )
    assert final["state"] == "succeeded"
    result = final["result"]
    assert result["applied_to_session"] is True and result["warnings"] == []
    assert set(result["maps"]) == set(MAP_NAMES)
    for kind in MAP_NAMES:
        path = maps_dir(tmp_path, "Crate") / f"{kind}.png"
        assert path.read_bytes() == MAP_BYTES
        assert result["maps"][kind] == str(path)
    (body,) = _posts_by_path(meshy)["/openapi/v1/retexture"]
    assert body["model_url"].startswith("data:application/octet-stream;base64,")
    assert body["text_style_prompt"] == "mossy stone" and body["enable_pbr"] is True
    (applied,) = session.ops_named("apply_maps")
    assert applied["name"] == "Crate" and set(applied["maps"]) == set(MAP_NAMES)
    assert jobs.status(job_id, env=ENV, cwd=tmp_path)["state"] == "succeeded"


def test_retexture_from_a_style_image_sends_an_image_style(tmp_path: Path) -> None:
    session = FakeSession(collections=["Crate"])
    style = str(make_png(tmp_path / "moss.png"))
    _job, final, meshy = retexture_and_run(
        RetextureRequest(name="Crate", image_path=style), tmp_path, session=session
    )
    assert final["state"] == "succeeded"
    (body,) = _posts_by_path(meshy)["/openapi/v1/retexture"]
    assert body["image_style_url"].startswith("data:image/png;base64,")
    assert "text_style_prompt" not in body


def test_retexture_of_a_missing_collection_is_refused_and_leaves_no_job(tmp_path: Path) -> None:
    session = FakeSession()
    with pytest.raises(MeshyError) as info:
        start_retexture(RetextureRequest(name="Crate", prompt="x"), tmp_path, session=session)
    assert info.value.code == "meshy.collection_not_found"
    assert not _jobs_exist(tmp_path)


def test_retexture_with_both_inputs_is_refused_before_any_session_call(tmp_path: Path) -> None:
    session = FakeSession(collections=["Crate"])
    style = str(make_png(tmp_path / "moss.png"))
    with pytest.raises(MeshyError) as info:
        start_retexture(
            RetextureRequest(name="Crate", prompt="x", image_path=style),
            tmp_path,
            session=session,
        )
    assert info.value.code == "meshy.invalid_request"
    assert session.ops == []


def test_retexture_with_an_unreachable_session_leaves_no_job(tmp_path: Path) -> None:
    session = FakeSession(collections=["Crate"], down={"export_glb"})
    with pytest.raises(PipelineError) as info:
        start_retexture(RetextureRequest(name="Crate", prompt="x"), tmp_path, session=session)
    assert info.value.code == UNREACHABLE
    assert not _jobs_exist(tmp_path)


def test_retexture_keeps_the_maps_when_the_session_is_unreachable(tmp_path: Path) -> None:
    session = FakeSession(collections=["Crate"], down={"apply_maps"})
    _job, final, _meshy = retexture_and_run(
        RetextureRequest(name="Crate", prompt="mossy stone"), tmp_path, session=session
    )
    assert final["state"] == "succeeded"
    result = final["result"]
    assert result["applied_to_session"] is False
    assert result["warnings"][0]["code"] == UNREACHABLE
    assert (maps_dir(tmp_path, "Crate") / "base_color.png").read_bytes() == MAP_BYTES


def test_retexture_without_a_base_color_map_fails(tmp_path: Path) -> None:
    session = FakeSession(collections=["Crate"])
    _job, final, _meshy = retexture_and_run(
        RetextureRequest(name="Crate", prompt="mossy stone"),
        tmp_path,
        meshy=FakeMeshy(texture_maps=False),
        session=session,
    )
    assert final["state"] == "failed"
    assert final["error"]["code"] == "meshy.task_failed"
    assert session.ops_named("apply_maps") == []


def test_the_shared_export_writes_the_input_glb_for_retexture(tmp_path: Path) -> None:
    session = FakeSession(collections=["Crate"])
    job_id, spawn = start_retexture(
        RetextureRequest(name="Crate", prompt="x"), tmp_path, session=session
    )
    assert (spawn.jobs[0] / jobs.INPUT_NAME).read_bytes() == b"glTF-exported"
    assert job_id == spawn.jobs[0].name
