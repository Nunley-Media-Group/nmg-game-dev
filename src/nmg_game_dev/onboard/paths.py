"""Framework root and the exclusion guard every copy goes through (#7 FR8, AC7, AC1).

``framework_root`` uses ``CLAUDE_PLUGIN_ROOT`` when set, otherwise the package's own checkout, so a
user-scope and a project-scope install onboard the same tree. ``assert_not_excluded`` keeps the
plugin's ``fixtures/`` folder and ``.mcp.json`` out of every consumer write.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from nmg_game_dev.onboard.errors import OnboardError

EXCLUDED: tuple[str, ...] = ("fixtures", ".mcp.json")
PLUGIN_ROOT_ENV = "CLAUDE_PLUGIN_ROOT"


def framework_root(env: Mapping[str, str]) -> Path:
    """The framework checkout: ``CLAUDE_PLUGIN_ROOT`` when set, else the package location."""
    raw = env.get(PLUGIN_ROOT_ENV, "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return Path(__file__).resolve().parents[3]


def assert_not_excluded(relative: Path) -> None:
    """Raise ``onboard.excluded_path`` when a relative path would write an excluded item."""
    for part in relative.parts:
        if part in EXCLUDED:
            raise OnboardError(
                "onboard.excluded_path",
                f"Refusing to write {relative}: {part!r} is never copied into a consumer.",
                "Remove the path from the install list; fixtures/ and .mcp.json stay in the "
                "framework.",
            )
