"""2D art generation with the fake worker: validation, sizes, prompts, untiled takes, skipping, the
queued art job, and the batch item size fields (#253 AC1, AC2, AC4, FR1, FR3)."""

from __future__ import annotations

import json
import os
import subprocess
import types
from pathlib import Path
from typing import Any

import pytest
from PIL import Image as PILImage

from nmg_game_dev.texture import art, jobs
from nmg_game_dev.texture.art import KINDS, ArtRequest, full_prompt, size
from nmg_game_dev.texture.batch import Batch, ImageItem
from nmg_game_dev.texture.errors import TextureGenError
from nmg_game_dev.texture.registry import REGISTRY
from tests.texture_fakes import (
    APPLE_SILICON_32GB,
    fake_spawn,
    read_log,
    recording_spawn,
    save_png,
    synthetic_image,
)

STYLE = "hand-painted, warm palette"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    return root


@pytest.fixture
def art_env(project: Path, models: Path, out_root: Path) -> dict[str, str]:
    return {
        "TEXTURE_GEN_MODELS_DIR": str(models),
        "CLAUDE_PROJECT_DIR": str(project),
        "NMG_GAME_DEV_TEXTURE_DIR": str(out_root),
    }


def _request(**overrides: Any) -> ArtRequest:
    values: dict[str, Any] = {
        "kind": "icon",
        "name": "HealthPotion",
        "prompt": "red potion bottle",
        "seeds": [1, 2, 3],
    }
    values.update(overrides)
    return ArtRequest(**values)


def _run(
    request: ArtRequest,
    env: dict[str, str],
    project: Path,
    spawn: Any,
) -> art.ArtResult:
    return art.run(
        request,
        env=env,
        facts=APPLE_SILICON_32GB,
        spawn=spawn,
        cwd=project,
    )


def _raw(project: Path, kind: str, name: str) -> Path:
    return project / "SourceArt" / "Art" / "raw" / kind


# --- validation -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"kind": "sprite"},
        {"name": "healthPotion"},
        {"name": "Health Potion"},
        {"prompt": "   "},
        {"seeds": []},
        {"seeds": [1, 1]},
        {"aspect": "9:16"},
        {"backend": "both"},
        {"resolution": 1000},
        {"resolution": 128},
        {"resolution": 4096},
    ],
)
def test_a_bad_request_is_refused_as_invalid(overrides: dict[str, Any]) -> None:
    with pytest.raises(TextureGenError) as caught:
        art.validate_request(_request(**overrides))
    assert caught.value.code == "texture.invalid_request"
    assert caught.value.remediation


def test_an_unknown_backend_is_refused_with_the_allowlist() -> None:
    with pytest.raises(TextureGenError) as caught:
        art.validate_request(_request(backend="sdxl"))
    assert caught.value.code == "texture.unknown_backend"
    assert "z-image-turbo" in caught.value.remediation


def test_a_valid_request_resolves_to_its_pinned_backend() -> None:
    assert art.validate_request(_request(), REGISTRY) is REGISTRY["flux2-klein-4b"]


def test_painting_defaults_to_16_9_and_icons_and_ui_are_square() -> None:
    assert _request(kind="painting").resolved_aspect() == "16:9"
    assert _request().resolved_aspect() == "1:1"
    assert _request(kind="ui").resolved_aspect() == "1:1"


# --- sizes and prompts (AC2, AC3) ------------------------------------------------------------


@pytest.mark.parametrize(
    ("aspect", "resolution", "expected"),
    [
        ("1:1", 1024, (1024, 1024)),
        ("1:1", 256, (256, 256)),
        ("16:9", 1024, (1024, 576)),
        ("3:2", 1024, (1024, 704)),
    ],
)
def test_size_has_the_long_side_at_resolution_and_multiples_of_64(
    aspect: str, resolution: int, expected: tuple[int, int]
) -> None:
    width, height = size(aspect, resolution)
    assert (width, height) == expected
    assert width % 64 == 0 and height % 64 == 0
    ratio = {"1:1": 1.0, "16:9": 16 / 9, "3:2": 1.5}[aspect]
    assert abs((width / height) / ratio - 1) <= 0.05


