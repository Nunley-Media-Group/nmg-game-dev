"""FinalizeRequest — the single input to ``pipeline.finalize`` and ``pipeline.run_step``.

A request names one authored collection in the open Blender session (or in a saved ``.blend``),
the category and asset class that decide the contract and budgets, and the export root that the
Desktop and Mobile folders are written under.  Validation happens at construction, so an invalid
request never reaches Blender or Unreal.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

AssetClass = Literal["small_prop", "standard_prop", "hero_prop", "character", "environment_piece"]
Device = Literal["GPU", "CPU"]
PieMode = Literal["wait", "refuse"]

_PASCAL_CASE = r"^[A-Z][A-Za-z0-9]*$"
DEFAULT_PIE_WAIT_SECONDS = 600.0
_COMPATIBLE_WITH = re.compile(r"^[A-Z][A-Za-z0-9]*/[A-Z][A-Za-z0-9]*$")


class FinalizeRequest(BaseModel):
    """Immutable, validated description of one asset to finalize.

    Attributes:
        collection: Blender collection name, e.g. ``Crate``.  Mobile output lives in
            ``<collection>_Mobile``.
        category: Content category, e.g. ``Props``.  Used in ``/Game/<Category>/<Name>/``.
        asset_class: Contract class; selects the budgets and the contract rules.
        export_root: Directory the FBX variants and sidecars are written under, as
            ``<export_root>/<Category>/<Name>/{Desktop,Mobile}``.
        blend: Optional saved ``.blend`` to finalize headlessly instead of the open session.
        budgets_path: Optional budget overrides file.  ``None`` uses the add-on defaults.
        device: Bake device.  ``GPU`` falls back to ``CPU`` inside Blender when unavailable.
        backlog_path: The design backlog (``docs/design/backlog.json``) when it holds an asset
            entry for ``collection``.  A successful ``finalize_asset`` job marks that entry
            ``finalized``.  It never enters the cache settings.
        pie_mode: What ``import_ue`` does when the editor is in Play In Editor (#149).  ``wait``
            polls until PIE ends or ``pie_wait_seconds`` elapses.  ``refuse`` fails at once.
        pie_wait_seconds: The PIE wait limit for ``wait`` mode.  Like ``pie_mode``, it never
            enters the cache settings.
        compatible_with: ``<Category>/<Name>`` characters whose Desktop skeleton this character's
            clips may play on (#138).  ``import_anims`` registers them as compatible skeletons in
            both directions.  Duplicates are dropped, keeping the first occurrence.
        material_variants_path: The ``<collection>.material-variants.json`` declaration, given
            explicitly or found beside ``blend``.  ``None`` means the asset declares no material
            variants.  Validate and export key their cache on its bytes (#148).
    """

    model_config = ConfigDict(frozen=True)

    collection: str = Field(pattern=_PASCAL_CASE)
    category: str = Field(pattern=_PASCAL_CASE)
    asset_class: AssetClass
    export_root: Path
    blend: Path | None = None
    budgets_path: Path | None = None
    device: Device = "GPU"
    backlog_path: Path | None = None
    pie_mode: PieMode = "wait"
    pie_wait_seconds: float = Field(default=DEFAULT_PIE_WAIT_SECONDS, ge=0)
    material_variants_path: Path | None = None
    compatible_with: tuple[str, ...] = ()

    @field_validator("compatible_with")
    @classmethod
    def _valid_compatible_with(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for item in value:
            if not _COMPATIBLE_WITH.match(item):
                raise ValueError(
                    f"compatible_with item {item!r} must be <Category>/<Name> in PascalCase"
                )
        return tuple(dict.fromkeys(value))

    @model_validator(mode="after")
    def _not_itself(self) -> FinalizeRequest:
        if f"{self.category}/{self.collection}" in self.compatible_with:
            raise ValueError("compatible_with must not name the asset being finalized")
        return self

    def to_json_dict(self) -> dict[str, object]:
        """Return the JSON-serialisable projection written to ``<job_dir>/request.json``."""
        return self.model_dump(mode="json")
