"""AC3: each design.* error is reported with its source file, field, and sync line format."""

from __future__ import annotations

from pathlib import Path

import pytest

from nmg_game_dev.design.model import DesignError, asset_name
from nmg_game_dev.design.parse import parse_tree

SRC_OLD_TOWN = "docs/design/regions/old-town.md"
SRC_CRATE = "docs/design/props/crate.md"
SRC_MISSION = "docs/design/missions/find-key.md"

REGION = """\
---
type: region
name: Old Town
---
Body text is never read.
"""

PROP = """\
---
type: prop
name: Crate
asset_class: standard_prop
category: Props
---
"""


def _mission(region: str = "Old Town", act: str = "1") -> str:
    return f"---\ntype: mission\nname: Find Key\nact: {act}\nregion: {region}\n---\n"


def _write(root: Path, relative: str, text: str) -> None:
    path = root / "docs" / "design" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _errors(root: Path) -> list[DesignError]:
    _entries, errors = parse_tree(root)
    return errors


def _only(root: Path) -> DesignError:
    errors = _errors(root)
    assert len(errors) == 1, [error.line() for error in errors]
    return errors[0]


def _assert_line(error: DesignError, code: str, source: str, field: str) -> None:
    assert (error.code, error.source, error.field) == (code, source, field)
    assert error.message
    assert error.line().startswith(f"error {code} {source}: {field} — ")


def test_asset_name_joins_the_name_words_in_pascal_case() -> None:
    assert asset_name("Old Town") == "OldTown"
    assert asset_name("find the key") == "FindTheKey"
    assert asset_name("3D Crate") is None


def test_entry_keeps_the_name_and_derives_the_asset_name(tmp_path: Path) -> None:
    _write(tmp_path, "regions/old-town.md", REGION)

    entries, errors = parse_tree(tmp_path)

    assert errors == []
    assert len(entries) == 1
    assert (entries[0].name, entries[0].asset_name) == ("Old Town", "OldTown")
    assert entries[0].source == SRC_OLD_TOWN
    assert entries[0].fields == {}


def test_missing_frontmatter_block_reports_frontmatter_missing(tmp_path: Path) -> None:
    _write(tmp_path, "regions/old-town.md", "# Old Town\n---\ntype: region\nname: Old Town\n---\n")

    _assert_line(_only(tmp_path), "design.frontmatter_missing", SRC_OLD_TOWN, "frontmatter")


def test_unclosed_frontmatter_block_reports_frontmatter_invalid(tmp_path: Path) -> None:
    _write(tmp_path, "regions/old-town.md", "---\ntype: region\nname: Old Town\n")

    error = _only(tmp_path)

    _assert_line(error, "design.frontmatter_invalid", SRC_OLD_TOWN, "frontmatter")
    assert "not closed" in error.message


def test_unparseable_yaml_reports_frontmatter_invalid(tmp_path: Path) -> None:
    _write(tmp_path, "regions/old-town.md", "---\ntype: [region\nname: Old Town\n---\n")

    error = _only(tmp_path)

    _assert_line(error, "design.frontmatter_invalid", SRC_OLD_TOWN, "frontmatter")
    assert "not valid YAML" in error.message


def test_unknown_type_reports_unknown_type(tmp_path: Path) -> None:
    _write(tmp_path, "ships/ship.md", "---\ntype: spaceship\nname: Ship\n---\n")

    _assert_line(_only(tmp_path), "design.unknown_type", "docs/design/ships/ship.md", "type")


def test_missing_type_reports_missing_field(tmp_path: Path) -> None:
    _write(tmp_path, "props/crate.md", "---\nname: Crate\n---\n")

    _assert_line(_only(tmp_path), "design.missing_field", SRC_CRATE, "type")


def test_missing_name_reports_missing_field(tmp_path: Path) -> None:
    _write(tmp_path, "regions/old-town.md", "---\ntype: region\n---\n")

    _assert_line(_only(tmp_path), "design.missing_field", SRC_OLD_TOWN, "name")


def test_asset_type_without_asset_class_or_category_reports_both(tmp_path: Path) -> None:
    _write(tmp_path, "props/crate.md", "---\ntype: prop\nname: Crate\n---\n")

    errors = _errors(tmp_path)

    assert [(error.code, error.source, error.field) for error in errors] == [
        ("design.missing_field", SRC_CRATE, "asset_class"),
        ("design.missing_field", SRC_CRATE, "category"),
    ]
    assert (
        errors[0]
        .line()
        .startswith("error design.missing_field docs/design/props/crate.md: asset_class — ")
    )


