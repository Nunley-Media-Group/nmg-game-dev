"""Resume state and the conversion report (#249 AC11, AC12)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nmg_game_dev.convert.plan import ManualPort
from nmg_game_dev.convert.report import Failure, render_report
from nmg_game_dev.convert.state import ConvertState, load_state, state_path
from nmg_game_dev.pipeline.errors import PipelineError


def test_state_round_trips_and_is_written_per_item(tmp_path: Path) -> None:
    assert load_state(tmp_path) is None
    state = ConvertState(state_path(tmp_path))
    state.add("asset:Props/Crate")
    assert json.loads(state_path(tmp_path).read_text()) == {
        "version": 1,
        "done": ["asset:Props/Crate"],
    }
    state.add("asset:Props/Crate")
    state.add("audio:SFX/Click")
    loaded = load_state(tmp_path)
    assert loaded is not None
    assert loaded.done == ["asset:Props/Crate", "audio:SFX/Click"]
    assert "audio:SFX/Click" in loaded


def test_state_keeps_the_first_runs_manual_port_and_deletions(tmp_path: Path) -> None:
    rows = [ManualPort("Source/Game/Game.cpp", "C++ game code")]
    ConvertState(state_path(tmp_path), manual_port=rows, deletions=["Source/", "a.uproject"]).save()
    loaded = load_state(tmp_path)
    assert loaded is not None
    assert loaded.manual_port == rows
    assert loaded.deletions == ["Source/", "a.uproject"]


@pytest.mark.parametrize(
    "text",
    [
        "{",
        "[]",
        '{"version": 2, "done": []}',
        '{"version": 1}',
        '{"version": 1, "done": [], "deletions": "Source/"}',
        '{"version": 1, "done": [], "manual_port": [{"path": "a"}]}',
    ],
)
def test_invalid_state_raises(tmp_path: Path, text: str) -> None:
    path = state_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(text)
    with pytest.raises(PipelineError) as caught:
        load_state(tmp_path)
    assert caught.value.code == "convert.state_invalid"


def test_report_lists_every_section() -> None:
    text = render_report(
        ["asset:Props/Crate"],
        [Failure("audio:SFX/Click", "audio.import_failed", "bad wav", "Re-export | the WAV.")],
        [ManualPort("Source/Game/Game.cpp", "C++ game code")],
        ["Content/", "Game.uproject"],
        deleted=False,
    )
    assert text.splitlines()[0] == "# Godot conversion report"
    assert "## Converted\n\n- `asset:Props/Crate`\n" in text
    assert "| `audio:SFX/Click` | `audio.import_failed` | Re-export \\| the WAV. |" in text
    assert "| `Source/Game/Game.cpp` | C++ game code |" in text
    assert text.endswith("## Deletions\n\nkept: 1 item failed\n")


def test_report_records_done_deletions_and_empty_sections() -> None:
    text = render_report([], [], [], ["Content/", "Game.uproject"], deleted=True)
    assert "## Converted\n\nNone.\n" in text
    assert "## Failed\n\nNone.\n" in text
    assert "## Manual port\n\nNone.\n" in text
    assert text.endswith("done: `Content/`, `Game.uproject`\n")
