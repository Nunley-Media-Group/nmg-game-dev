"""Locate each platform's packaged artifact and publish it under ``release/<platform>/`` (#6, FR9).

``locate_artifact`` takes the matches nearest the archive root. A launcher such as
``Windows/<Project>.exe`` therefore wins over helper executables nested deeper in the package, and
it fails with ``ship.artifact_ambiguous`` only when several matches share the shallowest depth.
``publish_artifact`` clears the platform's release folder before copying. Windows copies the whole
folder that holds the ``.exe``.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from nmg_game_dev.ship.errors import ShipError
from nmg_game_dev.ship.targets import Platform

PLATFORM_ARTIFACT: Final[dict[Platform, str]] = {
    "macos": ".app",
    "ios": ".ipa",
    "android": ".aab",
    "windows": ".exe",
}
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


def locate_artifact(archive_dir: Path, platform: Platform) -> Path:
    """Return the one artifact for ``platform`` nearest the root of ``archive_dir``."""
    suffix = PLATFORM_ARTIFACT[platform]
    matches = archive_dir.rglob(f"*{suffix}")
    if suffix == ".app":
        candidates = [path for path in matches if path.is_dir()]
    else:
        candidates = [path for path in matches if path.is_file()]
    if not candidates:
        raise ShipError(
            code="ship.artifact_not_found",
            message=f"No {suffix} artifact for {platform} under {archive_dir}.",
            remediation=f"Rerun the {platform} build; UAT should have archived a {suffix} there.",
            stage="publish",
        )
    depth = min(len(path.relative_to(archive_dir).parts) for path in candidates)
    nearest = sorted(
        path for path in candidates if len(path.relative_to(archive_dir).parts) == depth
    )
    if len(nearest) > 1:
        raise ShipError(
            code="ship.artifact_ambiguous",
            message=(
                f"{len(nearest)} {suffix} artifacts for {platform} sit at the same depth "
                f"under {archive_dir}."
            ),
            remediation=f"Remove the extra {suffix} artifacts from {archive_dir}, then rerun.",
            stage="publish",
        )
    return nearest[0]


def publish_artifact(src: Path, release_dir: Path, platform: Platform) -> Path:
    """Clear ``release/<platform>/`` and copy the artifact into it; return the published path."""
    dest_dir = release_dir / platform
    if dest_dir.is_dir():
        shutil.rmtree(dest_dir)
    dest_dir.parent.mkdir(parents=True, exist_ok=True)
    if platform == "windows":
        shutil.copytree(src.parent, dest_dir, symlinks=True)
        return dest_dir / src.name
    dest_dir.mkdir()
    target = dest_dir / src.name
    if src.is_dir():
        shutil.copytree(src, target, symlinks=True)
    else:
        shutil.copy2(src, target)
    return target


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
