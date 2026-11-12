"""The root-wide contact sheet (#152 AC2, AC5-AC8): cell order and labels, 2x2 tiling, paging,
skipped albedos, the on-demand error, a moved root, and a rebuild that needs no backend."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest
from PIL import Image as PILImage

from nmg_game_dev.texture import generate, hardware
from nmg_game_dev.texture.contact_sheet import ContactSheet, build, collect
from nmg_game_dev.texture.errors import TextureGenError
from nmg_game_dev.texture.sheet import GUTTER
from tests.texture_fakes import save_png, synthetic_image

TILE = 192
CELL = 384
LABEL = 40
ROW_PITCH = CELL + LABEL + GUTTER
PAGE_WIDTH = 6 * CELL + 7 * GUTTER
ONE_ROW_HEIGHT = GUTTER + ROW_PITCH
BACKGROUND = np.array((24, 24, 24), dtype=np.uint8)


def _write_set(root: Path, name: str, images: list[tuple[str, int]]) -> Path:
    """A texture set: one albedo PNG per (backend, seed) and the manifest that lists them."""
    folder = root / name
    entries = []
    for backend, seed in images:
        albedo = save_png(synthetic_image(256, seed=seed), folder / f"{backend}_{seed}_256.png")
        entries.append({"backend": backend, "seed": seed, "path": str(albedo)})
    (folder / "textures.json").write_text(
        json.dumps({"name": name, "images": entries}), encoding="utf-8"
    )
    return folder


def _cell_origin(index: int) -> tuple[int, int]:
    return (
        GUTTER + (index % 6) * (CELL + GUTTER),
        GUTTER + (index // 6) * ROW_PITCH,
    )


def test_cells_come_from_manifest_entries_in_set_backend_seed_order(tmp_path: Path) -> None:
    root = tmp_path / "root"
    _write_set(root, "b-stone", [("z-image-turbo", 1)])
    _write_set(root, "a-wood", [("z-image-turbo", 3), ("flux2-klein-4b", 9), ("flux2-klein-4b", 2)])

    cells, skipped = collect(root)

    assert [(c.set_name, c.backend, c.seed) for c in cells] == [
        ("a-wood", "flux2-klein-4b", 2),
        ("a-wood", "flux2-klein-4b", 9),
        ("a-wood", "z-image-turbo", 3),
        ("b-stone", "z-image-turbo", 1),
    ]
    assert all(c.path.parent == root / c.set_name and c.path.is_file() for c in cells)
    assert skipped == []


def test_derived_maps_and_comparison_sheets_are_never_cells(tmp_path: Path) -> None:
    root = tmp_path / "root"
    folder = _write_set(root, "stone", [("z-image-turbo", 5)])
    for suffix in ("_N", "_R", "_M", "_AO"):
        save_png(synthetic_image(256, seed=6), folder / f"z-image-turbo_5_256{suffix}.png")
    save_png(synthetic_image(256, seed=7), folder / "stone_compare.png")

    cells, _ = collect(root)

    assert [c.path.name for c in cells] == ["z-image-turbo_5_256.png"]


def test_each_cell_is_the_albedo_tiled_two_by_two_with_a_label(tmp_path: Path) -> None:
    root = tmp_path / "root"
    _write_set(root, "oak", [("z-image-turbo", 4)])

    sheet = build(root, require_sets=True)

    page = np.asarray(PILImage.open(sheet.pages[0]).convert("RGB"))
    albedo = PILImage.open(root / "oak" / "z-image-turbo_4_256.png").convert("RGB")
    expected = np.asarray(albedo.resize((TILE, TILE), PILImage.Resampling.LANCZOS))
    x, y = _cell_origin(0)
    for dx in (0, TILE):
        for dy in (0, TILE):
            tile = page[y + dy : y + dy + TILE, x + dx : x + dx + TILE]
            assert np.array_equal(tile, expected)
    label = page[y + CELL : y + CELL + LABEL, x : x + CELL]
    assert np.any(label != BACKGROUND)


def test_a_page_of_six_cells_is_one_row_tall_and_six_cells_wide(tmp_path: Path) -> None:
    root = tmp_path / "root"
    _write_set(root, "row", [("z-image-turbo", seed) for seed in range(6)])

    sheet = build(root, require_sets=True)

    assert sheet.cells == 6 and len(sheet.pages) == 1
    assert PILImage.open(sheet.pages[0]).size == (PAGE_WIDTH, ONE_ROW_HEIGHT)


def test_twenty_five_albedos_make_two_pages_and_a_stale_third_page_is_removed(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    _write_set(root, "many", [("z-image-turbo", seed) for seed in range(25)])
    stale = save_png(synthetic_image(64), root / "contact_sheet_003.png")

    sheet = build(root, require_sets=True)

    assert [p.name for p in sheet.pages] == ["contact_sheet_001.png", "contact_sheet_002.png"]
    assert sheet.cells == 25 and sheet.skipped == ()
    assert PILImage.open(sheet.pages[0]).size == (PAGE_WIDTH, GUTTER + 4 * ROW_PITCH)
    assert PILImage.open(sheet.pages[1]).size == (PAGE_WIDTH, ONE_ROW_HEIGHT)
    assert not stale.exists()
    assert sheet.as_json()["pages"] == [str(p) for p in sheet.pages]


def test_missing_and_non_image_albedos_and_unreadable_manifests_are_skipped(tmp_path: Path) -> None:
    root = tmp_path / "root"
    _write_set(root, "steady", [("z-image-turbo", 1)])
    gone = _write_set(root, "gone", [("z-image-turbo", 2)])
    missing = gone / "z-image-turbo_2_256.png"
    missing.unlink()
    not_image = root / "notimage" / "z-image-turbo_3_256.png"
    not_image.parent.mkdir(parents=True)
    not_image.write_bytes(b"this is not a png")
    (root / "notimage" / "textures.json").write_text(
        json.dumps({"images": [{"backend": "z-image-turbo", "seed": 3, "path": str(not_image)}]}),
        encoding="utf-8",
    )
    broken = root / "broken"
    broken.mkdir()
    (broken / "textures.json").write_text("{not json", encoding="utf-8")

    sheet = build(root, require_sets=True)

    assert sheet.cells == 1
    assert len(sheet.pages) == 1
    skipped = {entry["path"]: entry["reason"] for entry in sheet.skipped}
    assert set(skipped) == {str(missing), str(not_image), str(broken / "textures.json")}
    assert all(reason for reason in skipped.values())
    assert skipped[str(broken / "textures.json")].startswith("unreadable manifest:")


@pytest.mark.parametrize("empty_root", [False, True], ids=["missing-root", "empty-root"])
def test_a_root_without_texture_sets_raises_no_texture_sets_on_demand(
    tmp_path: Path, empty_root: bool
) -> None:
    root = tmp_path / "root"
    if empty_root:
        root.mkdir()

    with pytest.raises(TextureGenError) as caught:
        build(root, require_sets=True)

    assert caught.value.code == "texture.no_texture_sets"
    assert str(root) in caught.value.message
    assert "Generate a texture first" in caught.value.remediation
    assert "--root" in caught.value.remediation


def test_a_generate_style_build_on_an_empty_root_writes_nothing(tmp_path: Path) -> None:
    assert build(tmp_path / "missing", require_sets=False) == ContactSheet()


def test_a_moved_root_still_builds(tmp_path: Path) -> None:
    root = tmp_path / "root"
    _write_set(root, "wood", [("z-image-turbo", 8)])
    build(root, require_sets=True)
    moved = tmp_path / "elsewhere"
    shutil.move(str(root), str(moved))

    sheet = build(moved, require_sets=True)

    assert sheet.cells == 1 and sheet.skipped == ()
    assert sheet.pages == (moved / "contact_sheet_001.png",)
    assert sheet.pages[0].is_file()


def test_the_rebuild_calls_no_backend_or_hardware_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse() -> None:
        raise AssertionError("the contact sheet rebuild must not probe the host")

    monkeypatch.setattr(generate, "probe", refuse)
    monkeypatch.setattr(hardware, "probe", refuse)
    monkeypatch.delenv("TEXTURE_GEN_MODELS_DIR", raising=False)
    root = tmp_path / "root"
    _write_set(root, "steel", [("flux2-klein-4b", 1)])

    sheet = build(root, require_sets=True)

    assert sheet.cells == 1
