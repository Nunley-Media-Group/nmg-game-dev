"""Every Blender API reference snippet runs headless: AC7 (SCN007).

Run with scripts/run-blender-tests.sh. Under plain CPython the module is skipped.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

bpy = pytest.importorskip("bpy")

from .contract_fixtures import clear_scene  # noqa: E402

REFERENCE = (
    Path(__file__).resolve().parents[2] / "skills" / "model-asset" / "references" / "blender-api.md"
)
_FENCE = re.compile(r"```python\n(.*?)```", re.DOTALL)
SNIPPETS: list[str] = _FENCE.findall(REFERENCE.read_text(encoding="utf-8"))


def test_reference_covers_the_required_topics() -> None:
    """SCN007: the snippets cover bmesh, modifier apply, node groups, and shader lookup."""
    assert len(SNIPPETS) >= 6
    joined = "\n".join(SNIPPETS)
    for marker in ("bmesh.new", "modifiers.new", "modifier_apply", "GeometryNodeTree", ".type =="):
        assert marker in joined, f"no snippet contains {marker!r}"
    assert "Changes since Blender 4" in REFERENCE.read_text(encoding="utf-8")


@pytest.mark.parametrize("index", range(len(SNIPPETS)))
def test_snippet_runs_without_error(index: int) -> None:
    """SCN007: each fenced python snippet completes in a cleared headless scene."""
    clear_scene()
    namespace: dict[str, Any] = {"__name__": f"blender_api_snippet_{index}"}
    code = compile(SNIPPETS[index], f"{REFERENCE}#snippet-{index}", "exec")
    exec(code, namespace)  # noqa: S102 - the reference's own documented code
