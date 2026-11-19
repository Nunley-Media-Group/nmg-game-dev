"""The project art style: the style.json reader, and texture manifests that record it while texture
prompts stay unchanged (#253 FR2, AC3)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from nmg_game_dev.texture import generate
from nmg_game_dev.texture.errors import TextureGenError
from nmg_game_dev.texture.style import project_style
from tests.texture_fakes import APPLE_SILICON_32GB, read_log, recording_spawn

STYLE = "hand-painted, warm palette"


def _write_style(root: Path, content: str) -> Path:
    path = root / "SourceArt" / "Art" / "style.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_an_absent_style_file_means_no_project_style(tmp_path: Path) -> None:
    assert project_style(tmp_path) is None


def test_the_style_sentence_is_read_and_stripped(tmp_path: Path) -> None:
    _write_style(tmp_path, json.dumps({"style": f"  {STYLE}  "}))
    assert project_style(tmp_path) == STYLE


@pytest.mark.parametrize(
    "content",
    [
        "{not json",
        json.dumps({"palette": "warm"}),
        json.dumps({"style": 3}),
        json.dumps({"style": "   "}),
        json.dumps(["hand-painted"]),
    ],
)
def test_an_invalid_style_file_raises_style_invalid(tmp_path: Path, content: str) -> None:
    _write_style(tmp_path, content)
    with pytest.raises(TextureGenError) as caught:
        project_style(tmp_path)
    assert caught.value.code == "art.style_invalid"
    assert "style" in caught.value.remediation


@pytest.fixture
def texture_env(tmp_path: Path, models: Path) -> dict[str, str]:
    return {"TEXTURE_GEN_MODELS_DIR": str(models), "CLAUDE_PROJECT_DIR": str(tmp_path / "project")}


def _texture_run(
    tmp_path: Path, env: dict[str, str], worker: Path, log: Path, captured: list[dict[str, Any]]
) -> generate.TextureResult:
    project = Path(env["CLAUDE_PROJECT_DIR"])
    project.mkdir(parents=True, exist_ok=True)
    return generate.run(
        generate.TextureRequest(prompt="burlap", seeds=[1], resolution=256),
        env=env,
        facts=APPLE_SILICON_32GB,
        spawn=recording_spawn(worker, log, captured),
        cwd=project,
        output_root_override=tmp_path / "out",
    )


def test_a_texture_manifest_records_the_project_style_and_its_prompt_is_unchanged(
    tmp_path: Path, texture_env: dict[str, str], worker: Path, log: Path
) -> None:
    _write_style(Path(texture_env["CLAUDE_PROJECT_DIR"]), json.dumps({"style": STYLE}))
    captured: list[dict[str, Any]] = []
    _texture_run(tmp_path, texture_env, worker, log, captured)

    manifest = json.loads((tmp_path / "out" / "burlap" / "textures.json").read_text("utf-8"))
    assert manifest["project_style"] == STYLE
    assert manifest["prompt"] == "burlap"
    sent = captured[0]["items"][0]["prompt"]
    assert sent == f"burlap, {generate.STYLE_SUFFIX}"
    assert STYLE not in sent


def test_a_texture_manifest_without_a_style_file_records_null(
    tmp_path: Path, texture_env: dict[str, str], worker: Path, log: Path
) -> None:
    captured: list[dict[str, Any]] = []
    _texture_run(tmp_path, texture_env, worker, log, captured)
    manifest = json.loads((tmp_path / "out" / "burlap" / "textures.json").read_text("utf-8"))
    assert manifest["project_style"] is None
    assert len(read_log(log)) == 2  # the worker ran once: start and exit


def test_an_invalid_style_file_stops_a_texture_run_before_any_worker(
    tmp_path: Path, texture_env: dict[str, str], worker: Path, log: Path
) -> None:
    _write_style(Path(texture_env["CLAUDE_PROJECT_DIR"]), "{broken")
    captured: list[dict[str, Any]] = []
    with pytest.raises(TextureGenError) as caught:
        _texture_run(tmp_path, texture_env, worker, log, captured)
    assert caught.value.code == "art.style_invalid"
    assert captured == [] and read_log(log) == []