def test_unknown_asset_class_reports_invalid_field(tmp_path: Path) -> None:
    text = PROP.replace("standard_prop", "giant_prop")
    _write(tmp_path, "props/crate.md", text)

    _assert_line(_only(tmp_path), "design.invalid_field", SRC_CRATE, "asset_class")


def test_category_must_be_pascal_case(tmp_path: Path) -> None:
    text = PROP.replace("category: Props", "category: props")
    _write(tmp_path, "props/crate.md", text)

    _assert_line(_only(tmp_path), "design.invalid_field", SRC_CRATE, "category")


def test_act_zero_reports_invalid_field(tmp_path: Path) -> None:
    _write(tmp_path, "missions/find-key.md", _mission(region="Old Town", act="0"))
    _write(tmp_path, "regions/old-town.md", REGION)

    _assert_line(_only(tmp_path), "design.invalid_field", SRC_MISSION, "act")


def test_name_with_no_valid_asset_name_reports_invalid_name(tmp_path: Path) -> None:
    _write(tmp_path, "props/crate.md", PROP.replace("name: Crate", "name: 3D Crate"))

    error = _only(tmp_path)

    _assert_line(error, "design.invalid_name", SRC_CRATE, "name")
    assert "3D Crate" in error.message


def test_two_files_with_one_asset_name_report_a_duplicate(tmp_path: Path) -> None:
    _write(tmp_path, "regions/a-old-town.md", REGION)
    _write(tmp_path, "regions/b-old-town.md", REGION)

    error = _only(tmp_path)

    _assert_line(error, "design.duplicate_name", "docs/design/regions/b-old-town.md", "name")
    assert "OldTown" in error.message
    assert "docs/design/regions/a-old-town.md" in error.message


def test_depends_on_naming_no_entry_reports_unknown_reference(tmp_path: Path) -> None:
    _write(tmp_path, "regions/old-town.md", REGION)
    _write(
        tmp_path,
        "missions/find-key.md",
        _mission().replace("region: Old Town", "region: Old Town\ndepends_on: [Ghost]"),
    )

    error = _only(tmp_path)

    _assert_line(error, "design.unknown_reference", SRC_MISSION, "depends_on")
    assert error.message == "'Ghost' names no entry"


@pytest.mark.parametrize("region", ["Nowhere", "Crate"])
def test_mission_region_must_name_a_region_entry(tmp_path: Path, region: str) -> None:
    _write(tmp_path, "regions/old-town.md", REGION)
    _write(tmp_path, "props/crate.md", PROP)
    _write(tmp_path, "missions/find-key.md", _mission(region=region))

    error = _only(tmp_path)

    _assert_line(error, "design.unknown_reference", SRC_MISSION, "region")
    assert error.message == f"{region!r} does not name a region entry"


def test_file_with_several_problems_reports_every_one(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "props/crate.md",
        "---\ntype: prop\nname: 3D Crate\ncategory: props\n---\n",
    )

    errors = _errors(tmp_path)

    assert [(error.code, error.source, error.field) for error in errors] == [
        ("design.invalid_name", SRC_CRATE, "name"),
        ("design.missing_field", SRC_CRATE, "asset_class"),
        ("design.invalid_field", SRC_CRATE, "category"),
    ]


def test_missing_design_directory_reports_dir_missing(tmp_path: Path) -> None:
    entries, errors = parse_tree(tmp_path)

    assert entries == []
    assert len(errors) == 1
    _assert_line(errors[0], "design.dir_missing", "docs/design", "directory")


def test_valid_files_produce_sorted_entries_and_no_errors(tmp_path: Path) -> None:
    _write(tmp_path, "regions/old-town.md", REGION)
    _write(tmp_path, "props/crate.md", PROP)
    _write(tmp_path, "missions/find-key.md", _mission())

    entries, errors = parse_tree(tmp_path)

    assert errors == []
    assert [(entry.type, entry.asset_name) for entry in entries] == [
        ("mission", "FindKey"),
        ("prop", "Crate"),
        ("region", "OldTown"),
    ]
    mission = entries[0]
    assert mission.fields == {"act": 1, "region": "Old Town"}
