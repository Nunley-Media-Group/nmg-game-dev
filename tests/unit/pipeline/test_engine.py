"""Unit tests for the finalize orchestrator: chain, cache, gates, load-back, and UE import (#69).

These run the real orchestrator, cache, gates, and envelope handling, with in-process fakes for
Blender and Unreal.  They cover AC1 (order and result shape), AC2 (checkpoint, load-back order and
refusal), AC4 (cache hits, changes, and ``--force``), and AC6 (failures stop the run).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nmg_game_dev.pipeline import (
    STEP_ORDER,
    FinalizeClients,
    FinalizeRequest,
    FinalizeResult,
    FinalizeSessionChangedError,
    PipelineError,
    finalize,
    run_step,
)
from tests.finalize_fakes import FakeBlenderSession, FakeStepRunner, FakeUnrealRunner

BLENDER_STEPS = ("validate", "bake", "variants", "export", "reimport")


@pytest.fixture()
def blend_request(tmp_path: Path) -> FinalizeRequest:
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
def session_request(blend_request: FinalizeRequest) -> FinalizeRequest:
    return blend_request.model_copy(update={"blend": None})


class _Counter:
    """Hands out a fresh job directory for each run so relocation is exercised."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.n = 0

    def next(self) -> Path:
        self.n += 1
        return self.root / f"job-{self.n}"


@pytest.fixture()
def jobs(tmp_path: Path) -> _Counter:
    return _Counter(tmp_path / "jobs")


def _run(
    request: FinalizeRequest,
    tmp_path: Path,
    jobs: _Counter,
    runner: FakeStepRunner,
    *,
    unreal: FakeUnrealRunner | None = None,
    blender: FakeBlenderSession | None = None,
    force: bool = False,
    steps: tuple[str, ...] = STEP_ORDER,
) -> FinalizeResult:
    return finalize(
        request,
        steps=steps,
        force=force,
        cache_dir=tmp_path / "cache",
        runner=runner,
        job_dir=jobs.next(),
        clients=FinalizeClients(blender=blender, unreal=unreal),
    )


class TestChain:
    def test_all_steps_run_in_order_and_the_result_lists_each(
        self, blend_request: FinalizeRequest, tmp_path: Path, jobs: _Counter
    ) -> None:
        runner = FakeStepRunner(blend_request)
        unreal = FakeUnrealRunner()
        result = _run(blend_request, tmp_path, jobs, runner, unreal=unreal)

        assert runner.steps_run() == list(BLENDER_STEPS)
        assert [step.step for step in result.steps] == list(STEP_ORDER)
        assert result.desktop_content_path == "/Game/Props/Crate/Desktop"
        assert result.mobile_content_path == "/Game/Props/Crate/Mobile"
        assert len(unreal.codes) == 2

    def test_result_blend_is_the_variants_output(
        self, blend_request: FinalizeRequest, tmp_path: Path, jobs: _Counter
    ) -> None:
        result = _run(
            blend_request,
            tmp_path,
            jobs,
            FakeStepRunner(blend_request),
            unreal=FakeUnrealRunner(),
        )
        assert result.result_blend is not None
        assert result.result_blend.endswith("variants.blend")

    def test_headless_run_never_loads_back(
        self, blend_request: FinalizeRequest, tmp_path: Path, jobs: _Counter
    ) -> None:
        result = _run(
            blend_request,
            tmp_path,
            jobs,
            FakeStepRunner(blend_request),
            unreal=FakeUnrealRunner(),
        )
        assert result.loaded_back is False

    def test_export_passes_the_export_root_layout_to_reimport(
        self, blend_request: FinalizeRequest, tmp_path: Path, jobs: _Counter
    ) -> None:
        runner = FakeStepRunner(blend_request)
        _run(blend_request, tmp_path, jobs, runner, unreal=FakeUnrealRunner())
        reimport = next(call for call in runner.calls if call["step"] == "reimport")
        variants = reimport["inputs"]["variants"]
        assert set(variants) == {"Desktop", "Mobile"}
        assert variants["Desktop"]["dir"].endswith("Props/Crate/Desktop")


