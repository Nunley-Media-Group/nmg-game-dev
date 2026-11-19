"""Unit tests for the finalize orchestrator: chain, cache, gates, load-back, and Godot import.

These run the real orchestrator, cache, gates, and envelope handling, with in-process fakes for
Blender and ``godot --headless`` (#69, #249).  They cover the step order and result shape, the
checkpoint, load-back order and refusal, cache hits, changes, and ``--force``, failures that stop
the run, and the ``import_godot`` failures (``godot.not_found``, ``import_godot.import_failed``,
``import_godot.mismatch``), each of which stops the run before ``import_anims``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from nmg_game_dev.godot import binary as godot_binary
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
from nmg_game_dev.pipeline import cache as cache_module
from nmg_game_dev.pipeline import steps as steps_module
from tests.finalize_fakes import FakeBlenderSession, FakeStepRunner, FinalizeGodot

# export_anims runs its probe in Blender on every run, so it is a Blender step even with no clips.
BLENDER_STEPS = ("validate", "bake", "variants", "export", "export_anims", "reimport")


DESKTOP_RES = "res://export/Props/Crate/Desktop/Crate.glb"
MOBILE_RES = "res://export/Props/Crate/Mobile/Crate.glb"


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
    godot: FinalizeGodot | None = None,
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
        clients=FinalizeClients(
            blender=blender, godot=godot if godot is not None else FinalizeGodot(tmp_path)
        ),
    )


class TestChain:
    def test_all_steps_run_in_order_and_the_result_lists_each(
        self, blend_request: FinalizeRequest, tmp_path: Path, jobs: _Counter
    ) -> None:
        runner = FakeStepRunner(blend_request)
        godot = FinalizeGodot(tmp_path)
        result = _run(blend_request, tmp_path, jobs, runner, godot=godot)

        assert runner.steps_run() == list(BLENDER_STEPS)
        assert [step.step for step in result.steps] == list(STEP_ORDER)
        assert result.desktop_resource_path == DESKTOP_RES
        assert result.mobile_resource_path == MOBILE_RES
        assert godot.count("--import") == 1
        assert len(godot.probe_calls("probe_asset.gd")) == 2

    def test_import_runs_once_then_probes_each_variant_glb(
        self, blend_request: FinalizeRequest, tmp_path: Path, jobs: _Counter
    ) -> None:
        godot = FinalizeGodot(tmp_path)

        result = _run(blend_request, tmp_path, jobs, FakeStepRunner(blend_request), godot=godot)

        assert godot.calls[0] == ["--import"]
        assert [params["glb"] for params in godot.params] == [DESKTOP_RES, MOBILE_RES]
        assert set(godot.projects) == {tmp_path}
        imported = next(step for step in result.steps if step.step == "import_godot")
        assert imported.outputs["desktop_resource_path"] == DESKTOP_RES
        assert imported.outputs["imports"]["Mobile"]["meshes"][0]["tris"] == 800

    def test_result_blend_is_the_variants_output(
        self, blend_request: FinalizeRequest, tmp_path: Path, jobs: _Counter
    ) -> None:
        result = _run(
            blend_request,
            tmp_path,
            jobs,
            FakeStepRunner(blend_request),
            godot=FinalizeGodot(tmp_path),
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
            godot=FinalizeGodot(tmp_path),
        )
        assert result.loaded_back is False

    def test_export_passes_the_export_root_layout_to_reimport(
        self, blend_request: FinalizeRequest, tmp_path: Path, jobs: _Counter
    ) -> None:
        runner = FakeStepRunner(blend_request)
        _run(blend_request, tmp_path, jobs, runner, godot=FinalizeGodot(tmp_path))
        reimport = next(call for call in runner.calls if call["step"] == "reimport")
        variants = reimport["inputs"]["variants"]
        assert set(variants) == {"Desktop", "Mobile"}
        assert variants["Desktop"]["dir"].endswith("Props/Crate/Desktop")


class TestCache:
    def test_rerun_of_an_unchanged_asset_is_all_cache_hits(
        self, blend_request: FinalizeRequest, tmp_path: Path, jobs: _Counter
    ) -> None:
        _run(
            blend_request,
            tmp_path,
            jobs,
            FakeStepRunner(blend_request),
            godot=FinalizeGodot(tmp_path),
        )

        runner = FakeStepRunner(blend_request)
        godot = FinalizeGodot(tmp_path)
        result = _run(blend_request, tmp_path, jobs, runner, godot=godot)

        # Only the export_anims probe runs.  It is never cached, because it lists the clips.
        assert runner.steps_run() == ["export_anims"]
        assert all(step.cache_hit for step in result.steps)
        assert godot.calls == []

    def test_changed_asset_misses_every_step_from_the_first(
        self, blend_request: FinalizeRequest, tmp_path: Path, jobs: _Counter
    ) -> None:
        _run(
            blend_request,
            tmp_path,
            jobs,
            FakeStepRunner(blend_request),
            godot=FinalizeGodot(tmp_path),
        )

        runner = FakeStepRunner(blend_request, hash_value="asset-hash-changed")
        result = _run(blend_request, tmp_path, jobs, runner, godot=FinalizeGodot(tmp_path))

        assert runner.steps_run() == list(BLENDER_STEPS)
        assert not any(step.cache_hit for step in result.steps)

    def test_force_reruns_every_step_even_when_cached(
        self, blend_request: FinalizeRequest, tmp_path: Path, jobs: _Counter
    ) -> None:
        _run(
            blend_request,
            tmp_path,
            jobs,
            FakeStepRunner(blend_request),
            godot=FinalizeGodot(tmp_path),
        )

        runner = FakeStepRunner(blend_request)
        godot = FinalizeGodot(tmp_path)
        result = _run(blend_request, tmp_path, jobs, runner, godot=godot, force=True)

        assert runner.steps_run() == list(BLENDER_STEPS)
        assert godot.count("--import") == 1
        assert not any(step.cache_hit for step in result.steps)

    def test_a_changed_budget_file_changes_the_budget_dependent_keys(
        self, blend_request: FinalizeRequest, tmp_path: Path, jobs: _Counter
    ) -> None:
        _run(
            blend_request,
            tmp_path,
            jobs,
            FakeStepRunner(blend_request),
            godot=FinalizeGodot(tmp_path),
        )
        budgets = tmp_path / "nmg-budgets.json"
        budgets.write_text('{"Props": {"poly_budget": 5000}}', encoding="utf-8")
        request = blend_request.model_copy(update={"budgets_path": budgets})

        runner = FakeStepRunner(request)
        _run(request, tmp_path, jobs, runner, godot=FinalizeGodot(tmp_path))

        # The budget keys change for the three budget-dependent steps.  Export and reimport read the
        # variants output, which is byte-identical here, so their cached results stay valid.  The
        # export_anims probe is not cached, so it runs after them.
        assert runner.steps_run() == ["validate", "bake", "variants", "export_anims"]


class TestGates:
    def test_failing_contract_report_stops_before_bake_and_import(
        self, blend_request: FinalizeRequest, tmp_path: Path, jobs: _Counter
    ) -> None:
        runner = FakeStepRunner(blend_request, failing_reports=frozenset({"validate"}))
        godot = FinalizeGodot(tmp_path)
        with pytest.raises(PipelineError) as info:
            _run(blend_request, tmp_path, jobs, runner, godot=godot)

        assert info.value.code == "quality.contract_failed"
        assert "transform.root_applied" in info.value.message
        assert info.value.remediation
        assert runner.steps_run() == ["validate"]
        assert godot.calls == []

    def test_failing_reimport_report_blocks_import(
        self, blend_request: FinalizeRequest, tmp_path: Path, jobs: _Counter
    ) -> None:
        runner = FakeStepRunner(blend_request, failing_reports=frozenset({"reimport"}))
        godot = FinalizeGodot(tmp_path)
        with pytest.raises(PipelineError) as info:
            _run(blend_request, tmp_path, jobs, runner, godot=godot)

        assert info.value.code == "quality.reimport_mismatch"
        assert godot.calls == []

    def test_bake_failure_stops_the_run_and_nothing_is_imported(
        self, blend_request: FinalizeRequest, tmp_path: Path, jobs: _Counter
    ) -> None:
        runner = FakeStepRunner(
            blend_request,
            failures={"bake": ("texture.bake_failed", "refused", "Set Alpha to 1.")},
        )
        godot = FinalizeGodot(tmp_path)
        with pytest.raises(PipelineError) as info:
            _run(blend_request, tmp_path, jobs, runner, godot=godot)

        assert info.value.code == "bake.texture.bake_failed"
        assert info.value.stage == "bake"
        assert "variants" not in runner.steps_run()
        assert godot.calls == []

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
        godot = FinalizeGodot(tmp_path, events=events)

        result = _run(session_request, tmp_path, jobs, runner, godot=godot, blender=blender)

        assert blender.checkpoints == ["Crate"]
        assert blender.load_backs[0]["expected_hash"] == "asset-hash-0"
        assert blender.load_backs[0]["result_blend"].endswith("variants.blend")
        assert result.loaded_back is True
        assert events == [
            *BLENDER_STEPS,
            "load_back",
            "import",
            "probe_asset.gd",
            "probe_asset.gd",
        ]

    def test_refused_load_back_still_imports_then_fails_with_session_changed(
        self, session_request: FinalizeRequest, tmp_path: Path, jobs: _Counter
    ) -> None:
        blender = FakeBlenderSession(
            load_result={"ok": True, "loaded": False, "reason": "session_changed"}
        )
        godot = FinalizeGodot(tmp_path)
        with pytest.raises(FinalizeSessionChangedError) as info:
            _run(
                session_request,
                tmp_path,
                jobs,
                FakeStepRunner(session_request),
                godot=godot,
                blender=blender,
            )

        assert info.value.code == "finalize.session_changed"
        assert "variants.blend" in info.value.message
        assert info.value.result.loaded_back is False
        assert godot.count("--import") == 1

    def test_session_that_already_holds_the_result_is_served_from_cache(
        self, session_request: FinalizeRequest, tmp_path: Path, jobs: _Counter
    ) -> None:
        _run(
            session_request,
            tmp_path,
            jobs,
            FakeStepRunner(session_request),
            godot=FinalizeGodot(tmp_path),
            blender=FakeBlenderSession(),
        )

        runner = FakeStepRunner(session_request, hash_value="post-load-hash")
        blender = FakeBlenderSession(hash_value="post-load-hash")
        godot = FinalizeGodot(tmp_path)
        result = _run(session_request, tmp_path, jobs, runner, godot=godot, blender=blender)

        # Only the export_anims probe runs.  It is never cached, because it lists the clips.
        assert runner.steps_run() == ["export_anims"]
        assert all(step.cache_hit for step in result.steps)
        assert blender.load_backs == []
        assert godot.calls == []
        assert result.loaded_back is False

    def test_restored_original_session_reuses_the_chain_and_still_loads_back(
        self, session_request: FinalizeRequest, tmp_path: Path, jobs: _Counter
    ) -> None:
        _run(
            session_request,
            tmp_path,
            jobs,
            FakeStepRunner(session_request),
            godot=FinalizeGodot(tmp_path),
            blender=FakeBlenderSession(),
        )

        runner = FakeStepRunner(session_request)
        blender = FakeBlenderSession()
        result = _run(
            session_request, tmp_path, jobs, runner, godot=FinalizeGodot(tmp_path), blender=blender
        )

        # Only the export_anims probe runs.  It is never cached, because it lists the clips.
        assert runner.steps_run() == ["export_anims"]
        assert all(step.cache_hit for step in result.steps)
        assert len(blender.load_backs) == 1
        assert result.loaded_back is True


def _scale_tris(variant_meshes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**mesh, "tris": mesh["tris"] + 2} for mesh in variant_meshes]


def _rename(variant_meshes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**mesh, "name": "Lid"} for mesh in variant_meshes]


def _slots(variant_meshes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**mesh, "material_slots": 2} for mesh in variant_meshes]


def _bounds(variant_meshes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {**mesh, "bounds": {"min": mesh["bounds"]["min"], "max": [0.5, 1.01, 0.5]}}
        for mesh in variant_meshes
    ]


def _within_tolerance(variant_meshes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {**mesh, "bounds": {"min": mesh["bounds"]["min"], "max": [0.5, 1.0005, 0.5]}}
        for mesh in variant_meshes
    ]


class TestGodotImport:
    """``import_godot`` failures carry a code and remediation, and import_anims never runs."""

    def _fails(
        self, request: FinalizeRequest, tmp_path: Path, jobs: _Counter, godot: FinalizeGodot
    ) -> PipelineError:
        with pytest.raises(PipelineError) as info:
            _run(request, tmp_path, jobs, FakeStepRunner(request), godot=godot)
        assert info.value.remediation
        # import_anims would probe probe_anims.gd; it never ran.
        assert godot.probe_calls("probe_anims.gd") == []
        return info.value

    def test_unresolvable_binary_is_godot_not_found(
        self,
        blend_request: FinalizeRequest,
        tmp_path: Path,
        jobs: _Counter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        FinalizeGodot(tmp_path)  # the project exists; only the binary is missing
        monkeypatch.delenv("GODOT_BIN", raising=False)
        monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
        monkeypatch.setattr(godot_binary, "DEFAULT_GODOT_APP_BINARY", tmp_path / "no-godot")
        runner = FakeStepRunner(blend_request)
        with pytest.raises(PipelineError) as info:
            finalize(
                blend_request,
                cache_dir=tmp_path / "cache",
                runner=runner,
                job_dir=jobs.next(),
                clients=FinalizeClients(),
            )

        assert info.value.code == "godot.not_found"
        assert "GODOT_BIN" in info.value.remediation
        assert runner.steps_run() == list(BLENDER_STEPS)

    def test_an_error_line_from_the_import_is_import_failed(
        self, blend_request: FinalizeRequest, tmp_path: Path, jobs: _Counter
    ) -> None:
        godot = FinalizeGodot(tmp_path, import_errors=True)

        error = self._fails(blend_request, tmp_path, jobs, godot)

        assert error.code == "import_godot.import_failed"
        assert "ERROR: Failed loading resource" in error.message
        assert godot.probe_calls() == []

    def test_a_non_zero_import_exit_is_import_failed(
        self, blend_request: FinalizeRequest, tmp_path: Path, jobs: _Counter
    ) -> None:
        from nmg_game_dev.godot.runner import CommandResult

        class _Crashing(FinalizeGodot):
            def run(self, args: Any, **kwargs: Any) -> CommandResult:
                if list(args)[:1] == ["--import"]:
                    self.calls.append(list(args))
                    return CommandResult(139, stderr="Segmentation fault")
                return super().run(args, **kwargs)

        godot = _Crashing(tmp_path)

        error = self._fails(blend_request, tmp_path, jobs, godot)

        assert error.code == "import_godot.import_failed"
        assert "exited 139" in error.message

    @pytest.mark.parametrize(
        ("edit", "field"),
        [
            (_scale_tris, "tris"),
            (_rename, "name"),
            (_slots, "material_slots"),
            (_bounds, "bounds.max"),
        ],
    )
    def test_a_probe_difference_is_mismatch_naming_the_mesh_and_field(
        self,
        blend_request: FinalizeRequest,
        tmp_path: Path,
        jobs: _Counter,
        edit: Any,
        field: str,
    ) -> None:
        godot = FinalizeGodot(tmp_path, mesh_edits={"Mobile": edit})

        error = self._fails(blend_request, tmp_path, jobs, godot)

        assert error.code == "import_godot.mismatch"
        assert error.message.startswith("Mobile mesh ")
        assert f" {field}:" in error.message
        assert "Crate" in error.message or "Lid" in error.message

    def test_bounds_within_a_millimetre_match(
        self, blend_request: FinalizeRequest, tmp_path: Path, jobs: _Counter
    ) -> None:
        godot = FinalizeGodot(tmp_path, mesh_edits={"Desktop": _within_tolerance})

        result = _run(blend_request, tmp_path, jobs, FakeStepRunner(blend_request), godot=godot)

        assert result.desktop_resource_path == DESKTOP_RES

    def test_no_project_above_the_export_root_is_project_missing(
        self, tmp_path: Path, jobs: _Counter
    ) -> None:
        outside = tmp_path / "outside"
        blend = outside / "crate.blend"
        blend.parent.mkdir(parents=True)
        blend.write_bytes(b"authored")
        request = FinalizeRequest(
            collection="Crate",
            category="Props",
            asset_class="standard_prop",
            export_root=outside / "export",
            blend=blend,
        )
        godot = FinalizeGodot(tmp_path / "game")

        error = self._fails(request, tmp_path, jobs, godot)

        assert error.code == "import_godot.project_missing"
        assert godot.calls == []


class TestStepVersion:
    def test_a_cache_written_under_the_old_step_name_misses_import_godot(
        self,
        blend_request: FinalizeRequest,
        tmp_path: Path,
        jobs: _Counter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Populate the cache the way the previous release did: version "4" settings, and the
        # import entry stored under the old step name.
        monkeypatch.setattr(steps_module, "_STEP_VERSION", "4")
        old = FakeStepRunner(blend_request)
        _run(blend_request, tmp_path, jobs, old)
        cache = cache_module.ArtifactCache(tmp_path / "cache")
        input_hash = "asset-hash-0"
        old_key = cache.key("import_ue", input_hash, "settings")
        cache.put(
            old_key,
            step="import_ue",
            output_hash="old",
            outputs={"desktop_content_path": "/old"},
            blobs={},
            job_dir=jobs.next(),
        )
        monkeypatch.setattr(steps_module, "_STEP_VERSION", "5")

        godot = FinalizeGodot(tmp_path)
        runner = FakeStepRunner(blend_request)
        result = _run(blend_request, tmp_path, jobs, runner, godot=godot)

        imported = next(step for step in result.steps if step.step == "import_godot")
        assert imported.cache_hit is False
        assert godot.count("--import") == 1
        assert runner.steps_run() == list(BLENDER_STEPS)
        assert steps_module._STEP_VERSION == "5"
