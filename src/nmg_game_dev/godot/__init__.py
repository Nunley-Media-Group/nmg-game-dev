"""The Godot 4 engine boundary (#249).

Everything engine-side goes through here: resolving the binary, running ``godot --headless``
through an injectable runner, parsing the ``NMG_RESULT {json}`` lines GDScript probes print, and
writing Godot text resources directly. There is no live-editor bridge.
"""

from __future__ import annotations

from .binary import resolve_godot
from .presets import PRESETS, render_export_presets
from .project import ensure_keys, find_project, parse_config, read_config, res_path
from .result import parse_nmg_result
from .runner import (
    CommandResult,
    GodotRunner,
    SubprocessGodotRunner,
    import_project,
    run_probe,
)

__all__ = [
    "PRESETS",
    "CommandResult",
    "GodotRunner",
    "SubprocessGodotRunner",
    "ensure_keys",
    "find_project",
    "import_project",
    "parse_config",
    "parse_nmg_result",
    "read_config",
    "render_export_presets",
    "res_path",
    "resolve_godot",
    "run_probe",
]