class TestCache:
    def test_rerun_of_an_unchanged_asset_is_all_cache_hits(
        self, blend_request: FinalizeRequest, tmp_path: Path, jobs: _Counter
    ) -> None:
        _run(
            blend_request, tmp_path, jobs, FakeStepRunner(blend_request), unreal=FakeUnrealRunner()
        )

        runner = FakeStepRunner(blend_request)
        unreal = FakeUnrealRunner()
        result = _run(blend_request, tmp_path, jobs, runner, unreal=unreal)

        assert runner.steps_run() == []
        assert all(step.cache_hit for step in result.steps)
        assert unreal.codes == []

    def test_changed_asset_misses_every_step_from_the_first(
        self, blend_request: FinalizeRequest, tmp_path: Path, jobs: _Counter
    ) -> None:
        _run(
            blend_request, tmp_path, jobs, FakeStepRunner(blend_request), unreal=FakeUnrealRunner()
        )

        runner = FakeStepRunner(blend_request, hash_value="asset-hash-changed")
        result = _run(blend_request, tmp_path, jobs, runner, unreal=FakeUnrealRunner())

        assert runner.steps_run() == list(BLENDER_STEPS)
        assert not any(step.cache_hit for step in result.steps)

    def test_force_reruns_every_step_even_when_cached(
        self, blend_request: FinalizeRequest, tmp_path: Path, jobs: _Counter
    ) -> None:
        _run(
            blend_request, tmp_path, jobs, FakeStepRunner(blend_request), unreal=FakeUnrealRunner()
        )

        runner = FakeStepRunner(blend_request)
        unreal = FakeUnrealRunner()
        result = _run(blend_request, tmp_path, jobs, runner, unreal=unreal, force=True)

        assert runner.steps_run() == list(BLENDER_STEPS)
        assert len(unreal.codes) == 2
        assert not any(step.cache_hit for step in result.steps)

    def test_a_changed_budget_file_changes_the_budget_dependent_keys(
        self, blend_request: FinalizeRequest, tmp_path: Path, jobs: _Counter
    ) -> None:
        _run(
            blend_request, tmp_path, jobs, FakeStepRunner(blend_request), unreal=FakeUnrealRunner()
        )
        budgets = tmp_path / "nmg-budgets.json"
        budgets.write_text('{"Props": {"poly_budget": 5000}}', encoding="utf-8")
        request = blend_request.model_copy(update={"budgets_path": budgets})

        runner = FakeStepRunner(request)
        _run(request, tmp_path, jobs, runner, unreal=FakeUnrealRunner())

        # The budget keys change for the three budget-dependent steps.  Export and reimport read the
        # variants output, which is byte-identical here, so their cached results stay valid.
        assert runner.steps_run() == ["validate", "bake", "variants"]


class TestGates:
    def test_failing_contract_report_stops_before_bake_and_import(
        self, blend_request: FinalizeRequest, tmp_path: Path, jobs: _Counter
    ) -> None:
        runner = FakeStepRunner(blend_request, failing_reports=frozenset({"validate"}))
        unreal = FakeUnrealRunner()
        with pytest.raises(PipelineError) as info:
            _run(blend_request, tmp_path, jobs, runner, unreal=unreal)

        assert info.value.code == "quality.contract_failed"
        assert "transform.root_applied" in info.value.message
        assert info.value.remediation
        assert runner.steps_run() == ["validate"]
        assert unreal.codes == []

    def test_failing_reimport_report_blocks_import(
        self, blend_request: FinalizeRequest, tmp_path: Path, jobs: _Counter
    ) -> None:
        runner = FakeStepRunner(blend_request, failing_reports=frozenset({"reimport"}))
        unreal = FakeUnrealRunner()
        with pytest.raises(PipelineError) as info:
            _run(blend_request, tmp_path, jobs, runner, unreal=unreal)

        assert info.value.code == "quality.reimport_mismatch"
        assert unreal.codes == []

    def test_bake_failure_stops_the_run_and_nothing_is_imported(
        self, blend_request: FinalizeRequest, tmp_path: Path, jobs: _Counter
    ) -> None:
        runner = FakeStepRunner(
            blend_request,
            failures={"bake": ("texture.bake_failed", "refused", "Set Alpha to 1.")},
        )
        unreal = FakeUnrealRunner()
        with pytest.raises(PipelineError) as info:
            _run(blend_request, tmp_path, jobs, runner, unreal=unreal)

        assert info.value.code == "bake.texture.bake_failed"
        assert info.value.stage == "bake"
        assert "variants" not in runner.steps_run()
        assert unreal.codes == []

    def test_failed_ue_import_is_import_ue_failed(
        self, blend_request: FinalizeRequest, tmp_path: Path, jobs: _Counter
    ) -> None:
        unreal = FakeUnrealRunner(result={"ok": False, "error": "Asset save failed"})
        with pytest.raises(PipelineError) as info:
            _run(blend_request, tmp_path, jobs, FakeStepRunner(blend_request), unreal=unreal)
        assert info.value.code == "import_ue.failed"
        assert info.value.stage == "import_ue"

    def test_missing_blend_is_refused_before_any_step(
        self, blend_request: FinalizeRequest, tmp_path: Path, jobs: _Counter
    ) -> None:
        request = blend_request.model_copy(update={"blend": tmp_path / "missing.blend"})
        runner = FakeStepRunner(request)
        with pytest.raises(PipelineError) as info:
            _run(request, tmp_path, jobs, runner)
        assert info.value.code == "finalize.blend_not_found"
        assert runner.steps_run() == []

    def test_unknown_step_is_refused(
        self, blend_request: FinalizeRequest, tmp_path: Path, jobs: _Counter
    ) -> None:
        with pytest.raises(PipelineError) as info:
            _run(blend_request, tmp_path, jobs, FakeStepRunner(blend_request), steps=("nope",))
        assert info.value.code == "finalize.unknown_step"


