"""pytest-bdd bindings for meshy.feature: SCN001–SCN014 (#98), SCN015 (#105), SCN016–SCN019 (#106).

The Meshy transport, the Blender session, detached spawning, and time are the fakes in
``tests/meshy_fakes.py``. Session behavior, including the #105 normalization and the #106 arm raise,
is covered by ``tests/blender/test_meshy_session.py``. The #106 geometry needs bpy, so its steps
check that the Blender suite defines the test that runs them; the neutral-pose step runs
``rig_core``'s check on the geometry in ``tests/meshy_arm_geometry.py``.
"""

from __future__ import annotations

import base64
import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import types
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from nmg_game_dev.meshy import __main__ as cli
from nmg_game_dev.meshy import config, jobs
from nmg_game_dev.meshy.client import MeshyClient
from nmg_game_dev.meshy.paths import glb_path, jobs_root, maps_dir
from nmg_game_dev.meshy.request import GenerateRequest, RetextureRequest
from nmg_game_dev.meshy.session import MeshySession
from nmg_game_dev.onboard.gitignore import ensure_gitignore_env
from nmg_game_dev.pipeline.errors import PipelineError
from tests.meshy_arm_geometry import (
    bounding_box,
    drop_deg_from,
    landmarks,
    raise_arm_landmarks,
    side_pivot,
)
from tests.meshy_fakes import (
    ENV,
    GLB_BYTES,
    MAP_NAMES,
    TEST_KEY,
    FakeClock,
    FakeMeshy,
    FakeSession,
    RecordingSpawn,
    all_job_text,
    generate_and_run,
    make_png,
    retexture_and_run,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVER_FILE = REPO_ROOT / "mcp-servers" / "meshy" / "src" / "meshy_mcp" / "server.py"
RIG_CORE_DIR = REPO_ROOT / "plugins" / "nmg-game-dev-blender-addon" / "rig_core"
BLENDER_TESTS = REPO_ROOT / "tests" / "blender" / "test_meshy_session.py"
ENDPOINTS = {
    "image-to-3D": "/openapi/v1/image-to-3d",
    "multi-image-to-3D": "/openapi/v1/multi-image-to-3d",
}
FAILURES: dict[str, dict[str, Any]] = {
    "answers 401": {"create_status": 401},
    "answers 402": {"create_status": 402},
    "answers 429": {"create_status": 429},
    "ends the task FAILED": {"task_states": ["FAILED"], "task_error": "prompt refused"},
    "ends the task CANCELED": {"task_states": ["CANCELED"], "task_error": "cancelled"},
    "ends the task EXPIRED": {"task_states": ["EXPIRED"], "task_error": "expired"},
}

scenarios("meshy.feature")


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.setenv("MESHY_API_KEY", TEST_KEY)
    return {
        "project": tmp_path,
        "env": dict(ENV),
        "session": FakeSession(),
        "meshy": FakeMeshy(),
        "clock": FakeClock(),
        "images": [],
        "job_id": None,
        "final": None,
        "error": None,
        "text": None,
        "spawn": RecordingSpawn(),
        "monkeypatch": monkeypatch,
    }


def _images(ctx: dict[str, Any], count: int) -> tuple[str, ...]:
    paths = [make_png(Path(ctx["project"]) / f"ref{index}.png") for index in range(count)]
    ctx["images"] = [str(path) for path in paths]
    return tuple(ctx["images"])


def _generate(ctx: dict[str, Any], request: GenerateRequest) -> None:
    ctx["meshy"] = ctx["meshy"] if ctx["meshy"] is not None else FakeMeshy()
    job_id, final, meshy, session = generate_and_run(
        request,
        ctx["project"],
        meshy=ctx["meshy"],
        session=ctx["session"],
        env=ctx["env"],
    )
    ctx.update(job_id=job_id, final=final, meshy=meshy, session=session)


def _posts(ctx: dict[str, Any], path: str) -> list[dict[str, Any]]:
    return [body for sent_path, body in ctx["meshy"].posts() if sent_path == path]


def _refused(ctx: dict[str, Any], call: Any) -> None:
    try:
        call()
    except PipelineError as error:
        ctx["error"] = error
        return
    raise AssertionError("the call was expected to be refused")


# --- Givens ---------------------------------------------------------------------------------


@given('a Meshy API key is available and a reachable session with no "Crate" collection')
@given("a Meshy API key is available")
def _key_available() -> None:
    return None


@given(parsers.re(r"a Meshy API key is available and (?P<count>\d+) local reference images?"))
def _reference_images(ctx: dict[str, Any], count: str) -> None:
    _images(ctx, int(count))


@given('a Meshy API key is available and the session has collection "Crate" with mesh "SM_Crate"')
def _crate_exists(ctx: dict[str, Any]) -> None:
    ctx["session"] = FakeSession(collections=["Crate"])


@given("a generation job whose Meshy task succeeded")
@given("a Meshy job in progress")
@given("a Meshy generate job whose session import succeeds")
def _job_in_progress() -> None:
    return None


@given("the Blender session is unreachable at import time")
def _unreachable_import(ctx: dict[str, Any]) -> None:
    ctx["session"] = FakeSession(down={"import_glb"})


@given('MESHY_API_KEY is unset and the project .env contains "MESHY_API_KEY=key-from-dotenv"')
def _dotenv_key(ctx: dict[str, Any]) -> None:
    (ctx["project"] / ".env").write_text("MESHY_API_KEY=key-from-dotenv\n", encoding="utf-8")
    ctx["env"] = {}


@given("MESHY_API_KEY is unset and the project has no .env")
def _no_key(ctx: dict[str, Any]) -> None:
    ctx["env"] = {}


@given('a consumer project whose .gitignore lacks a ".env" entry')
def _gitignore_without_env(ctx: dict[str, Any]) -> None:
    (ctx["project"] / ".gitignore").write_text("node_modules/\n", encoding="utf-8")


@given("the repository")
@given("the same generate inputs")
def _repository() -> None:
    return None


# --- Whens ----------------------------------------------------------------------------------


@when(
    'the agent calls generate_model with name "Crate" and prompt "weathered wooden crate" and '
    "polls the job to completion"
)
def _text_generate(ctx: dict[str, Any]) -> None:
    _generate(ctx, GenerateRequest(name="Crate", prompt="weathered wooden crate"))


@when('the agent calls generate_model with name "Lamppost" and those image paths')
def _images_generate(ctx: dict[str, Any]) -> None:
    _generate(ctx, GenerateRequest(name="Lamppost", image_paths=tuple(ctx["images"])))


@when(
    'the agent calls generate_model with name "Ghost", those image paths, and prompt "pale '
    'translucent cloth"'
)
def _images_and_prompt(ctx: dict[str, Any]) -> None:
    _generate(
        ctx,
        GenerateRequest(
            name="Ghost", image_paths=tuple(ctx["images"]), prompt="pale translucent cloth"
        ),
    )


@when('the agent calls generate_model with name "Ghost", that image path, and pose "a-pose"')
def _pose_generate(ctx: dict[str, Any]) -> None:
    _generate(ctx, GenerateRequest(name="Ghost", image_paths=tuple(ctx["images"]), pose="a-pose"))


@when('the agent calls generate_model with name "Crate", a prompt, and texture false')
def _untextured(ctx: dict[str, Any]) -> None:
    _generate(ctx, GenerateRequest(name="Crate", prompt="crate", texture=False))


@when("the job finishes")
def _job_finishes(ctx: dict[str, Any]) -> None:
    _generate(ctx, GenerateRequest(name="Crate", prompt="crate", pose=ctx.get("pose")))


@when(
    'the agent calls retexture_model with name "Crate" and prompt "mossy stone" and polls it '
    "to completion"
)
def _retexture(ctx: dict[str, Any]) -> None:
    job_id, final, meshy = retexture_and_run(
        RetextureRequest(name="Crate", prompt="mossy stone"),
        ctx["project"],
        session=ctx["session"],
        env=ctx["env"],
    )
    ctx.update(job_id=job_id, final=final, meshy=meshy)


@when("a Meshy request is sent")
def _send_request(ctx: dict[str, Any]) -> None:
    key = config.api_key(ctx["env"], ctx["project"])
    ctx["meshy"] = FakeMeshy()
    MeshyClient(key, ctx["meshy"]).create_text_preview("crate")


@when('the agent calls generate_model with name "Crate" and a prompt')
def _generate_without_key(ctx: dict[str, Any]) -> None:
    _refused(
        ctx,
        lambda: jobs.start_generate(
            GenerateRequest(name="Crate", prompt="crate"),
            env=ctx["env"],
            cwd=ctx["project"],
            session=ctx["session"],
            spawn=ctx["spawn"],
        ),
    )
    ctx["meshy"] = ctx["meshy"] if ctx["meshy"] is not None else FakeMeshy()


@when(parsers.parse("Meshy {failure}"))
def _meshy_failure(ctx: dict[str, Any], failure: str) -> None:
    ctx["meshy"] = FakeMeshy(**FAILURES[failure])
    _generate(ctx, GenerateRequest(name="Crate", prompt="crate"))


@when(parsers.parse("the agent sends {request}"))
def _invalid_request(ctx: dict[str, Any], request: str) -> None:
    project, env, session = ctx["project"], ctx["env"], ctx["session"]
    meshy = FakeMeshy()
    ctx["meshy"] = meshy

    def start() -> str:
        if request == 'generate_model with name "crate"':
            return jobs.start_generate(
                GenerateRequest(name="crate", prompt="x"),
                env=env,
                cwd=project,
                session=session,
                spawn=ctx["spawn"],
            )
        if request == "generate_model with neither a prompt nor images":
            return jobs.start_generate(
                GenerateRequest(name="Crate"),
                env=env,
                cwd=project,
                session=session,
                spawn=ctx["spawn"],
            )
        if request == "generate_model with five images":
            images = _images(ctx, 5)
            return jobs.start_generate(
                GenerateRequest(name="Crate", image_paths=images),
                env=env,
                cwd=project,
                session=session,
                spawn=ctx["spawn"],
            )
        if request == 'generate_model with a ".gif" image':
            gif = project / "ref.gif"
            gif.write_bytes(b"GIF89a")
            return jobs.start_generate(
                GenerateRequest(name="Crate", image_paths=(str(gif),)),
                env=env,
                cwd=project,
                session=session,
                spawn=ctx["spawn"],
            )
        if request == "generate_model with an image path that does not exist":
            return jobs.start_generate(
                GenerateRequest(name="Crate", image_paths=(str(project / "gone.png"),)),
                env=env,
                cwd=project,
                session=session,
                spawn=ctx["spawn"],
            )
        if request == "generate_model with images and an 801-character prompt":
            images = _images(ctx, 1)
            return jobs.start_generate(
                GenerateRequest(name="Crate", prompt="a" * 801, image_paths=images),
                env=env,
                cwd=project,
                session=session,
                spawn=ctx["spawn"],
            )
        if request == "generate_model with images, a prompt, and texture false":
            images = _images(ctx, 1)
            return jobs.start_generate(
                GenerateRequest(name="Crate", prompt="x", image_paths=images, texture=False),
                env=env,
                cwd=project,
                session=session,
                spawn=ctx["spawn"],
            )
        if request == 'generate_model with pose "sitting"':
            return jobs.start_generate(
                GenerateRequest(name="Crate", prompt="x", pose="sitting"),
                env=env,
                cwd=project,
                session=session,
                spawn=ctx["spawn"],
            )
        if request == "retexture_model with both a prompt and an image path":
            style = _images(ctx, 1)[0]
            return jobs.start_retexture(
                RetextureRequest(name="Crate", prompt="x", image_path=style),
                env=env,
                cwd=project,
                session=session,
                spawn=ctx["spawn"],
            )
        if request == 'generate_model for an existing "Crate" collection':
            ctx["session"] = FakeSession(collections=["Crate"])
            return jobs.start_generate(
                GenerateRequest(name="Crate", prompt="x"),
                env=env,
                cwd=project,
                session=ctx["session"],
                spawn=ctx["spawn"],
            )
        if request == 'retexture_model for a missing "Crate" collection':
            return jobs.start_retexture(
                RetextureRequest(name="Crate", prompt="x"),
                env=env,
                cwd=project,
                session=session,
                spawn=ctx["spawn"],
            )
        raise AssertionError(f"no binding for request {request!r}")

    _refused(ctx, start)


@when('the developer runs "python -m nmg_game_dev.meshy generate" and then "status" for the job')
def _cli_generate_and_status(ctx: dict[str, Any]) -> None:
    monkeypatch = ctx["monkeypatch"]
    monkeypatch.chdir(ctx["project"])
    monkeypatch.setattr(jobs, "BlenderSessionClient", lambda: FakeSession())
    monkeypatch.setattr(jobs, "default_spawn", ctx["spawn"])
    generated = io.StringIO()
    with contextlib.redirect_stdout(generated):
        assert cli.main(["generate", "--name", "Crate", "--prompt", "crate"]) == 0
    job_id = json.loads(generated.getvalue())["job_id"]
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
        assert cli.main(["status", job_id]) == 0
    ctx["job_id"] = job_id
    ctx["text"] = printed.getvalue()


@when("onboarding runs twice")
def _onboard_twice(ctx: dict[str, Any]) -> None:
    target = ctx["project"] / ".gitignore"
    ctx["results"] = [
        ensure_gitignore_env("gitignore_env", target),
        ensure_gitignore_env("gitignore_env", target),
    ]


@when("the guard tests and scripts/validate-mcp-tools.py run")
def _guards(ctx: dict[str, Any]) -> None:
    validator = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "validate-mcp-tools.py")],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )
    assert validator.returncode == 0, validator.stdout + validator.stderr
    ctx["mcp_text"] = (REPO_ROOT / ".mcp.json").read_text(encoding="utf-8")
    ctx["mcp_json"] = json.loads(ctx["mcp_text"])


