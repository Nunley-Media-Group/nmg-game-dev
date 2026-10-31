"""The generation flow end to end with the fake worker: outputs, maps, both, and validation (#7
AC17-AC20)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from nmg_game_dev.texture.errors import TextureGenError
from nmg_game_dev.texture.generate import (
    TextureRequest,
    TextureResult,
    request_as_json,
    request_from_json,
    run,
    validate_request,
)
from nmg_game_dev.texture.hardware import HardwareFacts
from nmg_game_dev.texture.registry import REGISTRY
from tests.texture_fakes import APPLE_SILICON_32GB, fake_spawn, make_models, read_log


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