class TestRunStep:
    def test_run_step_returns_the_named_step_and_runs_its_prerequisites(
        self, blend_request: FinalizeRequest, tmp_path: Path, jobs: _Counter
    ) -> None:
        runner = FakeStepRunner(blend_request)
        result = run_step(
            "variants",
            blend_request,
            runner=runner,
            cache_dir=tmp_path / "cache",
            job_dir=jobs.next(),
        )
        assert result.step == "variants"
        assert runner.steps_run() == ["validate", "bake", "variants"]

    def test_run_step_validate_runs_only_validate(
        self, blend_request: FinalizeRequest, tmp_path: Path, jobs: _Counter
    ) -> None:
        runner = FakeStepRunner(blend_request)
        result = run_step(
            "validate",
            blend_request,
            runner=runner,
            cache_dir=tmp_path / "cache",
            job_dir=jobs.next(),
        )
        assert result.step == "validate"
        assert runner.steps_run() == ["validate"]
        assert str(result.outputs["report"]).endswith("validate.report.json")


class TestSession:
    def test_session_run_checkpoints_loads_back_then_imports(
        self, session_request: FinalizeRequest, tmp_path: Path, jobs: _Counter
    ) -> None:
        events: list[str] = []
        runner = FakeStepRunner(session_request, events=events)
        blender = FakeBlenderSession(events=events)
        unreal = FakeUnrealRunner(events=events)

        result = _run(session_request, tmp_path, jobs, runner, unreal=unreal, blender=blender)

        assert blender.checkpoints == ["Crate"]
        assert blender.load_backs[0]["expected_hash"] == "asset-hash-0"
        assert blender.load_backs[0]["result_blend"].endswith("variants.blend")
        assert result.loaded_back is True
        assert events == [*BLENDER_STEPS, "load_back", "import_ue", "import_ue"]

    def test_refused_load_back_still_imports_then_fails_with_session_changed(
        self, session_request: FinalizeRequest, tmp_path: Path, jobs: _Counter
    ) -> None:
        blender = FakeBlenderSession(
            load_result={"ok": True, "loaded": False, "reason": "session_changed"}
        )
        unreal = FakeUnrealRunner()
        with pytest.raises(FinalizeSessionChangedError) as info:
            _run(
                session_request,
                tmp_path,
                jobs,
                FakeStepRunner(session_request),
                unreal=unreal,
                blender=blender,
            )

        assert info.value.code == "finalize.session_changed"
        assert "variants.blend" in info.value.message
        assert info.value.result.loaded_back is False
        assert len(unreal.codes) == 2

    def test_session_that_already_holds_the_result_is_served_from_cache(
        self, session_request: FinalizeRequest, tmp_path: Path, jobs: _Counter
    ) -> None:
        _run(
            session_request,
            tmp_path,
            jobs,
            FakeStepRunner(session_request),
            unreal=FakeUnrealRunner(),
            blender=FakeBlenderSession(),
        )

        runner = FakeStepRunner(session_request, hash_value="post-load-hash")
        blender = FakeBlenderSession(hash_value="post-load-hash")
        unreal = FakeUnrealRunner()
        result = _run(session_request, tmp_path, jobs, runner, unreal=unreal, blender=blender)

        assert runner.steps_run() == []
        assert all(step.cache_hit for step in result.steps)
        assert blender.load_backs == []
        assert unreal.codes == []
        assert result.loaded_back is False

    def test_restored_original_session_reuses_the_chain_and_still_loads_back(
        self, session_request: FinalizeRequest, tmp_path: Path, jobs: _Counter
    ) -> None:
        _run(
            session_request,
            tmp_path,
            jobs,
            FakeStepRunner(session_request),
            unreal=FakeUnrealRunner(),
            blender=FakeBlenderSession(),
        )

        runner = FakeStepRunner(session_request)
        blender = FakeBlenderSession()
        result = _run(
            session_request, tmp_path, jobs, runner, unreal=FakeUnrealRunner(), blender=blender
        )

        assert runner.steps_run() == []
        assert all(step.cache_hit for step in result.steps)
        assert len(blender.load_backs) == 1
        assert result.loaded_back is True
