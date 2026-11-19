"""Discover what converting an Unreal consumer to Godot involves (#249 FR11, AC11).

``discover(root)`` reads the consumer and returns a ``ConversionPlan``. It never writes.

- **Assets:** every ``Content/<Category>/<Name>/Mobile/nmg-asset.json``. The asset class is the
  sidecar's ``class``. The Blender source is the single ``SourceArt/**/<Name>.blend``, compared
  case-insensitively. None gives the item the problem ``convert.source_missing``; several give
  ``convert.source_ambiguous``. An unreadable sidecar gives ``convert.sidecar_invalid``. A problem
  fails only that item.
- **Audio:** ``SourceArt/Audio/SFX/*.wav`` (no loop) and ``SourceArt/Audio/Music/*.wav`` (loop).
- **Scaffolds:** backlog entries of type region, mission, or system whose status is ``scaffolded``.
- **Manual port:** every file under ``Source/``, every ``Content/**/*.umap``, and every
  ``Content/**/*.uasset`` outside a finalized ``Content/<Category>/<Name>/`` folder.
- **Deletions:** ``Content/``, ``Source/``, ``Config/``, ``Plugins/``, each ``*.uproject``, and
  ``scripts/start-unreal-mcp.sh``, when they exist.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from nmg_game_dev.pipeline.errors import PipelineError

CONTENT: Final = "Content"
SOURCE_ART: Final = "SourceArt"
SIDECAR: Final = "nmg-asset.json"
BACKLOG: Final = Path("docs") / "design" / "backlog.json"
SCAFFOLD_TYPES: Final = ("region", "mission", "system")
AUDIO_KINDS: Final = (("SFX", False), ("Music", True))
DELETION_DIRS: Final = ("Content", "Source", "Config", "Plugins")
UNREAL_SCRIPTS: Final = ("scripts/start-unreal-mcp.sh",)
STAGE: Final = "convert"


def convert_error(code: str, message: str, remediation: str) -> PipelineError:
    """A ``PipelineError`` from the convert stage."""
    return PipelineError(code=code, message=message, remediation=remediation, stage=STAGE)


@dataclass(frozen=True)
class AssetItem:
    """One finalized Unreal asset to re-finalize from its Blender source into ``game/assets``."""

    category: str
    name: str
    asset_class: str
    source: Path | None
    problem: PipelineError | None = None

    @property
    def key(self) -> str:
        return f"asset:{self.category}/{self.name}"


@dataclass(frozen=True)
class AudioItem:
    """One stored WAV to import into Godot. ``kind`` is ``SFX`` or ``Music``."""

    kind: str
    name: str
    wav: Path
    loop: bool

    @property
    def key(self) -> str:
        return f"audio:{self.kind}/{self.name}"


@dataclass(frozen=True)
class ScaffoldItem:
    """One scaffolded backlog entry to scaffold again as Godot files."""

    entry_type: str
    name: str

    @property
    def key(self) -> str:
        return f"scaffold:{self.entry_type}/{self.name}"


@dataclass(frozen=True)
class ManualPort:
    """A file conversion cannot carry over; the developer ports it by hand."""

    path: str
    reason: str


Item = AssetItem | AudioItem | ScaffoldItem


@dataclass(frozen=True)
class ConversionPlan:
    """Everything one conversion run would convert, report, and delete."""

    assets: list[AssetItem] = field(default_factory=list)
    audio: list[AudioItem] = field(default_factory=list)
    scaffolds: list[ScaffoldItem] = field(default_factory=list)
    manual_port: list[ManualPort] = field(default_factory=list)
    deletions: list[str] = field(default_factory=list)

    @property
    def items(self) -> list[Item]:
        """Assets, then audio, then scaffolds: the order conversion runs them."""
        return [*self.assets, *self.audio, *self.scaffolds]


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _blend_sources(root: Path) -> list[Path]:
    base = root / SOURCE_ART
    if not base.is_dir():
        return []
    return sorted(
        path for path in base.rglob("*") if path.is_file() and path.suffix.lower() == ".blend"
    )


def _find_source(
    root: Path, name: str, blends: list[Path]
) -> tuple[Path | None, PipelineError | None]:
    matches = [path for path in blends if path.stem.lower() == name.lower()]
    if len(matches) == 1:
        return matches[0], None
    if not matches:
        return None, convert_error(
            "convert.source_missing",
            f"No SourceArt/**/{name}.blend was found for the asset {name}.",
            f"Add the asset's Blender source as SourceArt/<folder>/{name}.blend, then rerun "
            "/convert-to-godot.",
        )
    found = ", ".join(_rel(root, path) for path in matches)
    return None, convert_error(
        "convert.source_ambiguous",
        f"Several Blender sources match the asset {name}: {found}.",
        f"Keep exactly one SourceArt/**/{name}.blend (names are compared case-insensitively), "
        "then rerun /convert-to-godot.",
    )


def _asset_class(sidecar: Path) -> tuple[str, PipelineError | None]:
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        data = None
        detail = str(error)
    else:
        detail = "it has no string 'class'"
    if isinstance(data, dict) and isinstance(data.get("class"), str) and data["class"]:
        return str(data["class"]), None
    return "", convert_error(
        "convert.sidecar_invalid",
        f"{sidecar} cannot be read: {detail}.",
        "Restore the asset's Mobile/nmg-asset.json from git, then rerun /convert-to-godot.",
    )


def _assets(root: Path) -> list[AssetItem]:
    content = root / CONTENT
    if not content.is_dir():
        return []
    blends = _blend_sources(root)
    items: list[AssetItem] = []
    for sidecar in sorted(content.glob(f"*/*/Mobile/{SIDECAR}")):
        folder = sidecar.parent.parent
        category, name = folder.parent.name, folder.name
        asset_class, problem = _asset_class(sidecar)
        source: Path | None = None
        if problem is None:
            source, problem = _find_source(root, name, blends)
        items.append(AssetItem(category, name, asset_class, source, problem))
    return items


def _audio(root: Path) -> list[AudioItem]:
    items: list[AudioItem] = []
    for kind, loop in AUDIO_KINDS:
        folder = root / SOURCE_ART / "Audio" / kind
        if not folder.is_dir():
            continue
        for wav in sorted(folder.iterdir()):
            if wav.is_file() and wav.suffix.lower() == ".wav":
                items.append(AudioItem(kind, wav.stem, wav, loop))
    return items


def _scaffolds(root: Path) -> list[ScaffoldItem]:
    path = root / BACKLOG
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise convert_error(
            "convert.backlog_invalid",
            f"{BACKLOG.as_posix()} cannot be read: {error}.",
            "Run /design sync to rewrite the backlog, then rerun /convert-to-godot.",
        ) from error
    entries = data.get("entries") if isinstance(data, dict) else None
    items: list[ScaffoldItem] = []
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        if entry.get("type") in SCAFFOLD_TYPES and entry.get("status") == "scaffolded":
            items.append(ScaffoldItem(str(entry["type"]), str(entry.get("asset_name", ""))))
    return sorted(items, key=lambda item: (item.entry_type, item.name))


def _manual_port(root: Path, assets: list[AssetItem]) -> list[ManualPort]:
    rows: list[ManualPort] = []
    source = root / "Source"
    if source.is_dir():
        rows.extend(
            ManualPort(_rel(root, path), "C++ game code")
            for path in sorted(source.rglob("*"))
            if path.is_file()
        )
    content = root / CONTENT
    if content.is_dir():
        finalized = {content / item.category / item.name for item in assets}
        for path in sorted(content.rglob("*")):
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            if suffix == ".umap":
                rows.append(ManualPort(_rel(root, path), "level"))
            elif suffix == ".uasset" and not any(folder in path.parents for folder in finalized):
                rows.append(ManualPort(_rel(root, path), "asset that finalize did not produce"))
    return rows


def _deletions(root: Path) -> list[str]:
    found = [name + "/" for name in DELETION_DIRS if (root / name).is_dir()]
    found.extend(path.name for path in sorted(root.glob("*.uproject")) if path.is_file())
    found.extend(rel for rel in UNREAL_SCRIPTS if (root / rel).is_file())
    return found


def discover(root: Path) -> ConversionPlan:
    """Read ``root`` and return its conversion plan without writing anything."""
    assets = _assets(root)
    return ConversionPlan(
        assets=assets,
        audio=_audio(root),
        scaffolds=_scaffolds(root),
        manual_port=_manual_port(root, assets),
        deletions=_deletions(root),
    )