# --- Thens ----------------------------------------------------------------------------------


@then(
    'Meshy text-to-3D receives a "preview" request and then a "refine" request with enable_pbr true'
)
def _text_requests(ctx: dict[str, Any]) -> None:
    preview, refine = _posts(ctx, "/openapi/v2/text-to-3d")
    assert preview["mode"] == "preview"
    assert refine["mode"] == "refine" and refine["enable_pbr"] is True


@then(parsers.parse('the job reports "{state}" with loaded_into_session {loaded} and the GLB path'))
def _job_loaded(ctx: dict[str, Any], state: str, loaded: str) -> None:
    assert ctx["final"]["state"] == state
    assert ctx["final"]["result"]["loaded_into_session"] is (loaded == "true")
    assert ctx["final"]["result"]["glb_path"].endswith("SourceArt/Meshy/Crate/Crate.glb")


@then(parsers.parse('"{relative}" exists'))
def _file_exists(ctx: dict[str, Any], relative: str) -> None:
    assert (ctx["project"] / relative).is_file()
    assert (ctx["project"] / relative).read_bytes() == GLB_BYTES


@then(
    parsers.re(
        r'the session has collection "(?P<name>[^"]+)" with mesh "(?P<mesh>[^"]+)"'
        r'(?: and material "(?P<material>[^"]+)")?$'
    )
)
def _session_has(ctx: dict[str, Any], name: str, mesh: str, material: str | None) -> None:
    collection = ctx["session"].collections[name]
    assert collection["mesh"] == mesh
    if material is not None:
        assert collection["material"] == material


