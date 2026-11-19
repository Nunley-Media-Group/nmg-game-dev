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
BACKLOG_INVALID: Final = "audio.backlog_invalid"
TABLE_UNREADABLE: Final = "audio.table_unreadable"
TABLE_UNWRITABLE: Final = "audio.table_unwritable"
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
    left alone, and a project with no name table returns ``[]`` without reading the backlog. Every
    failure is an ``AudioError``: ``audio.godot_project_missing`` without ``game/project.godot``,
    ``audio.backlog_invalid`` when ``docs/design/backlog.json`` is not a backlog ``/design`` wrote,
    and ``audio.table_unreadable`` or ``audio.table_unwritable`` when a table file cannot be read
    or replaced.
    """
    game = paths.game_project(root)
    if not (game / PROJECT_FILE).is_file():
        raise AudioError(
            code=MISSING_PROJECT,
            message=f"No {PROJECT_FILE} was found at {game}.",
            remediation="Run /onboard-consumer to create game/project.godot, then refresh the "
            "audio tables again.",
        )
    current = {
        table: raw
        for table in sorted(game.glob(f"{SYSTEMS_DIR}/*/{TABLE_NAME}"))
        if _is_name_table(raw := _read(table))
    }
    if not current:
        return []
    text = render_table(root)
    data = text.encode("utf-8")
    rewritten: list[str] = []
    for table, existing in current.items():
        if existing == data:
            continue
        try:
            backlog.write_atomic(table, text)
        except OSError as error:
            raise AudioError(
                code=TABLE_UNWRITABLE,
                message=f"The Audio name table at {table} could not be written: {error}",
                remediation=f"Make {table.parent} writable, then refresh the audio tables again.",
            ) from error
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
    path = backlog_path(root)
    try:
        entries = backlog.load(path)
    except (ValueError, TypeError, OSError) as error:
        raise AudioError(
            code=BACKLOG_INVALID,
            message=f"The design backlog at {path} could not be read: {error}",
            remediation="Run `python -m nmg_game_dev.design sync` (/design) to rewrite the "
            "backlog from docs/design/, then refresh the audio tables again.",
        ) from error
    themes: dict[str, str] = {}
    for entry in entries:
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


def _read(path: Path) -> bytes:
    """Return the table file's bytes, or raise ``audio.table_unreadable``."""
    try:
        return path.read_bytes()
    except OSError as error:
        raise AudioError(
            code=TABLE_UNREADABLE,
            message=f"The Audio name table at {path} could not be read: {error}",
            remediation=f"Make {path} readable, or delete it and rerun /design to scaffold it, "
            "then refresh the audio tables again.",
        ) from error


def _is_name_table(data: bytes) -> bool:
    """Return True when the table's first line declares the ``NmgAudioTable`` script class.

    The header is compared as bytes, so a file that is not UTF-8 text is simply not a name table.
    """
    header = data.split(b"\n", 1)[0]
    return f'script_class="{TABLE_CLASS}"'.encode() in header
