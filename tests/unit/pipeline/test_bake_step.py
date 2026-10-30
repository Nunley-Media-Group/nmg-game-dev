"""The #67 bake acceptance, carried onto the finalize bake step (#69).

The bake step calls ``bake_core.bake_asset`` through the Blender entry.  Its envelope carries that
result verbatim under ``outputs["bake"]``, so the texture paths, byte totals, proof metrics, and
summary #67 reported still reach the caller.  A bake refusal surfaces as
``bake.texture.bake_failed``
with stage ``bake``.  The assertions that were tied to the removed ``Prompt`` and MCP script stage
API are not carried over.  Asset class and budgets come from the request now.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nmg_game_dev.pipeline import FinalizeRequest, PipelineError, StepResult, run_step
from tests.finalize_fakes import FakeStepRunner, default_bake_result

BAKE_REMEDIATION = "Set Alpha to 1 and Transmission Weight to 0, then rerun the bake."


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


def _bake(request: FinalizeRequest, tmp_path: Path, runner: FakeStepRunner) -> StepResult:
    return run_step(
        "bake",
        request,
        runner=runner,
        cache_dir=tmp_path / "cache",
        job_dir=tmp_path / "job",
    )


class TestOutputs:
    def test_outputs_carry_texture_paths_byte_totals_proof_and_summary(
        self, request_for: FinalizeRequest, tmp_path: Path
    ) -> None:
        runner = FakeStepRunner(request_for)
        result = _bake(request_for, tmp_path, runner)
        bake = result.outputs["bake"]

        assert (
            bake["desktop_textures"]
            == default_bake_result(tmp_path / "job", "Crate", "standard_prop")["desktop_textures"]
        )
        assert bake["mobile_textures"]
        assert bake["texture_bytes_desktop"] == 4096
        assert bake["texture_bytes_mobile"] == 1024
        assert bake["proof"]["mean_abs_diff"] == 0.012
        assert str(bake["summary"]).startswith("Baked 1 material for Crate")
        assert str(bake["manifest_path"]).endswith("bake.json")

    def test_step_summary_is_the_bake_summary(
        self, request_for: FinalizeRequest, tmp_path: Path
    ) -> None:
        result = _bake(request_for, tmp_path, FakeStepRunner(request_for))
        assert result.summary.startswith("Baked 1 material")

    def test_blend_output_points_at_the_bake_result(
        self, request_for: FinalizeRequest, tmp_path: Path
    ) -> None:
        result = _bake(request_for, tmp_path, FakeStepRunner(request_for))
        assert str(result.outputs["blend"]).endswith("bake.blend")

    def test_cache_hit_flag_from_bake_core_passes_through(
        self, request_for: FinalizeRequest, tmp_path: Path
    ) -> None:
        bake_result = {
            **default_bake_result(tmp_path / "job", "Crate", "standard_prop"),
            "cache_hit": True,
        }
        result = _bake(request_for, tmp_path, FakeStepRunner(request_for, bake_result=bake_result))
        assert result.outputs["bake"]["cache_hit"] is True

    def test_bake_runs_after_validate_with_the_checkpoint_as_input(
        self, request_for: FinalizeRequest, tmp_path: Path
    ) -> None:
        runner = FakeStepRunner(request_for)
        _bake(request_for, tmp_path, runner)
        assert runner.steps_run() == ["validate", "bake"]
        bake_call = next(call for call in runner.calls if call["step"] == "bake")
        assert str(bake_call["in_blend"]).endswith("checkpoint.blend")


class TestErrors:
    def test_bake_error_raises_bake_texture_bake_failed_with_stage_bake(
        self, request_for: FinalizeRequest, tmp_path: Path
    ) -> None:
        runner = FakeStepRunner(
            request_for,
            failures={
                "bake": (
                    "texture.bake_failed",
                    "Material 'Crate_Glass' has Alpha below 1 or linked on 'Principled BSDF'.",
                    BAKE_REMEDIATION,
                )
            },
        )
        with pytest.raises(PipelineError) as info:
            _bake(request_for, tmp_path, runner)
        assert info.value.code == "bake.texture.bake_failed"
        assert info.value.stage == "bake"
        assert "Crate_Glass" in info.value.message
        assert "Alpha" in info.value.remediation

    def test_already_prefixed_code_is_kept(
        self, request_for: FinalizeRequest, tmp_path: Path
    ) -> None:
        runner = FakeStepRunner(
            request_for,
            failures={"bake": ("bake.texture.bake_failed", "refused", BAKE_REMEDIATION)},
        )
        with pytest.raises(PipelineError) as info:
            _bake(request_for, tmp_path, runner)
        assert info.value.code == "bake.texture.bake_failed"

    def test_failed_bake_stops_the_run_before_later_steps(
        self, request_for: FinalizeRequest, tmp_path: Path
    ) -> None:
        runner = FakeStepRunner(
            request_for,
            failures={"bake": ("texture.bake_failed", "refused", BAKE_REMEDIATION)},
        )
        with pytest.raises(PipelineError):
            _bake(request_for, tmp_path, runner)
        assert "variants" not in runner.steps_run()
        assert "export" not in runner.steps_run()
