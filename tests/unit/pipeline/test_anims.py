"""Unit tests for the per-clip finalize steps export_anims and import_anims (#138).

These run the real orchestrator, per-clip cache, gates, and sidecar writer, with in-process fakes
for Blender (``FakeStepRunner``) and the Unreal editor (``FakeAnimUnrealRunner``).  No live Blender
or UE session is touched.  Each test names the acceptance criterion it covers.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from nmg_game_dev.pipeline import (
    STEP_ORDER,
    FinalizeClients,
    FinalizeRequest,
    FinalizeResult,
    PipelineError,
    finalize,
    run_step,
)
from nmg_game_dev.pipeline.anims import SIDECAR_NAME
from tests.finalize_fakes import (
    FakeAnimUnrealRunner,
    FakeBlenderSession,
    FakeStepRunner,
    FakeUnrealRunner,
    _decode_params,
)

DESKTOP_SKELETON = "/Game/Props/Crate/Desktop/SM_Crate_Skeleton"
ANIMATIONS = "/Game/Props/Crate/Animations"
IDLE = {"name": "Idle", "hash": "hash-idle", "valid_name": True}
WALK = {"name": "Walk", "hash": "hash-walk", "valid_name": True}


class _Router:
    """Sends anim-import UE calls to the anim fake and mesh-import calls to the mesh fake."""

    def __init__(self, anim: FakeAnimUnrealRunner, mesh: FakeUnrealRunner) -> None:
        self.anim = anim
        self.mesh = mesh

    def execute_python_code(self, code: str, *, timeout: float | None = None) -> str:
        if "PARAMS = json.loads(" in code and "prefix" in _decode_params(code):
            return self.anim.execute_python_code(code, timeout=timeout)
        return self.mesh.execute_python_code(code, timeout=timeout)


@pytest.fixture()
def request_for(tmp_path: Path) -> FinalizeRequest:
    blend = tmp_path / "crate.blend"
    blend.write_bytes(b"authored")
    return FinalizeRequest(
        collection="Crate",
        category="Props",
        asset_class="standard_prop",
        export_root=tmp_path / "export",
        blend=blend,
    )


@pytest.fixture()
def jobs(tmp_path: Path) -> list[int]:
    return [0]


def _job(tmp_path: Path, counter: list[int]) -> Path:
    counter[0] += 1
    return tmp_path / f"job-{counter[0]}"


def _anim_unreal(**overrides: Any) -> FakeAnimUnrealRunner:
    options: dict[str, Any] = {"skeletons": [DESKTOP_SKELETON]}
    options.update(overrides)
    return FakeAnimUnrealRunner(**options)


def _finalize(
    request: FinalizeRequest,
    tmp_path: Path,
    counter: list[int],
    *,
    clips: list[dict[str, Any]],
    unreal: FakeAnimUnrealRunner | None = None,
    steps: tuple[str, ...] = STEP_ORDER,
    force: bool = False,
    runner: FakeStepRunner | None = None,
) -> tuple[FinalizeResult, FakeStepRunner, FakeAnimUnrealRunner]:
    fake_runner = runner if runner is not None else FakeStepRunner(request, clips=clips)
    anim = unreal if unreal is not None else _anim_unreal()
    result = finalize(
        request,
        steps=steps,
        force=force,
        cache_dir=tmp_path / "cache",
        runner=fake_runner,
        job_dir=_job(tmp_path, counter),
        clients=FinalizeClients(
            blender=FakeBlenderSession(),
            unreal=_Router(anim, FakeUnrealRunner()),
        ),
    )
    return result, fake_runner, anim


def _export_calls(runner: FakeStepRunner) -> list[dict[str, Any]]:
    return [
        call
        for call in runner.calls
        if call["step"] == "export_anims" and (call.get("inputs") or {}).get("mode") == "export"
    ]


def _sidecar(request: FinalizeRequest) -> dict[str, Any]:
    path = request.export_root / request.category / request.collection / "Animations" / SIDECAR_NAME
    loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


def _anim_result(result: FinalizeResult) -> Mapping[str, Any]:
    assert result.animations is not None
    return result.animations


class TestExportPerClip:
    def test_each_clip_is_exported_as_its_own_fbx(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        # AC1: finalize all exports A_<Name>_Idle.fbx and A_<Name>_Walk.fbx under Animations/.
        result, runner, _anim = _finalize(request_for, tmp_path, jobs, clips=[IDLE, WALK])

        folder = request_for.export_root / "Props" / "Crate" / "Animations"
        assert (folder / "A_Crate_Idle.fbx").is_file()
        assert (folder / "A_Crate_Walk.fbx").is_file()
        assert [call["inputs"]["clips"] for call in _export_calls(runner)] == [["Idle", "Walk"]]
        assert _anim_result(result)["content_path"] == ANIMATIONS

    def test_sidecar_lists_real_clip_data_and_authored_source(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        # AC3 and FR4: nmg-animations.json lists every clip's measured data and its source.
        _finalize(request_for, tmp_path, jobs, clips=[IDLE, WALK])

        sidecar = _sidecar(request_for)
        assert sidecar["asset"] == "Crate"
        assert sidecar["armature"] == "Armature"
        assert sidecar["skeleton"] == DESKTOP_SKELETON
        clip = sidecar["clips"][0]
        assert clip == {
            "name": "Idle",
            "file": "A_Crate_Idle.fbx",
            "asset_path": f"{ANIMATIONS}/A_Crate_Idle",
            "frame_start": 1,
            "frame_end": 10,
            "frame_count": 10,
            "fps": 30.0,
            "source": "authored",
        }

    def test_a_provenance_clip_carries_its_recorded_source(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        # AC3: a provenance clip keeps its source dict (library, file, sha256, skeleton).
        source = {"library": "lib", "file": "idle.fbx", "sha256": "abc", "skeleton": "manny"}
        clip = {**IDLE, "source": source}
        _finalize(request_for, tmp_path, jobs, clips=[clip])

        assert _sidecar(request_for)["clips"][0]["source"] == source

    def test_only_the_clip_that_changed_is_exported_and_reimported(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        # AC6: Walk changes, so only Walk is re-exported and re-imported; Idle is served from cache.
        project = _anim_unreal()
        _finalize(request_for, tmp_path, jobs, clips=[IDLE, WALK], unreal=project)
        project.imported.clear()
        changed_walk = {**WALK, "hash": "hash-walk-changed"}

        result, runner, anim = _finalize(
            request_for, tmp_path, jobs, clips=[IDLE, changed_walk], unreal=project
        )

        assert [call["inputs"]["clips"] for call in _export_calls(runner)] == [["Walk"]]
        assert anim.imported == ["Walk"]
        clips = {clip["name"]: clip for clip in _anim_result(result)["clips"]}
        assert clips["Idle"]["export_cache_hit"] is True
        assert clips["Idle"]["import_cache_hit"] is True
        assert clips["Walk"]["export_cache_hit"] is False
        assert clips["Walk"]["import_cache_hit"] is False

    def test_mesh_steps_stay_cached_when_only_a_clip_changes(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        # AC6: the mesh steps' cached results are still served from cache.
        project = _anim_unreal()
        _finalize(request_for, tmp_path, jobs, clips=[IDLE, WALK], unreal=project)
        changed_walk = {**WALK, "hash": "hash-walk-changed"}

        result, runner, _anim = _finalize(
            request_for, tmp_path, jobs, clips=[IDLE, changed_walk], unreal=project
        )

        cache_hits = {step.step: step.cache_hit for step in result.steps}
        for mesh_step in ("validate", "bake", "variants", "export", "reimport", "import_ue"):
            assert cache_hits[mesh_step] is True, mesh_step
        # The probe, then the one export run for Walk.  Nothing else in Blender runs.
        assert runner.steps_run() == ["export_anims", "export_anims"]

    def test_clips_are_probed_and_exported_from_the_current_checkpoint(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        # AC6 and FR7: the asset hash does not cover actions, so on a clip-only change the mesh
        # steps restore the old cached variants .blend.  The probe and export must read this run's
        # checkpoint, which holds the session's current actions, never a cached step result.
        project = _anim_unreal()
        _finalize(request_for, tmp_path, jobs, clips=[IDLE, WALK], unreal=project)
        changed_walk = {**WALK, "hash": "hash-walk-changed"}

        _result, runner, _anim = _finalize(
            request_for, tmp_path, jobs, clips=[IDLE, changed_walk], unreal=project
        )

        anim_calls = [call for call in runner.calls if call["step"] == "export_anims"]
        assert len(anim_calls) == 2
        checkpoint = str(tmp_path / f"job-{jobs[0]}" / "checkpoint.blend")
        for call in anim_calls:
            assert call["in_blend"] == checkpoint

    def test_force_reexports_and_reimports_every_clip(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        # AC7: force reruns every clip.
        project = _anim_unreal()
        _finalize(request_for, tmp_path, jobs, clips=[IDLE, WALK], unreal=project)
        project.imported.clear()

        result, runner, anim = _finalize(
            request_for, tmp_path, jobs, clips=[IDLE, WALK], force=True, unreal=project
        )

        assert [call["inputs"]["clips"] for call in _export_calls(runner)] == [["Idle", "Walk"]]
        assert sorted(anim.imported) == ["Idle", "Walk"]
        assert all(not clip["export_cache_hit"] for clip in _anim_result(result)["clips"])

    def test_a_clip_with_an_invalid_name_stops_before_any_write(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        # AC11: the probe reports an invalid name, so no FBX and no sidecar is written.
        bad = {"name": "Run-Fast", "hash": "hash-bad", "valid_name": False}

        with pytest.raises(PipelineError) as info:
            _finalize(request_for, tmp_path, jobs, clips=[IDLE, bad])

        assert info.value.code == "finalize.clip_name_invalid"
        assert "Run-Fast" in info.value.message
        assert "A_Crate_" not in info.value.message
        folder = request_for.export_root / "Props" / "Crate" / "Animations"
        assert not folder.exists()

    def test_an_unrigged_asset_passes_through_with_no_clips(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        # AC8: no clips means both steps succeed, report zero clips, write nothing, and make no
        # Unreal call.
        result, runner, anim = _finalize(request_for, tmp_path, jobs, clips=[])

        assert _export_calls(runner) == []
        assert anim.codes == []
        assert _anim_result(result)["clips"] == []
        assert _anim_result(result)["content_path"] is None
        assert not (request_for.export_root / "Props" / "Crate" / "Animations").exists()
        steps = {step.step: step for step in result.steps}
        assert steps["export_anims"].summary == "export_anims: no clips"
        assert steps["import_anims"].summary == "import_anims: no clips"

    def test_run_step_export_anims_runs_its_prerequisites_and_returns_the_standard_shape(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        # AC9: the step runs alone, with its dependencies, and returns a StepResult.
        runner = FakeStepRunner(request_for, clips=[IDLE])

        step = run_step(
            "export_anims",
            request_for,
            cache_dir=tmp_path / "cache",
            runner=runner,
            job_dir=_job(tmp_path, jobs),
        )

        assert runner.steps_run() == [
            "validate",
            "bake",
            "variants",
            "export_anims",
            "export_anims",
        ]
        assert step.step == "export_anims"
        assert step.cache_hit is False
        assert step.outputs["clips"][0]["name"] == "Idle"
        assert step.summary == "export_anims: 1 clip(s), 0 from cache"


class TestImportPerClip:
    def test_clips_import_as_anim_sequences_on_the_desktop_skeleton(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        # AC4: each clip is imported on the Desktop skeleton, and the result lists the folder and
        # every clip.  The code uses the anim import flags.
        result, _runner, anim = _finalize(request_for, tmp_path, jobs, clips=[IDLE, WALK])

        assert anim.imported == ["Idle", "Walk"]
        params = anim.params[0]
        assert params["skeleton"] == DESKTOP_SKELETON
        assert params["anim_dir"] == ANIMATIONS
        assert [clip["asset_path"] for clip in params["clips"]] == [
            f"{ANIMATIONS}/A_Crate_Idle",
            f"{ANIMATIONS}/A_Crate_Walk",
        ]
        assert _anim_result(result)["content_path"] == ANIMATIONS
        assert [clip["name"] for clip in _anim_result(result)["clips"]] == ["Idle", "Walk"]

    def test_a_frame_count_difference_names_the_clip_and_both_values(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        # AC5: a clip whose AnimSequence has another frame count fails, naming clip and values.
        unreal = _anim_unreal(frame_counts={"Walk": 12})

        with pytest.raises(PipelineError) as info:
            _finalize(request_for, tmp_path, jobs, clips=[IDLE, WALK], unreal=unreal)

        assert info.value.code == "import_anims.clip_mismatch"
        assert "Walk" in info.value.message
        assert "expected 10" in info.value.message
        assert "measured 12" in info.value.message

    def test_a_skeleton_difference_fails_the_clip_check(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        # AC5: a clip on a different skeleton fails with import_anims.clip_mismatch.
        unreal = _anim_unreal(skeleton_of={"Idle": "/Game/Props/Other/Desktop/SM_Other_Skeleton"})

        with pytest.raises(PipelineError) as info:
            _finalize(request_for, tmp_path, jobs, clips=[IDLE], unreal=unreal)

        assert info.value.code == "import_anims.clip_mismatch"
        assert "Idle skeleton" in info.value.message

    def test_a_missing_desktop_skeleton_says_to_run_import_ue_first(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        # AC10: no Desktop skeleton means finalize.skeleton_not_found, with the import_ue remedy and
        # no AnimSequence created.
        unreal = FakeAnimUnrealRunner(skeletons=[])

        with pytest.raises(PipelineError) as info:
            _finalize(request_for, tmp_path, jobs, clips=[IDLE], unreal=unreal)

        assert info.value.code == "finalize.skeleton_not_found"
        assert "import_ue" in info.value.remediation
        assert unreal.imported == []

    def test_stale_sequences_are_reported_and_never_deleted(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        # AC12: A_<Name>_Run is listed under stale.  The host never deletes it.
        unreal = _anim_unreal(stale=["A_Crate_Run"], present=[f"{ANIMATIONS}/A_Crate_Run"])

        result, _runner, _anim = _finalize(request_for, tmp_path, jobs, clips=[IDLE], unreal=unreal)

        assert _anim_result(result)["stale"] == [f"{ANIMATIONS}/A_Crate_Run"]
        assert unreal.params[0]["prefix"] == "A_Crate_"

    def test_a_clip_whose_sequence_is_gone_is_imported_again(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        # The cached Idle is imported again when its AnimSequence no longer exists in the project.
        _finalize(request_for, tmp_path, jobs, clips=[IDLE])
        unreal = _anim_unreal(present=[])

        result, _runner, anim = _finalize(request_for, tmp_path, jobs, clips=[IDLE], unreal=unreal)

        assert anim.imported == ["Idle"]
        assert _anim_result(result)["clips"][0]["import_cache_hit"] is True


class TestCompatibleSkeletons:
    def _request(self, request_for: FinalizeRequest, *targets: str) -> FinalizeRequest:
        return request_for.model_copy(update={"compatible_with": targets})

    def test_registration_is_two_way_and_listed_in_the_result(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        # AC13: both characters list each other, keep their own skeletons, and the result lists it.
        other = "/Game/Props/Other/Desktop/SM_Other_Skeleton"
        unreal = _anim_unreal(skeletons=[DESKTOP_SKELETON, other])
        request = self._request(request_for, "Props/Other")

        result, _runner, anim = _finalize(request, tmp_path, jobs, clips=[IDLE], unreal=unreal)

        assert anim.compatible[DESKTOP_SKELETON] == [other]
        assert anim.compatible[other] == [DESKTOP_SKELETON]
        assert _anim_result(result)["compatible"] == [other]

    def test_registration_is_idempotent(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        # AC14: a rerun with the same compatible_with lists each other skeleton exactly once.
        other = "/Game/Props/Other/Desktop/SM_Other_Skeleton"
        unreal = _anim_unreal(skeletons=[DESKTOP_SKELETON, other])
        request = self._request(request_for, "Props/Other")
        _finalize(request, tmp_path, jobs, clips=[IDLE], unreal=unreal)

        _finalize(request, tmp_path, jobs, clips=[IDLE], unreal=unreal)

        assert unreal.compatible[DESKTOP_SKELETON] == [other]
        assert unreal.compatible[other] == [DESKTOP_SKELETON]

    def test_a_missing_target_names_it_and_registers_nothing(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        # AC15: a missing target fails with finalize.skeleton_not_found and changes nothing.
        unreal = _anim_unreal()
        request = self._request(request_for, "Props/Missing")

        with pytest.raises(PipelineError) as info:
            _finalize(request, tmp_path, jobs, clips=[IDLE], unreal=unreal)

        assert info.value.code == "finalize.skeleton_not_found"
        assert "Props/Missing" in info.value.message
        assert unreal.compatible == {}

    def test_a_bone_mismatch_names_the_differing_bones_and_registers_nothing(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        # AC15: differing bone names fail with finalize.skeleton_mismatch, listing those bones.
        other = "/Game/Props/Other/Desktop/SM_Other_Skeleton"
        unreal = _anim_unreal(
            skeletons=[DESKTOP_SKELETON, other],
            bones={DESKTOP_SKELETON: ["root", "spine"], other: ["root", "head"]},
        )
        request = self._request(request_for, "Props/Other")

        with pytest.raises(PipelineError) as info:
            _finalize(request, tmp_path, jobs, clips=[IDLE], unreal=unreal)

        assert info.value.code == "finalize.skeleton_mismatch"
        assert "head" in info.value.message
        assert "spine" in info.value.message
        assert unreal.compatible == {}

    def test_without_compatible_with_nothing_is_registered(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        # AC16: no compatible_with means no skeleton's list changes.
        other = "/Game/Props/Other/Desktop/SM_Other_Skeleton"
        unreal = _anim_unreal(skeletons=[DESKTOP_SKELETON, other])

        result, _runner, _anim = _finalize(request_for, tmp_path, jobs, clips=[IDLE], unreal=unreal)

        assert unreal.compatible == {}
        assert _anim_result(result)["compatible"] == []

    def test_zero_clips_with_a_compatible_target_still_registers(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        # With no clips, an Unreal call still runs when compatible_with is set.
        other = "/Game/Props/Other/Desktop/SM_Other_Skeleton"
        unreal = _anim_unreal(skeletons=[DESKTOP_SKELETON, other])
        request = self._request(request_for, "Props/Other")

        result, _runner, anim = _finalize(request, tmp_path, jobs, clips=[], unreal=unreal)

        assert len(anim.codes) == 1
        assert _anim_result(result)["compatible"] == [other]
        assert _anim_result(result)["content_path"] is None


class TestRequestCompatibleWith:
    def test_items_must_be_category_and_name(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            FinalizeRequest(
                collection="Crate",
                category="Props",
                asset_class="standard_prop",
                export_root=tmp_path,
                compatible_with=("props/other",),
            )

    def test_duplicates_are_dropped_and_self_reference_is_refused(self, tmp_path: Path) -> None:
        request = FinalizeRequest(
            collection="Crate",
            category="Props",
            asset_class="standard_prop",
            export_root=tmp_path,
            compatible_with=("Props/Other", "Props/Other"),
        )
        assert request.compatible_with == ("Props/Other",)
        with pytest.raises(ValueError):
            FinalizeRequest(
                collection="Crate",
                category="Props",
                asset_class="standard_prop",
                export_root=tmp_path,
                compatible_with=("Props/Crate",),
            )
