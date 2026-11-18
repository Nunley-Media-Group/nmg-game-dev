"""Terrain requests route import_godot to the chunked terrain scene import (#154, #249 FR4, AC4).

The real orchestrator, cache, gates, envelope handling and ``godot.terrain`` run.
``TerrainStepRunner`` is the Blender fake with a terrain export (chunks, 16-bit heightmap, splat,
layer textures).  ``FinalizeGodot`` answers ``probe_terrain.gd`` from the ``.tscn`` the import
wrote, so the reported collision range is the one decoded from the heightmap.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from nmg_game_dev.pipeline import FinalizeClients, FinalizeRequest, PipelineError, finalize
from tests.finalize_fakes import FinalizeGodot, TerrainStepRunner, terrain_entry


@pytest.fixture()
def terrain_request(tmp_path: Path) -> FinalizeRequest:
    blend = tmp_path / "hills.blend"
    blend.write_bytes(b"authored")
    return FinalizeRequest(
        collection="Hills",
        category="Environment",
        asset_class="terrain",
        export_root=tmp_path / "export",
        blend=blend,
    )


def _finalize(request: FinalizeRequest, tmp_path: Path, runner: Any, godot: FinalizeGodot) -> Any:
    return finalize(
        request,
        cache_dir=tmp_path / "cache",
        runner=runner,
        job_dir=tmp_path / "job",
        clients=FinalizeClients(godot=godot),
    )


def test_a_terrain_imports_both_scenes_with_one_import(
    terrain_request: FinalizeRequest, tmp_path: Path
) -> None:
    godot = FinalizeGodot(tmp_path)

    result = _finalize(terrain_request, tmp_path, TerrainStepRunner(terrain_request), godot)

    assert result.desktop_resource_path == "res://export/Environment/Hills/Desktop/Hills.tscn"
    assert result.mobile_resource_path == "res://export/Environment/Hills/Mobile/Hills.tscn"
    assert godot.calls[0] == ["--import"]
    assert godot.count("--import") == 1
    assert [params["mode"] for params in godot.params] == ["meshes", "scene", "scene"]
    assert godot.probe_calls("probe_asset.gd") == []
    imported = next(step for step in result.steps if step.step == "import_godot")
    desktop = imported.outputs["imports"]["Desktop"]
    assert desktop["chunks"] == 4  # (127 - 1) / 63 = 2 per side
    assert desktop["height_min"] == pytest.approx(10.0)
    assert desktop["height_max"] == pytest.approx(40.0)


def test_the_scene_instances_every_chunk_with_heightmap_collision(
    terrain_request: FinalizeRequest, tmp_path: Path
) -> None:
    _finalize(
        terrain_request, tmp_path, TerrainStepRunner(terrain_request), FinalizeGodot(tmp_path)
    )

    scene = (tmp_path / "export/Environment/Hills/Mobile/Hills.tscn").read_text(encoding="utf-8")
    assert scene.startswith("[gd_scene ")
    assert "format=3" in scene.splitlines()[0]
    for row in range(2):
        for col in range(2):
            chunk = f"Hills_Chunk_{row}_{col}"
            assert f'path="res://export/Environment/Hills/Mobile/{chunk}.glb"' in scene
            assert (
                f'[node name="{chunk}" parent="." instance=ExtResource("chunk_{chunk}")]' in scene
            )
            assert f'[node name="Mesh" parent="{chunk}"]' in scene
    assert 'path="res://addons/nmg_game_dev/terrain/nmg_terrain.gdshader"' in scene
    assert '[node name="Hills" type="Node3D"]' in scene
    assert 'type="StaticBody3D"' in scene
    assert 'type="CollisionShape3D"' in scene
    assert "map_width = 127" in scene
    assert "map_depth = 127" in scene
    # Mobile spacing is 2 m, so the shape is scaled (2, 1, 2).
    assert "transform = Transform3D(2, 0, 0, 0, 1, 0, 0, 0, 2, 0, 0, 0)" in scene


def test_a_missing_chunk_is_mismatch_before_godot_runs(
    terrain_request: FinalizeRequest, tmp_path: Path
) -> None:
    godot = FinalizeGodot(tmp_path)
    runner = TerrainStepRunner(terrain_request, skip_chunks=["Hills_Chunk_1_1.glb"])

    with pytest.raises(PipelineError) as info:
        _finalize(terrain_request, tmp_path, runner, godot)

    assert info.value.code == "import_godot.mismatch"
    assert "Hills_Chunk_1_1.glb" in info.value.message
    assert info.value.remediation
    assert godot.calls == []


def test_a_probe_range_off_by_more_than_five_centimetres_is_a_height_mismatch(
    terrain_request: FinalizeRequest, tmp_path: Path
) -> None:
    godot = FinalizeGodot(tmp_path, mesh_range=(10.0, 40.2))

    with pytest.raises(PipelineError) as info:
        _finalize(terrain_request, tmp_path, TerrainStepRunner(terrain_request), godot)

    assert info.value.code == "import_godot.terrain_height_mismatch"
    assert info.value.remediation
    assert godot.probe_calls("probe_anims.gd") == []


def test_a_range_within_tolerance_passes(terrain_request: FinalizeRequest, tmp_path: Path) -> None:
    godot = FinalizeGodot(tmp_path, mesh_range=(10.03, 39.97))

    result = _finalize(terrain_request, tmp_path, TerrainStepRunner(terrain_request), godot)

    assert result.desktop_resource_path is not None


def test_a_sidecar_without_the_mobile_entry_fails_before_godot_runs(
    terrain_request: FinalizeRequest, tmp_path: Path
) -> None:
    godot = FinalizeGodot(tmp_path)
    runner = TerrainStepRunner(terrain_request, entries={"desktop": terrain_entry("Desktop")})

    with pytest.raises(PipelineError) as info:
        _finalize(terrain_request, tmp_path, runner, godot)

    assert info.value.code == "import_godot.mismatch"
    assert "mobile" in info.value.message
    assert godot.calls == []


def test_a_validate_failure_stops_before_any_godot_call(
    terrain_request: FinalizeRequest, tmp_path: Path
) -> None:
    godot = FinalizeGodot(tmp_path)
    runner = TerrainStepRunner(terrain_request, failing_reports=frozenset({"validate"}))

    with pytest.raises(PipelineError) as info:
        _finalize(terrain_request, tmp_path, runner, godot)

    assert info.value.code == "quality.contract_failed"
    assert godot.calls == []


def test_terrain_clip_steps_are_no_ops(terrain_request: FinalizeRequest, tmp_path: Path) -> None:
    godot = FinalizeGodot(tmp_path)

    result = _finalize(terrain_request, tmp_path, TerrainStepRunner(terrain_request), godot)

    assert result.animations is not None
    assert result.animations["clips"] == []
    assert godot.probe_calls("probe_anims.gd") == []