@then(
    parsers.parse("Meshy {endpoint} receives the images as base64 data URIs with their MIME types")
)
def _images_as_data_uris(ctx: dict[str, Any], endpoint: str) -> None:
    (body,) = _posts(ctx, ENDPOINTS[endpoint])
    key = "image_url" if endpoint == "image-to-3D" else "image_urls"
    uris = [body[key]] if key == "image_url" else body[key]
    expected = ["image/png"] * len(ctx["images"])
    assert [uri.split(";", 1)[0].removeprefix("data:") for uri in uris] == expected
    for uri, path in zip(uris, ctx["images"], strict=True):
        assert base64.b64decode(uri.split(",", 1)[1]) == Path(path).read_bytes()


@then("no texture_prompt is sent")
def _no_texture_prompt(ctx: dict[str, Any]) -> None:
    for _path, body in ctx["meshy"].posts():
        assert "texture_prompt" not in body


@then(
    parsers.parse(
        'Meshy multi-image-to-3D receives the images and texture_prompt "{prompt}" in one request'
    )
)
def _texture_prompt(ctx: dict[str, Any], prompt: str) -> None:
    (body,) = _posts(ctx, ENDPOINTS["multi-image-to-3D"])
    assert body["texture_prompt"] == prompt
    assert len(body["image_urls"]) == len(ctx["images"])


