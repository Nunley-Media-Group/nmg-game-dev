"""pytest-bdd bindings for rigged_animations.feature: SCN001-SCN016 of #138.

Each scenario proves itself by running the named cases: unit tests with the fakes in
tests/finalize_fakes.py, and headless Blender cases through scripts/run-blender-tests.sh.
The Given, When, and Then steps are narrative and carry no assertions of their own, so the
scenario text stays the approved spec's.  A Blender case skips when no Blender resolves, as the
rigged bindings do, so a plain CPython run reports those cases as skipped rather than passed.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, scenario, then, when

from tests.release_fakes import resolved_blender

REPO_ROOT = Path(__file__).resolve().parents[2]
_ANIMS = "tests/unit/pipeline/test_anims.py::"
_UE = "tests/unit/test_unreal_import_anims.py::"
_CLI = "tests/unit/test_finalize_cli.py::"
_MCP = "tests/unit/test_finalize_mcp.py::"
_BLENDER = "tests/blender/test_finalize_anims.py::"


def _host(*nodes: str) -> None:
    """Run the unit cases ``nodes`` in a subprocess and fail with their output when one fails."""
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *nodes],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, (completed.stdout + completed.stderr)[-3000:]


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


@scenario("rigged_animations.feature", "Finalize exports one animation FBX per clip")
def test_scn001_one_animation_fbx_per_clip() -> None:
    _blender(_BLENDER + "test_one_armature_only_fbx_per_clip_and_each_reimports_as_one_clip")
    _host(_ANIMS + "TestExportPerClip::test_each_clip_is_exported_as_its_own_fbx")


@scenario(
    "rigged_animations.feature", "The clip set is provenance clips plus actions held on the rig"
)
def test_scn002_clip_set_is_provenance_plus_rig_actions() -> None:
    _blender(_BLENDER + "test_the_clip_set_is_provenance_plus_the_rigs_actions_and_excludes_other")


@scenario("rigged_animations.feature", "nmg-animations.json records real clip data")
def test_scn003_sidecar_records_real_clip_data() -> None:
    _blender(_BLENDER + "test_the_sidecar_fields_match_the_exported_actions_and_sources")
    _host(_ANIMS + "TestExportPerClip::test_sidecar_lists_real_clip_data_and_authored_source")
    _host(_ANIMS + "TestExportPerClip::test_a_provenance_clip_carries_its_recorded_source")


@scenario("rigged_animations.feature", "Clips import as AnimSequences on the Desktop skeleton")
def test_scn004_clips_import_as_anim_sequences() -> None:
    _host(_ANIMS + "TestImportPerClip::test_clips_import_as_anim_sequences_on_the_desktop_skeleton")
    _host(_UE + "test_the_program_imports_anim_sequences_on_the_desktop_skeleton")


@scenario("rigged_animations.feature", "An imported clip is checked against the sidecar")
def test_scn005_imported_clip_is_checked_against_the_sidecar() -> None:
    _host(
        _ANIMS + "TestImportPerClip::test_a_frame_count_difference_names_the_clip_and_both_values",
        _ANIMS + "TestImportPerClip::test_a_skeleton_difference_fails_the_clip_check",
    )


@scenario("rigged_animations.feature", "Clips are cached individually")
def test_scn006_clips_are_cached_individually() -> None:
    _host(
        _ANIMS + "TestExportPerClip::test_only_the_clip_that_changed_is_exported_and_reimported",
        _ANIMS + "TestExportPerClip::test_mesh_steps_stay_cached_when_only_a_clip_changes",
    )


@scenario("rigged_animations.feature", "Force reruns every clip")
def test_scn007_force_reruns_every_clip() -> None:
    _host(_ANIMS + "TestExportPerClip::test_force_reexports_and_reimports_every_clip")


@scenario("rigged_animations.feature", "Assets without clips pass through")
def test_scn008_assets_without_clips_pass_through() -> None:
    _host(_ANIMS + "TestExportPerClip::test_an_unrigged_asset_passes_through_with_no_clips")


@scenario("rigged_animations.feature", "The new steps run alone")
def test_scn009_the_new_steps_run_alone() -> None:
    _host(
        _ANIMS
        + "TestExportPerClip::test_run_step_export_anims_runs_its_prerequisites_and_returns_"
        + "the_standard_shape",
        _CLI + "test_export_anims_runs_its_prerequisites_and_no_later_step",
        _CLI + "test_import_anims_is_a_command_and_runs_the_whole_chain",
        _MCP + "test_run_finalize_step_accepts_both_clip_steps",
    )


@scenario("rigged_animations.feature", "import_anims needs the Desktop skeleton")
def test_scn010_import_anims_needs_the_desktop_skeleton() -> None:
    _host(_ANIMS + "TestImportPerClip::test_a_missing_desktop_skeleton_says_to_run_import_ue_first")


@scenario("rigged_animations.feature", "An invalid clip name stops the export")
def test_scn011_an_invalid_clip_name_stops_the_export() -> None:
    _blender(_BLENDER + "test_an_invalid_clip_name_is_reported_by_the_probe_and_writes_nothing")
    _host(_ANIMS + "TestExportPerClip::test_a_clip_with_an_invalid_name_stops_before_any_write")


@scenario("rigged_animations.feature", "Stale AnimSequences are reported, never deleted")
def test_scn012_stale_sequences_are_reported_never_deleted() -> None:
    _host(_ANIMS + "TestImportPerClip::test_stale_sequences_are_reported_and_never_deleted")


@scenario("rigged_animations.feature", "Compatible skeletons are registered on request")
def test_scn013_compatible_skeletons_are_registered_on_request() -> None:
    _host(_ANIMS + "TestCompatibleSkeletons::test_registration_is_two_way_and_listed_in_the_result")


@scenario("rigged_animations.feature", "Compatible registration is idempotent")
def test_scn014_compatible_registration_is_idempotent() -> None:
    _host(_ANIMS + "TestCompatibleSkeletons::test_registration_is_idempotent")


@scenario("rigged_animations.feature", "A compatible target must exist and match bone names")
def test_scn015_a_compatible_target_must_exist_and_match() -> None:
    _host(
        _ANIMS + "TestCompatibleSkeletons::test_a_missing_target_names_it_and_registers_nothing",
        _ANIMS
        + "TestCompatibleSkeletons::test_a_bone_mismatch_names_the_differing_bones_and_registers_"
        + "nothing",
    )


@scenario("rigged_animations.feature", "Without compatible_with nothing is registered")
def test_scn016_without_compatible_with_nothing_is_registered() -> None:
    _host(_ANIMS + "TestCompatibleSkeletons::test_without_compatible_with_nothing_is_registered")
