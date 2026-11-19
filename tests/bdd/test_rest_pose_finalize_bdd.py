"""pytest-bdd bindings for rest_pose_finalize.feature: SCN001-SCN005 of #236.

Each binding runs its proof in tests/blender/test_rest_pose_finalize.py through
scripts/run-blender-tests.sh, because every proof needs real Blender data. The proofs build a
rigged hero, pose it with no action assigned, and check the rest-pose geometry, so a plain CPython
run has no Blender to exercise. A binding skips when no Blender resolves. The Given, When, and
Then steps are narrative and carry no assertions of their own.

SCN003 runs two proofs: the export clause and the make_copy clause. reduce_asset itself refuses
any collection with an armature (reduce.rigged, #139 AC13), which SCN004 covers.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, scenario, then, when

from tests.release_fakes import resolved_blender

REPO_ROOT = Path(__file__).resolve().parents[2]
_BLENDER = "tests/blender/test_rest_pose_finalize.py::"


def _blender(node: str) -> None:
    """Run the headless Blender proof node; skip when no Blender resolves."""
    blender = resolved_blender()
    if blender is None:
        pytest.skip("Blender does not resolve (set BLENDER_BIN or BLENDER_APP); case not run")
    completed = subprocess.run(
        [str(REPO_ROOT / "scripts" / "run-blender-tests.sh"), _BLENDER + node],
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


@scenario("rest_pose_finalize.feature", "A posed rig does not fail the pivot check")
def test_scn001_a_posed_rig_does_not_fail_the_pivot_check() -> None:
    _blender("test_scn001_a_posed_rig_does_not_fail_the_pivot_check")


@scenario("rest_pose_finalize.feature", "The mesh checks measure the rest pose")
def test_scn002_the_mesh_checks_measure_the_rest_pose() -> None:
    _blender("test_scn002_the_mesh_checks_measure_the_rest_pose")


@scenario("rest_pose_finalize.feature", "Export and the reduce copy step do not bake the pose")
def test_scn003_export_and_the_reduce_copy_step_do_not_bake_the_pose() -> None:
    _blender("test_scn003_export_variants_does_not_bake_the_pose")
    _blender("test_scn003_make_copy_evaluates_the_rest_pose")


@scenario("rest_pose_finalize.feature", "The scene is left unchanged")
def test_scn004_the_scene_is_left_unchanged() -> None:
    _blender("test_scn004_the_scene_is_left_unchanged")


@scenario("rest_pose_finalize.feature", "Exporting clips does not leave a stray pose")
def test_scn005_exporting_clips_leaves_every_pose_bone_at_identity() -> None:
    _blender("test_scn005_exporting_clips_leaves_every_pose_bone_at_identity")
