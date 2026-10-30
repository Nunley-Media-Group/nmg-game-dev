"""Operator parity (AC4): each rig operator stores the direct result and reports its status."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

bpy = pytest.importorskip("bpy")

from .rig_fixtures import HERO_LANDMARKS, build_hero, build_library, reset_scene  # noqa: E402


@pytest.fixture()
def rig_core(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.rig_core")


@pytest.fixture()
def landmarks_file(tmp_path: Path) -> Path:
    path = tmp_path / "landmarks.json"
    path.write_text(json.dumps(HERO_LANDMARKS), encoding="utf-8")
    return path


def _stored_result() -> dict[str, Any]:
    return json.loads(bpy.context.scene.nmg_game_dev.last_result)


def _run_operator(operator: Any, **kwargs: Any) -> set[str]:
    """Run an operator; Blender raises RuntimeError when it reports an error, so catch that."""
    try:
        return set(operator(**kwargs))
    except RuntimeError:
        return {"CANCELLED"}


def test_ac4_rig_operator_stores_the_direct_result_and_finishes(
    rig_core: Any, landmarks_file: Path
) -> None:
    reset_scene()
    direct = rig_core.rig_humanoid("Hero", "humanoid", build_hero())

    outcome = _run_operator(
        bpy.ops.nmggamedev.rig_humanoid,
        collection_name="Hero",
        body_type="humanoid",
        landmarks_path=str(landmarks_file),
    )

    assert outcome == {"FINISHED"}
    assert direct["status"] == "ok"
    assert _stored_result() == direct


def test_ac4_rig_operator_cancels_with_the_direct_code(rig_core: Any, landmarks_file: Path) -> None:
    reset_scene()
    build_hero()
    direct = rig_core.rig_humanoid("Hero", "quadruped", HERO_LANDMARKS)

    outcome = _run_operator(
        bpy.ops.nmggamedev.rig_humanoid,
        collection_name="Hero",
        body_type="quadruped",
        landmarks_path=str(landmarks_file),
    )

    assert outcome == {"CANCELLED"}
    assert direct["code"] == "rig.unsupported_body"
    assert _stored_result() == direct


def test_ac4_rig_operator_reports_unreadable_landmarks(rig_core: Any, tmp_path: Path) -> None:
    reset_scene()
    build_hero()

    outcome = _run_operator(
        bpy.ops.nmggamedev.rig_humanoid,
        collection_name="Hero",
        body_type="humanoid",
        landmarks_path=str(tmp_path / "missing.json"),
    )

    assert outcome == {"CANCELLED"}
    assert _stored_result()["code"] == "rig.landmarks_missing"


def test_ac4_import_and_export_operators_match_direct_calls(
    rig_core: Any, landmarks_file: Path, tmp_path: Path
) -> None:
    reset_scene()
    assert rig_core.rig_humanoid("Hero", "humanoid", build_hero())["status"] == "ok"
    library = build_library(tmp_path / "library")

    import_outcome = _run_operator(
        bpy.ops.nmggamedev.import_animations,
        collection_name="Hero",
        library_dir=str(library),
        clips="Idle, Walk",
        motion_prompt="",
    )
    direct_import = rig_core.import_animations("Hero", str(library), ["Idle", "Walk"])

    assert import_outcome == {"FINISHED"}
    assert _stored_result() == direct_import
    assert [clip["name"] for clip in direct_import["clips"]] == ["Idle", "Walk"]

    out_dir = tmp_path / "out"
    export_outcome = _run_operator(
        bpy.ops.nmggamedev.export_rigged,
        collection_name="Hero",
        out_dir=str(out_dir),
    )
    direct_export = rig_core.export_rigged("Hero", str(out_dir))

    assert export_outcome == {"FINISHED"}
    assert _stored_result() == direct_export
    assert (out_dir / "SM_Hero.fbx").is_file()


def test_ac4_import_operator_cancels_on_unknown_clip(rig_core: Any, tmp_path: Path) -> None:
    reset_scene()
    assert rig_core.rig_humanoid("Hero", "humanoid", build_hero())["status"] == "ok"
    library = build_library(tmp_path / "library")

    outcome = _run_operator(
        bpy.ops.nmggamedev.import_animations,
        collection_name="Hero",
        library_dir=str(library),
        clips="Run",
        motion_prompt="",
    )

    assert outcome == {"CANCELLED"}
    assert _stored_result()["code"] == "anim.clip_not_found"