@then(parsers.parse('the image-to-3D request carries pose_mode "{pose}"'))
def _pose_mode(ctx: dict[str, Any], pose: str) -> None:
    (body,) = _posts(ctx, ENDPOINTS["image-to-3D"])
    assert body["pose_mode"] == pose


@then(parsers.parse('a generate_model call for "{name}" without pose sends no pose_mode'))
def _no_pose_mode(ctx: dict[str, Any], name: str) -> None:
    plain = FakeMeshy()
    generate_and_run(
        GenerateRequest(name=name, image_paths=tuple(ctx["images"])),
        ctx["project"] / "plain",
        meshy=plain,
        session=FakeSession(),
        env=ctx["env"],
    )
    for _path, body in plain.posts():
        assert "pose_mode" not in body


@then('exactly one text-to-3D request is sent, with mode "preview"')
def _single_preview(ctx: dict[str, Any]) -> None:
    posts = _posts(ctx, "/openapi/v2/text-to-3d")
    assert [body["mode"] for body in posts] == ["preview"]


@then(parsers.parse('the untextured mesh lands in the session as "{mesh}"'))
def _untextured_mesh(ctx: dict[str, Any], mesh: str) -> None:
    assert ctx["session"].collections["Crate"]["mesh"] == mesh


@then(parsers.parse('it reports "{state}" with loaded_into_session false and a warning "{code}"'))
def _unreachable_warning(ctx: dict[str, Any], state: str, code: str) -> None:
    assert ctx["final"]["state"] == state
    assert ctx["final"]["result"]["loaded_into_session"] is False
    assert ctx["final"]["result"]["warnings"][0]["code"] == code


