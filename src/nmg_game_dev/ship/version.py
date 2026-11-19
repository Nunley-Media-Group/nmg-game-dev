"""The build version ``/ship`` sets and the game shows (#254).

``resolve_version`` turns ``--bump`` or ``--version`` and the project's current
``application/config/version`` into a ``VersionPlan``. Every check raises a ``ship.version_*`` error
before anything is written. ``write_version`` then sets the new version in ``game/project.godot``
and in each export preset whose platform ships: macOS and iOS get ``application/short_version`` and
``application/version``, Android gets ``version/name`` and ``version/code`` plus one, and Windows
gets ``application/file_version`` and ``application/product_version`` as ``X.Y.Z.0``. Only those
lines change; every other byte of both files is kept.

See: the #254 design
(§ Version)
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from nmg_game_dev.godot.presets import PRESETS
from nmg_game_dev.godot.project import ConfigKey, godot_string, parse_config, read_config
from nmg_game_dev.ship.errors import ShipError
from nmg_game_dev.ship.targets import Platform

PROJECT_FILE: Final = "project.godot"
PRESETS_FILE: Final = "export_presets.cfg"
BUMPS: Final[tuple[str, ...]] = ("major", "minor", "patch")
SEMVER: Final = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
Semver = tuple[int, int, int]

_APPLICATION: Final = "application"
_VERSION_KEY: Final = "config/version"
_SECTION: Final = re.compile(r"^\[(?P<name>[^\]]+)\]\s*$")
_KEY: Final = re.compile(r"^\s*(?P<key>[^=;\s][^=]*?)\s*=")
_PRESET_SECTION: Final = re.compile(r"preset\.(\d+)")
_SHIPPED: Final[tuple[Platform, ...]] = ("macos", "ios", "android", "windows", "web")


@dataclass(frozen=True)
class VersionPlan:
    """The version a ship sets.

    Attributes:
        current: The version the project declares now, or None when it declares none.
        new: The version to ship. It equals ``current`` when no flag was passed.
        changed: True when the ship writes ``new`` into the project and its presets.
    """

    current: str | None
    new: str
    changed: bool


@dataclass(frozen=True)
class VersionEdits:
    """The rewritten text of both files, and one ``DRY-RUN:`` line per change.

    Attributes:
        project_text: The new ``game/project.godot`` text.
        presets_text: The new ``game/export_presets.cfg`` text.
        lines: A line for the version and for each key set; empty when nothing changes.
    """

    project_text: str
    presets_text: str
    lines: tuple[str, ...]


def parse_semver(text: str) -> Semver | None:
    """Return ``(major, minor, patch)`` for an ``X.Y.Z`` version, or None when it is not one."""
    match = SEMVER.match(text)
    if match is None:
        return None
    return (int(match[1]), int(match[2]), int(match[3]))


def resolve_version(project_file: Path, bump: str | None, version: str | None) -> VersionPlan:
    """Return the version to ship from ``--bump`` or ``--version`` and the project's current one.

    Raises ``ship.version_invalid`` for both flags, a malformed flag, or a malformed current
    version; ``ship.version_not_increased`` when ``--version`` is not above the current one (an
    absent current version counts as 0.0.0); and ``ship.version_missing`` when the project declares
    no version and no flag names one.
    """
    current = _current_version(project_file)
    if bump is not None and version is not None:
        raise _invalid(
            "--bump and --version were both given.",
            "Pass either --bump major|minor|patch or --version X.Y.Z, not both.",
        )
    base: Semver = (0, 0, 0)
    if current is not None:
        parsed = parse_semver(current)
        if parsed is None:
            raise _invalid(
                f"application/config/version in {project_file} is {current!r}, not X.Y.Z.",
                "Set application/config/version in game/project.godot to a version such as "
                "1.0.0, then rerun the ship.",
            )
        base = parsed
    if version is not None:
        target = parse_semver(version)
        if target is None:
            raise _invalid(
                f"--version {version!r} is not X.Y.Z.",
                "Pass --version as three numbers, such as 1.3.0.",
            )
        if target == base:
            raise ShipError(
                code="ship.version_not_increased",
                message=f"--version {version} is already the project's version: an earlier ship "
                "wrote it and then stopped before it finished.",
                remediation=f"Rerun the ship without --version or --bump to ship {version}.",
                stage="preflight",
            )
        if target < base:
            raise ShipError(
                code="ship.version_not_increased",
                message=f"--version {version} is not greater than the current version "
                f"({current or 'none'}).",
                remediation="Pass a version above the current one, or use --bump "
                "major|minor|patch.",
                stage="preflight",
            )
        return VersionPlan(current=current, new=version, changed=True)
    if bump is not None:
        if bump not in BUMPS:
            raise _invalid(
                f"--bump {bump!r} is not major, minor, or patch.",
                "Pass --bump major, minor, or patch.",
            )
        return VersionPlan(current=current, new=_bumped(base, bump), changed=True)
    if current is None:
        raise ShipError(
            code="ship.version_missing",
            message=f"{project_file} declares no application/config/version.",
            remediation="Pass --version X.Y.Z (or --bump) for the first ship.",
            stage="preflight",
        )
    return VersionPlan(current=current, new=current, changed=False)


def plan_version_edits(plan: VersionPlan, project_dir: Path) -> VersionEdits:
    """Return the new text of both files and their change lines; nothing is written.

    An unchanged plan returns both files as they are and no lines.
    """
    project_file = project_dir / PROJECT_FILE
    presets_file = project_dir / PRESETS_FILE
    project_text = project_file.read_bytes().decode("utf-8")
    presets_text = presets_file.read_bytes().decode("utf-8")
    if not plan.changed:
        return VersionEdits(project_text, presets_text, ())
    lines = [f"DRY-RUN: version {plan.current or 'none'} -> {plan.new}"]
    lines.append(
        f"DRY-RUN: set {_APPLICATION}/{_VERSION_KEY}={godot_string(plan.new)} in {project_file}"
    )
    new_project = _project_with_version(project_text, plan.new)
    new_presets, changes = _presets_with_version(presets_text, plan.new)
    lines += [
        f"DRY-RUN: set {name} {key}={literal} in {presets_file}" for name, key, literal in changes
    ]
    return VersionEdits(new_project, new_presets, tuple(lines))


def write_version(plan: VersionPlan, project_dir: Path) -> None:
    """Write ``plan.new`` to every shipping preset and game/project.godot; do nothing unchanged.

    The presets are written first, so the project only declares the new version once every preset
    carries it. A stop between the two writes leaves the old project version, and the rerun with
    the same flag writes both files again.
    """
    if not plan.changed:
        return
    edits = plan_version_edits(plan, project_dir)
    _replace_file(project_dir / PRESETS_FILE, edits.presets_text)
    _replace_file(project_dir / PROJECT_FILE, edits.project_text)


def patch_preset_literals(text: str, preset_index: int, literals: Mapping[str, str]) -> str:
    """Set each key to its Godot literal in ``[preset.<index>.options]``, replacing or appending it.

    ``literals`` holds encoded Godot literals such as ``'"1.3.0"'`` or ``"5"``, written as given.
    Every other line of ``text`` is kept byte for byte.
    """
    lines = text.splitlines(keepends=True)
    header = f"[preset.{preset_index}.options]"
    start = next((i for i, line in enumerate(lines) if line.strip() == header), None)
    if start is None:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines += ["\n", f"{header}\n", "\n"]
        start = len(lines) - 2
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith("[")),
        len(lines),
    )
    pending = dict(literals)
    for i in range(start + 1, end):
        key = lines[i].split("=", 1)[0].strip()
        if key in pending:
            lines[i] = f"{key}={pending.pop(key)}\n"
    insert_at = end
    while insert_at > start + 1 and not lines[insert_at - 1].strip():
        insert_at -= 1
    lines[insert_at:insert_at] = [f"{key}={value}\n" for key, value in pending.items()]
    return "".join(lines)


def _invalid(message: str, remediation: str) -> ShipError:
    return ShipError(
        code="ship.version_invalid", message=message, remediation=remediation, stage="preflight"
    )


def _bumped(base: Semver, part: str) -> str:
    major, minor, patch = base
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def _unquote(literal: str) -> str:
    if len(literal) >= 2 and literal[0] == literal[-1] == '"':
        return literal[1:-1]
    return literal


def _current_version(project_file: Path) -> str | None:
    """The unquoted ``application/config/version``; an empty value counts as none."""
    literal = read_config(project_file).get((_APPLICATION, _VERSION_KEY))
    if literal is None:
        return None
    return _unquote(literal) or None


def _project_with_version(text: str, version: str) -> str:
    """Set ``application/config/version``: replace its line, or add it under ``[application]``."""
    literal = godot_string(version)
    lines = text.splitlines(keepends=True)
    section = ""
    header_at: int | None = None
    for index, line in enumerate(lines):
        header = _SECTION.match(line.strip())
        if header is not None:
            section = header.group("name")
            if section == _APPLICATION and header_at is None:
                header_at = index
            continue
        key = _KEY.match(line)
        if section == _APPLICATION and key is not None and key.group("key") == _VERSION_KEY:
            lines[index] = f"{_VERSION_KEY}={literal}{_line_ending(line)}"
            return "".join(lines)
    if header_at is not None:
        if not lines[header_at].endswith("\n"):
            lines[header_at] += "\n"
        lines.insert(header_at + 1, f"{_VERSION_KEY}={literal}\n")
        return "".join(lines)
    body = text if not text or text.endswith("\n") else f"{text}\n"
    return f"{body}\n[{_APPLICATION}]\n\n{_VERSION_KEY}={literal}\n"


def _line_ending(line: str) -> str:
    return line[len(line.rstrip("\r\n")) :]


def _presets_with_version(text: str, version: str) -> tuple[str, list[tuple[str, str, str]]]:
    """Set the version keys of every shipping preset; return the text and (name, key, literal)."""
    config = parse_config(text)
    changes: list[tuple[str, str, str]] = []
    for index, platform, name in _shipping_presets(config):
        literals = _version_literals(platform, version, _prior_code(config, index))
        if not literals:
            continue
        text = patch_preset_literals(text, index, literals)
        changes += [(name, key, literal) for key, literal in literals.items()]
    return text, changes


def _shipping_presets(config: Mapping[ConfigKey, str]) -> list[tuple[int, Platform, str]]:
    """Return ``(index, platform, preset name)`` for each preset whose platform ships."""
    found: list[tuple[int, Platform, str]] = []
    for (section, key), value in config.items():
        match = _PRESET_SECTION.fullmatch(section)
        if match is None or key != "platform":
            continue
        name = _unquote(value)
        platform = next((candidate for candidate in _SHIPPED if PRESETS[candidate] == name), None)
        if platform is not None:
            found.append((int(match[1]), platform, name))
    return sorted(found)


def _prior_code(config: Mapping[ConfigKey, str], index: int) -> int:
    """The preset's current ``version/code``; an absent or non-integer value counts as 0."""
    literal = config.get((f"preset.{index}.options", "version/code"), "")
    try:
        return int(_unquote(literal))
    except ValueError:
        return 0


def _version_literals(platform: Platform, version: str, prior_code: int) -> dict[str, str]:
    """The version keys for ``platform`` as Godot literals; web has none."""
    if platform in ("macos", "ios"):
        keys = ("application/short_version", "application/version")
        return {key: godot_string(version) for key in keys}
    if platform == "android":
        return {"version/name": godot_string(version), "version/code": str(prior_code + 1)}
    if platform == "windows":
        quad = godot_string(f"{version}.0")
        return {key: quad for key in ("application/file_version", "application/product_version")}
    return {}


def _replace_file(path: Path, text: str) -> None:
    """Replace ``path`` through a temp sibling, so an interrupted write leaves the old file."""
    temp = path.with_name(f"{path.name}.tmp")
    try:
        temp.write_bytes(text.encode("utf-8"))
        os.replace(temp, path)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
