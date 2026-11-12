"""PIE preflight before each variant import (#149, AC10, FR9).

The fake client records every UE call in order, so a test can prove that no import request is sent
while PIE is reported.  Sleeps and the clock are injected.  No editor is started.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from nmg_game_dev.pipeline import FinalizeClients, FinalizeRequest, jobs
from nmg_game_dev.pipeline.clients.unreal_mcp import UnrealTimeoutError
from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.pipeline.request import PieMode
from nmg_game_dev.pipeline.steps import STEP_ORDER, settings_hash
from nmg_game_dev.unreal.import_asset import import_variant
from nmg_game_dev.unreal.preflight import (
    PIE_CHECK_TIMEOUT_S,
    PIE_REMEDIATION,
    ensure_not_in_pie,
    is_in_pie,
)
from nmg_game_dev.unreal.retry import RetrySettings
from tests.finalize_fakes import FakeBlenderSession, FakeStepRunner, FakeUnrealRunner, dead_pid

Reply = bool | Exception


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def read(self) -> float:
        return self.now


class _Editor:
    """A UE client that answers PIE checks from ``pie`` and records every call in ``events``."""

    def __init__(self, pie: list[Reply]) -> None:
        self.pie = list(pie)
        self.events: list[str] = []
        self.timeouts: list[float | None] = []

    def execute_python_code(self, code: str, *, timeout: float | None = None) -> str:
        if "is_in_play_in_editor" in code:
            self.events.append("pie")
            self.timeouts.append(timeout)
            reply: Reply = self.pie.pop(0) if self.pie else False
            if isinstance(reply, Exception):
                raise reply
            return "NMG_RESULT " + json.dumps({"pie": reply})
        self.events.append("import")
        return "NMG_RESULT " + json.dumps({"ok": True, "static_meshes": {}})


def _preflight_then_import(
    editor: _Editor, clock: _Clock, *, mode: PieMode, wait_s: float
) -> dict[str, Any]:
    """Run the same order ``engine._run_import`` runs: the preflight, then the import."""
    ensure_not_in_pie(
        editor,
        mode=mode,
        wait_s=wait_s,
        sleep=clock.sleep,
        clock=clock.read,
    )
    return import_variant(
        editor,
        variant_dir="/exports/Crate/Desktop",
        dest="/Game/Props/Crate/Desktop",
        name="Crate",
        report={"snapshot": {}},
        retry=RetrySettings(retries=4, base_delay_s=20.0),
        sleep=clock.sleep,
        clock=clock.read,
    )


def test_the_import_waits_for_pie_to_end_and_is_sent_only_after() -> None:
    editor = _Editor([True, True, True, False])
    clock = _Clock()

    result = _preflight_then_import(editor, clock, mode="wait", wait_s=600)

    assert editor.events == ["pie", "pie", "pie", "pie", "import"]
    assert clock.sleeps == [5.0, 5.0, 5.0]
    assert result["attempts"] == 1


def test_pie_still_on_at_the_limit_fails_editor_busy_and_sends_no_import() -> None:
    editor = _Editor([True] * 10)
    clock = _Clock()

    with pytest.raises(PipelineError) as info:
        _preflight_then_import(editor, clock, mode="wait", wait_s=10)

    assert info.value.code == "import_ue.editor_busy"
    assert info.value.stage == "import_ue"
    assert info.value.remediation == PIE_REMEDIATION
    assert "Stop the Play In Editor session, then rerun finalize." in info.value.remediation
    assert "import" not in editor.events
    assert clock.sleeps == [5.0, 5.0]


def test_refuse_mode_fails_at_once_without_polling() -> None:
    editor = _Editor([True])
    clock = _Clock()

    with pytest.raises(PipelineError) as info:
        _preflight_then_import(editor, clock, mode="refuse", wait_s=600)

    assert info.value.code == "import_ue.editor_busy"
    assert editor.events == ["pie"]
    assert clock.sleeps == []


def test_a_timed_out_pie_check_counts_as_busy_and_then_the_import_proceeds() -> None:
    editor = _Editor([UnrealTimeoutError("timed out", "wait"), False])
    clock = _Clock()

    _preflight_then_import(editor, clock, mode="wait", wait_s=600)

    assert editor.events == ["pie", "pie", "import"]
    assert clock.sleeps == [5.0]


def test_a_timed_out_pie_check_in_refuse_mode_sends_no_import() -> None:
    editor = _Editor([UnrealTimeoutError("timed out", "wait")])
    clock = _Clock()

    with pytest.raises(PipelineError) as info:
        _preflight_then_import(editor, clock, mode="refuse", wait_s=600)

    assert info.value.code == "import_ue.editor_busy"
    assert "import" not in editor.events


def test_the_pie_check_has_a_ten_second_timeout() -> None:
    editor = _Editor([False])

    assert is_in_pie(editor) is False
    assert PIE_CHECK_TIMEOUT_S == 10.0
    assert editor.timeouts == [10.0]


def test_a_pie_check_reply_without_the_flag_counts_as_not_in_pie() -> None:
    class _Plain:
        def execute_python_code(self, code: str, *, timeout: float | None = None) -> str:
            return 'NMG_RESULT {"ok": true}'

    assert is_in_pie(_Plain()) is False


def test_a_refused_import_in_a_job_sends_no_import_request(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    request = FinalizeRequest(
        collection="Crate",
        category="Props",
        asset_class="standard_prop",
        export_root=tmp_path / "export",
        pie_mode="refuse",
    )
    unreal = FakeUnrealRunner(pie_replies=[True])

    def launch(job_dir: Path) -> int:
        jobs.run_job(
            job_dir,
            clients=FinalizeClients(blender=FakeBlenderSession(), unreal=unreal),
            runner=FakeStepRunner(request),
        )
        return dead_pid()

    job_id = jobs.start(request, cache_root=cache, launcher=launch)

    status = jobs.status(job_id, cache_root=cache)
    assert status["state"] == "failed"
    assert status["error"]["code"] == "import_ue.editor_busy"
    assert status["error"]["stage"] == "import_ue"
    assert unreal.pie_checks == 1
    assert unreal.codes == []


def test_the_pie_options_are_outside_every_cache_settings_hash(tmp_path: Path) -> None:
    default = FinalizeRequest(
        collection="Crate",
        category="Props",
        asset_class="standard_prop",
        export_root=tmp_path / "export",
    )
    changed = FinalizeRequest(
        collection="Crate",
        category="Props",
        asset_class="standard_prop",
        export_root=tmp_path / "export",
        pie_mode="refuse",
        pie_wait_seconds=30,
    )

    assert default.pie_mode == "wait"
    assert default.pie_wait_seconds == 600
    for step in STEP_ORDER:
        assert settings_hash(step, default, "budgets") == settings_hash(step, changed, "budgets")
