"""Unit tests for ``godot.import_asset`` (#249 FR1, AC1, AC2)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from nmg_game_dev.godot.import_asset import compare_meshes, import_variants
from nmg_game_dev.pipeline.errors import PipelineError
from tests.finalize_fakes import FinalizeGodot, asset_meshes


def _variants(root: Path, *, meshes: bool = True, glb: bool = True) -> dict[str, Path]:
    folders = {}
    for variant in ("Desktop", "Mobile"):
        folder = root / "assets" / "Props" / "Crate" / variant
        folder.mkdir(parents=True)
        if glb:
            (folder / "Crate.glb").write_bytes(b"glb")
        sidecar: dict[str, Any] = {"class": "standard_prop"}
        if meshes:
            sidecar["meshes"] = asset_meshes("Crate", variant)
        (folder / "nmg-asset.json").write_text(json.dumps(sidecar), encoding="utf-8")
        folders[variant] = folder
    return folders


def test_import_runs_once_and_probes_each_variant(tmp_path: Path) -> None:
    godot = FinalizeGodot(tmp_path)
    folders = _variants(tmp_path)

    result = import_variants(godot, tmp_path, name="Crate", variant_dirs=folders)

    assert godot.calls[0] == ["--import"]
    assert [params["glb"] for params in godot.params] == [
        "res://assets/Props/Crate/Desktop/Crate.glb",
        "res://assets/Props/Crate/Mobile/Crate.glb",
    ]
    assert result["Mobile"]["resource_path"] == "res://assets/Props/Crate/Mobile/Crate.glb"
    assert result["Desktop"]["material_variants"] == []


def test_a_missing_glb_fails_before_godot_runs(tmp_path: Path) -> None:
    godot = FinalizeGodot(tmp_path)
    with pytest.raises(PipelineError) as info:
        import_variants(godot, tmp_path, name="Crate", variant_dirs=_variants(tmp_path, glb=False))
    assert info.value.code == "import_godot.mismatch"
    assert godot.calls == []


def test_a_sidecar_without_meshes_fails_before_godot_runs(tmp_path: Path) -> None:
    godot = FinalizeGodot(tmp_path)
    with pytest.raises(PipelineError) as info:
        import_variants(
            godot, tmp_path, name="Crate", variant_dirs=_variants(tmp_path, meshes=False)
        )
    assert info.value.code == "import_godot.mismatch"
    assert "lists no meshes" in info.value.message
    assert godot.calls == []


def test_a_probe_without_a_meshes_list_is_import_failed(tmp_path: Path) -> None:
    godot = FinalizeGodot(tmp_path, responses={"probe_asset.gd": {"other": 1}})
    with pytest.raises(PipelineError) as info:
        import_variants(godot, tmp_path, name="Crate", variant_dirs=_variants(tmp_path))
    assert info.value.code == "import_godot.import_failed"


def _mesh(**changes: Any) -> dict[str, Any]:
    mesh: dict[str, Any] = {
        "name": "Crate",
        "tris": 12,
        "material_slots": 1,
        "bounds": {"min": [0.0, 0.0, 0.0], "max": [1.0, 1.0, 1.0]},
    }
    mesh.update(changes)
    return mesh


@pytest.mark.parametrize(
    ("measured", "fragment"),
    [
        ([], "Crate name"),
        ([_mesh(), _mesh(name="Extra")], "Extra name"),
        ([_mesh(tris=10)], "Crate tris: expected 12, imported 10"),
        ([_mesh(material_slots=2)], "Crate material_slots"),
        (
            [_mesh(bounds={"min": [0.0, -0.002, 0.0], "max": [1.0, 1.0, 1.0]})],
            "Crate bounds.min",
        ),
    ],
)
def test_compare_meshes_names_the_mesh_and_field(
    measured: list[dict[str, Any]], fragment: str
) -> None:
    with pytest.raises(PipelineError) as info:
        compare_meshes("Desktop", [_mesh()], measured)
    assert info.value.code == "import_godot.mismatch"
    assert fragment in info.value.message
    assert info.value.remediation


def test_compare_meshes_allows_a_millimetre() -> None:
    near = _mesh(bounds={"min": [0.0009, 0.0, 0.0], "max": [1.0, 0.9991, 1.0]})
    compare_meshes("Desktop", [_mesh()], [near])
