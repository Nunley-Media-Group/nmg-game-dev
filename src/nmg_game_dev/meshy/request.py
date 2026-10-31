"""Meshy request models, validation, and generation routing (#98 FR3, AC1–AC5, AC11).

Validation runs before any Meshy call and raises ``meshy.invalid_request``. Routing chooses the
Meshy endpoint from the image count: no image → text-to-3D, one image → image-to-3D, two to four
images → multi-image-to-3D. With images, the prompt is sent as ``texture_prompt``.
"""

from __future__ import annotations

import base64
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from nmg_game_dev.meshy.errors import MeshyError

Route = Literal["text", "image", "multi_image"]

NAME_RE: Final = re.compile(r"^[A-Z][A-Za-z0-9]*$")
MAX_IMAGES: Final = 4
MAX_IMAGE_BYTES: Final = 20 * 1024 * 1024
MAX_PROMPT_CHARS: Final = 800
POSES: Final = ("a-pose", "t-pose")
IMAGE_MIME: Final[Mapping[str, str]] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}
GLB_MIME: Final = "application/octet-stream"


def _invalid(message: str, remediation: str) -> MeshyError:
    return MeshyError("meshy.invalid_request", message, remediation)


def check_name(name: str) -> None:
    if not NAME_RE.match(name):
        raise _invalid(
            f"The name {name!r} is not PascalCase.",
            "Use a PascalCase name such as Crate or Lamppost; it becomes the collection name.",
        )


def clean_prompt(prompt: str | None) -> str | None:
    """Return the stripped prompt, or None when it is absent or blank."""
    text = (prompt or "").strip()
    return text or None


def check_image(path_text: str) -> Path:
    """Return ``path_text`` as a Path after checking its type, existence, and size."""
    path = Path(path_text)
    if path.suffix.lower() not in IMAGE_MIME:
        raise _invalid(
            f"{path_text} is not a PNG, JPEG, or WebP image.",
            "Pass .png, .jpg, .jpeg, or .webp reference images.",
        )
    if not path.is_file():
        raise _invalid(
            f"The reference image {path_text} does not exist.",
            "Pass the path of an existing reference image.",
        )
    if path.stat().st_size > MAX_IMAGE_BYTES:
        raise _invalid(
            f"The reference image {path_text} is larger than 20 MB.",
            "Shrink or re-export the image below 20 MB, then retry.",
        )
    return path


def data_uri(payload: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(payload).decode('ascii')}"


def image_data_uri(path: Path) -> str:
    """Return ``path`` as a base64 data URI with the MIME type of its extension."""
    mime = IMAGE_MIME.get(path.suffix.lower())
    if mime is None:
        raise _invalid(
            f"{path} is not a PNG, JPEG, or WebP image.",
            "Pass .png, .jpg, .jpeg, or .webp reference images.",
        )
    return data_uri(path.read_bytes(), mime)


@dataclass(frozen=True)
class GenerateRequest:
    """A request to generate a model from a prompt, reference images, or both."""

    name: str
    prompt: str | None = None
    image_paths: tuple[str, ...] = ()
    texture: bool = True
    pose: str | None = None

    def validate(self) -> None:
        check_name(self.name)
        prompt = clean_prompt(self.prompt)
        if prompt is None and not self.image_paths:
            raise _invalid(
                "generate_model needs a prompt, one to four reference images, or both.",
                "Pass prompt=<text>, image_paths=[<path>, ...], or both.",
            )
        if len(self.image_paths) > MAX_IMAGES:
            raise _invalid(
                f"generate_model takes at most {MAX_IMAGES} reference images, "
                f"got {len(self.image_paths)}.",
                f"Pass one to {MAX_IMAGES} images.",
            )
        for path_text in self.image_paths:
            check_image(path_text)
        if self.image_paths and prompt is not None and len(prompt) > MAX_PROMPT_CHARS:
            raise _invalid(
                f"A prompt sent with images may be at most {MAX_PROMPT_CHARS} characters.",
                "Shorten the prompt; it steers only the texture when images are given.",
            )
        if not self.texture and prompt is not None and self.image_paths:
            raise _invalid(
                "A prompt with images needs texture=True: the prompt only steers the texture.",
                "Drop the prompt, or drop texture=False.",
            )
        if self.pose is not None and self.pose not in POSES:
            raise _invalid(
                f"pose must be a-pose or t-pose, got {self.pose!r}.",
                "Pass pose='a-pose' or pose='t-pose' for limbed characters, or omit it.",
            )


@dataclass(frozen=True)
class RetextureRequest:
    """A request to retexture an authored collection from a prompt or one style image."""

    name: str
    prompt: str | None = None
    image_path: str | None = None

    def validate(self) -> None:
        check_name(self.name)
        has_prompt = clean_prompt(self.prompt) is not None
        has_image = bool(self.image_path)
        if has_prompt == has_image:
            raise _invalid(
                "retexture_model needs exactly one of prompt and image_path.",
                "Pass prompt=<text> or image_path=<path>, not both and not neither.",
            )
        if self.image_path:
            check_image(self.image_path)


def route(request: GenerateRequest) -> Route:
    """Return the Meshy endpoint family for ``request`` by its image count."""
    count = len(request.image_paths)
    if count == 0:
        return "text"
    if count == 1:
        return "image"
    return "multi_image"