@pytest.mark.parametrize("aspect", ["1:1", "16:9", "3:2"])
@pytest.mark.parametrize("resolution", range(art.MIN_RESOLUTION, art.MAX_RESOLUTION + 1, 64))
def test_every_accepted_resolution_keeps_the_aspect_within_5_percent(
    aspect: str, resolution: int
) -> None:
    request = _request(kind="painting", aspect=aspect, resolution=resolution)
    ratio = {"1:1": 1.0, "16:9": 16 / 9, "3:2": 1.5}[aspect]
    try:
        art.validate_request(request)
    except TextureGenError as error:
        assert error.code == "texture.invalid_request"
        assert "--resolution" in error.remediation
        return
    width, height = size(aspect, resolution)
    assert width == resolution
    assert width % 64 == 0 and height % 64 == 0
    assert abs((width / height) / ratio - 1) <= 0.05


@pytest.mark.parametrize(
    ("aspect", "resolution", "suggested"),
    [("16:9", 512, "448 or 576"), ("16:9", 256, "448 or 576"), ("3:2", 320, "384 or 576")],
)
def test_a_resolution_that_misses_the_aspect_names_the_nearest_valid_ones(
    aspect: str, resolution: int, suggested: str
) -> None:
    with pytest.raises(TextureGenError) as caught:
        art.validate_request(_request(kind="painting", aspect=aspect, resolution=resolution))
    assert caught.value.code == "texture.invalid_request"
    assert f"--resolution {suggested}" in caught.value.remediation


def test_full_prompt_adds_the_project_style_between_prompt_and_kind_style() -> None:
    request = _request()
    assert full_prompt(request, STYLE) == f"red potion bottle, {STYLE}, {KINDS['icon'].framing}"


def test_full_prompt_without_a_project_style_is_prompt_and_kind_style() -> None:
    assert full_prompt(_request(), None) == f"red potion bottle, {KINDS['icon'].framing}"


# --- generation (AC1, AC2, AC3, AC4) ----------------------------------------------------------


def test_art_takes_are_written_untiled_with_a_manifest_and_sheet(
    project: Path, art_env: dict[str, str], worker: Path, log: Path, tmp_path: Path
) -> None:
    source = save_png(synthetic_image(256, seed=4), tmp_path / "source.png")
    captured: list[dict[str, Any]] = []
    result = _run(
        _request(),
        art_env,
        project,
        recording_spawn(worker, log, captured, source_png=source),
    )
    raw = _raw(project, "icon", "HealthPotion")
    for seed in (1, 2, 3):
        take = raw / f"HealthPotion-{seed}.png"
        assert take.read_bytes() == source.read_bytes(), "the take must hold the worker's pixels"
    assert {path.name for path in raw.iterdir()} == {
        "HealthPotion-1.png",
        "HealthPotion-2.png",
        "HealthPotion-3.png",
        "HealthPotion.json",
        "HealthPotion_sheet.png",
    }
    manifest = json.loads((raw / "HealthPotion.json").read_text(encoding="utf-8"))
    assert manifest["prompt"] == "red potion bottle"
    assert manifest["backend"] == "flux2-klein-4b"
    assert manifest["repo"] == REGISTRY["flux2-klein-4b"].repo
    assert [take["seed"] for take in manifest["takes"]] == [1, 2, 3]
    assert manifest["skipped"] == []
    assert PILImage.open(raw / "HealthPotion_sheet.png").format == "PNG"
    assert [image.seed for image in result.images] == [1, 2, 3]
    # One worker process covers all three takes, so the model loads once.
    assert [event["event"] for event in read_log(log)] == ["start", "exit"]


def test_the_prompt_sent_to_the_worker_carries_the_kind_framing(
    project: Path, art_env: dict[str, str], worker: Path, log: Path
) -> None:
    captured: list[dict[str, Any]] = []
    _run(_request(seeds=[7]), art_env, project, recording_spawn(worker, log, captured))
    (item,) = captured[0]["items"]
    assert item["prompt"] == full_prompt(_request(), None)
    assert item["seed"] == 7
    assert item["path"].endswith("HealthPotion-7.png")