@then("the GLB stays on disk")
def _glb_kept(ctx: dict[str, Any]) -> None:
    assert glb_path(ctx["project"], "Crate").read_bytes() == GLB_BYTES


@then("the import result and the job result carry merged_vertices and origin_offset")
def _normalization_reported(ctx: dict[str, Any]) -> None:
    imported = ctx["session"].import_results["Crate"]
    job_result = ctx["final"]["result"]
    for key in ("merged_vertices", "origin_offset"):
        assert key in imported and key in job_result
        assert job_result[key] == imported[key]


@then("Meshy retexture receives the exported collection as a GLB data URI")
def _retexture_input(ctx: dict[str, Any]) -> None:
    (body,) = _posts(ctx, "/openapi/v1/retexture")
    assert body["model_url"].startswith("data:application/octet-stream;base64,")


@then(
    "base color, normal, roughness, and metallic maps are saved under "
    '"SourceArt/Textures/Meshy/Crate/"'
)
def _maps_saved(ctx: dict[str, Any]) -> None:
    for kind in MAP_NAMES:
        assert (maps_dir(ctx["project"], "Crate") / f"{kind}.png").is_file()


@then("the job reports applied_to_session true with the map paths")
def _applied(ctx: dict[str, Any]) -> None:
    result = ctx["final"]["result"]
    assert result["applied_to_session"] is True
    assert set(result["maps"]) == set(MAP_NAMES)


