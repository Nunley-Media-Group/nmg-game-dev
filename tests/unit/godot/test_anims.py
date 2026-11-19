"""Unit tests for ``godot.anims``: import settings, clip checks, compatible skeletons (#249 FR3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from nmg_game_dev.godot.anims import (
    ClipPlan,
    check_compatible,
    has_library_importer,
    import_clips,
    verify_clips,
    write_library_importer,
)
from nmg_game_dev.pipeline.errors import PipelineError
from tests.finalize_fakes import FinalizeGodot


def _clip(tmp_path: Path, name: str = "Walk") -> ClipPlan:
    folder = tmp_path / "assets" / "Props" / "Hero" / "Animations"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"A_Hero_{name}.glb"
    path.write_bytes(b"glb")
    return ClipPlan(name=name, file=path, fps=30.0, expected_frames=9)


def test_the_library_importer_is_written_once(tmp_path: Path) -> None:
    clip = _clip(tmp_path)
    assert has_library_importer(clip.file) is False
    assert write_library_importer(clip.file) is True
    text = clip.file.with_name("A_Hero_Walk.glb.import").read_text(encoding="utf-8")
    assert text == '[remap]\n\nimporter="animation_library"\n'
    assert write_library_importer(clip.file) is False


def test_a_scene_importer_is_replaced(tmp_path: Path) -> None:
    clip = _clip(tmp_path)
    settings = clip.file.with_name("A_Hero_Walk.glb.import")
    settings.write_text('[remap]\n\nimporter="scene"\n', encoding="utf-8")
    assert write_library_importer(clip.file) is True
    assert has_library_importer(clip.file) is True


def test_import_clips_imports_then_probes_only_the_given_clips(tmp_path: Path) -> None:
    godot = FinalizeGodot(tmp_path)
    clip = _clip(tmp_path)

    result = import_clips(godot, tmp_path, clips=[clip])

    assert godot.calls[0] == ["--import"]
    assert godot.probed_clips() == [["Walk"]]
    assert result["clips"]["Walk"]["frame_count"] == 9


def test_without_clips_only_the_skeletons_are_probed(tmp_path: Path) -> None:
    godot = FinalizeGodot(tmp_path)
    import_clips(godot, tmp_path, clips=[], skeletons=[tmp_path / "x.glb"])
    assert godot.count("--import") == 0
    assert godot.probed_clips() == [[]]


def test_an_import_error_is_import_anims_failed(tmp_path: Path) -> None:
    godot = FinalizeGodot(tmp_path, import_errors=True)
    with pytest.raises(PipelineError) as info:
        import_clips(godot, tmp_path, clips=[_clip(tmp_path)])
    assert info.value.code == "import_anims.failed"


def test_verify_clips_returns_bones_and_flags_differences(tmp_path: Path) -> None:
    clip = _clip(tmp_path)
    measured = {"Walk": {"animation": "Walk", "frame_count": 9, "bones": ["spine", "root"]}}
    assert verify_clips([clip], measured) == {"Walk": ["root", "spine"]}
    with pytest.raises(PipelineError) as info:
        verify_clips([clip], {"Walk": {"frame_count": 8}})
    assert info.value.code == "import_anims.clip_mismatch"
    with pytest.raises(PipelineError) as info:
        verify_clips([clip], {})
    assert info.value.code == "import_anims.clip_mismatch"


def test_check_compatible(tmp_path: Path) -> None:
    scene = tmp_path / "assets" / "Props" / "Other" / "Desktop" / "Other.glb"
    resource = "res://assets/Props/Other/Desktop/Other.glb"
    targets = [("Props/Other", scene)]
    ok = {resource: {"found": True, "bones": ["root", "spine"]}}
    assert check_compatible(tmp_path, ["root"], targets, ok) == [resource]
    with pytest.raises(PipelineError) as info:
        check_compatible(tmp_path, ["head"], targets, ok)
    assert info.value.code == "finalize.skeleton_mismatch"
    assert "head" in info.value.message
    with pytest.raises(PipelineError) as info:
        check_compatible(tmp_path, ["root"], targets, {resource: {"found": False}})
    assert info.value.code == "finalize.skeleton_not_found"
