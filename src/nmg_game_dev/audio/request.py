"""The request ``import_audio`` validates before it writes anything (#155 FR2, AC5).

``KINDS`` maps the request kind to its folder name. A name is PascalCase and must not start with a
sound prefix. ``NAME_RE`` already rejects underscores, so the prefixes are checked first only to
give a clearer message.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from nmg_game_dev.audio.errors import AudioError

KINDS: Final[dict[str, str]] = {"sfx": "SFX", "music": "Music"}
NAME_RE: Final = re.compile(r"[A-Z][A-Za-z0-9]*")
RESERVED_PREFIXES: Final = ("SFX_", "MUS_")
FORMATS: Final = frozenset({".wav", ".mp3", ".ogg", ".flac"})

_INVALID_REMEDIATION: Final = (
    "Pass a PascalCase name such as DoorCreak (no underscore, and not starting with SFX_ or "
    "MUS_), a kind of sfx or music, and the path of a file that exists."
)
_FORMAT_REMEDIATION: Final = (
    "Save the sound as .wav, .mp3, .ogg, or .flac, then import that file. Other formats are not "
    "decoded."
)


@dataclass(frozen=True)
class AudioRequest:
    """One import: the source file, the asset name, its kind, and whether it loops."""

    file: Path
    name: str
    kind: str
    loop: bool = False

    def validate(self) -> None:
        """Raise ``audio.invalid_request`` or ``audio.unsupported_format`` on a bad request."""
        if self.kind not in KINDS:
            raise _invalid(f"kind must be sfx or music, not {self.kind!r}")
        if self.name.startswith(RESERVED_PREFIXES):
            raise _invalid(f"name {self.name!r} must not start with SFX_ or MUS_")
        if not NAME_RE.fullmatch(self.name):
            raise _invalid(f"name {self.name!r} is not PascalCase (^[A-Z][A-Za-z0-9]*$)")
        if not self.file.is_file():
            raise _invalid(f"the file {self.file} does not exist")
        if self.file.suffix.lower() not in FORMATS:
            raise AudioError(
                code="audio.unsupported_format",
                message=f"{self.file.name} has an unsupported extension",
                remediation=_FORMAT_REMEDIATION,
            )


def _invalid(message: str) -> AudioError:
    return AudioError(
        code="audio.invalid_request",
        message=message,
        remediation=_INVALID_REMEDIATION,
    )
