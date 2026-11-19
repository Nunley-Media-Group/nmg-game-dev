"""Unit tests for the per-clip finalize steps export_anims and import_anims (#138, #249 FR3).

These run the real orchestrator, per-clip cache, gates, and sidecar writer, with in-process fakes
for Blender (``FakeStepRunner``) and ``godot --headless`` (``FinalizeGodot``).  No live Blender
or Godot editor is touched.  Each clip is a ``.glb`` imported as a Godot animation library.
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
from nmg_game_dev.pipeline.anims import SIDECAR_NAME, run_import_anims
from nmg_game_dev.pipeline.cache import ArtifactCache
from tests.finalize_fakes import FakeBlenderSession, FakeStepRunner, FinalizeGodot

DESKTOP = "res://export/Props/Crate/Desktop/Crate.glb"
ANIMATIONS = "res://export/Props/Crate/Animations"
OTHER = "res://export/Props/Other/Desktop/Other.glb"
IDLE = {"name": "Idle", "hash": "hash-idle", "valid_name": True}
WALK = {"name": "Walk", "hash": "hash-walk", "valid_name": True}


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


def _godot(tmp_path: Path, **options: Any) -> FinalizeGodot:
    return FinalizeGodot(tmp_path, **options)


def _finalize(
    request: FinalizeRequest,
    tmp_path: Path,
    counter: list[int],
    *,
    clips: list[dict[str, Any]],
    godot: FinalizeGodot | None = None,
    steps: tuple[str, ...] = STEP_ORDER,
    force: bool = False,
    runner: FakeStepRunner | None = None,
) -> tuple[FinalizeResult, FakeStepRunner, FinalizeGodot]:
    fake_runner = runner if runner is not None else FakeStepRunner(request, clips=clips)
    engine = godot if godot is not None else _godot(tmp_path)
    result = finalize(
        request,
        steps=steps,
        force=force,
        cache_dir=tmp_path / "cache",
        runner=fake_runner,
        job_dir=_job(tmp_path, counter),
        clients=FinalizeClients(blender=FakeBlenderSession(), godot=engine),
    )
    return result, fake_runner, engine


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


def _written(request: FinalizeRequest) -> list[str]:
    """Return the names under Animations/ (clip files and sidecar), or [] when there are none."""
    folder = request.export_root / request.category / request.collection / "Animations"
    if not folder.exists():
        return []
    return sorted(path.name for path in folder.iterdir())


def _anim_result(result: FinalizeResult) -> Mapping[str, Any]:
    assert result.animations is not None
    return result.animations


def _clip_imports(godot: FinalizeGodot) -> list[list[str]]:
    """The clip names each probe_anims.gd call measured."""
    return godot.probed_clips()


def _other_character(request: FinalizeRequest) -> Path:
    scene = request.export_root / "Props" / "Other" / "Desktop" / "Other.glb"
    scene.parent.mkdir(parents=True, exist_ok=True)
    scene.write_bytes(b"glb other")
    return scene


class TestExportPerClip:
    def test_each_clip_is_exported_as_its_own_glb(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        # finalize exports A_<Name>_Idle.glb and A_<Name>_Walk.glb under Animations/.
        result, runner, _godot_runner = _finalize(request_for, tmp_path, jobs, clips=[IDLE, WALK])

        folder = request_for.export_root / "Props" / "Crate" / "Animations"
        assert (folder / "A_Crate_Idle.glb").is_file()
        assert (folder / "A_Crate_Walk.glb").is_file()
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
        assert sidecar["skeleton"] == DESKTOP
        clip = sidecar["clips"][0]
        assert clip == {
            "name": "Idle",
            "file": "A_Crate_Idle.glb",
            "asset_path": f"{ANIMATIONS}/A_Crate_Idle.glb",
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
        # AC3: Walk changes, so only Walk is re-exported and re-imported; Idle is served from cache.
        _finalize(request_for, tmp_path, jobs, clips=[IDLE, WALK])
        changed_walk = {**WALK, "hash": "hash-walk-changed"}

        result, runner, godot = _finalize(request_for, tmp_path, jobs, clips=[IDLE, changed_walk])

        assert [call["inputs"]["clips"] for call in _export_calls(runner)] == [["Walk"]]
        # The recorded Godot calls name one clip: one --import, then a probe of Walk only.
        assert godot.calls[0] == ["--import"]
        assert _clip_imports(godot) == [["Walk"]]
        walk = request_for.export_root / "Props" / "Crate" / "Animations" / "A_Crate_Walk.glb"
        probe_params = next(params for params in godot.params if "skeletons" in params)
        assert probe_params["clips"] == [
            {"name": "Walk", "path": f"{ANIMATIONS}/A_Crate_Walk.glb", "fps": 30.0}
        ]
        assert walk.with_name("A_Crate_Walk.glb.import").is_file()
        clips = {clip["name"]: clip for clip in _anim_result(result)["clips"]}
        assert clips["Idle"]["export_cache_hit"] is True
        assert clips["Idle"]["import_cache_hit"] is True
        assert clips["Walk"]["export_cache_hit"] is False
        assert clips["Walk"]["import_cache_hit"] is False

    def test_mesh_steps_stay_cached_when_only_a_clip_changes(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        # AC3: the mesh steps' cached results are still served from cache.
        _finalize(request_for, tmp_path, jobs, clips=[IDLE, WALK])
        changed_walk = {**WALK, "hash": "hash-walk-changed"}

        result, runner, godot = _finalize(request_for, tmp_path, jobs, clips=[IDLE, changed_walk])

        cache_hits = {step.step: step.cache_hit for step in result.steps}
        for mesh_step in ("validate", "bake", "variants", "export", "reimport", "import_godot"):
            assert cache_hits[mesh_step] is True, mesh_step
        assert godot.probe_calls("probe_asset.gd") == []
        # The probe, then the one export run for Walk.  Nothing else in Blender runs.
        assert runner.steps_run() == ["export_anims", "export_anims"]

    def test_clips_are_probed_and_exported_from_the_current_checkpoint(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        # AC6 and FR7: the asset hash does not cover actions, so on a clip-only change the mesh
        # steps restore the old cached variants .blend.  The probe and export must read this run's
        # checkpoint, which holds the session's current actions, never a cached step result.
        _finalize(request_for, tmp_path, jobs, clips=[IDLE, WALK])
        changed_walk = {**WALK, "hash": "hash-walk-changed"}

        _result, runner, _godot_runner = _finalize(
            request_for, tmp_path, jobs, clips=[IDLE, changed_walk]
        )

        anim_calls = [call for call in runner.calls if call["step"] == "export_anims"]
        assert len(anim_calls) == 2
        checkpoint = str(tmp_path / f"job-{jobs[0]}" / "checkpoint.blend")
        for call in anim_calls:
            assert call["in_blend"] == checkpoint

    def test_force_reexports_and_reimports_every_clip(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        # Force reruns every clip.
        _finalize(request_for, tmp_path, jobs, clips=[IDLE, WALK])

        result, runner, godot = _finalize(
            request_for, tmp_path, jobs, clips=[IDLE, WALK], force=True
        )

        assert [call["inputs"]["clips"] for call in _export_calls(runner)] == [["Idle", "Walk"]]
        assert _clip_imports(godot) == [["Idle", "Walk"]]
        assert all(not clip["export_cache_hit"] for clip in _anim_result(result)["clips"])

    def test_a_clip_with_an_invalid_name_stops_before_any_write(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        # The probe reports an invalid name, so no clip file and no sidecar is written.
        bad = {"name": "Run-Fast", "hash": "hash-bad", "valid_name": False}

        with pytest.raises(PipelineError) as info:
            _finalize(request_for, tmp_path, jobs, clips=[IDLE, bad])

        assert info.value.code == "finalize.clip_name_invalid"
        assert "Run-Fast" in info.value.message
        assert "A_Crate_" not in info.value.message
        folder = request_for.export_root / "Props" / "Crate" / "Animations"
        assert not folder.exists()

    def test_an_action_with_another_rigs_suffix_stops_before_any_write(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        # FR3 and AC4: the probe reports Idle@SK_Cop on SK_Crate, so no clip and no sidecar.
        runner = FakeStepRunner(request_for, clips=[IDLE], rig_mismatch=["Idle@SK_Cop"])

        with pytest.raises(PipelineError) as info:
            _finalize(request_for, tmp_path, jobs, clips=[IDLE], runner=runner)

        assert info.value.code == "finalize.clip_rig_mismatch"
        assert info.value.stage == "export_anims"
        assert "Idle@SK_Cop" in info.value.message
        assert "<Clip>@SK_Crate" in info.value.remediation
        assert _export_calls(runner) == []
        assert _written(request_for) == []

    def test_two_actions_giving_one_clip_stop_before_any_write(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        # FR4 and AC5: Idle is the clip of both Idle and Idle@SK_Crate, so nothing is exported.
        duplicate = {"name": "Idle", "actions": ["Idle", "Idle@SK_Crate"]}
        runner = FakeStepRunner(request_for, clips=[], duplicates=[duplicate])

        with pytest.raises(PipelineError) as info:
            _finalize(request_for, tmp_path, jobs, clips=[], runner=runner)

        assert info.value.code == "finalize.clip_name_duplicate"
        assert info.value.stage == "export_anims"
        assert "Clip Idle" in info.value.message
        assert "(Idle, Idle@SK_Crate)" in info.value.message
        assert "Keep one action per clip on SK_Crate" in info.value.remediation
        assert _export_calls(runner) == []
        assert _written(request_for) == []

    def test_mismatch_is_reported_before_a_duplicate_and_an_invalid_name(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        # The order is mismatch, then duplicate, then invalid name.  Each case holds all three.
        bad = {"name": "Run-Fast", "hash": "hash-bad", "valid_name": False}
        duplicate = {"name": "Idle", "actions": ["Idle", "Idle@SK_Crate"]}
        everything = FakeStepRunner(
            request_for, clips=[bad], rig_mismatch=["Idle@SK_Cop"], duplicates=[duplicate]
        )
        with pytest.raises(PipelineError) as mismatch:
            _finalize(request_for, tmp_path, jobs, clips=[bad], runner=everything)
        assert mismatch.value.code == "finalize.clip_rig_mismatch"

        no_mismatch = FakeStepRunner(request_for, clips=[bad], duplicates=[duplicate])
        with pytest.raises(PipelineError) as duplicated:
            _finalize(request_for, tmp_path, jobs, clips=[bad], runner=no_mismatch)
        assert duplicated.value.code == "finalize.clip_name_duplicate"
        assert _written(request_for) == []

    def test_a_probe_without_the_identity_keys_exports_as_before(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        # A probe that reports neither rig_mismatch nor duplicates is read as reporting none.
        class _ProbeWithoutIdentityKeys(FakeStepRunner):
            def _anim_outputs(
                self, job_dir: Path, inputs: Mapping[str, Any] | None
            ) -> dict[str, Any]:
                outputs = super()._anim_outputs(job_dir, inputs)
                outputs.pop("rig_mismatch", None)
                outputs.pop("duplicates", None)
                return outputs

        runner = _ProbeWithoutIdentityKeys(request_for, clips=[IDLE, WALK])
        _finalize(request_for, tmp_path, jobs, clips=[IDLE, WALK], runner=runner)

        assert [call["inputs"]["clips"] for call in _export_calls(runner)] == [["Idle", "Walk"]]

    def test_an_unrigged_asset_passes_through_with_no_clips(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        # No clips means both steps succeed, report zero clips, write nothing, and run no clip
        # probe.
        result, runner, godot = _finalize(request_for, tmp_path, jobs, clips=[])

        assert _export_calls(runner) == []
        assert godot.probe_calls("probe_anims.gd") == []
        assert _anim_result(result)["clips"] == []
        assert _anim_result(result)["content_path"] is None
        assert not (request_for.export_root / "Props" / "Crate" / "Animations").exists()
        steps = {step.step: step for step in result.steps}
        assert steps["export_anims"].summary == "export_anims: no clips"
        assert steps["import_anims"].summary == "import_anims: no clips"

    def test_run_step_export_anims_runs_its_prerequisites_and_returns_the_standard_shape(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        # The step runs alone, with its dependencies, and returns a StepResult.
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
    def test_clips_import_as_animation_libraries(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        # AC3: each changed clip gets an animation_library .import before the one --import, and
        # the probe measures every clip.
        result, _runner, godot = _finalize(request_for, tmp_path, jobs, clips=[IDLE, WALK])

        folder = request_for.export_root / "Props" / "Crate" / "Animations"
        for clip in ("Idle", "Walk"):
            settings = (folder / f"A_Crate_{clip}.glb.import").read_text(encoding="utf-8")
            assert 'importer="animation_library"' in settings
        assert godot.count("--import") == 2  # import_godot, then import_anims
        assert _clip_imports(godot) == [["Idle", "Walk"]]
        assert _anim_result(result)["content_path"] == ANIMATIONS
        assert [clip["asset_path"] for clip in _anim_result(result)["clips"]] == [
            f"{ANIMATIONS}/A_Crate_Idle.glb",
            f"{ANIMATIONS}/A_Crate_Walk.glb",
        ]

    def test_an_existing_library_import_file_is_kept(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        folder = request_for.export_root / "Props" / "Crate" / "Animations"
        folder.mkdir(parents=True)
        kept = '[remap]\n\nimporter="animation_library"\nuid="uid://keep"\n'
        (folder / "A_Crate_Idle.glb.import").write_text(kept, encoding="utf-8")

        _finalize(request_for, tmp_path, jobs, clips=[IDLE])

        assert (folder / "A_Crate_Idle.glb.import").read_text(encoding="utf-8") == kept

    def test_a_frame_count_difference_names_the_clip_and_both_values(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        # A clip whose library has another frame count fails, naming the clip and both values.
        # Frames 1 to 10 at 30 fps are an animation 9 frames long.
        godot = _godot(tmp_path, frame_counts={"Walk": 12})

        with pytest.raises(PipelineError) as info:
            _finalize(request_for, tmp_path, jobs, clips=[IDLE, WALK], godot=godot)

        assert info.value.code == "import_anims.clip_mismatch"
        assert info.value.remediation
        assert "Walk" in info.value.message
        assert "expected 9" in info.value.message
        assert "measured 12" in info.value.message

    def test_a_clip_that_did_not_load_as_a_library_is_a_mismatch(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        godot = _godot(tmp_path, missing_clips=["Idle"])

        with pytest.raises(PipelineError) as info:
            _finalize(request_for, tmp_path, jobs, clips=[IDLE], godot=godot)

        assert info.value.code == "import_anims.clip_mismatch"
        assert "Idle" in info.value.message

    def test_a_failed_clip_import_is_import_anims_failed(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        from nmg_game_dev.godot.runner import CommandResult

        godot = _godot(
            tmp_path, responses={"probe_anims.gd": CommandResult(1, stderr="ERROR: bad clip")}
        )

        with pytest.raises(PipelineError) as info:
            _finalize(request_for, tmp_path, jobs, clips=[IDLE], godot=godot)

        assert info.value.code == "import_anims.failed"
        assert "ERROR: bad clip" in info.value.message

    def test_a_missing_desktop_scene_says_to_run_import_godot_first(
        self, request_for: FinalizeRequest, tmp_path: Path
    ) -> None:
        # No Desktop .glb means finalize.skeleton_not_found with the import_godot remedy, and no
        # Godot call.
        godot = _godot(tmp_path)
        exported = [
            {
                "name": "Idle",
                "file": "A_Crate_Idle.glb",
                "frame_start": 1,
                "frame_end": 10,
                "fps": 30.0,
                "output_hash": "out-idle",
            }
        ]

        with pytest.raises(PipelineError) as info:
            run_import_anims(
                request_for,
                cache=ArtifactCache(tmp_path / "cache"),
                job_dir=tmp_path / "job",
                exported=exported,
                client=lambda: godot,
                force=False,
            )

        assert info.value.code == "finalize.skeleton_not_found"
        assert "import_godot" in info.value.remediation
        assert godot.calls == []

    def test_stale_clip_files_are_reported_and_never_deleted(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        # A_<Name>_Run.glb is listed under stale.  The host never deletes it.
        folder = request_for.export_root / "Props" / "Crate" / "Animations"
        folder.mkdir(parents=True)
        (folder / "A_Crate_Run.glb").write_bytes(b"old run")

        result, _runner, _godot_runner = _finalize(request_for, tmp_path, jobs, clips=[IDLE])

        assert _anim_result(result)["stale"] == [f"{ANIMATIONS}/A_Crate_Run.glb"]
        assert (folder / "A_Crate_Run.glb").is_file()

    def test_a_clip_whose_import_settings_are_gone_is_imported_again(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        # A cached Idle is imported again when its .import file no longer selects the library.
        _finalize(request_for, tmp_path, jobs, clips=[IDLE])
        folder = request_for.export_root / "Props" / "Crate" / "Animations"
        (folder / "A_Crate_Idle.glb.import").unlink()

        result, _runner, godot = _finalize(request_for, tmp_path, jobs, clips=[IDLE])

        assert _clip_imports(godot) == [["Idle"]]
        assert (folder / "A_Crate_Idle.glb.import").is_file()
        assert _anim_result(result)["clips"][0]["import_cache_hit"] is False


class TestCompatibleSkeletons:
    def _request(self, request_for: FinalizeRequest, *targets: str) -> FinalizeRequest:
        return request_for.model_copy(update={"compatible_with": targets})

    def test_a_target_holding_every_animated_bone_is_listed(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        # The probe reads the target's Desktop Skeleton3D; every clip bone exists there.
        _other_character(request_for)
        godot = _godot(
            tmp_path,
            clip_bones=["root", "spine"],
            skeleton_bones={OTHER: ["root", "spine", "head"]},
        )
        request = self._request(request_for, "Props/Other")

        result, _runner, godot = _finalize(request, tmp_path, jobs, clips=[IDLE], godot=godot)

        probe_params = next(params for params in godot.params if "skeletons" in params)
        assert probe_params["skeletons"] == [OTHER]
        assert _anim_result(result)["compatible"] == [OTHER]

    def test_a_missing_target_names_it(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        # A target with no Desktop scene fails with finalize.skeleton_not_found.
        request = self._request(request_for, "Props/Missing")

        with pytest.raises(PipelineError) as info:
            _finalize(request, tmp_path, jobs, clips=[IDLE])

        assert info.value.code == "finalize.skeleton_not_found"
        assert "Props/Missing" in info.value.message
        assert info.value.remediation

    def test_a_target_the_probe_cannot_load_is_not_found(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        _other_character(request_for)

        def unloadable(params: dict[str, Any]) -> dict[str, Any]:
            return {
                "clips": {
                    clip["name"]: {"animation": clip["name"], "frame_count": 9, "bones": ["root"]}
                    for clip in params["clips"]
                },
                "skeletons": {OTHER: {"found": False, "bones": []}},
            }

        godot = _godot(tmp_path, responses={"probe_anims.gd": unloadable})
        request = self._request(request_for, "Props/Other")

        with pytest.raises(PipelineError) as info:
            _finalize(request, tmp_path, jobs, clips=[IDLE], godot=godot)

        assert info.value.code == "finalize.skeleton_not_found"

    def test_a_missing_bone_names_the_bones(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        # A clip bone absent from the target skeleton fails with finalize.skeleton_mismatch.
        _other_character(request_for)
        godot = _godot(
            tmp_path, clip_bones=["root", "spine"], skeleton_bones={OTHER: ["root", "head"]}
        )
        request = self._request(request_for, "Props/Other")

        with pytest.raises(PipelineError) as info:
            _finalize(request, tmp_path, jobs, clips=[IDLE], godot=godot)

        assert info.value.code == "finalize.skeleton_mismatch"
        assert "spine" in info.value.message
        assert "Props/Other" in info.value.message

    def test_a_rerun_checks_cached_clip_bones_against_the_target(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        # Unchanged clips are not re-imported, but their recorded bones still meet the check.
        _other_character(request_for)
        request = self._request(request_for, "Props/Other")
        first = _godot(
            tmp_path, clip_bones=["root", "spine"], skeleton_bones={OTHER: ["root", "spine"]}
        )
        _finalize(request, tmp_path, jobs, clips=[IDLE], godot=first)
        shrunk = _godot(tmp_path, skeleton_bones={OTHER: ["root"]})

        with pytest.raises(PipelineError) as info:
            _finalize(request, tmp_path, jobs, clips=[IDLE], godot=shrunk)

        assert info.value.code == "finalize.skeleton_mismatch"
        assert _clip_imports(shrunk) == [[]]
        assert shrunk.count("--import") == 0

    def test_without_compatible_with_nothing_is_listed(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        result, _runner, _godot_runner = _finalize(request_for, tmp_path, jobs, clips=[IDLE])

        assert _anim_result(result)["compatible"] == []

    def test_zero_clips_with_a_compatible_target_still_checks_it(
        self, request_for: FinalizeRequest, tmp_path: Path, jobs: list[int]
    ) -> None:
        # With no clips, one skeleton probe still runs when compatible_with is set.
        _other_character(request_for)
        request = self._request(request_for, "Props/Other")

        result, _runner, godot = _finalize(request, tmp_path, jobs, clips=[])

        assert _clip_imports(godot) == [[]]
        assert _anim_result(result)["compatible"] == [OTHER]
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
