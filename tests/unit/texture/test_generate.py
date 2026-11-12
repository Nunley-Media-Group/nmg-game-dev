"""The generation flow end to end with the fake worker: outputs, maps, both, and validation (#7
AC17-AC20)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from nmg_game_dev.texture.contact_sheet import ContactSheet
from nmg_game_dev.texture.errors import TextureGenError
from nmg_game_dev.texture.generate import (
    TextureRequest,
    TextureResult,
    backend_status,
    batch_from_items,
    request_as_json,
    request_from_json,
    run,
    run_batch,
    validate_batch,
    validate_request,
)
from nmg_game_dev.texture.hardware import HardwareFacts
from nmg_game_dev.texture.registry import REGISTRY
from tests.texture_fakes import (
    APPLE_SILICON_32GB,
    fake_spawn,
    make_models,
    read_log,
    save_png,
    synthetic_image,
)


def _run(
    request: TextureRequest,
    worker: Path,
    log: Path,
    env: dict[str, str],
    out_root: Path,
    facts: HardwareFacts = APPLE_SILICON_32GB,
) -> TextureResult:
    return run(
        request,
        env=env,
        facts=facts,
        spawn=fake_spawn(worker, log),
        cwd=out_root.parent,
        output_root_override=out_root,
    )


def test_single_backend_writes_seamless_pngs_and_manifest(
    worker: Path, log: Path, env: dict[str, str], out_root: Path
) -> None:
    request = TextureRequest(
        prompt="burlap weave",
        backend="z-image-turbo",
        seeds=[7, 8],
        resolution=256,
        name="Burlap Weave",
    )
    result = _run(request, worker, log, env, out_root)

    assert result.name == "burlap-weave"
    assert [r.path.name for r in result.images] == [
        "z-image-turbo_7_256.png",
        "z-image-turbo_8_256.png",
    ]
    assert all(r.path.exists() and r.maps == {} for r in result.images)
    assert result.compare is None and result.skipped == ()
    manifest = json.loads(result.manifest.read_text())
    assert list(manifest) == sorted(manifest)
    assert manifest["prompt"] == "burlap weave"
    assert manifest["images"][0]["backend"] == "z-image-turbo"
    assert manifest["images"][0]["steps"] == REGISTRY["z-image-turbo"].default_steps
    assert manifest["images"][0]["repo"] == "Tongyi-MAI/Z-Image-Turbo"
    assert manifest["images"][0]["seconds"] >= 0
    assert "seamless tileable texture" in manifest["style_suffix"]
    assert (out_root / "burlap-weave" / "textures.json").exists()
    assert not (out_root / "burlap-weave" / ".batch").exists()


def test_one_load_per_batch_and_one_png_per_request(
    worker: Path, log: Path, env: dict[str, str], out_root: Path
) -> None:
    request = TextureRequest(
        prompt="stone", backend="flux2-klein-4b", seeds=[1, 2, 3], resolution=256, name="s"
    )
    _run(request, worker, log, env, out_root)
    events = read_log(log)
    assert [e["event"] for e in events] == ["start", "exit"]
    assert len(list((out_root / "s").glob("flux2-klein-4b_*_256.png"))) == 3


def test_maps_and_ao_are_derived_next_to_each_albedo(
    worker: Path, log: Path, env: dict[str, str], out_root: Path
) -> None:
    request = TextureRequest(
        prompt="stone",
        backend="flux2-klein-4b",
        seeds=[5],
        resolution=256,
        name="stone",
        maps="stone",
        ao=True,
    )
    result = _run(request, worker, log, env, out_root)
    maps = result.images[0].maps
    assert set(maps) == {"N", "R", "M", "AO"}
    assert maps["AO"].endswith("flux2-klein-4b_5_256_AO.png")
    assert all(Path(path).exists() for path in maps.values())


def test_both_runs_each_model_and_writes_a_comparison_sheet(
    worker: Path, log: Path, env: dict[str, str], out_root: Path
) -> None:
    request = TextureRequest(
        prompt="burlap", backend="both", seeds=[11], resolution=256, name="burlap"
    )
    result = _run(request, worker, log, env, out_root)

    assert [r.backend for r in result.images] == ["z-image-turbo", "flux2-klein-4b"]
    assert result.compare == out_root / "burlap" / "burlap_compare.png"
    assert result.compare.exists()
    assert result.skipped == ()


def test_both_skips_an_unavailable_model_and_lists_it(
    worker: Path, log: Path, out_root: Path, tmp_path: Path
) -> None:
    models = make_models(tmp_path / "models", ids=("z-image-turbo",))
    env = {"TEXTURE_GEN_MODELS_DIR": str(models)}
    request = TextureRequest(prompt="burlap", backend="both", seeds=[1], resolution=256, name="b")
    result = _run(request, worker, log, env, out_root)

    assert [r.backend for r in result.images] == ["z-image-turbo"]
    assert result.skipped == ({"backend": "flux2-klein-4b", "availability": "not_installed"},)
    assert result.compare is None


def test_both_with_nothing_available_raises_the_first_error(
    worker: Path, log: Path, out_root: Path, tmp_path: Path
) -> None:
    env = {"TEXTURE_GEN_MODELS_DIR": str(tmp_path / "empty")}
    request = TextureRequest(prompt="burlap", backend="both", seeds=[1], resolution=256)
    with pytest.raises(TextureGenError) as caught:
        _run(request, worker, log, env, out_root)
    assert caught.value.code == "texture.model_not_installed"


def test_explicit_unavailable_backend_raises(
    worker: Path, log: Path, env: dict[str, str], out_root: Path
) -> None:
    request = TextureRequest(prompt="burlap", backend="z-image-turbo", seeds=[1], resolution=256)
    with pytest.raises(TextureGenError) as caught:
        _run(
            request,
            worker,
            log,
            env,
            out_root,
            facts=APPLE_SILICON_32GB.__class__("Linux", "x86_64", 64.0),
        )
    assert caught.value.code == "texture.unsupported_platform"
    assert log.exists() is False


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"prompt": "   "}, "empty"),
        ({"prompt": "x", "resolution": 300}, "power of two"),
        ({"prompt": "x", "resolution": 4096}, "power of two"),
        ({"prompt": "x", "seeds": []}, "No seeds"),
        ({"prompt": "x", "maps": "marble"}, "preset"),
        ({"prompt": "x", "ao": True}, "no material"),
    ],
)
def test_invalid_requests_are_refused(kwargs: dict[str, Any], message: str) -> None:
    with pytest.raises(TextureGenError) as caught:
        validate_request(TextureRequest(**kwargs))
    assert caught.value.code == "texture.invalid_request"
    assert message.lower() in caught.value.message.lower()


def test_default_request_gets_one_random_seed() -> None:
    first = TextureRequest(prompt="x")
    assert len(first.seeds) == 1 and isinstance(first.seeds[0], int)


def test_request_round_trips_through_json() -> None:
    original = TextureRequest(prompt="x", seeds=[3], maps=(0.4, 0.6), ao=False, name="n")
    restored = request_from_json(json.loads(json.dumps(request_as_json(original))))
    assert restored == original


def test_a_generate_run_refreshes_the_root_sheet_with_every_set(
    worker: Path, log: Path, env: dict[str, str], out_root: Path
) -> None:
    existing = out_root / "rusted-steel"
    albedo = save_png(synthetic_image(256, seed=2), existing / "z-image-turbo_2_256.png")
    manifest = {"images": [{"backend": "z-image-turbo", "seed": 2, "path": str(albedo)}]}
    (existing / "textures.json").write_text(json.dumps(manifest), encoding="utf-8")
    request = TextureRequest(
        prompt="oak planks", backend="z-image-turbo", seeds=[4], resolution=256, name="oak-planks"
    )

    result = _run(request, worker, log, env, out_root)

    sheet = result.contact_sheet
    assert sheet.cells == 2 and sheet.skipped == ()
    assert sheet.pages == (out_root / "contact_sheet_001.png",)
    assert sheet.pages[0].is_file()
    assert result.as_json()["contact_sheet"] == {
        "pages": [str(out_root / "contact_sheet_001.png")],
        "cells": 2,
        "skipped": [],
    }


def test_a_failed_sheet_build_is_reported_and_the_run_still_succeeds(
    worker: Path,
    log: Path,
    env: dict[str, str],
    out_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def disk_full(root: Path, *, require_sets: bool) -> ContactSheet:
        raise OSError("disk full")

    monkeypatch.setattr("nmg_game_dev.texture.generate.build_contact_sheet", disk_full)
    request = TextureRequest(
        prompt="burlap", backend="z-image-turbo", seeds=[6], resolution=256, name="burlap"
    )

    result = _run(request, worker, log, env, out_root)

    assert len(result.images) == 1 and result.images[0].path.exists()
    assert (out_root / "burlap" / "textures.json").is_file()
    assert result.contact_sheet.pages == () and result.contact_sheet.cells == 0
    assert result.contact_sheet.skipped == (
        {"path": str(out_root), "reason": "OSError: disk full"},
    )


def test_run_refuses_missing_dependencies_before_any_spawn(
    worker: Path, log: Path, env: dict[str, str], out_root: Path
) -> None:
    request = TextureRequest(
        prompt="burlap", backend="z-image-turbo", seeds=[1], resolution=256, name="burlap"
    )
    with pytest.raises(TextureGenError) as caught:
        run(
            request,
            env=env,
            facts=APPLE_SILICON_32GB,
            spawn=fake_spawn(worker, log),
            cwd=out_root.parent,
            output_root_override=out_root,
            deps_probe=lambda: "mlx",
        )
    assert caught.value.code == "texture.dependencies_missing"
    assert "mlx" in caught.value.message and "uv run --project" in caught.value.remediation
    assert not log.exists()
    assert not (out_root / "burlap").exists()


def test_backend_status_reports_dependencies_missing_for_each_available_backend(
    models: Path,
) -> None:
    status = backend_status(
        env={"TEXTURE_GEN_MODELS_DIR": str(models)},
        facts=APPLE_SILICON_32GB,
        deps_probe=lambda: "mlx",
    )
    assert status == {
        "z-image-turbo": "dependencies_missing",
        "flux2-klein-4b": "dependencies_missing",
    }


def test_a_batch_names_every_invalid_request_by_index_and_starts_nothing(
    worker: Path, log: Path, env: dict[str, str], out_root: Path
) -> None:
    requests = [
        TextureRequest(prompt="ok", backend="z-image-turbo", seeds=[1], resolution=256),
        TextureRequest(prompt="   ", backend="z-image-turbo", seeds=[2], resolution=256),
        TextureRequest(prompt="fine", backend="z-image-turbo", seeds=[3], resolution=256),
        TextureRequest(prompt="bad size", backend="z-image-turbo", seeds=[4], resolution=300),
    ]
    with pytest.raises(TextureGenError) as caught:
        run_batch(
            requests,
            env=env,
            facts=APPLE_SILICON_32GB,
            spawn=fake_spawn(worker, log),
            cwd=out_root.parent,
            output_root_override=out_root,
        )
    error = caught.value
    assert error.code == "texture.invalid_request"
    assert "request 1" in error.message and "request 3" in error.message
    assert "request 0" not in error.message and "request 2" not in error.message
    assert not log.exists() and not out_root.exists()


def test_an_empty_batch_is_invalid() -> None:
    with pytest.raises(TextureGenError) as caught:
        validate_batch([])
    assert caught.value.code == "texture.invalid_request"
    assert "empty" in caught.value.message.lower()


def test_a_batch_loads_each_backend_once_and_counts_every_image(
    worker: Path, log: Path, env: dict[str, str], out_root: Path
) -> None:
    requests = [
        TextureRequest(
            prompt="stone", backend="flux2-klein-4b", seeds=[1, 2], resolution=256, name="stone"
        ),
        TextureRequest(
            prompt="wood", backend="flux2-klein-4b", seeds=[3], resolution=256, name="wood"
        ),
    ]
    progress: list[tuple[int, int]] = []
    batch = run_batch(
        requests,
        env=env,
        facts=APPLE_SILICON_32GB,
        spawn=fake_spawn(worker, log),
        cwd=out_root.parent,
        output_root_override=out_root,
        on_progress=lambda done, total: progress.append((done, total)),
    )

    events = read_log(log)
    assert [e["event"] for e in events] == ["start", "exit"]
    assert events[0]["items"] == 3
    assert progress[0] == (0, 3) and progress[-1] == (3, 3)
    assert [r.name for r in batch.results] == ["stone", "wood"]
    assert [[img.seed for img in r.images] for r in batch.results] == [[1, 2], [3]]
    assert (out_root / "stone" / "textures.json").is_file()
    assert (out_root / "wood" / "textures.json").is_file()
    payload = batch.as_json()
    assert list(payload) == ["results"]
    assert [entry["name"] for entry in payload["results"]] == ["stone", "wood"]


def test_every_result_of_a_batch_carries_the_one_contact_sheet_refresh(
    worker: Path, log: Path, env: dict[str, str], out_root: Path
) -> None:
    requests = [
        TextureRequest(
            prompt="stone", backend="z-image-turbo", seeds=[1], resolution=256, name="a"
        ),
        TextureRequest(prompt="wood", backend="z-image-turbo", seeds=[2], resolution=256, name="b"),
    ]
    batch = run_batch(
        requests,
        env=env,
        facts=APPLE_SILICON_32GB,
        spawn=fake_spawn(worker, log),
        cwd=out_root.parent,
        output_root_override=out_root,
    )
    sheets = [result.contact_sheet for result in batch.results]
    assert sheets[0] == sheets[1]
    assert sheets[0].cells == 2
    assert sheets[0].pages == (out_root / "contact_sheet_001.png",)


def test_a_batch_item_takes_the_request_fields_and_rejects_unknown_or_malformed_ones() -> None:
    parsed = batch_from_items([{"prompt": "oak", "maps": [0.4, 0.6], "seeds": [3], "name": None}])
    assert parsed == (TextureRequest(prompt="oak", seeds=[3], maps=(0.4, 0.6)),)

    with pytest.raises(TextureGenError) as caught:
        batch_from_items([{"prompt": "ok"}, {"prompt": "x", "colour": "red"}, "not an object"])
    error = caught.value
    assert error.code == "texture.invalid_request"
    assert "request 1" in error.message and "request 2" in error.message
    assert "request 0" not in error.message

    with pytest.raises(TextureGenError) as not_array:
        batch_from_items({"prompt": "x"})
    assert not_array.value.code == "texture.invalid_request"
