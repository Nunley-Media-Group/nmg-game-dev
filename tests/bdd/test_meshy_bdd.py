"""pytest-bdd bindings for meshy.feature: SCN001–SCN014 (#98).

The Meshy transport, the Blender session, detached spawning, and time are the fakes in
``tests/meshy_fakes.py``. Session behavior is covered by ``tests/blender/test_meshy_session.py``.
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
from nmg_game_dev.onboard.gitignore import ensure_gitignore_env
from nmg_game_dev.pipeline.errors import PipelineError
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
    _generate(ctx, GenerateRequest(name="Crate", prompt="crate"))


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
