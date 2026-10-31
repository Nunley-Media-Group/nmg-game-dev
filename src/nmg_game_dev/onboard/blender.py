"""Link the Blender add-on into Blender's extensions folder (#7 FR6, AC3, AC8, AC9).

``<BLENDER_EXTENSIONS_DIR>/nmg_game_dev_blender_addon`` is a symlink to the framework's add-on. A
correct link is unchanged. A link to somewhere else, or a non-link at that path, is drift. With
``refresh`` the path is replaced by the correct link.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from nmg_game_dev.onboard.report import REFRESH_REMEDIATION, StepResult

ADDON_LINK_NAME = "nmg_game_dev_blender_addon"
ADDON_SOURCE_REL = Path("plugins") / "nmg-game-dev-blender-addon"
DEFAULT_EXTENSIONS_DIR = (
    Path.home()
    / "Library"
    / "Application Support"
    / "Blender"
    / "5.2"
    / "extensions"
    / "user_default"
)


def link_addon(framework: Path, extensions_dir: Path, *, refresh: bool) -> StepResult:
    """Create, verify, or (with ``refresh``) repair the add-on symlink in ``extensions_dir``."""
    source = framework / ADDON_SOURCE_REL
    link = extensions_dir / ADDON_LINK_NAME
    name = "blender_addon"
    if link.is_symlink():
        if os.readlink(link) == str(source):
            return StepResult(name, "unchanged", f"{link} links to the framework add-on")
        if not refresh:
            return StepResult(
                name,
                "drift",
                f"{link} points at {os.readlink(link)}, not {source}; left unchanged",
                REFRESH_REMEDIATION,
            )
        link.unlink()
        link.symlink_to(source, target_is_directory=True)
        return StepResult(name, "refreshed", f"relinked {link} to the framework add-on")
    if link.exists():
        if not refresh:
            return StepResult(
                name,
                "drift",
                f"{link} exists and is not a link to the framework add-on; left unchanged",
                REFRESH_REMEDIATION,
            )
        if link.is_dir():
            shutil.rmtree(link)
        else:
            link.unlink()
        link.symlink_to(source, target_is_directory=True)
        return StepResult(name, "refreshed", f"replaced {link} with a link to the framework add-on")
    extensions_dir.mkdir(parents=True, exist_ok=True)
    link.symlink_to(source, target_is_directory=True)
    return StepResult(name, "installed", f"linked {link} to the framework add-on")
