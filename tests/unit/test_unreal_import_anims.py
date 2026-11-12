"""Unit tests for the UE Python of the finalize import_anims step (#138).

No editor runs here.  The tests check the generated program's text and syntax, and the host's
handling of the NMG_RESULT replies, through the fake Unreal runner.  The UE calls themselves are
verified against a live editor by the spec's verify stage, not by these tests.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from nmg_game_dev.pipeline import FinalizeRequest, PipelineError
from nmg_game_dev.pipeline.anims import run_import_anims
from nmg_game_dev.pipeline.cache import ArtifactCache
from nmg_game_dev.unreal.import_anims import build_anim_import_code
from tests.finalize_fakes import FakeAnimUnrealRunner, _decode_params

SKELETON = "/Game/Props/Crate/Desktop/SM_Crate_Skeleton"


def _params() -> dict[str, object]:
    return {
        "name": "Crate",
        "anim_dir": "/Game/Props/Crate/Animations",
        "skeleton": SKELETON,
        "prefix": "A_Crate_",
        "clips": [
            {
                "name": "Idle",
                "asset_name": "A_Crate_Idle",
                "asset_path": "/Game/Props/Crate/Animations/A_Crate_Idle",
                "file": "/export/Props/Crate/Animations/A_Crate_Idle.fbx",
                "import": True,
                "expected_frame_count": 10,
            }
        ],
        "compatible": [],
    }


def test_the_program_compiles_and_round_trips_its_parameters() -> None:
    code = build_anim_import_code(_params())

    compile(code, "<ue-import-anims>", "exec")
    assert _decode_params(code) == _params()


def test_the_program_imports_anim_sequences_on_the_desktop_skeleton() -> None:
    # AC4 and FR5: FBXIT_ANIMATION, skeletal with no mesh, animations on, no materials or textures,
    # onto the Desktop skeleton, with the sequence named A_<Name>_<Clip>.
    code = build_anim_import_code(_params())

    for expected in (
        "FBXIT_ANIMATION",
        'set_editor_property("import_mesh", False)',
        'set_editor_property("import_as_skeletal", True)',
        'set_editor_property("import_animations", True)',
        'set_editor_property("import_materials", False)',
        'set_editor_property("import_textures", False)',
        'set_editor_property("skeleton", _load(PARAMS["skeleton"]))',
        'task.destination_name = clip["asset_name"]',
        'task.destination_path = PARAMS["anim_dir"]',
        "unreal.AnimSequence",
        "created non-AnimSequence assets",
    ):
        assert expected in code, expected


def test_the_program_checks_skeletons_before_it_imports_anything() -> None:
    # AC10 and AC15: the own and compatible skeleton checks run before any import.
    code = build_anim_import_code(_params())

    assert code.index("_check_targets(own_names)") < code.index("_import_clip(tools, clip)")
    assert '"skeleton_not_found"' in code
    assert '"skeleton_mismatch"' in code


def test_the_program_lists_stale_sequences_and_never_deletes() -> None:
    # AC12: stale sequences are listed.  Nothing in the program removes an asset.
    code = build_anim_import_code(_params())

    assert 'list_assets(PARAMS["anim_dir"]' in code
    assert 'RESULT["stale"].append' in code
    assert "delete" not in code.lower()


def test_registration_waits_for_the_verification_to_pass() -> None:
    # AC5 and AC13: no skeleton is registered when a clip fails its check.
    code = build_anim_import_code(_params())

    assert code.index('if RESULT["mismatch"]:') < code.index("_add_compatible(own, target")


def _run_import(
    tmp_path: Path, request: FinalizeRequest, unreal: FakeAnimUnrealRunner
) -> dict[str, Any]:
    cache = ArtifactCache(tmp_path / "cache")
    exported = [
        {
            "name": "Idle",
            "file": "A_Crate_Idle.fbx",
            "frame_count": 10,
            "output_hash": "out-idle",
            "cache_hit": False,
        }
    ]
    return run_import_anims(
        request,
        cache=cache,
        job_dir=tmp_path / "job",
        exported=exported,
        client=lambda: unreal,
        force=False,
    )


def _request(tmp_path: Path, **overrides: object) -> FinalizeRequest:
    values: dict[str, object] = {
        "collection": "Crate",
        "category": "Props",
        "asset_class": "standard_prop",
        "export_root": tmp_path / "export",
    }
    values.update(overrides)
    return FinalizeRequest.model_validate(values)


def test_a_reply_that_reports_no_desktop_skeleton_fails_before_any_clip(tmp_path: Path) -> None:
    unreal = FakeAnimUnrealRunner(skeletons=[])

    with pytest.raises(PipelineError) as info:
        _run_import(tmp_path, _request(tmp_path), unreal)

    assert info.value.code == "finalize.skeleton_not_found"
    assert info.value.stage == "import_anims"
    assert "import_ue" in info.value.remediation
    assert unreal.imported == []


def test_a_program_error_becomes_import_anims_failed(tmp_path: Path) -> None:
    unreal = FakeAnimUnrealRunner(skeletons=[SKELETON], error="RuntimeError: boom")

    with pytest.raises(PipelineError) as info:
        _run_import(tmp_path, _request(tmp_path), unreal)

    assert info.value.code == "import_anims.failed"
    assert "boom" in info.value.message


def test_an_unparseable_reply_becomes_import_anims_failed(tmp_path: Path) -> None:
    class _Silent:
        def execute_python_code(self, code: str) -> str:
            return "no result line here"

    with pytest.raises(PipelineError) as info:
        run_import_anims(
            _request(tmp_path),
            cache=ArtifactCache(tmp_path / "cache"),
            job_dir=tmp_path / "job",
            exported=[
                {
                    "name": "Idle",
                    "file": "A_Crate_Idle.fbx",
                    "frame_count": 10,
                    "output_hash": "h",
                    "cache_hit": False,
                }
            ],
            client=_Silent,
            force=False,
        )
    assert info.value.code == "import_anims.failed"


def test_a_clip_key_count_difference_reports_expected_and_measured(tmp_path: Path) -> None:
    unreal = FakeAnimUnrealRunner(skeletons=[SKELETON], frame_counts={"Idle": 7})

    with pytest.raises(PipelineError) as info:
        _run_import(tmp_path, _request(tmp_path), unreal)

    assert info.value.code == "import_anims.clip_mismatch"
    assert "Idle" in info.value.message
    assert "expected 10" in info.value.message
    assert "measured 7" in info.value.message


def test_a_compatible_bone_mismatch_names_the_bones(tmp_path: Path) -> None:
    other = "/Game/Props/Other/Desktop/SM_Other_Skeleton"
    unreal = FakeAnimUnrealRunner(
        skeletons=[SKELETON, other],
        bones={SKELETON: ["root", "spine"], other: ["root", "head"]},
    )
    request = _request(tmp_path, compatible_with=("Props/Other",))

    with pytest.raises(PipelineError) as info:
        _run_import(tmp_path, request, unreal)

    assert info.value.code == "finalize.skeleton_mismatch"
    assert "head" in info.value.message and "spine" in info.value.message
    assert unreal.compatible == {}


def test_json_round_trip_of_the_reply_is_what_the_host_reads(tmp_path: Path) -> None:
    unreal = FakeAnimUnrealRunner(skeletons=[SKELETON])

    outputs = _run_import(tmp_path, _request(tmp_path), unreal)

    assert json.loads(json.dumps(outputs)) == outputs
    assert outputs["clips"] == [
        {
            "name": "Idle",
            "asset_path": "/Game/Props/Crate/Animations/A_Crate_Idle",
            "cache_hit": False,
        }
    ]