@pytest.mark.parametrize(
    ("kind", "aspect", "width", "height"),
    [
        ("icon", None, 1024, 1024),
        ("ui", None, 1024, 1024),
        ("painting", None, 1024, 576),
        ("painting", "3:2", 1024, 704),
        ("painting", "1:1", 1024, 1024),
    ],
)
def test_each_kind_writes_takes_at_its_framing_size(
    kind: str,
    aspect: str | None,
    width: int,
    height: int,
    project: Path,
    art_env: dict[str, str],
    worker: Path,
    log: Path,
) -> None:
    captured: list[dict[str, Any]] = []
    request = _request(kind=kind, name="Sample", seeds=[1], aspect=aspect)
    result = _run(request, art_env, project, recording_spawn(worker, log, captured))
    take = _raw(project, kind, "Sample") / "Sample-1.png"
    with PILImage.open(take) as image:
        assert image.size == (width, height)
    assert (result.width, result.height) == (width, height)
    (item,) = captured[0]["items"]
    assert (item["width"], item["height"]) == (width, height)
    assert KINDS[kind].framing in item["prompt"]


def test_a_project_style_is_added_to_art_prompts_and_recorded(
    project: Path, art_env: dict[str, str], worker: Path, log: Path
) -> None:
    style_file = project / "SourceArt" / "Art" / "style.json"
    style_file.parent.mkdir(parents=True)
    style_file.write_text(json.dumps({"style": STYLE}), encoding="utf-8")
    captured: list[dict[str, Any]] = []
    result = _run(_request(seeds=[1]), art_env, project, recording_spawn(worker, log, captured))
    assert captured[0]["items"][0]["prompt"] == full_prompt(_request(), STYLE)
    assert result.project_style == STYLE
    manifest = json.loads(
        (_raw(project, "icon", "HealthPotion") / "HealthPotion.json").read_text(encoding="utf-8")
    )
    assert manifest["project_style"] == STYLE


def test_without_a_style_file_the_prompt_has_only_the_kind_style(
    project: Path, art_env: dict[str, str], worker: Path, log: Path
) -> None:
    captured: list[dict[str, Any]] = []
    result = _run(_request(seeds=[1]), art_env, project, recording_spawn(worker, log, captured))
    assert result.project_style is None
    assert captured[0]["items"][0]["prompt"] == full_prompt(_request(), None)


def test_existing_takes_are_reported_as_skipped_and_not_regenerated(
    project: Path, art_env: dict[str, str], worker: Path, log: Path
) -> None:
    raw = _raw(project, "icon", "HealthPotion")
    raw.mkdir(parents=True)
    existing = save_png(synthetic_image(256, seed=9), raw / "HealthPotion-2.png")
    before = existing.read_bytes()
    captured: list[dict[str, Any]] = []
    result = _run(_request(), art_env, project, recording_spawn(worker, log, captured))
    assert result.skipped == (2,)
    assert [item["seed"] for item in captured[0]["items"]] == [1, 3]
    assert existing.read_bytes() == before
    manifest = json.loads((raw / "HealthPotion.json").read_text(encoding="utf-8"))
    assert manifest["skipped"] == [2]
    assert [take["seed"] for take in manifest["takes"]] == [1, 2, 3]


def test_when_every_seed_exists_no_worker_starts_and_no_model_is_needed(
    project: Path, worker: Path, log: Path, tmp_path: Path
) -> None:
    raw = _raw(project, "icon", "HealthPotion")
    raw.mkdir(parents=True)
    for seed in (1, 2):
        save_png(synthetic_image(256, seed=seed), raw / f"HealthPotion-{seed}.png")

    def refuse(batch_file: Path) -> subprocess.CompletedProcess[str]:
        raise AssertionError("no worker may start when every take exists")

    # No models folder is configured, so an availability check would fail: skipping it is the test.
    env = {"CLAUDE_PROJECT_DIR": str(project), "NMG_GAME_DEV_TEXTURE_DIR": str(tmp_path / "out")}
    result = art.run(
        _request(seeds=[1, 2]),
        env=env,
        facts=APPLE_SILICON_32GB,
        spawn=refuse,
        cwd=project,
    )
    assert result.skipped == (1, 2)
    assert result.images == ()
    assert result.contact_sheet.name == "HealthPotion_sheet.png"


