"""Vocabulary and value types for the design-doc backlog (#112).

``ENTITY_TYPES`` are the seven design doc types.  ``ASSET_TYPES`` are the four that finalize as a
Blender asset.  ``asset_name`` derives the PascalCase name that the backlog and Unreal use.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from typing import Any, Final

ENTITY_TYPES: Final = ("character", "vehicle", "prop", "environment", "region", "mission", "system")
ASSET_TYPES: Final = frozenset({"character", "vehicle", "prop", "environment"})
ASSET_CLASSES: Final = (
    "small_prop",
    "standard_prop",
    "hero_prop",
    "character",
    "environment_piece",
)
PASCAL_CASE: Final = re.compile(r"^[A-Z][A-Za-z0-9]*$")
_WORD: Final = re.compile(r"[A-Za-z0-9]+")


def asset_name(name: str) -> str | None:
    """Return the PascalCase join of the name's alphanumeric words, or ``None`` if it is invalid.

    ``Old Town`` becomes ``OldTown``.  A name with no words, or whose join does not start with a
    letter, yields ``None``.
    """
    words = _WORD.findall(name)
    if not words:
        return None
    joined = "".join(word[0].upper() + word[1:] for word in words)
    return joined if PASCAL_CASE.fullmatch(joined) else None


@dataclass(frozen=True)
class Entry:
    """One design entity in the backlog.

    Attributes:
        type: One of ``ENTITY_TYPES``.
        name: The free-text name from the frontmatter.
        asset_name: The PascalCase name; unique across the backlog.
        source: The design file, relative to the project root, with forward slashes.
        fields: Every frontmatter key except ``type`` and ``name``.
        status: ``planned``, ``finalized``, ``scaffolded``, or ``orphaned``.
    """

    type: str
    name: str
    asset_name: str
    source: str
    fields: dict[str, Any] = dataclasses.field(default_factory=dict)
    status: str = "planned"

    def with_status(self, status: str) -> Entry:
        """Return a copy of this entry with ``status`` replaced."""
        return dataclasses.replace(self, status=status)

    def to_json(self) -> dict[str, Any]:
        """Return the entry's backlog JSON object."""
        return {
            "type": self.type,
            "name": self.name,
            "asset_name": self.asset_name,
            "source": self.source,
            "fields": self.fields,
            "status": self.status,
        }


@dataclass(frozen=True)
class DesignError:
    """One problem found in a design file, reported with its file and field.

    Attributes:
        code: A ``design.*`` error code.
        source: The design file (or ``docs/design`` for a missing directory).
        field: The frontmatter field at fault, or ``frontmatter`` / ``directory`` when none is.
        message: A plain-language explanation.
    """

    code: str
    source: str
    field: str
    message: str

    def line(self) -> str:
        """Return the report line ``error <code> <source>: <field> — <message>``."""
        return f"error {self.code} {self.source}: {self.field} — {self.message}"
