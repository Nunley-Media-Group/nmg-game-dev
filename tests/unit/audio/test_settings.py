"""Per-sound finishing settings in ``SourceArt/Audio/audio.json`` (#252 FR3, AC5, AC7, T002).

``resolve`` picks explicit values, then the stored entry, then the kind's defaults. ``save``
upserts the entry as sorted, indented JSON. Invalid values fail as ``audio.invalid_request``, and a
malformed file fails as ``audio.settings_invalid``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nmg_game_dev.audio import settings
from nmg_game_dev.audio.errors import AudioError
from nmg_game_dev.audio.settings import FinishSettings


def _audio_json(root: Path) -> Path:
    return root / "SourceArt" / "Audio" / "audio.json"


def test_defaults_come_from_the_kind_when_nothing_is_stored(tmp_path: Path) -> None:
    sfx = settings.resolve(tmp_path, "DoorCreak", "sfx")
    music = settings.resolve(tmp_path, "ForestTheme", "music")

    assert sfx == FinishSettings(loudness_lufs=-16.0, finish=True, max_seconds=None)
    assert music == FinishSettings(loudness_lufs=-18.0, finish=True, max_seconds=None)
    assert sfx.loop_crossfade_ms == 500


def test_explicit_values_win_over_the_defaults(tmp_path: Path) -> None:
    resolved = settings.resolve(
        tmp_path,
        "DoorCreak",
        "sfx",
        finish=False,
        max_seconds=1.5,
        loudness_lufs=-12.0,
        loop_crossfade_ms=250,
    )

    assert resolved == FinishSettings(
        loudness_lufs=-12.0, finish=False, max_seconds=1.5, loop_crossfade_ms=250
    )


def test_a_stored_entry_is_reused_when_no_setting_is_passed(tmp_path: Path) -> None:
    stored = FinishSettings(
        loudness_lufs=-14.0, finish=True, max_seconds=1.0, loop_crossfade_ms=300
    )
    settings.save(tmp_path, "DoorCreak", "sfx", False, stored)

    assert settings.resolve(tmp_path, "DoorCreak", "sfx") == stored
    overridden = settings.resolve(tmp_path, "DoorCreak", "sfx", max_seconds=2.0)
    assert overridden.max_seconds == 2.0
    assert overridden.loudness_lufs == -14.0


def test_a_stored_entry_of_another_kind_is_not_reused(tmp_path: Path) -> None:
    settings.save(tmp_path, "Theme", "sfx", False, FinishSettings(loudness_lufs=-10.0))

    resolved = settings.resolve(tmp_path, "Theme", "music")

    assert resolved.loudness_lufs == -18.0


def test_save_writes_sorted_indented_json_with_a_trailing_newline(tmp_path: Path) -> None:
    settings.save(tmp_path, "Zed", "sfx", False, FinishSettings(loudness_lufs=-16.0))
    settings.save(
        tmp_path,
        "ForestTheme",
        "music",
        True,
        FinishSettings(loudness_lufs=-18.0, max_seconds=30.0, loop_crossfade_ms=500),
    )

    text = _audio_json(tmp_path).read_text(encoding="utf-8")
    assert text.endswith("}\n")
    assert text.index('"ForestTheme"') < text.index('"Zed"')
    payload = json.loads(text)
    assert payload == {
        "version": 1,
        "sounds": {
            "ForestTheme": {
                "kind": "music",
                "loop": True,
                "finish": True,
                "max_seconds": 30.0,
                "loudness_lufs": -18.0,
                "loop_crossfade_ms": 500,
            },
            "Zed": {
                "kind": "sfx",
                "loop": False,
                "finish": True,
                "max_seconds": None,
                "loudness_lufs": -16.0,
                "loop_crossfade_ms": 500,
            },
        },
    }


def test_save_upserts_one_entry_and_keeps_the_others(tmp_path: Path) -> None:
    settings.save(tmp_path, "Door", "sfx", False, FinishSettings(loudness_lufs=-16.0))
    settings.save(tmp_path, "Door", "sfx", True, FinishSettings(loudness_lufs=-13.0))

    stored = settings.load(tmp_path)

    assert list(stored) == ["Door"]
    assert stored["Door"].loop is True
    assert stored["Door"].settings.loudness_lufs == -13.0


@pytest.mark.parametrize(
    ("kwargs", "expected_message"),
    [
        ({"max_seconds": 0.0}, "max_seconds"),
        ({"max_seconds": -1.0}, "max_seconds"),
        ({"loudness_lufs": -41.0}, "loudness_lufs"),
        ({"loudness_lufs": -4.0}, "loudness_lufs"),
        ({"loop_crossfade_ms": -1}, "loop_crossfade_ms"),
    ],
    ids=["zero-seconds", "negative-seconds", "too-quiet", "too-loud", "negative-crossfade"],
)
def test_an_out_of_range_explicit_value_is_an_invalid_request(
    tmp_path: Path, kwargs: dict[str, float | int], expected_message: str
) -> None:
    with pytest.raises(AudioError) as caught:
        settings.resolve(tmp_path, "DoorCreak", "sfx", **kwargs)  # type: ignore[arg-type]

    assert caught.value.code == "audio.invalid_request"
    assert expected_message in caught.value.message
    assert caught.value.remediation
    assert not _audio_json(tmp_path).exists()


@pytest.mark.parametrize(
    "text",
    [
        "{not json",
        '["a list"]',
        '{"version": 2, "sounds": {}}',
        '{"version": 1, "sounds": []}',
        '{"version": 1, "sounds": {"Door": "nope"}}',
        '{"version": 1, "sounds": {"Door": {"kind": "voice", "loop": false}}}',
        (
            '{"version": 1, "sounds": {"Door": {"kind": "sfx", "loop": false, "finish": true,'
            ' "max_seconds": null, "loudness_lufs": 99, "loop_crossfade_ms": 500}}}'
        ),
    ],
    ids=[
        "not-json",
        "not-an-object",
        "wrong-version",
        "sounds-not-an-object",
        "entry-not-an-object",
        "bad-kind-and-missing-fields",
        "loudness-out-of-range",
    ],
)
def test_a_malformed_audio_json_is_settings_invalid(tmp_path: Path, text: str) -> None:
    _audio_json(tmp_path).parent.mkdir(parents=True)
    _audio_json(tmp_path).write_text(text, encoding="utf-8")

    with pytest.raises(AudioError) as caught:
        settings.resolve(tmp_path, "DoorCreak", "sfx")

    assert caught.value.code == "audio.settings_invalid"
    assert caught.value.remediation


def test_describe_returns_the_resolved_values() -> None:
    described = settings.describe(FinishSettings(loudness_lufs=-16.0, max_seconds=1.0))

    assert described == {
        "finish": True,
        "max_seconds": 1.0,
        "loudness_lufs": -16.0,
        "loop_crossfade_ms": 500,
    }
