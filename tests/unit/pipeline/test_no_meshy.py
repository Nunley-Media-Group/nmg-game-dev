"""AC1 and AC7 (#69): the finalize package exposes no prompt, source, generate, or Meshy routing."""

from __future__ import annotations

import inspect
from pathlib import Path

import nmg_game_dev.pipeline as pipeline
from nmg_game_dev.pipeline import STEP_ORDER, finalize, run_step

_SRC = Path(__file__).resolve().parents[3] / "src" / "nmg_game_dev"


def test_finalize_and_run_step_take_no_prompt_or_source() -> None:
    for function in (finalize, run_step):
        parameters = inspect.signature(function).parameters
        assert "source" not in parameters
        assert "prompt" not in parameters


def test_prompt_run_and_source_symbols_are_gone() -> None:
    for name in ("Prompt", "Source", "run", "PipelineResult", "McpClients"):
        assert not hasattr(pipeline, name), name


def test_no_meshy_or_generate_in_package_source() -> None:
    offenders = [
        str(path.relative_to(_SRC))
        for path in _SRC.rglob("*.py")
        if "meshy" in path.read_text(encoding="utf-8").lower()
        or "generate_mesh" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_step_order_is_the_six_finalize_steps() -> None:
    assert STEP_ORDER == ("validate", "bake", "variants", "export", "reimport", "import_ue")
