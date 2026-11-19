"""Blender proofs for shared_clip_names.feature: SCN001-SCN003, SCN007, and SCN008 of #233.

Each test here is the proof for one scenario, on real Blender data.
tests/bdd/test_shared_clip_names_bdd.py binds every scenario with pytest-bdd and runs these node
ids through scripts/run-blender-tests.sh, the same arrangement as
tests/bdd/test_rigged_animations_bdd.py.  pytest-bdd's ``scenario`` decorator is not used here,
because its fixture hook fails under the pytest that Blender bundles.

The rigs are built as test_finalize_anims.py builds them, so SCN001 to SCN003 use the names
StreetThug and Cop.  SCN007 and SCN008 build the rig_fixtures humanoids, Hero and Variant, to stand
for StreetThug and Cop, because rig_humanoid needs a collection the fixture builds.  Under plain
CPython the module is skipped.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

bpy = pytest.importorskip("bpy")

from .rig_fixtures import build_hero, build_variant, reset_scene  # noqa: E402
from .test_finalize_anims import (  # noqa: E402
    _clip,
    _hold,
    _reset,
    _rig,
    _root_lift,
)


@pytest.fixture()
def anims(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.finalize_core.anims")


@pytest.fixture()
def rig_core(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.rig_core")


def _key_table(action: Any) -> list[tuple[str, int, tuple[tuple[float, ...], ...]]]:
    return [
        (curve.data_path, curve.array_index, tuple(tuple(p.co) for p in curve.keyframe_points))
        for layer in action.layers
        for strip in layer.strips
        for bag in strip.channelbags
        for curve in bag.fcurves
    ]


def _action_names() -> list[str]:
    return sorted(action.name for action in bpy.data.actions)


def _two_rigs(rig_core: Any) -> None:
    """Build Hero (StreetThug) and Variant (Cop) in one scene, each with its own SK_<Name>."""
    reset_scene()
    bpy.context.scene.render.fps = 30
    assert rig_core.rig_humanoid("Hero", "humanoid", build_hero())["status"] == "ok"
    assert rig_core.rig_humanoid("Variant", "humanoid", build_variant())["status"] == "ok"


def test_scn001_an_suffixed_action_exports_under_its_bare_name(anims: Any, tmp_path: Path) -> None:
    _reset()
    try:
        thug = _rig("StreetThug")
        _hold(thug, _clip(thug, "Idle@SK_StreetThug", (1, 10), 0.1))

        (record,) = anims.export_clips("StreetThug", ["Idle"], tmp_path)

        assert record["name"] == "Idle"
        assert record["file"] == "A_StreetThug_Idle.glb"
        assert (tmp_path / "A_StreetThug_Idle.glb").is_file()
    finally:
        _reset()


def test_scn002_two_characters_each_export_their_own_idle(anims: Any, tmp_path: Path) -> None:
    _reset()
    try:
        thug = _rig("StreetThug")
        _hold(thug, _clip(thug, "Idle@SK_StreetThug", (1, 10), 0.1))
        cop = _rig("Cop")
        _hold(cop, _clip(cop, "Idle@SK_Cop", (1, 10), 0.3))

        records = anims.export_clips("StreetThug", ["Idle"], tmp_path)
        records += anims.export_clips("Cop", ["Idle"], tmp_path)
        lifts: dict[str, float] = {}
        for record in records:
            bpy.ops.wm.read_homefile(use_empty=True)
            bpy.ops.import_scene.gltf(
                filepath=str(tmp_path / record["file"]), disable_bone_shape=True
            )
            (action,) = bpy.data.actions
            lifts[record["file"]] = _root_lift(action)

        assert lifts["A_Cop_Idle.glb"] == pytest.approx(
            3 * lifts["A_StreetThug_Idle.glb"], rel=1e-3
        )
    finally:
        _reset()


def test_scn003_unsuffixed_action_names_export_as_before(anims: Any, tmp_path: Path) -> None:
    _reset()
    try:
        thug = _rig("StreetThug")
        idle = _clip(thug, "Idle", (1, 10), 0.1)
        _hold(thug, idle)

        (record,) = anims.export_clips("StreetThug", ["Idle"], tmp_path)
        hashes = {clip["name"]: clip["hash"] for clip in anims.probe("StreetThug")["clips"]}

        assert (record["name"], record["file"]) == ("Idle", "A_StreetThug_Idle.glb")
        provenance = anims.provenance_of(thug).get("Idle")
        assert hashes["Idle"] == anims.clip_hash(thug, "Idle", idle, provenance)
    finally:
        _reset()


def test_scn007_importing_a_clip_onto_one_rig_leaves_the_other_alone(rig_core: Any) -> None:
    _two_rigs(rig_core)
    assert rig_core.import_animations("Hero", library="builtin", clips=["Idle"])["status"] == "ok"
    thug_action = bpy.data.actions["Idle@SK_Hero"]
    thug_keys = _key_table(thug_action)
    thug_provenance = bpy.data.objects["SK_Hero"]["nmg_animations"]

    baked = rig_core.import_animations("Variant", library="builtin", clips=["Idle"])

    assert baked["status"] == "ok", baked
    assert bpy.data.actions["Idle@SK_Variant"] != thug_action
    assert bpy.data.actions["Idle@SK_Hero"] == thug_action
    assert _key_table(thug_action) == thug_keys
    assert bpy.data.objects["SK_Hero"]["nmg_animations"] == thug_provenance
    for rig_name in ("Hero", "Variant"):
        provenance = json.loads(bpy.data.objects[f"SK_{rig_name}"]["nmg_animations"])
        assert list(provenance) == ["Idle"], rig_name


def test_scn008_reimporting_a_clip_replaces_only_that_rigs_action(rig_core: Any) -> None:
    _two_rigs(rig_core)
    assert rig_core.import_animations("Hero", library="builtin", clips=["Idle"])["status"] == "ok"
    assert (
        rig_core.import_animations("Variant", library="builtin", clips=["Idle"])["status"] == "ok"
    )
    variant_action = bpy.data.actions["Idle@SK_Variant"]
    variant_keys = _key_table(variant_action)

    again = rig_core.import_animations("Hero", library="builtin", clips=["Idle"])

    assert again["status"] == "ok", again
    names = _action_names()
    assert [name for name in names if name.startswith("Idle")] == [
        "Idle@SK_Hero",
        "Idle@SK_Variant",
    ]
    assert "Idle@SK_Hero.001" not in names
    assert bpy.data.actions["Idle@SK_Variant"] == variant_action
    assert _key_table(variant_action) == variant_keys
