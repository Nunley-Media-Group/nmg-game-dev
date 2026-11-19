"""The project art style: the sentence every art prompt carries and texture manifests record
(#253 FR2, AC3).

``SourceArt/Art/style.json`` holds ``{"style": "..."}`` under the project root. Texture prompts
never include it; ``generate`` only records it as ``project_style`` in ``textures.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

from nmg_game_dev.texture.errors import TextureGenError

STYLE_RELATIVE_PATH = Path("SourceArt") / "Art" / "style.json"


def project_style(root: Path) -> str | None:
    """The stripped ``style`` sentence in ``<root>/SourceArt/Art/style.json``, or None when the file
    is absent.

    Invalid JSON, a missing ``style`` string, or an empty one raises ``art.style_invalid``.
    """
    path = root / STYLE_RELATIVE_PATH
    if not path.is_file():
        return None
    try:
        data: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise _invalid(path, f"it is not readable JSON ({error})") from error
    style = data.get("style") if isinstance(data, dict) else None
    if not isinstance(style, str) or not style.strip():
        raise _invalid(path, 'it needs a non-empty "style" string')
    return style.strip()


def _invalid(path: Path, reason: str) -> TextureGenError:
    return TextureGenError(
        "art.style_invalid",
        f"The project style file {path} is invalid: {reason}.",
        'Write the file as {"style": "one sentence describing the look"}, or delete it to '
        "generate art without a project style.",
    )
