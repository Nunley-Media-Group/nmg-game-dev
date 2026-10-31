"""The backlog file ``docs/design/backlog.json``: load, merge, dump, and atomic writes (#112).

The file is ``{"version": 1, "entries": [...]}``.  ``dump`` is byte-stable for the same entries,
so a re-sync of an unchanged doc set rewrites identical bytes.  Writes go to a temp file in the
same directory and replace the target with ``os.replace``.  A failed write leaves the old file.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Final

from .model import ASSET_TYPES, Entry

BACKLOG_VERSION: Final = 1


def load(path: Path) -> list[Entry]:
    """Return the entries in the backlog, or an empty list when the file does not exist.

    Raises ``ValueError`` when the file is not a backlog this module wrote.
    """
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    raw = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        raise ValueError(f"{path} does not hold an entries list")
    return [_entry_from_json(item, path) for item in raw]


def merge(previous: Iterable[Entry], parsed: Iterable[Entry]) -> list[Entry]:
    """Combine the previous backlog with a fresh parse of the design docs.

    Matching is by ``asset_name``.  An entry keeps its previous status, except that an
    ``orphaned`` entry whose file is back becomes ``planned``.  A new entry is ``planned``.  An
    entry whose file was removed becomes ``orphaned``; it keeps its other fields.
    """
    old = {entry.asset_name: entry for entry in previous}
    merged: dict[str, Entry] = {}
    for entry in parsed:
        prior = old.get(entry.asset_name)
        status = "planned" if prior is None or prior.status == "orphaned" else prior.status
        merged[entry.asset_name] = entry.with_status(status)
    for name, prior in old.items():
        if name not in merged:
            merged[name] = prior if prior.status == "orphaned" else prior.with_status("orphaned")
    return sort_entries(merged.values())


def sort_entries(entries: Iterable[Entry]) -> list[Entry]:
    """Return the entries sorted by ``(type, asset_name)``."""
    return sorted(entries, key=lambda entry: (entry.type, entry.asset_name))


def dump(entries: Iterable[Entry]) -> str:
    """Return the backlog text: sorted, indented, sorted keys, and a trailing newline."""
    payload = {
        "version": BACKLOG_VERSION,
        "entries": [entry.to_json() for entry in sort_entries(entries)],
    }
    return json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n"


def write_atomic(path: Path, text: str) -> None:
    """Replace ``path`` with ``text`` in one step, so readers never see a partial file."""
    descriptor, temp_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(temp_name, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temp_name)
        raise


def find_asset(path: Path, asset_name: str) -> Entry | None:
    """Return the asset-type entry named ``asset_name``, or ``None`` when there is none."""
    for entry in load(path):
        if entry.asset_name == asset_name and entry.type in ASSET_TYPES:
            return entry
    return None


def update_statuses(path: Path, statuses: Mapping[str, str]) -> list[str]:
    """Set the status of each entry named in ``statuses``, with one atomic write.

    Returns the asset names that matched no entry.  The file is written only when one matched.
    """
    entries = load(path)
    updated: list[Entry] = []
    matched: set[str] = set()
    for entry in entries:
        if entry.asset_name in statuses:
            matched.add(entry.asset_name)
            updated.append(entry.with_status(statuses[entry.asset_name]))
        else:
            updated.append(entry)
    if matched:
        write_atomic(path, dump(updated))
    return sorted(set(statuses) - matched)


def mark(path: Path, asset_name: str, status: str) -> bool:
    """Set one entry's status.  Returns ``False`` when no entry has that asset name."""
    return not update_statuses(path, {asset_name: status})


def _entry_from_json(item: Any, path: Path) -> Entry:
    if not isinstance(item, dict):
        raise ValueError(f"{path} holds an entry that is not an object")
    try:
        entry = Entry(
            type=str(item["type"]),
            name=str(item["name"]),
            asset_name=str(item["asset_name"]),
            source=str(item["source"]),
            fields=dict(item.get("fields") or {}),
            status=str(item["status"]),
        )
    except KeyError as error:
        raise ValueError(f"{path} has an entry without {error.args[0]}") from error
    return entry
