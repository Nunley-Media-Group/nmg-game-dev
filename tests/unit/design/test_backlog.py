"""AC1 and AC2: the backlog shape, its order, and how a re-sync keeps or flags entries."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from nmg_game_dev.design.backlog import (
    dump,
    find_asset,
    load,
    mark,
    merge,
    update_statuses,
    write_atomic,
)
from nmg_game_dev.design.model import Entry
from nmg_game_dev.design.parse import parse_tree
from nmg_game_dev.design.paths import backlog_path

CRATE = """\
---
type: prop
name: Crate
asset_class: standard_prop
category: Props
---
"""

CRATE_EDITED = """\
---
type: prop
name: Crate
asset_class: hero_prop
category: Containers
---
"""

REGION = """\
---
type: region
name: Old Town
---
"""

HERO = """\
---
type: character
name: Hero
asset_class: character
category: Characters
---
"""


def _write(root: Path, relative: str, text: str) -> None:
    path = root / "docs" / "design" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _sync(root: Path) -> list[Entry]:
    """Parse the design docs and merge them into the backlog, as the sync command does."""
    entries, errors = parse_tree(root)
    assert errors == []
    path = backlog_path(root)
    merged = merge(load(path), entries)
    write_atomic(path, dump(merged))
    return merged


def _backlog_payload(root: Path) -> dict[str, object]:
    payload: dict[str, object] = json.loads(backlog_path(root).read_text(encoding="utf-8"))
    return payload


def test_entries_are_sorted_by_type_then_asset_name(tmp_path: Path) -> None:
    # The region file sorts first by path, so only the sort can put it last.
    _write(tmp_path, "a-old-town.md", REGION)
    _write(tmp_path, "props/crate.md", CRATE)
    _write(tmp_path, "props/barrel.md", CRATE.replace("Crate", "Barrel"))

    _sync(tmp_path)

    entries = _backlog_payload(tmp_path)["entries"]
    assert isinstance(entries, list)
    assert [(entry["type"], entry["asset_name"]) for entry in entries] == [
        ("prop", "Barrel"),
        ("prop", "Crate"),
        ("region", "OldTown"),
    ]


def test_each_entry_has_the_fields_the_backlog_contract_names(tmp_path: Path) -> None:
    _write(tmp_path, "props/crate.md", CRATE)

    _sync(tmp_path)

    entries = _backlog_payload(tmp_path)["entries"]
    assert entries == [
        {
            "type": "prop",
            "name": "Crate",
            "asset_name": "Crate",
            "source": "docs/design/props/crate.md",
            "fields": {"asset_class": "standard_prop", "category": "Props"},
            "status": "planned",
        }
    ]


def test_dump_is_versioned_json_with_one_trailing_newline() -> None:
    entry = Entry(
        type="region",
        name="Old Town",
        asset_name="OldTown",
        source="docs/design/regions/old-town.md",
    )

    text = dump([entry])

    assert json.loads(text)["version"] == 1
    assert set(json.loads(text)) == {"version", "entries"}
    assert text.endswith("}\n")
    assert not text.endswith("\n\n")


def test_resync_keeps_a_finalized_status_and_takes_the_edited_fields(tmp_path: Path) -> None:
    _write(tmp_path, "props/crate.md", CRATE)
    _sync(tmp_path)
    assert mark(backlog_path(tmp_path), "Crate", "finalized") is True

    _write(tmp_path, "props/crate.md", CRATE_EDITED)
    _sync(tmp_path)

    crate = find_asset(backlog_path(tmp_path), "Crate")
    assert crate is not None
    assert crate.status == "finalized"
    assert crate.fields["asset_class"] == "hero_prop"
    assert crate.fields["category"] == "Containers"


def test_a_new_file_adds_a_planned_entry_and_keeps_the_others(tmp_path: Path) -> None:
    _write(tmp_path, "props/crate.md", CRATE)
    _sync(tmp_path)
    mark(backlog_path(tmp_path), "Crate", "finalized")

    _write(tmp_path, "characters/hero.md", HERO)
    _sync(tmp_path)

    path = backlog_path(tmp_path)
    hero = find_asset(path, "Hero")
    crate = find_asset(path, "Crate")
    assert hero is not None and hero.status == "planned"
    assert crate is not None and crate.status == "finalized"


def test_a_removed_file_marks_its_entry_orphaned_and_keeps_its_fields(tmp_path: Path) -> None:
    _write(tmp_path, "props/crate.md", CRATE)
    _sync(tmp_path)
    mark(backlog_path(tmp_path), "Crate", "finalized")

    (tmp_path / "docs" / "design" / "props" / "crate.md").unlink()
    _sync(tmp_path)

    crate = find_asset(backlog_path(tmp_path), "Crate")
    assert crate is not None
    assert crate.status == "orphaned"
    assert crate.source == "docs/design/props/crate.md"
    assert crate.fields["category"] == "Props"


def test_an_orphaned_entry_becomes_planned_when_its_file_returns(tmp_path: Path) -> None:
    _write(tmp_path, "props/crate.md", CRATE)
    _sync(tmp_path)
    (tmp_path / "docs" / "design" / "props" / "crate.md").unlink()
    _sync(tmp_path)

    _write(tmp_path, "props/crate.md", CRATE)
    _sync(tmp_path)

    crate = find_asset(backlog_path(tmp_path), "Crate")
    assert crate is not None
    assert crate.status == "planned"


def test_resync_of_an_unchanged_doc_set_rewrites_identical_bytes(tmp_path: Path) -> None:
    _write(tmp_path, "props/crate.md", CRATE)
    _write(tmp_path, "regions/old-town.md", REGION)
    _sync(tmp_path)
    mark(backlog_path(tmp_path), "Crate", "finalized")
    first = backlog_path(tmp_path).read_bytes()

    _sync(tmp_path)

    assert backlog_path(tmp_path).read_bytes() == first


def test_mark_reports_whether_an_entry_has_that_asset_name(tmp_path: Path) -> None:
    _write(tmp_path, "props/crate.md", CRATE)
    _sync(tmp_path)
    before = backlog_path(tmp_path).read_bytes()

    assert mark(backlog_path(tmp_path), "Ghost", "finalized") is False
    assert backlog_path(tmp_path).read_bytes() == before
    assert mark(backlog_path(tmp_path), "Crate", "scaffolded") is True


def test_update_statuses_returns_the_names_that_matched_no_entry(tmp_path: Path) -> None:
    _write(tmp_path, "props/crate.md", CRATE)
    _sync(tmp_path)

    unmatched = update_statuses(
        backlog_path(tmp_path), {"Crate": "finalized", "Ghost": "finalized"}
    )

    assert unmatched == ["Ghost"]
    crate = find_asset(backlog_path(tmp_path), "Crate")
    assert crate is not None and crate.status == "finalized"


def test_find_asset_returns_only_asset_type_entries(tmp_path: Path) -> None:
    _write(tmp_path, "props/crate.md", CRATE)
    _write(tmp_path, "regions/old-town.md", REGION)
    _sync(tmp_path)

    path = backlog_path(tmp_path)
    assert find_asset(path, "OldTown") is None
    assert find_asset(path, "Ghost") is None
    assert find_asset(path, "Crate") is not None


def test_load_returns_no_entries_when_the_backlog_is_missing(tmp_path: Path) -> None:
    assert load(tmp_path / "backlog.json") == []


def test_load_rejects_a_file_without_an_entries_list(tmp_path: Path) -> None:
    path = tmp_path / "backlog.json"
    path.write_text('{"version": 1}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="entries list"):
        load(path)


def test_write_atomic_replaces_the_file_and_leaves_no_temp_file(tmp_path: Path) -> None:
    target = tmp_path / "backlog.json"
    target.write_text("old\n", encoding="utf-8")

    write_atomic(target, "new\n")

    assert target.read_text(encoding="utf-8") == "new\n"
    assert sorted(item.name for item in tmp_path.iterdir()) == ["backlog.json"]


def test_failed_write_keeps_the_old_file_and_removes_the_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "backlog.json"
    target.write_text("old\n", encoding="utf-8")

    def refuse(source: str, destination: str) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", refuse)
    with pytest.raises(OSError, match="disk full"):
        write_atomic(target, "new\n")

    assert target.read_text(encoding="utf-8") == "old\n"
    assert sorted(item.name for item in tmp_path.iterdir()) == ["backlog.json"]