@then(parsers.parse('it carries "Authorization: Bearer {key}"'))
def _carries_key(ctx: dict[str, Any], key: str) -> None:
    assert ctx["meshy"].sent[-1].headers["Authorization"] == f"Bearer {key}"


@then(
    parsers.parse(
        'with MESHY_API_KEY "{key}" in the environment the next request carries "Authorization: '
        'Bearer {bearer}"'
    )
)
def _env_overrides(ctx: dict[str, Any], key: str, bearer: str) -> None:
    env = {"MESHY_API_KEY": key}
    resolved = config.api_key(env, ctx["project"])
    meshy = FakeMeshy()
    MeshyClient(resolved, meshy).create_text_preview("crate")
    assert meshy.sent[-1].headers["Authorization"] == f"Bearer {bearer}"


@then(parsers.parse('it returns error "{code}" with a remediation naming "{first}" and "{second}"'))
def _missing_key(ctx: dict[str, Any], code: str, first: str, second: str) -> None:
    error = ctx["error"]
    assert error.code == code
    assert first in error.remediation and second in error.remediation
    assert len(ctx["meshy"].sent) == 0
    assert not jobs_root(ctx["project"]).exists() or not any(jobs_root(ctx["project"]).iterdir())


@then("no HTTP request was sent and no job directory exists")
def _nothing_sent(ctx: dict[str, Any]) -> None:
    assert len(ctx["meshy"].sent) == 0
    assert not jobs_root(ctx["project"]).exists() or not any(jobs_root(ctx["project"]).iterdir())


@then(parsers.parse('the job reports "{state}" with code "{code}" and a remediation'))
def _job_failed_with(ctx: dict[str, Any], state: str, code: str) -> None:
    assert ctx["final"]["state"] == state
    assert ctx["final"]["error"]["code"] == code
    assert ctx["final"]["error"]["remediation"]


@then("the API key appears in no job file and no error message")
def _no_key_anywhere(ctx: dict[str, Any]) -> None:
    job_dir = jobs_root(ctx["project"]) / ctx["job_id"]
    assert TEST_KEY not in all_job_text(job_dir)
    assert TEST_KEY not in json.dumps(ctx["final"])


@then(parsers.parse('it returns "{code}" with a remediation'))
def _refused_with(ctx: dict[str, Any], code: str) -> None:
    assert ctx["error"].code == code
    assert ctx["error"].remediation


@then("no Meshy request was sent")
def _no_meshy_request(ctx: dict[str, Any]) -> None:
    assert len(ctx["meshy"].sent) == 0


@then("the CLI prints the same status JSON that get_meshy_job returns for that job")
def _cli_matches_server(ctx: dict[str, Any]) -> None:
    spec = importlib.util.spec_from_file_location("_meshy_bdd_server", SERVER_FILE)
    assert spec is not None and spec.loader is not None
    src = str(SERVER_FILE.parents[1])
    if src not in sys.path:
        sys.path.insert(0, src)
    module: types.ModuleType = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert json.loads(ctx["text"]) == module.get_meshy_job(ctx["job_id"])


