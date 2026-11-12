"""pytest-bdd bindings for texture_contact_sheet.feature: SCN001-SCN008 (#152).

Synthetic PNG albedos and manifests, the fake worker, and in-process calls to the CLI and the MCP
tool. No model, editor, or network is used. Where a scenario says the rebuild needs no backend, both
hardware probes are patched to fail.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest
from PIL import Image as PILImage
from pytest_bdd import given, parsers, scenario, then, when

from nmg_game_dev.texture import contact_sheet, generate, hardware
from nmg_game_dev.texture.__main__ import main
from nmg_game_dev.texture.generate import TextureRequest
from nmg_game_dev.texture.sheet import GUTTER
from tests.texture_fakes import (
    APPLE_SILICON_32GB,
    fake_spawn,
    make_models,
    save_png,
    synthetic_image,
    write_fake_worker,
)

FEATURE = "texture_contact_sheet.feature"
REPO = Path(__file__).resolve().parents[2]
SERVER_FILE = REPO / "mcp-servers" / "texture-gen" / "src" / "texture_gen_mcp" / "server.py"
TOOLS_JSON = REPO / "mcp-servers" / "texture-gen" / "tools.json"
TILE = 192
ROW_PITCH = contact_sheet.CELL + contact_sheet.LABEL_HEIGHT + GUTTER


def _make_set(
    root: Path, name: str, albedos: list[tuple[str, int]], *, derived: bool = False
) -> Path:
    """A texture set: an albedo PNG per (backend, seed) and its manifest, plus optional derived
    maps and a comparison sheet that must never become cells."""
    folder = root / name
    images: list[dict[str, Any]] = []
    for backend, seed in albedos:
        albedo = save_png(synthetic_image(256, seed=seed), folder / f"{backend}_{seed}_256.png")
        images.append({"backend": backend, "seed": seed, "path": str(albedo)})
        if derived:
            for suffix in ("_N", "_R"):
                save_png(
                    synthetic_image(256, seed=seed + 50),
                    folder / f"{backend}_{seed}_256{suffix}.png",
                )
    if derived:
        save_png(synthetic_image(256, seed=1), folder / f"{name}_compare.png")
    manifest = {"name": name, "images": images}
    (folder / "textures.json").write_text(json.dumps(manifest), encoding="utf-8")
    return folder


def _load_server() -> ModuleType:
    src = str(SERVER_FILE.parents[1])
    if src not in sys.path:
        sys.path.insert(0, src)
    spec = importlib.util.spec_from_file_location(
        "texture_gen_server_contact_sheet_bdd", SERVER_FILE
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _assert_cells_tiled(page_path: Path, cells: list[contact_sheet.Cell]) -> None:
    """Every cell on the page is its albedo at 192 px, repeated 2x2, with a drawn label strip."""
    page = np.asarray(PILImage.open(page_path).convert("RGB"))
    background = np.array(contact_sheet.BACKGROUND, dtype=np.uint8)
    for index, cell in enumerate(cells):
        x = GUTTER + (index % contact_sheet.COLUMNS) * (contact_sheet.CELL + GUTTER)
        y = GUTTER + (index // contact_sheet.COLUMNS) * ROW_PITCH
        albedo = PILImage.open(cell.path).convert("RGB")
        expected = np.asarray(albedo.resize((TILE, TILE), PILImage.Resampling.LANCZOS))
        for dx in (0, TILE):
            for dy in (0, TILE):
                tile = page[y + dy : y + dy + TILE, x + dx : x + dx + TILE]
                assert np.array_equal(tile, expected)
        top = y + contact_sheet.CELL
        label = page[top : top + contact_sheet.LABEL_HEIGHT, x : x + contact_sheet.CELL]
        assert np.any(label != background)


# --- SCN001 ------------------------------


@scenario(FEATURE, "Generate refreshes a root-wide contact sheet")
def test_generate_refreshes_a_root_wide_contact_sheet() -> None:
    """AC1: a generate run refreshes the root sheet and reports it in its JSON result."""


@given(
    parsers.parse('an output root holding the texture set "{name}" with one albedo'),
    target_fixture="ctx",
)
def _root_holding_one_set(tmp_path: Path, name: str) -> dict[str, Any]:
    root = tmp_path / "out"
    _make_set(root, name, [("z-image-turbo", 1)])
    return {"tmp": tmp_path, "root": root}


@when(parsers.parse('a generate run for "{name}" succeeds with the fake worker'))
def _generate_with_fake_worker(ctx: dict[str, Any], name: str) -> None:
    worker = write_fake_worker(ctx["tmp"] / "worker")
    env = {"TEXTURE_GEN_MODELS_DIR": str(make_models(ctx["tmp"] / "models"))}
    request = TextureRequest(
        prompt=name, backend="z-image-turbo", seeds=[2], resolution=256, name=name
    )
    ctx["result"] = generate.run(
        request,
        env=env,
        facts=APPLE_SILICON_32GB,
        spawn=fake_spawn(worker, ctx["tmp"] / "worker.log"),
        output_root_override=ctx["root"],
    )


@then(parsers.parse("the output root holds contact_sheet_001.png with {count:d} cells"))
def _root_holds_first_page(ctx: dict[str, Any], count: int) -> None:
    assert (ctx["root"] / "contact_sheet_001.png").is_file()
    assert ctx["result"].contact_sheet.cells == count


@then(
    parsers.parse(
        "the run's JSON result has contact_sheet with that page, cells {count:d}, "
        "and no skipped entries"
    )
)
def _run_json_has_the_sheet(ctx: dict[str, Any], count: int) -> None:
    assert ctx["result"].as_json()["contact_sheet"] == {
        "pages": [str(ctx["root"] / "contact_sheet_001.png")],
        "cells": count,
        "skipped": [],
    }


# --- SCN002 ------------------------------


@scenario(FEATURE, "Each cell shows the albedo tiled 2x2 with its name label")
def test_each_cell_shows_the_albedo_tiled_with_its_name_label() -> None:
    """AC2: cells come from manifests only, ordered by set, backend, and seed, tiled 2x2."""


@given(
    parsers.parse(
        'texture sets "{first}" and "{second}" whose folders also hold _N, _R, and '
        "_compare.png files"
    ),
    target_fixture="ctx",
)
def _two_sets_with_derived_files(tmp_path: Path, first: str, second: str) -> dict[str, Any]:
    root = tmp_path / "out"
    _make_set(root, first, [("z-image-turbo", 1)], derived=True)
    _make_set(
        root,
        second,
        [("z-image-turbo", 3), ("flux2-klein-4b", 9), ("flux2-klein-4b", 2)],
        derived=True,
    )
    return {"root": root}


@when("the contact sheet is built")
def _build_the_sheet(ctx: dict[str, Any]) -> None:
    ctx["sheet"] = contact_sheet.build(ctx["root"], require_sets=True)
    ctx["cells"], _ = contact_sheet.collect(ctx["root"])


@then('the cells are ordered "a-wood" before "b-stone", then by backend and seed')
def _cells_are_ordered(ctx: dict[str, Any]) -> None:
    assert [(c.set_name, c.backend, c.seed) for c in ctx["cells"]] == [
        ("a-wood", "flux2-klein-4b", 2),
        ("a-wood", "flux2-klein-4b", 9),
        ("a-wood", "z-image-turbo", 3),
        ("b-stone", "z-image-turbo", 1),
    ]


@then(
    "each cell is its albedo repeated 2x2 under a label with the set name and the backend and seed"
)
def _cells_are_tiled_with_labels(ctx: dict[str, Any]) -> None:
    _assert_cells_tiled(ctx["sheet"].pages[0], ctx["cells"])


@then("no derived map or comparison sheet is a cell")
def _no_derived_cells(ctx: dict[str, Any]) -> None:
    names = [cell.path.name for cell in ctx["cells"]]
    assert len(names) == 4 and ctx["sheet"].cells == 4
    assert all(name.endswith("_256.png") for name in names)


# --- SCN003 ------------------------------


@scenario(FEATURE, "The sheet command rebuilds on demand")
def test_the_sheet_command_rebuilds_on_demand() -> None:
    """AC3: the sheet command rebuilds the pages, prints JSON, and exits 0."""


@given("an output root with texture sets", target_fixture="ctx")
def _root_with_texture_sets(tmp_path: Path) -> dict[str, Any]:
    root = tmp_path / "out"
    _make_set(root, "rusted-steel", [("z-image-turbo", 1)])
    _make_set(root, "oak-planks", [("flux2-klein-4b", 2)])
    return {"root": root}


@when('"python -m nmg_game_dev.texture sheet --root <root>" runs')
def _sheet_command_runs(ctx: dict[str, Any], capsys: pytest.CaptureFixture[str]) -> None:
    ctx["exit"] = main(["sheet", "--root", str(ctx["root"])])
    ctx["stdout"] = capsys.readouterr().out


@then("it prints JSON with pages, cells, and skipped")
def _prints_the_json(ctx: dict[str, Any]) -> None:
    printed = json.loads(ctx["stdout"])
    assert set(printed) == {"pages", "cells", "skipped"}
    assert printed["cells"] == 2
    assert printed["pages"] == [str(ctx["root"] / "contact_sheet_001.png")]


@then("it exits 0")
def _exits_zero(ctx: dict[str, Any]) -> None:
    assert ctx["exit"] == 0


# --- SCN004 ------------------------------


@scenario(FEATURE, "The texture_contact_sheet tool rebuilds on demand")
def test_the_texture_contact_sheet_tool_rebuilds_on_demand() -> None:
    """AC4: the MCP tool rebuilds the sheet for the output root and is declared in tools.json."""


@given(
    "the texture-gen MCP server with NMG_GAME_DEV_TEXTURE_DIR pointing at an output root "
    "with texture sets",
    target_fixture="ctx",
)
def _server_pointed_at_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    root = tmp_path / "out"
    _make_set(root, "rusted-steel", [("z-image-turbo", 1)])
    monkeypatch.setenv("NMG_GAME_DEV_TEXTURE_DIR", str(root))
    return {"root": root, "server": _load_server()}


@when("the texture_contact_sheet tool is called")
def _tool_is_called(ctx: dict[str, Any]) -> None:
    ctx["tool"] = ctx["server"].texture_contact_sheet()


@then("it returns pages, cells, and skipped")
def _tool_returns_the_keys(ctx: dict[str, Any]) -> None:
    assert set(ctx["tool"]) == {"pages", "cells", "skipped"}
    assert ctx["tool"]["cells"] == 1


@then("tools.json declares texture_contact_sheet")
def _tools_json_declares_the_tool(ctx: dict[str, Any]) -> None:
    declared = {
        tool["name"] for tool in json.loads(TOOLS_JSON.read_text(encoding="utf-8"))["tools"]
    }
    assert "texture_contact_sheet" in declared


# --- SCN005 ------------------------------


@scenario(FEATURE, "Large roots page into numbered sheets")
def test_large_roots_page_into_numbered_sheets() -> None:
    """AC5: 24 cells per page, every page reported, and stale higher pages removed."""


@given(
    "an output root with 25 albedos and a stale contact_sheet_003.png",
    target_fixture="ctx",
)
def _root_with_25_albedos(tmp_path: Path) -> dict[str, Any]:
    root = tmp_path / "out"
    _make_set(root, "many", [("z-image-turbo", seed) for seed in range(25)])
    save_png(synthetic_image(64), root / "contact_sheet_003.png")
    return {"root": root}


@then("contact_sheet_001.png holds 24 cells and contact_sheet_002.png holds 1")
def _first_page_is_full(ctx: dict[str, Any]) -> None:
    first, second = ctx["sheet"].pages
    assert PILImage.open(first).size[1] == GUTTER + 4 * ROW_PITCH
    assert PILImage.open(second).size[1] == GUTTER + ROW_PITCH
    assert ctx["sheet"].cells == 25


@then("both page paths are reported")
def _both_pages_reported(ctx: dict[str, Any]) -> None:
    assert [p.name for p in ctx["sheet"].pages] == [
        "contact_sheet_001.png",
        "contact_sheet_002.png",
    ]
    assert ctx["sheet"].as_json()["pages"] == [str(p) for p in ctx["sheet"].pages]


@then("contact_sheet_003.png no longer exists")
def _stale_page_removed(ctx: dict[str, Any]) -> None:
    assert not (ctx["root"] / "contact_sheet_003.png").exists()


# --- SCN006 ------------------------------


@scenario(FEATURE, "Unreadable albedos are skipped without failing")
def test_unreadable_albedos_are_skipped_without_failing() -> None:
    """AC6: a missing albedo and a non-image albedo are listed under skipped; the rest render."""


@given(
    "an output root where one manifest lists a missing albedo and another lists a file "
    "that is not an image",
    target_fixture="ctx",
)
def _root_with_unreadable_albedos(tmp_path: Path) -> dict[str, Any]:
    root = tmp_path / "out"
    _make_set(root, "steady", [("z-image-turbo", 1)])
    gone = _make_set(root, "gone", [("z-image-turbo", 2)])
    missing = gone / "z-image-turbo_2_256.png"
    missing.unlink()
    not_image = root / "notimage" / "z-image-turbo_3_256.png"
    not_image.parent.mkdir(parents=True)
    not_image.write_bytes(b"this is not a png")
    manifest = {"images": [{"backend": "z-image-turbo", "seed": 3, "path": str(not_image)}]}
    (root / "notimage" / "textures.json").write_text(json.dumps(manifest), encoding="utf-8")
    return {"root": root, "missing": missing, "not_image": not_image}


@then("both are listed under skipped with their path and reason")
def _both_listed_as_skipped(ctx: dict[str, Any]) -> None:
    skipped = {entry["path"]: entry["reason"] for entry in ctx["sheet"].skipped}
    assert set(skipped) == {str(ctx["missing"]), str(ctx["not_image"])}
    assert all(reason for reason in skipped.values())


@then("the remaining albedos appear as cells")
def _remaining_albedos_render(ctx: dict[str, Any]) -> None:
    assert ctx["sheet"].cells == 1
    assert (ctx["root"] / "contact_sheet_001.png").is_file()


# --- SCN007 ------------------------------


@scenario(FEATURE, "An empty root reports an error on demand")
def test_an_empty_root_reports_an_error_on_demand() -> None:
    """AC7: the sheet command exits 1 with the error; the tool returns the structured error."""


@given("an output root with no texture sets", target_fixture="ctx")
def _empty_root(tmp_path: Path) -> dict[str, Any]:
    root = tmp_path / "empty"
    root.mkdir()
    return {"root": root}


@when("the sheet command runs")
def _sheet_command_runs_empty(ctx: dict[str, Any], capsys: pytest.CaptureFixture[str]) -> None:
    ctx["exit"] = main(["sheet", "--root", str(ctx["root"])])
    ctx["stderr"] = capsys.readouterr().err


@then('stderr has "ERROR [texture.no_texture_sets]" and a "Remediation:" line')
def _stderr_has_the_error(ctx: dict[str, Any]) -> None:
    assert "ERROR [texture.no_texture_sets]" in ctx["stderr"]
    assert "Remediation:" in ctx["stderr"]


@then("it exits 1")
def _exits_one(ctx: dict[str, Any]) -> None:
    assert ctx["exit"] == 1


@then("the texture_contact_sheet tool returns the error code texture.no_texture_sets")
def _tool_returns_the_error(ctx: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NMG_GAME_DEV_TEXTURE_DIR", str(ctx["root"]))
    result = _load_server().texture_contact_sheet()
    assert result["error"]["code"] == "texture.no_texture_sets"


# --- SCN008 ------------------------------


@scenario(FEATURE, "The rebuild needs no texture backend")
def test_the_rebuild_needs_no_texture_backend() -> None:
    """AC8: the rebuild runs when the hardware probe would fail and no weights are installed."""


@given(
    "a host with no texture model weights whose hardware probe would fail",
    target_fixture="ctx",
)
def _host_without_weights(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    def refuse() -> None:
        raise AssertionError("the contact sheet rebuild must not probe the host")

    monkeypatch.setattr(generate, "probe", refuse)
    monkeypatch.setattr(hardware, "probe", refuse)
    monkeypatch.delenv("TEXTURE_GEN_MODELS_DIR", raising=False)
    return {"tmp": tmp_path}


@when("the sheet command runs on an output root with texture sets")
def _sheet_command_runs_without_backend(
    ctx: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    root = ctx["tmp"] / "out"
    _make_set(root, "steel", [("flux2-klein-4b", 1)])
    ctx["root"] = root
    ctx["exit"] = main(["sheet", "--root", str(root)])
    ctx["stdout"] = capsys.readouterr().out


@then("the contact sheet is built")
def _sheet_is_built(ctx: dict[str, Any]) -> None:
    assert ctx["exit"] == 0
    assert (ctx["root"] / "contact_sheet_001.png").is_file()
    assert json.loads(ctx["stdout"])["cells"] == 1