def test_a_worker_that_writes_no_take_is_reported_as_a_worker_failure(
    project: Path, art_env: dict[str, str]
) -> None:
    def silent(batch_file: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    with pytest.raises(TextureGenError) as caught:
        _run(_request(seeds=[1]), art_env, project, silent)
    assert caught.value.code == "texture.worker_failed"


# --- batch items and the queued art job (FR1, FR3) --------------------------------------------


def test_an_image_item_emits_width_and_height_only_when_they_are_set(tmp_path: Path) -> None:
    square = ImageItem(index=0, prompt="p", seed=1, resolution=256, path=tmp_path / "a.png")
    assert "width" not in square.as_json() and "height" not in square.as_json()
    wide = ImageItem(
        index=1,
        prompt="p",
        seed=2,
        resolution=1024,
        path=tmp_path / "b.png",
        width=1024,
        height=576,
    )
    assert wide.as_json()["width"] == 1024 and wide.as_json()["height"] == 576
    spec = REGISTRY["z-image-turbo"]
    batch = Batch(spec=spec, weights=tmp_path, items=(wide,), batch_file=tmp_path / "x.json")
    assert batch.as_json()["items"][0]["height"] == 576


def test_an_art_job_is_queued_then_runs_to_succeeded(
    project: Path,
    art_env: dict[str, str],
    out_root: Path,
    worker: Path,
    log: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spawned: list[list[str]] = []

    class _Runner:
        pid = os.getpid()

    def popen(argv: list[str], **kwargs: object) -> _Runner:
        spawned.append(argv)
        return _Runner()

    monkeypatch.setattr(
        jobs, "subprocess", types.SimpleNamespace(Popen=popen, DEVNULL=subprocess.DEVNULL)
    )
    job_id = jobs.start(
        _request(seeds=[1, 2]),
        env=art_env,
        facts=APPLE_SILICON_32GB,
        cwd=project,
    )
    queued = jobs.status(job_id, env=art_env, cwd=project)
    assert queued["state"] == "queued" and queued["total"] == 2
    assert spawned and spawned[0][-2] == "run-queue"

    job_dir = out_root / ".jobs" / job_id
    final = jobs.run_job(
        job_dir,
        env=art_env,
        facts=APPLE_SILICON_32GB,
        spawn=fake_spawn(worker, log),
    )
    assert final["state"] == "succeeded"
    assert final["completed"] == final["total"] == 2
    assert [image["seed"] for image in final["result"]["images"]] == [1, 2]
    assert final["result"]["manifest"].endswith("HealthPotion.json")


def test_an_art_job_with_every_take_present_starts_no_backend_check(
    project: Path, out_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = _raw(project, "icon", "HealthPotion")
    raw.mkdir(parents=True)
    save_png(synthetic_image(256, seed=1), raw / "HealthPotion-1.png")

    class _Runner:
        pid = os.getpid()

    monkeypatch.setattr(
        jobs,
        "subprocess",
        types.SimpleNamespace(Popen=lambda *a, **k: _Runner(), DEVNULL=subprocess.DEVNULL),
    )
    # No models folder: only a job with missing takes checks the backend and dependencies.
    env = {"CLAUDE_PROJECT_DIR": str(project), "NMG_GAME_DEV_TEXTURE_DIR": str(out_root)}
    job_id = jobs.start(_request(seeds=[1]), env=env, facts=APPLE_SILICON_32GB, cwd=project)
    assert jobs.status(job_id, env=env, cwd=project)["total"] == 0


def test_the_art_job_refuses_to_start_when_a_missing_take_has_no_model(
    project: Path, out_root: Path
) -> None:
    env = {"CLAUDE_PROJECT_DIR": str(project), "NMG_GAME_DEV_TEXTURE_DIR": str(out_root)}
    with pytest.raises(TextureGenError) as caught:
        jobs.start(_request(seeds=[1]), env=env, facts=APPLE_SILICON_32GB, cwd=project)
    assert caught.value.code == "texture.model_not_installed"
    assert not (out_root / ".jobs").exists(), "a refused job must not be queued"