@then("pipeline and finalize sources contain no Meshy code")
def _pipeline_clean(ctx: dict[str, Any]) -> None:
    for folder in ("pipeline", "finalize"):
        for path in (REPO_ROOT / "src" / "nmg_game_dev" / folder).rglob("*.py"):
            assert "meshy" not in path.read_text(encoding="utf-8").lower(), path


@then(
    '.mcp.json declares a "meshy" uv run server with no MESHY_API_KEY text and the other four '
    "entries unchanged"
)
def _mcp_entries(ctx: dict[str, Any]) -> None:
    servers = ctx["mcp_json"]["mcpServers"]
    assert servers["meshy"]["command"] == "uv"
    assert "run" in servers["meshy"]["args"]
    assert "MESHY_API_KEY" not in ctx["mcp_text"]
    assert {"blender", "unreal", "finalize", "texture-gen"} <= set(servers)


@then("the generate_model description limits pose to characters and creatures with limbs")
def _pose_description(ctx: dict[str, Any]) -> None:
    manifest = json.loads(
        (REPO_ROOT / "mcp-servers" / "meshy" / "tools.json").read_text(encoding="utf-8")
    )
    description = next(
        tool["description"] for tool in manifest["tools"] if tool["name"] == "generate_model"
    )
    assert "characters and creatures with limbs" in description


@then("product steering lists Meshy as an optional opt-in paid source")
def _steering(ctx: dict[str, Any]) -> None:
    text = (REPO_ROOT / "steering" / "snippets" / "project-product.md").read_text(encoding="utf-8")
    assert "Optional Meshy source" in text and "opt-in and paid" in text


