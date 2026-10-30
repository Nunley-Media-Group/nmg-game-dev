"""pytest-bdd bindings for texture_bake.feature: the finalize bake step at #67 AC5 and AC6 (#69)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pytest_bdd import given, parsers, scenario, then, when

from nmg_game_dev.pipeline import FinalizeRequest, PipelineError, StepResult, run_step
from tests.finalize_fakes import FakeStepRunner

_TRANSPARENCY_REMEDIATION = "Set Alpha to 1 and Transmission Weight to 0, then rerun the bake."


@scenario(
    "texture_bake.feature",
    "The bake step outputs carry the texture paths, byte totals, proof, and summary",
)
def test_bake_outputs_carry_bake_fields() -> None:
    """AC5: the bake step reports the same texture paths, byte totals, proof, and summary."""


@scenario(
    "texture_bake.feature",
    "A material the bake cannot represent raises PipelineError for the bake step",
)
def test_unrepresentable_material_raises() -> None:
    """AC6: a bake error becomes a PipelineError with stage bake and a remediation."""


@given(
    parsers.parse(
        'an authored collection "{collection}" of class "{asset_class}" in category "{category}"'
    ),
    target_fixture="request_obj",
)
def _request(collection: str, asset_class: str, category: str, tmp_path: Path) -> FinalizeRequest:
    blend = tmp_path / f"{collection.lower()}.blend"
    blend.write_bytes(b"authored")
    return FinalizeRequest(
        collection=collection,
        category=category,
        asset_class=asset_class,  # type: ignore[arg-type]
        export_root=tmp_path / "export",
        blend=blend,
    )


@given(
    parsers.parse('the Blender runner returns a successful bake for "{collection}"'),
    target_fixture="runner",
)
def _successful_bake(request_obj: FinalizeRequest) -> FakeStepRunner:
    return FakeStepRunner(request_obj)


@given(
    parsers.parse(
        "the Blender runner reports a texture.bake_failed error for a material with alpha 0.5"
    ),
    target_fixture="runner",
)
def _failed_bake(request_obj: FinalizeRequest) -> FakeStepRunner:
    return FakeStepRunner(
        request_obj,
        failures={
            "bake": (
                "texture.bake_failed",
                "Material 'Crate_Glass' has Alpha below 1 or linked on 'Principled BSDF'.",
                _TRANSPARENCY_REMEDIATION,
            )
        },
    )


@when("the bake step runs", target_fixture="stage_state")
def _run_bake(
    request_obj: FinalizeRequest, runner: FakeStepRunner, tmp_path: Path
) -> dict[str, Any]:
    state: dict[str, Any] = {}
    try:
        state["result"] = run_step(
            "bake",
            request_obj,
            runner=runner,
            cache_dir=tmp_path / "cache",
            job_dir=tmp_path / "job",
        )
    except PipelineError as error:
        state["error"] = error
    return state


@then("the bake outputs carry the Desktop and Mobile texture paths")
def _paths(stage_state: dict[str, Any]) -> None:
    result = stage_state["result"]
    assert isinstance(result, StepResult)
    bake = result.outputs["bake"]
    assert bake["desktop_textures"]
    assert bake["mobile_textures"]


@then("the bake outputs carry the texture byte totals, proof metrics, and summary")
def _totals(stage_state: dict[str, Any]) -> None:
    result = stage_state["result"]
    assert isinstance(result, StepResult)
    bake = result.outputs["bake"]
    assert bake["texture_bytes_desktop"] == 4096
    assert bake["texture_bytes_mobile"] == 1024
    assert bake["proof"]["mean_abs_diff"] == 0.012
    assert str(bake["summary"]).startswith("Baked 1 material")


@then(parsers.parse('a PipelineError is raised with code "{code}" and stage "{stage}"'))
def _error(stage_state: dict[str, Any], code: str, stage: str) -> None:
    error = stage_state.get("error")
    assert isinstance(error, PipelineError)
    assert error.code == code
    assert error.stage == stage


@then("the PipelineError remediation names the transparency fix")
def _remediation(stage_state: dict[str, Any]) -> None:
    error = stage_state["error"]
    assert "Alpha" in error.remediation
