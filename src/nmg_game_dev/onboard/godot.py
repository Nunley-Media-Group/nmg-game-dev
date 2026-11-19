"""The Godot onboarding steps: project file, export presets, and tool checks (#249 FR10, AC10).

``ensure_godot_project`` creates ``<game>/project.godot`` with the Compatibility renderer for mobile
and web, the ``nmg_game_dev`` editor plugin, and the ``NmgAssets`` autoload. On an existing file it
adds missing keys (``refreshed``) and reports a framework key with another value as ``drift``,
leaving it alone unless ``refresh``. ``[editor_plugins] enabled`` is checked by membership: other
plugins may be enabled too, and ``refresh`` adds ``nmg_game_dev`` to the list without removing
them. ``ensure_export_presets`` writes ``<game>/export_presets.cfg`` when missing and treats any
byte difference as drift. ``find_godot`` and ``find_ffmpeg`` report the
tools as found (``unchanged``) or missing (``skipped`` with a remediation); onboarding never fails
on a missing tool.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Final

from nmg_game_dev.godot.binary import DEFAULT_GODOT_APP_BINARY, resolve_godot
from nmg_game_dev.godot.presets import render_export_presets
from nmg_game_dev.godot.project import (
    ConfigKey,
    ensure_keys,
    godot_string,
    parse_config,
    render_config,
)
from nmg_game_dev.onboard.commands import Which
from nmg_game_dev.onboard.report import REFRESH_REMEDIATION, StepResult
from nmg_game_dev.pipeline.errors import PipelineError

PROJECT_FILE: Final = "project.godot"
PRESETS_FILE: Final = "export_presets.cfg"
ADDON_REL: Final = "addons/nmg_game_dev"
PLUGIN_CFG_RES: Final = f"res://{ADDON_REL}/plugin.cfg"
AUTOLOAD_RES: Final = f"res://{ADDON_REL}/nmg_assets.gd"
CONFIG_VERSION: Final = "5"
COMPATIBILITY: Final = '"gl_compatibility"'

DRIFT_CHECKED: Final[dict[ConfigKey, str]] = {
    ("rendering", "renderer/rendering_method.mobile"): COMPATIBILITY,
    ("rendering", "renderer/rendering_method.web"): COMPATIBILITY,
    ("editor_plugins", "enabled"): f"PackedStringArray({godot_string(PLUGIN_CFG_RES)})",
    ("autoload", "NmgAssets"): godot_string(f"*{AUTOLOAD_RES}"),
}
"""Framework-owned keys: added when missing, reported as drift when they differ."""

PLUGINS_KEY: Final[ConfigKey] = ("editor_plugins", "enabled")
"""Compared by membership: the consumer may enable other editor plugins beside nmg_game_dev."""

GODOT_REMEDIATION: Final = "Install Godot 4 or set GODOT_BIN"
FFMPEG_REMEDIATION: Final = "Install ffmpeg or set FFMPEG_BIN (needed to import music)"
_KEY_LINE = re.compile(r"^(?P<key>[^=;\s][^=]*?)\s*=")
_SECTION_LINE = re.compile(r"^\[(?P<name>[^\]]+)\]\s*$")
_PACKED_STRINGS = re.compile(r"^PackedStringArray\((?P<items>.*)\)$", re.DOTALL)


def _plugin_list(value: str) -> list[str] | None:
    """The paths in a ``PackedStringArray("a", "b")`` literal, or ``None`` when it is not one."""
    match = _PACKED_STRINGS.match(value.strip())
    if match is None:
        return None
    try:
        items = json.loads(f"[{match.group('items')}]")
    except json.JSONDecodeError:
        return None
    if not isinstance(items, list) or not all(isinstance(item, str) for item in items):
        return None
    return items


def _with_our_plugin(value: str) -> str:
    """``value``'s plugins plus ``nmg_game_dev``'s, keeping every plugin the consumer enabled."""
    items = _plugin_list(value) or []
    if PLUGIN_CFG_RES not in items:
        items.append(PLUGIN_CFG_RES)
    return f"PackedStringArray({', '.join(godot_string(item) for item in items)})"


def required_keys(project_name: str) -> dict[ConfigKey, str]:
    """Every key onboarding needs in ``project.godot``; only ``DRIFT_CHECKED`` is compared."""
    return {
        ("", "config_version"): CONFIG_VERSION,
        ("application", "config/name"): godot_string(project_name),
        **DRIFT_CHECKED,
    }


def render_project(project_name: str) -> str:
    """The ``project.godot`` text onboarding creates for a new consumer."""
    body = render_config(
        [
            ("application", [("config/name", godot_string(project_name))]),
            ("autoload", [("NmgAssets", DRIFT_CHECKED[("autoload", "NmgAssets")])]),
            ("editor_plugins", [("enabled", DRIFT_CHECKED[("editor_plugins", "enabled")])]),
            (
                "rendering",
                [
                    ("renderer/rendering_method.mobile", COMPATIBILITY),
                    ("renderer/rendering_method.web", COMPATIBILITY),
                ],
            ),
        ]
    )
    return f"config_version={CONFIG_VERSION}\n\n{body}"


def _set_values(text: str, values: Mapping[ConfigKey, str]) -> str:
    """Replace the value of each existing ``(section, key)`` line; other bytes are kept."""
    lines = text.splitlines(keepends=True)
    section = ""
    for index, line in enumerate(lines):
        stripped = line.strip()
        header = _SECTION_LINE.match(stripped)
        if header:
            section = header.group("name")
            continue
        match = _KEY_LINE.match(stripped)
        if match is None:
            continue
        wanted = values.get((section, match.group("key").strip()))
        if wanted is not None:
            ending = "\n" if line.endswith("\n") else ""
            lines[index] = f"{match.group('key').strip()}={wanted}{ending}"
    return "".join(lines)


def _names(keys: list[ConfigKey]) -> str:
    return ", ".join(f"[{section}] {key}" if section else key for section, key in keys)


def ensure_godot_project(name: str, path: Path, project_name: str, *, refresh: bool) -> StepResult:
    """Create, complete, verify, or (with ``refresh``) repair ``project.godot`` at ``path``."""
    rel = f"{path.parent.name}/{path.name}"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_project(project_name), encoding="utf-8")
        return StepResult(name, "installed", f"created {rel} (Compatibility renderer)")
    text = path.read_text(encoding="utf-8")
    updated, added, drifted = ensure_keys(text, required_keys(project_name))
    drifted = [key for key in drifted if key in DRIFT_CHECKED]
    current_plugins = parse_config(updated).get(PLUGINS_KEY, "")
    if PLUGINS_KEY in drifted and PLUGIN_CFG_RES in (_plugin_list(current_plugins) or []):
        drifted.remove(PLUGINS_KEY)  # nmg_game_dev is enabled alongside other plugins
    if drifted and refresh:
        wanted = {key: DRIFT_CHECKED[key] for key in drifted}
        if PLUGINS_KEY in wanted:
            wanted[PLUGINS_KEY] = _with_our_plugin(current_plugins)
        updated = _set_values(updated, wanted)
    if updated != text:
        path.write_text(updated, encoding="utf-8")
    if drifted and not refresh:
        detail = f"{rel} sets {_names(drifted)} differently; left unchanged"
        if added:
            detail = f"added {_names(added)} to {rel}; {detail}"
        return StepResult(name, "drift", detail, REFRESH_REMEDIATION)
    if drifted:
        return StepResult(name, "refreshed", f"restored {_names(drifted)} in {rel}")
    if added:
        return StepResult(name, "refreshed", f"added {_names(added)} to {rel}")
    return StepResult(name, "unchanged", rel)


def project_name_of(project: Path, fallback: str) -> str:
    """The ``config/name`` in ``project``, or ``fallback`` when it is absent or unreadable."""
    if not project.is_file():
        return fallback
    raw = parse_config(project.read_text(encoding="utf-8")).get(("application", "config/name"))
    if raw is None:
        return fallback
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return fallback
    return value if isinstance(value, str) and value else fallback


def ensure_export_presets(name: str, path: Path, project_name: str, *, refresh: bool) -> StepResult:
    """Write ``export_presets.cfg`` when missing; a byte difference is drift unless ``refresh``."""
    rel = f"{path.parent.name}/{path.name}"
    wanted = render_export_presets(project_name)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(wanted, encoding="utf-8")
        return StepResult(name, "installed", f"wrote {rel} with the per-target presets")
    if path.read_bytes() == wanted.encode("utf-8"):
        return StepResult(name, "unchanged", rel)
    if refresh:
        path.write_text(wanted, encoding="utf-8")
        return StepResult(name, "refreshed", f"restored {rel} from the framework presets")
    return StepResult(
        name,
        "drift",
        f"{rel} differs from the framework presets; content left unchanged",
        REFRESH_REMEDIATION,
    )


def find_godot(
    name: str,
    env: Mapping[str, str],
    which: Which,
    *,
    default_app: Path = DEFAULT_GODOT_APP_BINARY,
) -> StepResult:
    """Report the Godot executable as found or missing."""
    try:
        path = resolve_godot(env, which, default_app=default_app)
    except PipelineError:
        return StepResult(name, "skipped", "Godot was not found", GODOT_REMEDIATION)
    return StepResult(name, "unchanged", f"found at {path}")


def find_ffmpeg(name: str, env: Mapping[str, str], which: Which) -> StepResult:
    """Report ffmpeg (``FFMPEG_BIN``, then PATH) as found or missing."""
    override = env.get("FFMPEG_BIN", "")
    if override and Path(override).is_file() and os.access(override, os.X_OK):
        return StepResult(name, "unchanged", f"found at {override}")
    on_path = which("ffmpeg")
    if on_path:
        return StepResult(name, "unchanged", f"found at {on_path}")
    return StepResult(name, "skipped", "ffmpeg was not found", FFMPEG_REMEDIATION)
