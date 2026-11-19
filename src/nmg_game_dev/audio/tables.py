"""The Audio component's name table: render it and refresh it after imports (#237).

``render_table`` writes the ``NmgAudioTable`` Godot text resource. ``sounds`` maps each sound under
``game/assets/Audio/`` by its file stem to its ``res://`` path, and ``themes`` maps each region's
asset name to the ``music`` field the design backlog gives it. ``refresh_tables`` rewrites every
``game/systems/*/audio_table.tres`` whose header declares ``script_class="NmgAudioTable"``, so
``import_audio`` and ``python -m nmg_game_dev.audio refresh`` keep the name table current. The
output depends only on the files present and the backlog, so a second refresh writes the same bytes.
Nothing here runs Godot.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from nmg_game_dev.audio import paths
from nmg_game_dev.audio.errors import AudioError
from nmg_game_dev.design import backlog
from nmg_game_dev.design.paths import backlog_path
from nmg_game_dev.godot.project import PROJECT_FILE, godot_string

TABLE_NAME: Final = "audio_table.tres"
TABLE_CLASS: Final = "NmgAudioTable"
TABLE_SCRIPT: Final = "res://addons/nmg_game_dev/audio/nmg_audio_table.gd"
SYSTEMS_DIR: Final = "systems"
MISSING_PROJECT: Final = "audio.godot_project_missing"
SOUND_SUFFIXES: Final = (".wav", ".ogg")


def render_table(root: Path) -> str:
    """Return the ``NmgAudioTable`` text for the project at ``root``, with keys sorted."""
    lines = [
        f'[gd_resource type="Resource" script_class="{TABLE_CLASS}" load_steps=2 format=3]',
        "",
        f'[ext_resource type="Script" path={godot_string(TABLE_SCRIPT)} id="1_table"]',
        "",
        "[resource]",
        'script = ExtResource("1_table")',
        f"sounds = {_dictionary(_sounds(root))}",
        f"themes = {_dictionary(_themes(root))}",
    ]
    return "\n".join(lines) + "\n"


def refresh_tables(root: Path) -> list[str]:
    """Rewrite each Audio name table under ``game/systems/`` whose text changed.

    Returns the project-relative paths rewritten, sorted. A table whose text is already current is
    left alone. Raises ``audio.godot_project_missing`` without ``game/project.godot``.
    """
    game = paths.game_project(root)
    if not (game / PROJECT_FILE).is_file():
        raise AudioError(
            code=MISSING_PROJECT,
            message=f"No {PROJECT_FILE} was found at {game}.",
            remediation="Run /onboard-consumer to create game/project.godot, then refresh the "
            "audio tables again.",
        )
    text = render_table(root)
    data = text.encode("utf-8")
    rewritten: list[str] = []
    for table in sorted(game.glob(f"{SYSTEMS_DIR}/*/{TABLE_NAME}")):
        if not _is_name_table(table) or table.read_bytes() == data:
            continue
        backlog.write_atomic(table, text)
        rewritten.append(table.relative_to(root).as_posix())
    return rewritten


def _sounds(root: Path) -> dict[str, str]:
    """Map each imported sound's file stem to its ``res://`` path, from ``game/assets/Audio/``."""
    audio_dir = paths.game_project(root) / paths.AUDIO_DIR
    sounds: dict[str, str] = {}
    if not audio_dir.is_dir():
        return sounds
    for path in sorted(audio_dir.iterdir()):
        if path.is_file() and path.suffix in SOUND_SUFFIXES:
            sounds[path.stem] = f"res://{(paths.AUDIO_DIR / path.name).as_posix()}"
    return sounds


def _themes(root: Path) -> dict[str, str]:
    """Map each region's asset name to the ``music`` sound its backlog entry names."""
    themes: dict[str, str] = {}
    for entry in backlog.load(backlog_path(root)):
        music = entry.fields.get("music")
        if entry.type == "region" and isinstance(music, str) and music.strip():
            themes[entry.asset_name] = music
    return dict(sorted(themes.items()))


def _dictionary(mapping: dict[str, str]) -> str:
    """Render a ``{key: value}`` string map as one Godot dictionary literal, keys sorted."""
    items = ", ".join(
        f"{godot_string(key)}: {godot_string(value)}" for key, value in sorted(mapping.items())
    )
    return "{" + items + "}"


def _is_name_table(path: Path) -> bool:
    """Return True when the table's header declares the ``NmgAudioTable`` script class."""
    with path.open(encoding="utf-8") as handle:
        header = handle.readline()
    return f'script_class="{TABLE_CLASS}"' in header
