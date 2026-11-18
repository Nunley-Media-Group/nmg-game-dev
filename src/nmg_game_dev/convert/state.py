"""Conversion resume state: ``game/.nmg-convert.json`` (#249 FR11, AC12).

The file is ``{"version": 1, "done": [<item key>, ...]}``. Keys are ``asset:<Category>/<Name>``,
``audio:<Kind>/<Name>``, and ``scaffold:<type>/<Name>``. The file is written when a conversion
starts and again after each item succeeds, so an interrupted or partly failed run resumes with the
items that are not done yet. Its presence also marks a run as a resume, which skips the clean
working tree guard.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from nmg_game_dev.convert.plan import convert_error
from nmg_game_dev.pipeline.errors import PipelineError

STATE_REL: Final = Path("game") / ".nmg-convert.json"
STATE_VERSION: Final = 1


def state_path(root: Path) -> Path:
    """``<root>/game/.nmg-convert.json``."""
    return root / STATE_REL


@dataclass
class ConvertState:
    """The keys of the items that have already converted."""

    path: Path
    done: list[str] = field(default_factory=list)

    def __contains__(self, key: object) -> bool:
        return key in self.done

    def add(self, key: str) -> None:
        """Record ``key`` as converted and write the file."""
        if key not in self.done:
            self.done.append(key)
        self.save()

    def save(self) -> None:
        """Write the state atomically."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps({"version": STATE_VERSION, "done": self.done}, indent=2) + "\n"
        descriptor, temp = tempfile.mkstemp(dir=self.path.parent, prefix=".nmg-convert.")
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temp, self.path)


def load_state(root: Path) -> ConvertState | None:
    """The saved state, or ``None`` when no conversion has started in ``root``."""
    path = state_path(root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise _invalid(path, str(error)) from error
    if not isinstance(data, dict):
        raise _invalid(path, "expected a JSON object")
    done = data.get("done")
    if data.get("version") != STATE_VERSION or not isinstance(done, list):
        raise _invalid(path, "expected {'version': 1, 'done': [...]}")
    return ConvertState(path, [str(key) for key in done])


def _invalid(path: Path, detail: str) -> PipelineError:
    return convert_error(
        "convert.state_invalid",
        f"{path} cannot be read: {detail}.",
        f"Delete {STATE_REL.as_posix()} to restart the conversion from a clean git working tree.",
    )
