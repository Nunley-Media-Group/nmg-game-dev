"""Render ``game/export_presets.cfg`` with one preset per ship target (#249 FR9, FR10).

Desktop presets exclude every ``Mobile/`` asset folder; mobile and web presets exclude every
``Desktop/`` folder, so a package never carries the other variant.
"""

from __future__ import annotations

import re
from typing import Final

from .project import godot_string, render_config

PRESETS: Final[dict[str, str]] = {
    "macos": "macOS",
    "ios": "iOS",
    "android": "Android",
    "windows": "Windows Desktop",
    "web": "Web",
}
"""Ship target -> Godot preset name (which is also the Godot export platform name)."""

DESKTOP_TARGETS: Final = ("macos", "windows")
EXCLUDE_DESKTOP: Final = "assets/*/Desktop/*"
EXCLUDE_MOBILE: Final = "assets/*/Mobile/*"


def exclude_filter(target: str) -> str:
    """Return the variant exclude filter for ``target``."""
    return EXCLUDE_MOBILE if target in DESKTOP_TARGETS else EXCLUDE_DESKTOP


def bundle_id(project_name: str) -> str:
    """Return a reverse-DNS bundle id derived from the project name."""
    slug = re.sub(r"[^a-z0-9]", "", project_name.lower()) or "game"
    return f"com.nmg.{slug}"


def _options(target: str, project_name: str) -> list[tuple[str, str]]:
    ident = godot_string(bundle_id(project_name))
    if target == "macos":
        return [("application/bundle_identifier", ident), ("codesign/codesign", "0")]
    if target == "ios":
        return [
            ("application/app_store_team_id", '""'),
            ("application/provisioning_profile_uuid_release", '""'),
            ("application/bundle_identifier", ident),
        ]
    if target == "android":
        return [
            ("gradle_build/use_gradle_build", "true"),
            ("gradle_build/export_format", "1"),
            ("package/unique_name", ident),
        ]
    if target == "windows":
        return [("binary_format/embed_pck", "true")]
    return [("variant/thread_support", "false")]


def render_export_presets(project_name: str) -> str:
    """Return the full ``export_presets.cfg`` text for ``project_name``."""
    sections: list[tuple[str, list[tuple[str, str]]]] = []
    for index, (target, preset) in enumerate(PRESETS.items()):
        sections.append(
            (
                f"preset.{index}",
                [
                    ("name", godot_string(preset)),
                    ("platform", godot_string(preset)),
                    ("runnable", "true"),
                    ("dedicated_server", "false"),
                    ("custom_features", '""'),
                    ("export_filter", '"all_resources"'),
                    ("include_filter", '""'),
                    ("exclude_filter", godot_string(exclude_filter(target))),
                    ("export_path", '""'),
                    ("encryption_include_filters", '""'),
                    ("encryption_exclude_filters", '""'),
                    ("encrypt_pck", "false"),
                    ("encrypt_directory", "false"),
                ],
            )
        )
        sections.append((f"preset.{index}.options", _options(target, project_name)))
    return render_config(sections)
