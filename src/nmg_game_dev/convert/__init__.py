"""Convert an Unreal consumer project to Godot: ``/convert-to-godot`` (#249 FR11).

``discover`` plans the conversion, ``run_convert`` performs it, and ``python -m
nmg_game_dev.convert`` is the CLI the skill runs.
"""

from __future__ import annotations

from nmg_game_dev.convert.plan import ConversionPlan, discover
from nmg_game_dev.convert.runner import ConvertResult, ScaffoldOutcome, run_convert

__all__ = ["ConversionPlan", "ConvertResult", "ScaffoldOutcome", "discover", "run_convert"]
