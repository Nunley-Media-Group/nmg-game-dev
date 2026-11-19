"""pytest-bdd bindings for shared_clip_names.feature: SCN001-SCN009 of #233.

SCN004 to SCN006 run the real finalize pipeline with ``FakeStepRunner`` standing in for Blender.
Each asserts the refusal code, its message and remediation, and that no clip file or sidecar is
written.  SCN009 reads the four docs for the naming rule and both new codes.  SCN001 to SCN003,
SCN007, and SCN008 need real Blender data: each binding runs its proof in
tests/blender/test_shared_clip_names_bdd.py through scripts/run-blender-tests.sh and skips when no
Blender resolves.  The Given, When, and Then steps are narrative and carry no assertions of their
own.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenario, then, when

from nmg_game_dev.pipeline import (
    STEP_ORDER,
    FinalizeClients,
    FinalizeRequest,
    PipelineError,
    finalize,
)
from nmg_game_dev.pipeline.anims import SIDECAR_NAME
from tests.finalize_fakes import FakeBlenderSession, FakeStepRunner, FinalizeGodot
from tests.release_fakes import resolved_blender

REPO_ROOT = Path(__file__).resolve().parents[2]
_BLENDER = "tests/blender/test_shared_clip_names_bdd.py::"
IDLE = {"name": "Idle", "hash": "hash-idle"}
DOCS = (
    "docs/asset-contract.md",
    "docs/rigging-and-animation.md",
    "docs/mcp/finalize.md",
    "skills/finalize-asset/SKILL.md",
)


def _request(root: Path) -> FinalizeRequest:
    blend = root / "streetthug.blend"
    blend.write_bytes(b"authored")
    return FinalizeRequest(
        collection="StreetThug",
        category="Characters",
        asset_class="character",
        export_root=root / "export",
        blend=blend,
    )


def _refused(
    root: Path,
    *,
    clips: list[dict[str, Any]],
    rig_mismatch: list[str] | None = None,
    duplicates: list[dict[str, Any]] | None = None,
) -> tuple[PipelineError, FinalizeRequest]:
    """Run finalize on a StreetThug whose probe reports the given problems; return the refusal."""
    request = _request(root)
    runner = FakeStepRunner(
        request,
        clips=clips,
        rig_mismatch=rig_mismatch or [],
        duplicates=duplicates or [],
    )
    with pytest.raises(PipelineError) as info:
        finalize(
            request,
            steps=STEP_ORDER,
            cache_dir=root / "cache",
            runner=runner,
            job_dir=root / "job",
            clients=FinalizeClients(blender=FakeBlenderSession(), godot=FinalizeGodot(root)),
        )
    return info.value, request


def _nothing_written(request: FinalizeRequest) -> bool:
    """True when no clip file and no sidecar exists under the clip folder."""
    folder = request.export_root / request.category / request.collection / "Animations"
    return not (folder / SIDECAR_NAME).exists() and not list(folder.glob("A_*.glb"))


def _blender(*nodes: str) -> None:
    """Run the headless Blender proofs ``nodes``; skip when no Blender resolves."""
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


@scenario("shared_clip_names.feature", "An @-suffixed action exports under its bare clip name")
def test_scn001_an_suffixed_action_exports_under_its_bare_name() -> None:
    _blender(_BLENDER + "test_scn001_an_suffixed_action_exports_under_its_bare_name")


@scenario("shared_clip_names.feature", "Two characters in one file each export their own Idle")
def test_scn002_two_characters_each_export_their_own_idle() -> None:
    _blender(_BLENDER + "test_scn002_two_characters_each_export_their_own_idle")


@scenario("shared_clip_names.feature", "Unsuffixed action names export as before")
def test_scn003_unsuffixed_action_names_export_as_before() -> None:
    _blender(_BLENDER + "test_scn003_unsuffixed_action_names_export_as_before")


@scenario(
    "shared_clip_names.feature", "Importing a clip onto one character leaves the others alone"
)
def test_scn007_importing_a_clip_onto_one_rig_leaves_the_other_alone() -> None:
    _blender(_BLENDER + "test_scn007_importing_a_clip_onto_one_rig_leaves_the_other_alone")


@scenario("shared_clip_names.feature", "Re-importing a clip replaces only that rig's action")
def test_scn008_reimporting_a_clip_replaces_only_that_rigs_action() -> None:
    _blender(_BLENDER + "test_scn008_reimporting_a_clip_replaces_only_that_rigs_action")


@scenario("shared_clip_names.feature", "A suffix naming another rig stops the export")
def test_scn004_a_suffix_naming_another_rig_stops_the_export(tmp_path: Path) -> None:
    error, request = _refused(tmp_path, clips=[IDLE], rig_mismatch=["Idle@SK_Cop"])

    assert error.code == "finalize.clip_rig_mismatch"
    assert "Idle@SK_Cop" in error.message
    assert error.remediation
    assert _nothing_written(request)


@scenario("shared_clip_names.feature", "Two actions resolving to one clip stop the export")
def test_scn005_two_actions_resolving_to_one_clip_stop_the_export(tmp_path: Path) -> None:
    duplicate = {"name": "Idle", "actions": ["Idle", "Idle@SK_StreetThug"]}

    error, request = _refused(tmp_path, clips=[], duplicates=[duplicate])

    assert error.code == "finalize.clip_name_duplicate"
    assert "Idle" in error.message
    assert "Idle, Idle@SK_StreetThug" in error.message
    assert error.remediation
    assert _nothing_written(request)


@scenario("shared_clip_names.feature", "The bare clip name is still validated")
def test_scn006_the_bare_clip_name_is_still_validated(tmp_path: Path) -> None:
    bad = {"name": "1Idle", "hash": "hash-bad", "valid_name": False}

    error, request = _refused(tmp_path, clips=[bad])

    assert error.code == "finalize.clip_name_invalid"
    assert "1Idle" in error.message
    assert error.remediation
    assert _nothing_written(request)


@scenario("shared_clip_names.feature", "The clip naming rule is documented")
def test_scn009_the_clip_naming_rule_is_documented() -> None:
    texts = {doc: (REPO_ROOT / doc).read_text(encoding="utf-8") for doc in DOCS}

    for doc, text in texts.items():
        assert "@SK_<Name>" in text, doc
        assert "finalize.clip_rig_mismatch" in text, doc
        assert "finalize.clip_name_duplicate" in text, doc
    contract = texts["docs/asset-contract.md"]
    section = contract.split("### Animation clips", 1)[1].split("\n### ", 1)[0]
    assert "optional" in section
    assert "bare" in section
