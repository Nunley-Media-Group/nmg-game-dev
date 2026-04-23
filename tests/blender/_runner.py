"""Blender headless pytest bootstrap driver.

Invoked as::

    blender --background --python tests/blender/_runner.py -- tests/blender

Blender consumes its own arguments up to ``--``; everything after ``--`` is
forwarded via ``sys.argv`` and parsed here as the pytest target path.

Steps:
1. Parse the pytest target from ``sys.argv`` (after ``--``).
2. Attempt ``import pytest``.  On ``ImportError``, bootstrap pip into
   Blender's bundled Python (idempotent — safe to run on every launch).
3. Invoke ``pytest.main([target, "-q"])`` and exit with pytest's return code.

No Blender GUI APIs are imported here so this script runs cleanly under
``--background``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# The add-on source directory is hyphenated (nmg-game-dev-blender-addon) for
# layout consistency with nmg-game-dev-ue-plugin, but Python/Blender require
# the snake_case module id ``nmg_game_dev_blender_addon``.  Bridge the gap by
# linking the source directory into Blender's user-addons path under the
# snake_case name before pytest (and thus addon_utils.enable) runs.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_ADDON_SRC = _REPO_ROOT / "plugins" / "nmg-game-dev-blender-addon"
_ADDON_MODULE_ID = "nmg_game_dev_blender_addon"


def _parse_target() -> str:
    """Return the pytest target path from argv after ``--``.

    Blender 5.x leaks its own CLI args (e.g. ``--background``) into
    ``sys.argv`` ahead of the ``--`` separator, so we cannot trust
    ``sys.argv[1:]`` directly.  Slice strictly after the ``--`` sentinel and
    default to ``"tests/blender"`` when no target is given.
    """
    argv = sys.argv
    if "--" in argv:
        tail = argv[argv.index("--") + 1 :]
        return tail[0] if tail else "tests/blender"
    return "tests/blender"


def _ensure_pytest() -> None:
    """Bootstrap pytest (+ pytest-bdd) into Blender's Python if not already available.

    pytest-bdd is installed even though the Blender test suite does not use it
    directly: the repo's ``pyproject.toml`` declares ``bdd_features_base_dir``
    under ``[tool.pytest.ini_options]``, and pytest rejects that key at startup
    unless the plugin defining it is importable.
    """
    try:
        import pytest  # noqa: F401, PLC0415
        import pytest_bdd  # noqa: F401, PLC0415
    except ImportError:
        print(
            "[_runner] pytest/pytest-bdd not found — bootstrapping via ensurepip + pip …",
            file=sys.stderr,
        )
        subprocess.run(
            [sys.executable, "-m", "ensurepip", "--upgrade"],
            check=True,
        )
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--upgrade",
                "pip",
                "pytest",
                "pytest-bdd",
            ],
            check=True,
        )


def _install_addon_link() -> None:
    """Idempotently link the hyphenated source dir into Blender's addons path
    under the snake_case module id so ``addon_utils.enable`` can resolve it.
    """
    import bpy  # noqa: PLC0415 — bpy only available under Blender

    addons_dir = Path(bpy.utils.user_resource("SCRIPTS", path="addons", create=True))
    link = addons_dir / _ADDON_MODULE_ID

    if link.is_symlink():
        if link.resolve() == _ADDON_SRC.resolve():
            return
        link.unlink()
    elif link.exists():
        # A stale real directory at the target would shadow the source;
        # bail loudly rather than silently deleting user content.
        raise RuntimeError(
            f"Expected symlink at {link}, found a real directory or file. "
            "Remove it manually and re-run."
        )

    link.symlink_to(_ADDON_SRC, target_is_directory=True)


def main() -> None:
    target = _parse_target()
    _ensure_pytest()
    _install_addon_link()

    import pytest  # noqa: PLC0415 — imported after potential install

    # Blender leaves its own CLI args in sys.argv (e.g. --background);
    # reset sys.argv so pytest's argparse error formatter does not
    # inherit "Blender" as the program name or misread leaked flags.
    sys.argv = [sys.argv[0], target, "-q"]
    result = pytest.main([target, "-q"])
    sys.exit(result)


if __name__ == "__main__":
    main()
