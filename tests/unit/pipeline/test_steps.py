"""Unit tests for the finalize step table, settings, gates, and envelope handling (#69)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nmg_game_dev.pipeline import PipelineError
from nmg_game_dev.pipeline.request import FinalizeRequest
from nmg_game_dev.pipeline.steps import (
    STEP_ORDER,
    blobs_for,
    chain_input,
    envelope_outputs,
    gate_outputs,
    ordered_steps,
    parse_step,
    ue_destination,
)


def _request(tmp_path: Path) -> FinalizeRequest:
    blend = tmp_path / "crate.blend"
    blend.write_bytes(b"x")
    return FinalizeRequest(
        collection="Crate",
        category="Props",
        asset_class="standard_prop",
        export_root=tmp_path / "export",
        blend=blend,
    )


def test_ordered_steps_runs_every_prerequisite_of_the_requested_step() -> None:
    assert ordered_steps(("variants",)) == ("validate", "bake", "variants")
    assert ordered_steps(("import_ue",)) == (
        "validate",
        "bake",
        "variants",
        "export",
        "reimport",
        "import_ue",
    )
    assert ordered_steps(("export_anims",)) == ("validate", "bake", "variants", "export_anims")
    assert ordered_steps(("import_anims",)) == STEP_ORDER
    assert ordered_steps(("reimport",)) == ("validate", "bake", "variants", "export", "reimport")
    assert ordered_steps(("bake", "validate")) == ("validate", "bake")


def test_parse_step_refuses_an_unknown_name() -> None:
    with pytest.raises(PipelineError) as info:
        parse_step("generate")
    assert info.value.code == "finalize.unknown_step"


def test_ue_destination_is_the_content_folder_per_variant(tmp_path: Path) -> None:
    assert ue_destination(_request(tmp_path), "Mobile") == "/Game/Props/Crate/Mobile"


def test_chain_input_depends_on_the_asset_hash_as_well_as_the_output() -> None:
    assert chain_input("asset-a", "out") != chain_input("asset-b", "out")
    assert chain_input("asset-a", "out") != chain_input("asset-a", "other")


def test_a_failing_envelope_becomes_a_step_prefixed_pipeline_error() -> None:
    envelope = {
        "schemaVersion": 1,
        "step": "bake",
        "ok": False,
        "outputs": {},
        "error": {"code": "texture.bake_failed", "message": "m", "remediation": "r"},
    }
    with pytest.raises(PipelineError) as info:
        envelope_outputs("bake", envelope)
    assert info.value.code == "bake.texture.bake_failed"
    assert info.value.stage == "bake"


def test_an_envelope_for_another_step_is_refused() -> None:
    with pytest.raises(PipelineError) as info:
        envelope_outputs(
            "bake", {"schemaVersion": 1, "step": "variants", "ok": True, "outputs": {}}
        )
    assert info.value.code == "finalize.bad_envelope"


def test_a_passing_envelope_returns_its_outputs() -> None:
    outputs = envelope_outputs(
        "validate",
        {"schemaVersion": 1, "step": "validate", "ok": True, "outputs": {"report": "/r.json"}},
    )
    assert outputs == {"report": "/r.json"}


def test_a_failing_contract_report_is_gated_as_contract_failed(tmp_path: Path) -> None:
    report = tmp_path / "validate.report.json"
    report.write_text(
        json.dumps(
            {
                "kind": "contract",
                "asset": "Crate",
                "class": "standard_prop",
                "passed": False,
                "findings": [{"rule": "r", "target": "t", "message": "m", "remediation": "fix"}],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(PipelineError) as info:
        gate_outputs("validate", {"report": str(report)})
    assert info.value.code == "quality.contract_failed"


def test_blobs_for_names_each_export_folder_and_report(tmp_path: Path) -> None:
    outputs = {
        "variants": {
            "Desktop": {"dir": str(tmp_path / "D"), "pre_report": str(tmp_path / "pD.json")},
            "Mobile": {"dir": str(tmp_path / "M"), "pre_report": str(tmp_path / "pM.json")},
        },
        "sidecar": str(tmp_path / "nmg-variants.json"),
    }
    blobs = blobs_for("export", outputs)
    assert set(blobs) == {
        "Desktop",
        "Mobile",
        "export.pre-report-Desktop.json",
        "export.pre-report-Mobile.json",
        "nmg-variants.json",
    }


def test_per_clip_steps_are_flagged_and_the_mesh_steps_are_not() -> None:
    # The per-clip flag keeps export_anims and import_anims out of the whole-step cache (#138).
    from nmg_game_dev.pipeline.steps import STEPS

    per_clip = {name for name, spec in STEPS.items() if spec.per_clip}
    assert per_clip == {"export_anims", "import_anims"}


def test_clip_settings_hash_follows_the_export_options_fingerprint(tmp_path: Path) -> None:
    # The export clip key changes when ANIM_EXPORT_OPTIONS changes, and not otherwise.
    from nmg_game_dev.pipeline.steps import clip_settings_hash

    request = _request(tmp_path)
    same = clip_settings_hash("export_anims", request, options="opts-a")
    assert same == clip_settings_hash("export_anims", request, options="opts-a")
    assert same != clip_settings_hash("export_anims", request, options="opts-b")


def test_clip_settings_hash_does_not_include_compatible_with(tmp_path: Path) -> None:
    from nmg_game_dev.pipeline.steps import clip_settings_hash

    plain = _request(tmp_path)
    compatible = plain.model_copy(update={"compatible_with": ("Props/Other",)})
    assert clip_settings_hash("import_anims", plain) == clip_settings_hash(
        "import_anims", compatible
    )


def test_the_desktop_skeleton_path_names_the_character() -> None:
    from nmg_game_dev.pipeline.steps import desktop_skeleton_path

    request = FinalizeRequest(
        collection="Hero",
        category="Characters",
        asset_class="character",
        export_root=Path("/tmp/x"),
    )
    assert desktop_skeleton_path(request) == "/Game/Characters/Hero/Desktop/SM_Hero_Skeleton"


def test_import_ue_chain_is_unchanged_by_the_new_steps() -> None:
    # AC9 and the spec test: ordered_steps(("import_ue",)) equals today's six-step chain.
    assert ordered_steps(("import_ue",)) == (
        "validate",
        "bake",
        "variants",
        "export",
        "reimport",
        "import_ue",
    )
