"""Meshy key resolution and the project root (#98 FR2, AC8, AC9).

The key is the process ``MESHY_API_KEY`` when it is non-empty, else the ``MESHY_API_KEY=`` line of
``<project>/.env``. The project root is ``CLAUDE_PROJECT_DIR`` when set, else the working directory.
Nothing here writes a file, and the key is never echoed into a message.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Final

from nmg_game_dev.meshy.errors import MeshyError

KEY_NAME: Final = "MESHY_API_KEY"
PROJECT_DIR_ENV: Final = "CLAUDE_PROJECT_DIR"
DOTENV_NAME: Final = ".env"
REDACTED: Final = "***"
_EXPORT_PREFIX: Final = "export "


def project_root(env: Mapping[str, str], cwd: Path) -> Path:
    """Return ``CLAUDE_PROJECT_DIR`` when it is set, else ``cwd``."""
    raw = env.get(PROJECT_DIR_ENV, "").strip()
    return Path(raw) if raw else cwd


def read_dotenv(path: Path) -> dict[str, str]:
    """Parse ``KEY=VALUE`` lines from ``path``.

    Blank lines and ``#`` comments are skipped, an ``export `` prefix is dropped, surrounding
    whitespace is stripped, and one pair of matching quotes is removed. A missing or unreadable file
    holds no values. When a key repeats, the last line wins.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix(_EXPORT_PREFIX).strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def api_key(env: Mapping[str, str], cwd: Path) -> str:
    """Return the Meshy key, or raise ``meshy.api_key_missing`` before any Meshy work starts."""
    key = env.get(KEY_NAME, "").strip()
    if key:
        return key
    key = read_dotenv(project_root(env, cwd) / DOTENV_NAME).get(KEY_NAME, "").strip()
    if key:
        return key
    raise MeshyError(
        "meshy.api_key_missing",
        f"No {KEY_NAME} is set in the environment or in the project {DOTENV_NAME} file.",
        f"Add {KEY_NAME}=<key> to the project's git-ignored {DOTENV_NAME} file (or export "
        f"{KEY_NAME}), then retry.",
    )


def redact(text: str, key: str) -> str:
    """Replace every occurrence of ``key`` in ``text`` with ``***``."""
    return text.replace(key, REDACTED) if key else text
