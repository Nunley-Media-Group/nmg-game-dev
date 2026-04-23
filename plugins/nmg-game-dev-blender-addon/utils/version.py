from __future__ import annotations

from pathlib import Path


def version_tuple() -> tuple[int, int, int]:
    """Return the repo-root VERSION as a (major, minor, patch) int tuple.

    Walks up from this file until VERSION is found. Raises RuntimeError on
    missing or malformed input — never returns zeros silently, so /open-pr's
    version-rewrite has a deterministic target.
    """
    start = Path(__file__).resolve().parent
    current = start
    while True:
        candidate = current / "VERSION"
        if candidate.is_file():
            raw = candidate.read_text(encoding="utf-8").strip()
            parts = raw.split(".")
            if len(parts) != 3 or not all(p.isdigit() for p in parts):
                raise RuntimeError(
                    f"VERSION file at {candidate} contains '{raw}', "
                    "which is not a valid X.Y.Z semver triple."
                )
            return (int(parts[0]), int(parts[1]), int(parts[2]))
        parent = current.parent
        if parent == current:
            raise RuntimeError(
                f"VERSION file not found — searched from {start} to filesystem root."
            )
        current = parent
