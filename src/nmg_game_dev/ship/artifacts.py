"""Each platform's export artifact under ``release/<platform>/`` and its SHA-256 (#6, #249 FR9).

Godot exports straight into the release folder: ``macos/<App>.app``, ``ios/<App>.ipa``,
``android/<App>.aab``, ``windows/<App>.exe``, and the ``web/`` folder around ``index.html``.
``artifact_sha256`` hashes a file by its bytes and a folder (the ``.app`` bundle, the web build) by
its sorted relative paths and file bytes.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from nmg_game_dev.ship.targets import Platform

PLATFORM_ARTIFACT: Final[dict[Platform, str]] = {
    "macos": "{app}.app",
    "ios": "{app}.ipa",
    "android": "{app}.aab",
    "windows": "{app}.exe",
    "web": "index.html",
}
"""The ``--export-release`` output name per platform; ``{app}`` is the sanitized project name."""


def export_path(release_dir: Path, platform: Platform, app: str) -> Path:
    """Return the path Godot exports ``platform`` to, inside ``release/<platform>/``."""
    return release_dir / platform / PLATFORM_ARTIFACT[platform].format(app=app)


def release_artifact(release_dir: Path, platform: Platform, app: str) -> Path:
    """Return the artifact listed in the release notes: the web build is its whole folder."""
    if platform == "web":
        return release_dir / platform
    return export_path(release_dir, platform, app)


_CHUNK: Final = 1024 * 1024


@dataclass(frozen=True)
class ReleaseEntry:
    """One published artifact.

    Attributes:
        platform: The platform that produced it.
        path: The artifact's path relative to the release folder, as POSIX text.
        sha256: The SHA-256 of the artifact. For a folder, see ``artifact_sha256``.
    """

    platform: Platform
    path: str
    sha256: str


def artifact_sha256(path: Path) -> str:
    """SHA-256 of a file, or of a folder over its sorted relative paths and file bytes."""
    digest = hashlib.sha256()
    if not path.is_dir():
        for chunk in _chunks(path):
            digest.update(chunk)
        return digest.hexdigest()
    for child in sorted(path.rglob("*"), key=lambda item: item.relative_to(path).as_posix()):
        rel = child.relative_to(path).as_posix()
        if child.is_symlink():
            digest.update(f"link {rel} -> {os.readlink(child)}\n".encode())
        elif child.is_file():
            digest.update(f"file {rel}\n".encode())
            for chunk in _chunks(child):
                digest.update(chunk)
    return digest.hexdigest()


def _chunks(path: Path) -> Iterator[bytes]:
    with path.open("rb") as handle:
        yield from iter(lambda: handle.read(_CHUNK), b"")
