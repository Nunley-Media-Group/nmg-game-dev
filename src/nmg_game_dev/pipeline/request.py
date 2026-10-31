"""FinalizeRequest — the single input to ``pipeline.finalize`` and ``pipeline.run_step``.

A request names one authored collection in the open Blender session (or in a saved ``.blend``),
the category and asset class that decide the contract and budgets, and the export root that the
Desktop and Mobile folders are written under.  Validation happens at construction, so an invalid
request never reaches Blender or Unreal.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AssetClass = Literal["small_prop", "standard_prop", "hero_prop", "character", "environment_piece"]
Device = Literal["GPU", "CPU"]

_PASCAL_CASE = r"^[A-Z][A-Za-z0-9]*$"


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

    def to_json_dict(self) -> dict[str, object]:
        """Return the JSON-serialisable projection written to ``<job_dir>/request.json``."""
        return self.model_dump(mode="json")
