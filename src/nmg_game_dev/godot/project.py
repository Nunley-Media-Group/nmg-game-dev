"""Locate a Godot project and read or update its ``ConfigFile`` text (#249 FR1, FR10).

Godot's ``project.godot``, ``export_presets.cfg`` and ``*.import`` files share one INI-like format:
``[section]`` headers followed by ``key=value`` lines whose values are Godot variant literals. The
helpers here treat values as opaque literal strings, so callers pass already-encoded values such as
``'"gl_compatibility"'`` or ``'PackedStringArray("res://a")'``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Final

from nmg_game_dev.pipeline.errors import PipelineError

PROJECT_FILE: Final = "project.godot"
_SECTION = re.compile(r"^\[(?P<name>[^\]]+)\]\s*$")
_KEY = re.compile(r"^(?P<key>[^=;\s][^=]*?)\s*=\s*(?P<value>.*)$")

ConfigKey = tuple[str, str]
"""``(section, key)``; the empty section holds keys before the first header."""


def find_project(export_root: Path) -> Path:
    """Return the nearest directory at or above ``export_root`` holding ``project.godot``."""
    start = export_root.resolve()
    for candidate in (start, *start.parents):
        if (candidate / PROJECT_FILE).is_file():
            return candidate
    raise PipelineError(
        code="import_godot.project_missing",
        message=f"No {PROJECT_FILE} was found at or above {export_root}.",
        remediation="Run /onboard-consumer to create game/project.godot, or set export_root to a "
        "folder inside the Godot project.",
        stage="import_godot",
    )


def res_path(project: Path, path: Path) -> str:
    """Return the ``res://`` path for ``path`` inside ``project``."""
    relative = path.resolve().relative_to(project.resolve())
    return "res://" + relative.as_posix()


def godot_string(value: str) -> str:
    """Encode ``value`` as a Godot string literal."""
    return json.dumps(value)


def parse_config(text: str) -> dict[ConfigKey, str]:
    """Return every ``(section, key) -> value literal`` in ``text``. Later duplicates win."""
    values: dict[ConfigKey, str] = {}
    section = ""
    for line in text.splitlines():
        stripped = line.strip()
        header = _SECTION.match(stripped)
        if header:
            section = header.group("name")
            continue
        match = _KEY.match(stripped)
        if match:
            values[(section, match.group("key").strip())] = match.group("value").strip()
    return values


def read_config(path: Path) -> dict[ConfigKey, str]:
    """Parse the config file at ``path``."""
    return parse_config(path.read_text(encoding="utf-8"))


def ensure_keys(
    text: str, required: Mapping[ConfigKey, str]
) -> tuple[str, list[ConfigKey], list[ConfigKey]]:
    """Add each missing required key; report keys whose value differs without changing them.

    Returns ``(new_text, added, drifted)``. A missing section is appended at the end.
    """
    existing = parse_config(text)
    added: list[ConfigKey] = []
    drifted: list[ConfigKey] = []
    pending: dict[str, list[tuple[str, str]]] = {}
    for (section, key), value in required.items():
        current = existing.get((section, key))
        if current is None:
            pending.setdefault(section, []).append((key, value))
            added.append((section, key))
        elif current != value:
            drifted.append((section, key))
    if not pending:
        return text, added, drifted
    lines = text.splitlines()
    for section, entries in pending.items():
        new_lines = [f"{key}={value}" for key, value in entries]
        index = _section_end(lines, section)
        if index is None:
            if lines and lines[-1].strip():
                lines.append("")
            lines.extend([f"[{section}]", "", *new_lines])
        else:
            lines[index:index] = new_lines
    return "\n".join(lines) + "\n", added, drifted


def _section_end(lines: Sequence[str], section: str) -> int | None:
    """Return the insert index after the last key of ``section``, or None when it is absent."""
    current = ""
    present = section == ""
    insert: int | None = 0 if present else None
    for index, line in enumerate(lines):
        stripped = line.strip()
        header = _SECTION.match(stripped)
        if header:
            current = header.group("name")
            if current == section:
                present = True
                insert = index + 1
            continue
        if current == section and _KEY.match(stripped):
            insert = index + 1
    return insert if present else None


def render_config(sections: Iterable[tuple[str, Sequence[tuple[str, str]]]]) -> str:
    """Render ``[(section, [(key, value literal), ...]), ...]`` as Godot ``ConfigFile`` text."""
    blocks: list[str] = []
    for section, entries in sections:
        body = "\n".join(f"{key}={value}" for key, value in entries)
        blocks.append(f"[{section}]\n\n{body}\n" if body else f"[{section}]\n")
    return "\n".join(blocks)
