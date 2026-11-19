"""pytest-bdd bindings for rigged_animations.feature: SCN001-SCN016 of #138, on Godot (#249).

Each scenario proves itself in its own test: a host proof that runs the real finalize pipeline with
``FakeStepRunner`` (Blender) and ``FinalizeGodot`` (``godot --headless``) from
tests/finalize_fakes.py, plus the headless Blender cases named for it through
scripts/run-blender-tests.sh.  The Given, When, and Then steps are narrative and carry no
assertions of their own.  A Blender case skips when no Blender resolves, so a plain CPython run
reports those cases as skipped rather than passed.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenario, then, when

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
from tests.finalize_fakes import FakeBlenderSession, FakeStepRunner, FinalizeGodot
from tests.release_fakes import resolved_blender

REPO_ROOT = Path(__file__).resolve().parents[2]
_BLENDER = "tests/blender/test_finalize_anims.py::"
IDLE = {"name": "Idle", "hash": "hash-idle"}
WALK = {"name": "Walk", "hash": "hash-walk"}
ANIMS_RES = "res://export/Props/Crate/Animations"
HERO_RES = "res://export/Characters/Hero/Desktop/Hero.glb"


class _Project:
    """One temporary Godot project with a Crate request and fresh job directories."""

    def __init__(self, root: Path, *, compatible_with: tuple[str, ...] = ()) -> None:
        self.root = root
        blend = root / "crate.blend"
        blend.write_bytes(b"authored")
        self.request = FinalizeRequest(
            collection="Crate",
            category="Props",
            asset_class="character",
            export_root=root / "export",
            blend=blend,
            compatible_with=compatible_with,
        )
        self.jobs = 0

    @property
    def animations(self) -> Path:
        return self.request.export_root / "Props" / "Crate" / "Animations"

    def run(
        self,
        *,
        clips: Sequence[Mapping[str, Any]] = (IDLE, WALK),
        godot: FinalizeGodot | None = None,
        runner: FakeStepRunner | None = None,
        force: bool = False,
        steps: tuple[str, ...] = STEP_ORDER,
    ) -> tuple[FinalizeResult, FakeStepRunner, FinalizeGodot]:
        self.jobs += 1
        fake = runner if runner is not None else FakeStepRunner(self.request, clips=clips)
        engine = godot if godot is not None else FinalizeGodot(self.root)
        result = finalize(
            self.request,
            steps=steps,
            force=force,
            cache_dir=self.root / "cache",
            runner=fake,
            job_dir=self.root / f"job-{self.jobs}",
            clients=FinalizeClients(blender=FakeBlenderSession(), godot=engine),
        )
        return result, fake, engine

    def hero(self, *, bones: Sequence[str] = ("root",)) -> FinalizeGodot:
        """Write the Desktop scene of Characters/Hero; return a Godot fake knowing its bones."""
        scene = self.request.export_root / "Characters" / "Hero" / "Desktop" / "Hero.glb"
        scene.parent.mkdir(parents=True, exist_ok=True)
        scene.write_bytes(b"glb hero")
        return FinalizeGodot(self.root, skeleton_bones={HERO_RES: list(bones)})


def _exported(runner: FakeStepRunner) -> list[list[str]]:
    return [
        list((call.get("inputs") or {}).get("clips", []))
        for call in runner.calls
        if call["step"] == "export_anims" and (call.get("inputs") or {}).get("mode") == "export"
    ]


def _raises(project: _Project, godot: FinalizeGodot, code: str) -> PipelineError:
    with pytest.raises(PipelineError) as info:
        project.run(godot=godot)
    assert info.value.code == code
    assert info.value.remediation
    return info.value


def _blender(*nodes: str) -> None:
    """Run the headless Blender cases ``nodes``; skip when no Blender resolves."""
    blender = resolved_blender()
    if blender is None:
        pytest.skip("Blender does not resolve (set BLENDER_BIN or BLENDER_APP); cases not run")
    completed = subprocess.run(
        [str(REPO_ROOT / "scripts" / "run-blender-tests.sh"), *nodes],
        cwd=REPO_ROOT,
        env={**os.environ, "BLENDER_BIN": blender},
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, (completed.stdout + completed.stderr)[-3000:]


# Narrative steps: the scenario's own test runs the proof, so these carry no assertions.
@given(parsers.parse("{text}"))
def _given(text: str) -> None:
    del text


@when(parsers.parse("{text}"))
def _when(text: str) -> None:
    del text


@then(parsers.parse("{text}"))
def _then(text: str) -> None:
    del text


@scenario("rigged_animations.feature", "Finalize exports one animation .glb per clip")
def test_scn001_one_animation_glb_per_clip(tmp_path: Path) -> None:
    _blender(_BLENDER + "test_one_armature_only_glb_per_clip_and_each_reimports_as_one_clip")
    project = _Project(tmp_path)
    _result, runner, _godot = project.run()
    assert _exported(runner) == [["Idle", "Walk"]]
    assert sorted(path.name for path in project.animations.glob("*.glb")) == [
        "A_Crate_Idle.glb",
        "A_Crate_Walk.glb",
    ]


@scenario(
    "rigged_animations.feature", "The clip set is provenance clips plus actions held on the rig"
)
def test_scn002_clip_set_is_provenance_plus_rig_actions() -> None:
    _blender(_BLENDER + "test_the_clip_set_is_provenance_plus_the_rigs_actions_and_excludes_other")


@scenario("rigged_animations.feature", "nmg-animations.json records real clip data")
def test_scn003_sidecar_records_real_clip_data(tmp_path: Path) -> None:
    _blender(_BLENDER + "test_the_sidecar_fields_match_the_exported_actions_and_sources")
    project = _Project(tmp_path)
    project.run(clips=(IDLE, {**WALK, "source": "meshy:walking"}))
    sidecar = json.loads((project.animations / SIDECAR_NAME).read_text(encoding="utf-8"))
    by_name = {clip["name"]: clip for clip in sidecar["clips"]}
    assert by_name["Idle"]["file"] == "A_Crate_Idle.glb"
    assert by_name["Idle"]["asset_path"] == f"{ANIMS_RES}/A_Crate_Idle.glb"
    assert (by_name["Idle"]["frame_start"], by_name["Idle"]["frame_end"]) == (1, 10)
    assert (by_name["Idle"]["frame_count"], by_name["Idle"]["fps"]) == (10, 30.0)
    assert by_name["Idle"]["source"] == "authored"
    assert by_name["Walk"]["source"] == "meshy:walking"


@scenario("rigged_animations.feature", "Clips import as Godot animation libraries")
def test_scn004_clips_import_as_animation_libraries(tmp_path: Path) -> None:
    project = _Project(tmp_path)
    result, _runner, godot = project.run()
    for clip in ("Idle", "Walk"):
        settings = project.animations / f"A_Crate_{clip}.glb.import"
        assert 'importer="animation_library"' in settings.read_text(encoding="utf-8")
    # One import for the mesh step, one for the clips.
    assert godot.count("--import") == 2
    assert godot.probed_clips() == [["Idle", "Walk"]]
    assert result.animations is not None
    assert [clip["asset_path"] for clip in result.animations["clips"]] == [
        f"{ANIMS_RES}/A_Crate_Idle.glb",
        f"{ANIMS_RES}/A_Crate_Walk.glb",
    ]


@scenario("rigged_animations.feature", "An imported clip is checked against the sidecar")
def test_scn005_imported_clip_is_checked_against_the_sidecar(tmp_path: Path) -> None:
    project = _Project(tmp_path)
    error = _raises(
        project, FinalizeGodot(tmp_path, frame_counts={"Walk": 12}), "import_anims.clip_mismatch"
    )
    assert "Walk" in error.message and "9" in error.message and "12" in error.message
    error = _raises(
        project, FinalizeGodot(tmp_path, missing_clips=("Idle",)), "import_anims.clip_mismatch"
    )
    assert "Idle" in error.message


@scenario("rigged_animations.feature", "Clips are cached individually")
def test_scn006_clips_are_cached_individually(tmp_path: Path) -> None:
    project = _Project(tmp_path)
    project.run()
    result, runner, godot = project.run(clips=(IDLE, {**WALK, "hash": "hash-walk-2"}))
    assert _exported(runner) == [["Walk"]]
    assert godot.probed_clips() == [["Walk"]]
    assert result.animations is not None
    hits = {clip["name"]: clip["import_cache_hit"] for clip in result.animations["clips"]}
    assert hits == {"Idle": True, "Walk": False}
    mesh = [step for step in result.steps if step.step not in ("export_anims", "import_anims")]
    assert all(step.cache_hit for step in mesh)


@scenario("rigged_animations.feature", "Force reruns every clip")
def test_scn007_force_reruns_every_clip(tmp_path: Path) -> None:
    project = _Project(tmp_path)
    project.run()
    _result, runner, godot = project.run(force=True)
    assert _exported(runner) == [["Idle", "Walk"]]
    assert godot.probed_clips() == [["Idle", "Walk"]]


@scenario("rigged_animations.feature", "Assets without clips pass through")
def test_scn008_assets_without_clips_pass_through(tmp_path: Path) -> None:
    project = _Project(tmp_path)
    result, _runner, godot = project.run(clips=())
    assert result.animations is not None
    assert result.animations["clips"] == []
    assert not project.animations.exists()
    assert godot.probed_clips() == []
    assert result.desktop_resource_path == "res://export/Props/Crate/Desktop/Crate.glb"


@scenario("rigged_animations.feature", "The new steps run alone")
def test_scn009_the_new_steps_run_alone(tmp_path: Path) -> None:
    project = _Project(tmp_path)
    project.run(steps=("import_godot",))
    for step in ("export_anims", "import_anims"):
        result = run_step(
            step,
            project.request,
            runner=FakeStepRunner(project.request, clips=(IDLE,)),
            cache_dir=tmp_path / "cache",
            job_dir=tmp_path / f"alone-{step}",
            clients=FinalizeClients(godot=FinalizeGodot(tmp_path)),
        )
        assert result.step == step
        assert {"name", "cache_hit"} <= set(result.outputs["clips"][0])
        assert result.summary


@scenario("rigged_animations.feature", "import_anims needs the Desktop skeleton")
def test_scn010_import_anims_needs_the_desktop_skeleton(tmp_path: Path) -> None:
    project = _Project(tmp_path)
    project.run(steps=("export_anims",))
    godot = FinalizeGodot(tmp_path)
    exported = json.loads((project.animations / SIDECAR_NAME).read_text(encoding="utf-8"))
    desktop = project.request.export_root / "Props" / "Crate" / "Desktop" / "Crate.glb"
    from nmg_game_dev.pipeline import anims
    from nmg_game_dev.pipeline.cache import ArtifactCache

    assert not desktop.exists()
    with pytest.raises(PipelineError) as info:
        anims.run_import_anims(
            project.request,
            cache=ArtifactCache(tmp_path / "cache"),
            job_dir=tmp_path / "anims-only",
            exported=[{**clip, "output_hash": "h"} for clip in exported["clips"]],
            client=lambda: godot,
            force=False,
        )
    assert info.value.code == "finalize.skeleton_not_found"
    assert "import_godot" in info.value.remediation
    assert godot.calls == []


@scenario("rigged_animations.feature", "An invalid clip name stops the export")
def test_scn011_an_invalid_clip_name_stops_the_export(tmp_path: Path) -> None:
    _blender(_BLENDER + "test_an_invalid_clip_name_is_reported_by_the_probe_and_writes_nothing")
    project = _Project(tmp_path)
    with pytest.raises(PipelineError) as info:
        project.run(clips=({"name": "2Bad", "hash": "h", "valid_name": False},))
    assert info.value.code == "finalize.clip_name_invalid"
    assert "2Bad" in info.value.message
    assert not project.animations.exists()


@scenario("rigged_animations.feature", "Stale clip files are reported, never deleted")
def test_scn012_stale_clip_files_are_reported_never_deleted(tmp_path: Path) -> None:
    project = _Project(tmp_path)
    project.animations.mkdir(parents=True)
    stale = project.animations / "A_Crate_Run.glb"
    stale.write_bytes(b"glb run")
    result, _runner, _godot = project.run()
    assert stale.is_file()
    assert result.animations is not None
    assert result.animations["stale"] == [f"{ANIMS_RES}/A_Crate_Run.glb"]


@scenario("rigged_animations.feature", "Compatible skeletons are checked on request")
def test_scn013_compatible_skeletons_are_checked_on_request(tmp_path: Path) -> None:
    project = _Project(tmp_path, compatible_with=("Characters/Hero",))
    result, _runner, godot = project.run(godot=project.hero())
    assert result.animations is not None
    assert result.animations["compatible"] == [HERO_RES]
    skeletons = [params["skeletons"] for params in godot.params if "skeletons" in params]
    assert skeletons == [[HERO_RES]]


@scenario("rigged_animations.feature", "Compatible checking is idempotent")
def test_scn014_compatible_checking_is_idempotent(tmp_path: Path) -> None:
    project = _Project(tmp_path, compatible_with=("Characters/Hero",))
    project.run(godot=project.hero())
    result, _runner, _godot = project.run(godot=project.hero())
    assert result.animations is not None
    assert result.animations["compatible"] == [HERO_RES]


@scenario("rigged_animations.feature", "A compatible target must exist and match bone names")
def test_scn015_a_compatible_target_must_exist_and_match(tmp_path: Path) -> None:
    project = _Project(tmp_path, compatible_with=("Characters/Hero",))
    error = _raises(project, FinalizeGodot(tmp_path), "finalize.skeleton_not_found")
    assert "Characters/Hero" in error.message
    godot = project.hero(bones=("pelvis",))
    error = _raises(project, godot, "finalize.skeleton_mismatch")
    assert "root" in error.message


@scenario("rigged_animations.feature", "Without compatible_with nothing is checked")
def test_scn016_without_compatible_with_nothing_is_checked(tmp_path: Path) -> None:
    project = _Project(tmp_path)
    result, _runner, godot = project.run()
    assert result.animations is not None
    assert result.animations["compatible"] == []
    assert [params["skeletons"] for params in godot.params if "skeletons" in params] == [[]]
