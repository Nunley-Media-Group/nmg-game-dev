"""Unit tests for the finalize step table, settings, gates, and envelope handling (#69)."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from nmg_game_dev.pipeline import PipelineError
from nmg_game_dev.pipeline.request import FinalizeRequest
from nmg_game_dev.pipeline.steps import (
    _BAKE_VERSION,
    _STEP_VERSION,
    STEP_ORDER,
    blobs_for,
    chain_input,
    envelope_outputs,
    gate_outputs,
    ordered_steps,
    parse_step,
    settings_hash,
    variant_dir,
)

_BAKE_CACHE = (
    Path(__file__).resolve().parents[3]
    / "plugins"
    / "nmg-game-dev-blender-addon"
    / "bake_core"
    / "cache.py"
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
    assert ordered_steps(("import_godot",)) == (
        "validate",
        "bake",
        "variants",
        "export",
        "reimport",
        "import_godot",
    )
    assert ordered_steps(("export_anims",)) == ("validate", "bake", "variants", "export_anims")
    assert ordered_steps(("import_anims",)) == STEP_ORDER
    assert ordered_steps(("reimport",)) == ("validate", "bake", "variants", "export", "reimport")
    assert ordered_steps(("bake", "validate")) == ("validate", "bake")


def test_parse_step_refuses_an_unknown_name() -> None:
    with pytest.raises(PipelineError) as info:
        parse_step("generate")
    assert info.value.code == "finalize.unknown_step"


def test_variant_dir_and_glb_path_follow_the_export_root(tmp_path: Path) -> None:
    from nmg_game_dev.pipeline.steps import glb_path

    request = _request(tmp_path)
    assert variant_dir(request, "Mobile") == tmp_path / "export" / "Props" / "Crate" / "Mobile"
    assert glb_path(request, "Desktop") == (
        tmp_path / "export" / "Props" / "Crate" / "Desktop" / "Crate.glb"
    )


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


def test_the_desktop_skeleton_key_names_the_character_glb() -> None:
    from nmg_game_dev.pipeline.steps import desktop_skeleton_key

    request = FinalizeRequest(
        collection="Hero",
        category="Characters",
        asset_class="character",
        export_root=Path("/tmp/x"),
    )
    assert desktop_skeleton_key(request) == "Characters/Hero/Desktop/Hero.glb"


def test_import_godot_chain_is_the_six_step_mesh_chain() -> None:
    assert ordered_steps(("import_godot",)) == (
        "validate",
        "bake",
        "variants",
        "export",
        "reimport",
        "import_godot",
    )


def test_import_godot_is_a_godot_step_and_the_salt_is_five() -> None:
    from nmg_game_dev.pipeline.steps import _STEP_VERSION, STEPS

    assert STEPS["import_godot"].kind == "godot"
    assert STEPS["import_anims"].kind == "godot"
    assert "import_ue" not in STEPS
    assert _STEP_VERSION == "5"


def test_the_import_godot_settings_cover_collection_category_and_export_root(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    base = settings_hash("import_godot", request, "budgets")
    moved = request.model_copy(update={"export_root": tmp_path / "elsewhere"})
    renamed = request.model_copy(update={"category": "Crates"})
    assert settings_hash("import_godot", moved, "budgets") != base
    assert settings_hash("import_godot", renamed, "budgets") != base


def test_a_bake_key_from_before_the_bake_version_bump_misses(tmp_path: Path) -> None:
    # #240: the tiling bake changed its output, so a bake cached before it must not be restored.
    request = _request(tmp_path)
    pre_bump = {
        "step": "bake",
        "version": _STEP_VERSION,
        "collection": request.collection,
        "asset_class": request.asset_class,
        "device": request.device,
        "budgets": "budgets",
    }
    pre_bump_key = hashlib.sha256(json.dumps(pre_bump, sort_keys=True).encode()).hexdigest()
    assert settings_hash("bake", request, "budgets") != pre_bump_key


def test_the_bake_key_version_mirrors_the_add_on_bake_version() -> None:
    match = re.search(r'^BAKE_VERSION = "([^"]+)"$', _BAKE_CACHE.read_text(), re.MULTILINE)
    assert match is not None
    assert match.group(1) == _BAKE_VERSION
