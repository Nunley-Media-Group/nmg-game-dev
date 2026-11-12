"""Blender headless pytest bootstrap driver.

Invoked as::

    blender --background --python tests/blender/_runner.py -- tests/blender

Blender consumes its own arguments up to ``--``; everything after ``--`` is
forwarded via ``sys.argv`` and parsed here as the pytest target path.

The add-on link is created only under ``BLENDER_USER_SCRIPTS``, which
``scripts/run-blender-tests.sh`` sets to a per-run temporary directory (#189). Running this
file directly without that variable raises instead of touching the user's scripts directory.

Steps:
1. Parse the pytest target from ``sys.argv`` (after ``--``).
2. Attempt ``import pytest``.  On ``ImportError``, bootstrap pip into
   Blender's bundled Python (idempotent — safe to run on every launch).
3. Invoke ``pytest.main([target, "-q"])`` and exit with pytest's return code. The exit goes
   through ``os._exit`` after flushing, because Blender swallows the ``SystemExit`` that
   ``sys.exit`` raises from a ``--python`` script.

No Blender GUI APIs are imported here so this script runs cleanly under
``--background``.
"""

from __future__ import annotations

import importlib.util
import os
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


def _isolated_addons_dir() -> Path:
    """Return Blender's addons path, which must resolve inside this run's ``BLENDER_USER_SCRIPTS``.

    ``scripts/run-blender-tests.sh`` sets ``BLENDER_USER_SCRIPTS`` to a per-run temporary
    directory. Both checks run before any filesystem write: the variable must be set, and
    Blender's ``SCRIPTS/addons`` path must resolve inside it. Otherwise the runner would link
    into the user's real Blender scripts directory.
    """
    import bpy  # noqa: PLC0415 — bpy only available under Blender

    user_scripts = os.environ.get("BLENDER_USER_SCRIPTS", "")
    if not user_scripts:
        raise RuntimeError(
            "BLENDER_USER_SCRIPTS is unset; run the Blender tests through "
            "scripts/run-blender-tests.sh, which gives each run its own user scripts directory."
        )
    root = Path(user_scripts).resolve()
    addons_dir = Path(bpy.utils.user_resource("SCRIPTS", path="addons")).resolve()
    if not addons_dir.is_relative_to(root):
        raise RuntimeError(
            f"Blender resolved its addons path to {addons_dir}, outside BLENDER_USER_SCRIPTS "
            f"({root}); refusing to link the add-on there. Run the Blender tests through "
            "scripts/run-blender-tests.sh."
        )
    return addons_dir


def _install_addon_link() -> None:
    """Idempotently link the hyphenated source dir into the run's isolated addons path
    under the snake_case module id so ``addon_utils.enable`` can resolve it.
    """
    addons_dir = _isolated_addons_dir()
    addons_dir.mkdir(parents=True, exist_ok=True)
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


def _verify_addon_origin() -> None:
    """Fail unless ``import nmg_game_dev_blender_addon`` resolves to this checkout's source.

    Guards against another copy of the add-on (for example one installed as an extension or
    enabled from another path) shadowing the per-run link, which would make this suite test
    a different checkout's code.
    """
    spec = importlib.util.find_spec(_ADDON_MODULE_ID)
    origin = Path(spec.origin if spec and spec.origin else "").resolve()
    if not origin.is_relative_to(_ADDON_SRC.resolve()):
        raise RuntimeError(
            f"{_ADDON_MODULE_ID} resolved to {origin}, not this checkout's {_ADDON_SRC}. "
            "Remove the other copy from Blender's add-on paths and re-run."
        )


def main() -> None:
    target = _parse_target()
    _ensure_pytest()
    _install_addon_link()
    # Blender puts a scripts addons directory on sys.path only when it exists at startup. The
    # per-run directory is created after startup (#189), so refresh the script paths or
    # addon_utils.enable cannot find the linked add-on.
    import bpy  # noqa: PLC0415 — bpy only available under Blender

    bpy.utils.refresh_script_paths()
    _verify_addon_origin()

    import pytest  # noqa: PLC0415 — imported after potential install

    # Blender leaves its own CLI args in sys.argv (e.g. --background);
    # reset sys.argv so pytest's argparse error formatter does not
    # inherit "Blender" as the program name or misread leaked flags.
    sys.argv = [sys.argv[0], target, "-q"]
    result = pytest.main([target, "-q"])
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(int(result))


if __name__ == "__main__":
    main()