@then('the consumer .gitignore contains exactly one ".env" line')
def _one_env_line(ctx: dict[str, Any]) -> None:
    lines = (ctx["project"] / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert lines.count(".env") == 1


@then(parsers.parse('the "gitignore_env" step reports "{first}" then "{second}"'))
def _gitignore_steps(ctx: dict[str, Any], first: str, second: str) -> None:
    assert [result.status for result in ctx["results"]] == [first, second]


@then('no ".env" file was created')
def _no_env_file(ctx: dict[str, Any]) -> None:
    assert not (ctx["project"] / ".env").exists()


# --- #106: A-pose arms are raised to rig_humanoid's limit (SCN016–SCN019) -------------------------


def _rig_landmarks() -> types.ModuleType:
    """Load ``rig_core.landmarks`` by file, since the add-on's package imports bpy."""
    package = "_nmg_rig_core"
    if package not in sys.modules:
        stub = types.ModuleType(package)
        stub.__path__ = [str(RIG_CORE_DIR)]
        sys.modules[package] = stub
    return importlib.import_module(f"{package}.landmarks")


def _blender_covers(test_name: str) -> None:
    """Check that the Blender suite defines ``test_name``, the test that runs a bpy-only step."""
    assert f"def {test_name}(" in BLENDER_TESTS.read_text(encoding="utf-8")


def _import_hero(ctx: dict[str, Any], pose: str | None) -> dict[str, Any]:
    return MeshySession(FakeSession()).import_glb("Hero", Path(ctx["glb"]), pose=pose)


def _rotations(arm_raise: dict[str, Any]) -> dict[str, float]:
    return {side: float(report["rotation_deg"]) for side, report in arm_raise.items()}


@given("a GLB of a 1.8 m box humanoid with both arms dropped 55 degrees")
def _humanoid_55(ctx: dict[str, Any]) -> None:
    ctx.update(glb=str(ctx["project"] / "hero.glb"), drop_deg=55.0)


@given("a GLB of the box humanoid")
def _box_humanoid(ctx: dict[str, Any]) -> None:
    ctx.update(glb=str(ctx["project"] / "hero.glb"), drop_deg=55.0)


@given("a Meshy generate job with pose a-pose whose session import succeeds")
def _a_pose_job(ctx: dict[str, Any]) -> None:
    ctx["pose"] = "a-pose"


@given(
    "the raised Hero with shoulder landmarks at the pivots and wrist landmarks on the raised arms"
)
def _raised_hero(ctx: dict[str, Any]) -> None:
    ctx.update(glb=str(ctx["project"] / "hero.glb"), drop_deg=55.0)
    ctx["import"] = _import_hero(ctx, "a-pose")


@when('import_glb imports it as "Hero" with pose a-pose')
def _import_a_pose(ctx: dict[str, Any]) -> None:
    ctx["import"] = _import_hero(ctx, "a-pose")


@when("import_glb imports it with pose t-pose, with no pose, or as an A-pose dropped 45 degrees")
def _import_compliant(ctx: dict[str, Any]) -> None:
    # The A-pose dropped 45 degrees is not reachable here: the fake answers every a-pose the same
    # way. Tests/blender/test_meshy_session.py runs that case on real geometry.
    ctx["imports"] = {
        "t-pose": _import_hero(ctx, "t-pose"),
        "no pose": _import_hero(ctx, None),
    }


@when("rig_core.landmarks.validate runs for a humanoid")
def _validate_raised(ctx: dict[str, Any]) -> None:
    validate = _rig_landmarks().validate
    drop = float(ctx["drop_deg"])
    # The control: unraised landmarks at 55 degrees must fail the check with the code under test.
    ctx["unraised_failure"] = validate("humanoid", landmarks(drop), bounding_box(drop))
    arm_raise = ctx["import"]["arm_raise"]
    raised = raise_arm_landmarks(landmarks(drop), _rotations(arm_raise))
    raised_drop = float(arm_raise["left"]["drop_after_deg"])
    ctx["failure"] = validate("humanoid", raised, bounding_box(raised_drop))


@then("each arm's drop is 48 degrees within 0.5")
def _arms_drop_to_48(ctx: dict[str, Any]) -> None:
    arm_raise = ctx["import"]["arm_raise"]
    points = raise_arm_landmarks(landmarks(ctx["drop_deg"]), _rotations(arm_raise))
    for suffix, sign, side in (("l", 1.0, "left"), ("r", -1.0, "right")):
        report = arm_raise[side]
        assert report["drop_before_deg"] == pytest.approx(ctx["drop_deg"], abs=0.05)
        assert report["drop_after_deg"] == pytest.approx(48.0, abs=0.5)
        drop = drop_deg_from(side_pivot(sign), points[f"hand_tip_{suffix}"])
        assert drop == pytest.approx(48.0, abs=0.5)


@then("torso-midline and leg vertices have not moved")
def _midline_and_legs_still() -> None:
    _blender_covers("test_a_raise_keeps_the_torso_midline_and_legs_still")


@then("vertex count, face count, and connectivity are unchanged with no flipped faces")
def _counts_and_normals_kept() -> None:
    _blender_covers("test_a_raise_keeps_counts_connectivity_and_normals")


@then("no vertex moves")
def _no_vertex_moves(ctx: dict[str, Any]) -> None:
    for name, result in ctx["imports"].items():
        assert result["arm_raise"] is None, name
    _blender_covers("test_compliant_or_non_a_pose_imports_move_no_vertex")


@then(
    "the job result carries arm_raise with left and right drop_before_deg, drop_after_deg, "
    "and rotation_deg"
)
def _job_carries_arm_raise(ctx: dict[str, Any]) -> None:
    (imported,) = ctx["session"].ops_named("import_glb")
    assert imported["pose"] == "a-pose"
    arm_raise = ctx["final"]["result"]["arm_raise"]
    assert set(arm_raise) == {"left", "right"}
    for report in arm_raise.values():
        assert set(report) == {"drop_before_deg", "drop_after_deg", "rotation_deg"}


@then("it does not report rig.pose_not_neutral")
def _not_pose_neutral(ctx: dict[str, Any]) -> None:
    control = ctx["unraised_failure"]
    assert control is not None and control["code"] == "rig.pose_not_neutral"
    assert ctx["failure"] is None, ctx["failure"]
