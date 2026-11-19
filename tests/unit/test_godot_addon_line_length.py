"""Guard: every line of the Godot add-on's GDScript fits 100 columns (#286 AC2, FR4).

Every ``.gd`` file under ``plugins/nmg-game-dev-godot-addon/`` is measured in characters, a tab
counting as one. The test also fails when no ``.gd`` file is found, so it cannot pass vacuously.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from tests._scaffold_contract import REPO_ROOT

ADDON_ROOT: Final = REPO_ROOT / "plugins" / "nmg-game-dev-godot-addon"
MAX_COLUMNS: Final = 100


def addon_gd_files() -> list[Path]:
    files: list[Path] = sorted(ADDON_ROOT.rglob("*.gd"))
    assert files, f"no .gd files found under {ADDON_ROOT}"
    return files


def overlong_lines(files: list[Path]) -> list[str]:
    """Return ``path:line: length`` for every line of ``files`` over the column limit."""
    too_long: list[str] = []
    for file in files:
        text = file.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), start=1):
            if len(line) > MAX_COLUMNS:
                relative = file.relative_to(REPO_ROOT).as_posix()
                too_long.append(f"{relative}:{number}: {len(line)}")
    return too_long


def test_every_godot_addon_gd_line_fits_one_hundred_columns() -> None:
    too_long = overlong_lines(addon_gd_files())
    assert too_long == [], "lines over 100 characters:\n" + "\n".join(too_long)
