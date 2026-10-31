"""Parse ``docs/design/**/*.md`` into backlog entries and ``design.*`` errors (#112 FR2-FR4).

Each file starts with a ``---`` frontmatter block that YAML parses.  The body is free text and is
never read.  ``parse_file`` reports every problem in one file.  ``parse_tree`` adds the checks that
span files: duplicate asset names and references to entries that do not exist.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .model import (
    ASSET_CLASSES,
    ASSET_TYPES,
    ENTITY_TYPES,
    PASCAL_CASE,
    DesignError,
    Entry,
    asset_name,
)
from .paths import design_dir

_FENCE = "---"


class _FrontmatterError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def parse_tree(root: Path) -> tuple[list[Entry], list[DesignError]]:
    """Parse every ``docs/design/**/*.md`` under ``root``.

    Returns the entries sorted by ``(type, asset_name)`` and every error found.  A missing
    ``docs/design/`` yields ``design.dir_missing`` and no entries.
    """
    directory = design_dir(root)
    if not directory.is_dir():
        return [], [
            DesignError(
                "design.dir_missing",
                _relative(directory, root),
                "directory",
                "the design directory does not exist; create docs/design/ and add one markdown "
                "file per design entity",
            )
        ]

    entries: list[Entry] = []
    errors: list[DesignError] = []
    for path in sorted(directory.glob("**/*.md")):
        result = parse_file(path, root)
        if isinstance(result, Entry):
            entries.append(result)
        else:
            errors.extend(result)

    errors.extend(_duplicate_errors(entries))
    errors.extend(_reference_errors(entries))
    return sorted(entries, key=lambda entry: (entry.type, entry.asset_name)), errors


def parse_file(path: Path, root: Path) -> Entry | list[DesignError]:
    """Validate one design file.  Return its entry, or every error it has."""
    source = _relative(path, root)
    try:
        # utf-8-sig drops the byte-order mark some editors add, so the leading --- is still found.
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as error:
        return [
            DesignError("design.frontmatter_invalid", source, "frontmatter", f"unreadable: {error}")
        ]

    try:
        data = _frontmatter(text)
    except _FrontmatterError as error:
        return [DesignError(error.code, source, "frontmatter", error.message)]

    if "type" not in data:
        return [DesignError("design.missing_field", source, "type", "the type field is required")]
    entry_type = data["type"]
    if not isinstance(entry_type, str) or entry_type not in ENTITY_TYPES:
        return [
            DesignError(
                "design.unknown_type",
                source,
                "type",
                f"type must be one of {', '.join(ENTITY_TYPES)}",
            )
        ]

    errors: list[DesignError] = []
    name = _check_name(data, source, errors)
    derived: str | None = None
    if name is not None:
        derived = asset_name(name)
        if derived is None:
            errors.append(
                DesignError(
                    "design.invalid_name",
                    source,
                    "name",
                    f"{name!r} yields no valid asset name; use letters or digits that start "
                    "with a letter",
                )
            )
    if entry_type in ASSET_TYPES:
        _check_asset_fields(data, source, errors)
    _check_optional_fields(entry_type, data, source, errors)

    if errors or name is None or derived is None:
        return errors
    fields = {str(key): value for key, value in data.items() if key not in ("type", "name")}
    return Entry(type=entry_type, name=name, asset_name=derived, source=source, fields=fields)


def _frontmatter(text: str) -> dict[str, Any]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != _FENCE:
        raise _FrontmatterError(
            "design.frontmatter_missing", "the file must begin with a --- frontmatter block"
        )
    end = next((index for index in range(1, len(lines)) if lines[index].strip() == _FENCE), None)
    if end is None:
        raise _FrontmatterError(
            "design.frontmatter_invalid", "the frontmatter block is not closed by a --- line"
        )
    try:
        data = yaml.safe_load("\n".join(lines[1:end]))
    except yaml.YAMLError as error:
        detail = " ".join(str(error).split())
        raise _FrontmatterError(
            "design.frontmatter_invalid", f"the frontmatter is not valid YAML: {detail}"
        ) from error
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise _FrontmatterError(
            "design.frontmatter_invalid", "the frontmatter must map field names to values"
        )
    return data


def _check_name(data: dict[str, Any], source: str, errors: list[DesignError]) -> str | None:
    if "name" not in data:
        errors.append(
            DesignError("design.missing_field", source, "name", "the name field is required")
        )
        return None
    name = data["name"]
    if not isinstance(name, str) or not name.strip():
        errors.append(
            DesignError("design.invalid_field", source, "name", "name must be a non-empty string")
        )
        return None
    return name


def _check_asset_fields(data: dict[str, Any], source: str, errors: list[DesignError]) -> None:
    for key in ("asset_class", "category"):
        if key not in data:
            errors.append(
                DesignError("design.missing_field", source, key, f"{key} is required for this type")
            )
    if "category" in data:
        category = data["category"]
        if not isinstance(category, str) or not PASCAL_CASE.fullmatch(category):
            errors.append(
                DesignError(
                    "design.invalid_field", source, "category", "category must be PascalCase"
                )
            )
    if "asset_class" in data:
        asset_class = data["asset_class"]
        if not isinstance(asset_class, str) or asset_class not in ASSET_CLASSES:
            errors.append(
                DesignError(
                    "design.invalid_field",
                    source,
                    "asset_class",
                    f"asset_class must be one of {', '.join(ASSET_CLASSES)}",
                )
            )


def _check_optional_fields(
    entry_type: str, data: dict[str, Any], source: str, errors: list[DesignError]
) -> None:
    if "act" in data:
        act = data["act"]
        if not isinstance(act, int) or isinstance(act, bool) or act < 1:
            errors.append(
                DesignError(
                    "design.invalid_field", source, "act", "act must be an integer of 1 or more"
                )
            )
    if "depends_on" in data:
        depends_on = data["depends_on"]
        if not isinstance(depends_on, list) or not all(
            isinstance(item, str) and item.strip() for item in depends_on
        ):
            errors.append(
                DesignError(
                    "design.invalid_field",
                    source,
                    "depends_on",
                    "depends_on must be a list of entry names",
                )
            )
    if entry_type == "mission" and "region" in data:
        region = data["region"]
        if not isinstance(region, str) or not region.strip():
            errors.append(
                DesignError(
                    "design.invalid_field", source, "region", "region must name a region entry"
                )
            )


def _duplicate_errors(entries: list[Entry]) -> list[DesignError]:
    first_seen: dict[str, Entry] = {}
    errors: list[DesignError] = []
    for entry in sorted(entries, key=lambda item: item.source):
        earlier = first_seen.get(entry.asset_name)
        if earlier is None:
            first_seen[entry.asset_name] = entry
            continue
        errors.append(
            DesignError(
                "design.duplicate_name",
                entry.source,
                "name",
                f"asset name {entry.asset_name} is also used by {earlier.source}",
            )
        )
    return errors


def _reference_errors(entries: list[Entry]) -> list[DesignError]:
    everything = {name for entry in entries for name in (entry.name, entry.asset_name)}
    regions = {
        name
        for entry in entries
        if entry.type == "region"
        for name in (entry.name, entry.asset_name)
    }
    errors: list[DesignError] = []
    for entry in entries:
        for dependency in entry.fields.get("depends_on", []):
            if dependency not in everything:
                errors.append(
                    DesignError(
                        "design.unknown_reference",
                        entry.source,
                        "depends_on",
                        f"{dependency!r} names no entry",
                    )
                )
        region = entry.fields.get("region")
        if entry.type == "mission" and region is not None and region not in regions:
            errors.append(
                DesignError(
                    "design.unknown_reference",
                    entry.source,
                    "region",
                    f"{region!r} does not name a region entry",
                )
            )
    return errors


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()
