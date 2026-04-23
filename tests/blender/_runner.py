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


def _parse_target() -> str:
    """Return the pytest target path from argv after ``--``.

    Blender passes everything after ``--`` through to ``sys.argv``; the
    separator itself is removed by Blender, so ``sys.argv`` is the list that
    follows ``--``.  Default to ``"tests/blender"`` when no target is given.
    """
    # Under blender --background --python runner.py -- tests/blender,
    # sys.argv[0] is the runner script path; sys.argv[1:] are our args.
    args = sys.argv[1:]
    return args[0] if args else "tests/blender"


def _ensure_pytest() -> None:
    """Bootstrap pytest into Blender's Python if not already available."""
    try:
        import pytest  # noqa: F401, PLC0415
    except ImportError:
        print(
            "[_runner] pytest not found — bootstrapping via ensurepip + pip …",
            file=sys.stderr,
        )
        subprocess.run(
            [sys.executable, "-m", "ensurepip", "--upgrade"],
            check=True,
        )
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "pip", "pytest"],
            check=True,
        )


def main() -> None:
    target = _parse_target()
    _ensure_pytest()

    import pytest  # noqa: PLC0415 — imported after potential install

    result = pytest.main([target, "-q"])
    sys.exit(result)


if __name__ == "__main__":
    main()
