"""Request validation and generation routing (#98 FR3, AC1–AC5, AC11)."""

from __future__ import annotations

import base64
from collections.abc import Callable
from pathlib import Path

import pytest

from nmg_game_dev.meshy import request as request_module
from nmg_game_dev.meshy.errors import MeshyError
from nmg_game_dev.meshy.request import (
    GenerateRequest,
    RetextureRequest,
    image_data_uri,
    route,
)
from tests.meshy_fakes import make_png


def _invalid(call: Callable[[], object]) -> MeshyError:
    with pytest.raises(MeshyError) as info:
        call()
    assert info.value.code == "meshy.invalid_request"
    assert info.value.remediation
    return info.value


@pytest.mark.parametrize("name", ["crate", "Crate_Box", "1Crate", ""])
def test_name_must_be_pascal_case(name: str) -> None:
    _invalid(GenerateRequest(name=name, prompt="x").validate)


def test_generate_needs_a_prompt_or_images() -> None:
    _invalid(GenerateRequest(name="Crate").validate)
    _invalid(GenerateRequest(name="Crate", prompt="   ").validate)


def test_more_than_four_images_is_rejected(tmp_path: Path) -> None:
    images = tuple(str(make_png(tmp_path / f"{i}.png")) for i in range(5))
    _invalid(GenerateRequest(name="Crate", image_paths=images).validate)


def test_gif_and_missing_images_are_rejected(tmp_path: Path) -> None:
    gif = tmp_path / "a.gif"
    gif.write_bytes(b"GIF89a")
    _invalid(GenerateRequest(name="Crate", image_paths=(str(gif),)).validate)
    _invalid(GenerateRequest(name="Crate", image_paths=(str(tmp_path / "gone.png"),)).validate)


def test_oversize_image_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    image = make_png(tmp_path / "big.png")
    monkeypatch.setattr(request_module, "MAX_IMAGE_BYTES", 4)
    _invalid(GenerateRequest(name="Crate", image_paths=(str(image),)).validate)


def test_prompt_with_images_is_capped_at_800_characters(tmp_path: Path) -> None:
    image = str(make_png(tmp_path / "ref.png"))
    GenerateRequest(name="Ghost", prompt="a" * 800, image_paths=(image,)).validate()
    _invalid(GenerateRequest(name="Ghost", prompt="a" * 801, image_paths=(image,)).validate)


def test_prompt_with_images_and_no_texture_is_rejected(tmp_path: Path) -> None:
    image = str(make_png(tmp_path / "ref.png"))
    _invalid(
        GenerateRequest(name="Ghost", prompt="x", image_paths=(image,), texture=False).validate
    )


def test_untextured_prompt_alone_and_images_alone_are_valid(tmp_path: Path) -> None:
    GenerateRequest(name="Crate", prompt="crate", texture=False).validate()
    GenerateRequest(
        name="Crate", image_paths=(str(make_png(tmp_path / "a.png")),), texture=False
    ).validate()


@pytest.mark.parametrize("pose", ["a-pose", "t-pose", None])
def test_known_poses_are_valid(pose: str | None) -> None:
    GenerateRequest(name="Crate", prompt="x", pose=pose).validate()


def test_unknown_pose_is_rejected() -> None:
    _invalid(GenerateRequest(name="Crate", prompt="x", pose="sitting").validate)


def test_retexture_needs_exactly_one_of_prompt_and_image(tmp_path: Path) -> None:
    image = str(make_png(tmp_path / "style.png"))
    RetextureRequest(name="Crate", prompt="mossy stone").validate()
    RetextureRequest(name="Crate", image_path=image).validate()
    _invalid(RetextureRequest(name="Crate", prompt="x", image_path=image).validate)
    _invalid(RetextureRequest(name="Crate").validate)
    _invalid(RetextureRequest(name="Crate", prompt="   ").validate)


def test_routing_follows_the_image_count(tmp_path: Path) -> None:
    images = [str(make_png(tmp_path / f"{i}.png")) for i in range(4)]
    assert route(GenerateRequest(name="Crate", prompt="x")) == "text"
    assert route(GenerateRequest(name="Lamp", image_paths=tuple(images[:1]))) == "image"
    assert route(GenerateRequest(name="Lamp", image_paths=tuple(images[:2]))) == "multi_image"
    assert route(GenerateRequest(name="Lamp", image_paths=tuple(images))) == "multi_image"


@pytest.mark.parametrize(
    ("suffix", "mime"),
    [
        (".png", "image/png"),
        (".jpg", "image/jpeg"),
        (".jpeg", "image/jpeg"),
        (".WEBP", "image/webp"),
    ],
)
def test_image_data_uri_carries_the_matching_mime(tmp_path: Path, suffix: str, mime: str) -> None:
    image = tmp_path / f"ref{suffix}"
    image.write_bytes(b"pixels")
    uri = image_data_uri(image)
    prefix = f"data:{mime};base64,"
    assert uri.startswith(prefix)
    assert base64.b64decode(uri[len(prefix) :]) == b"pixels"


def test_image_data_uri_rejects_unknown_suffix(tmp_path: Path) -> None:
    gif = tmp_path / "ref.gif"
    gif.write_bytes(b"x")
    with pytest.raises(MeshyError) as info:
        image_data_uri(gif)
    assert info.value.code == "meshy.invalid_request"
