"""``discover``: assets with case-insensitive sources, audio, scaffolds, manual port, deletions."""

from __future__ import annotations

from pathlib import Path

from nmg_game_dev.convert.plan import AssetItem, AudioItem, ScaffoldItem, discover
from tests.convert_fakes import make_unreal_consumer, snapshot


def test_discover_lists_every_item_without_writing(tmp_path: Path) -> None:
    root = make_unreal_consumer(tmp_path / "Game", commit=False)
    before = snapshot(root)

    plan = discover(root)

    assert snapshot(root) == before
    assert plan.assets == [
        AssetItem("Characters", "Hero", "character", root / "SourceArt/Characters/HERO.blend"),
        AssetItem("Props", "Crate", "standard_prop", root / "SourceArt/Props/crate.blend"),
    ]
    assert plan.audio == [
        AudioItem("SFX", "Click", root / "SourceArt/Audio/SFX/Click.wav", False),
        AudioItem("Music", "Theme", root / "SourceArt/Audio/Music/Theme.wav", True),
    ]
    assert plan.scaffolds == [
        ScaffoldItem("mission", "Intro"),
        ScaffoldItem("region", "Harbor"),
        ScaffoldItem("system", "Inventory"),
    ]
    assert [item.key for item in plan.items] == [
        "asset:Characters/Hero",
        "asset:Props/Crate",
        "audio:SFX/Click",
        "audio:Music/Theme",
        "scaffold:mission/Intro",
        "scaffold:region/Harbor",
        "scaffold:system/Inventory",
    ]


def test_manual_port_lists_source_levels_and_unfinalized_uassets(tmp_path: Path) -> None:
    root = make_unreal_consumer(tmp_path / "Game", commit=False)
    rows = {row.path: row.reason for row in discover(root).manual_port}
    assert rows == {
        "Source/Game/Game.cpp": "C++ game code",
        "Source/Game/Game.h": "C++ game code",
        "Content/Maps/Main.umap": "level",
        "Content/Misc/Stray.uasset": "asset that finalize did not produce",
    }


def test_deletions_name_only_existing_unreal_paths(tmp_path: Path) -> None:
    root = make_unreal_consumer(tmp_path / "Game", commit=False)
    assert discover(root).deletions == [
        "Content/",
        "Source/",
        "Config/",
        "Plugins/",
        "Game.uproject",
        "scripts/start-unreal-mcp.sh",
    ]
    (root / "scripts" / "start-unreal-mcp.sh").unlink()
    for name in ("Config", "Plugins"):
        for path in sorted((root / name).rglob("*"), reverse=True):
            path.unlink() if path.is_file() else path.rmdir()
        (root / name).rmdir()
    assert discover(root).deletions == ["Content/", "Source/", "Game.uproject"]


def test_missing_source_is_an_item_problem(tmp_path: Path) -> None:
    root = make_unreal_consumer(tmp_path / "Game", commit=False)
    (root / "SourceArt" / "Props" / "crate.blend").unlink()
    crate = next(item for item in discover(root).assets if item.name == "Crate")
    assert crate.source is None
    assert crate.problem is not None
    assert crate.problem.code == "convert.source_missing"
    assert "Crate.blend" in crate.problem.remediation


def test_several_sources_are_ambiguous(tmp_path: Path) -> None:
    root = make_unreal_consumer(tmp_path / "Game", commit=False)
    other = root / "SourceArt" / "Old" / "CRATE.blend"
    other.parent.mkdir()
    other.write_bytes(b"blend")
    crate = next(item for item in discover(root).assets if item.name == "Crate")
    assert crate.problem is not None
    assert crate.problem.code == "convert.source_ambiguous"
    assert "SourceArt/Old/CRATE.blend" in crate.problem.message
    assert "SourceArt/Props/crate.blend" in crate.problem.message


def test_blend_backups_do_not_count_as_sources(tmp_path: Path) -> None:
    root = make_unreal_consumer(tmp_path / "Game", commit=False)
    (root / "SourceArt" / "Props" / "crate.blend1").write_bytes(b"backup")
    crate = next(item for item in discover(root).assets if item.name == "Crate")
    assert crate.problem is None


def test_unreadable_sidecar_is_an_item_problem(tmp_path: Path) -> None:
    root = make_unreal_consumer(tmp_path / "Game", commit=False)
    (root / "Content" / "Props" / "Crate" / "Mobile" / "nmg-asset.json").write_text("{")
    crate = next(item for item in discover(root).assets if item.name == "Crate")
    assert crate.problem is not None and crate.problem.code == "convert.sidecar_invalid"


def test_empty_project_plans_nothing(tmp_path: Path) -> None:
    plan = discover(tmp_path)
    assert plan.items == [] and plan.manual_port == [] and plan.deletions == []
