"""List mounted volumes and whether each can hold the texture models (#7 FR1, AC6).

The volumes are ``/`` and the directories under ``/Volumes``, de-duplicated by resolved path (the
``Macintosh HD`` link points at ``/``). ``fits_models`` is true when a volume has at least 60 GiB
free.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from nmg_game_dev.onboard.textures import REQUIRED_FREE_BYTES

VOLUMES_ROOT = Path("/Volumes")


def _free_bytes(path: Path) -> int:
    return shutil.disk_usage(path).free


def _default_mounts() -> list[Path]:
    mounts = [Path("/")]
    try:
        mounts.extend(sorted(p for p in VOLUMES_ROOT.iterdir() if p.is_dir()))
    except OSError:
        pass
    return mounts


def list_volumes(
    *,
    free_bytes: Callable[[Path], int] = _free_bytes,
    mounts: Callable[[], Sequence[Path]] = _default_mounts,
) -> list[dict[str, Any]]:
    """Return ``[{"mount", "free_bytes", "fits_models"}]`` for each distinct mounted volume."""
    seen: set[Path] = set()
    rows: list[dict[str, Any]] = []
    for mount in mounts():
        try:
            resolved = mount.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        try:
            free = int(free_bytes(mount))
        except OSError:
            continue
        rows.append(
            {
                "mount": str(mount),
                "free_bytes": free,
                "fits_models": free >= REQUIRED_FREE_BYTES,
            }
        )
    return rows


def volumes_json() -> str:
    return json.dumps(list_volumes(), indent=2)
