"""Artifact location, publishing, and hashing (#6, FR9, AC1, AC5)."""

from __future__ import annotations

from pathlib import Path

import pytest

from nmg_game_dev.ship.artifacts import artifact_sha256, locate_artifact, publish_artifact
from nmg_game_dev.ship.errors import ShipError


def _app(archive: Path, name: str = "Dogfood.app") -> Path:
    app = archive / "Mac" / name
    (app / "Contents" / "MacOS").mkdir(parents=True)
    (app / "Contents" / "MacOS" / "Dogfood").write_bytes(b"binary")
    return app


def test_locate_finds_the_app_bundle(tmp_path: Path) -> None:
    app = _app(tmp_path)
    assert locate_artifact(tmp_path, "macos") == app


def test_locate_prefers_the_shallowest_executable(tmp_path: Path) -> None:
    launcher = tmp_path / "Windows" / "Dogfood.exe"
    launcher.parent.mkdir(parents=True)
    launcher.write_bytes(b"exe")
    helper = tmp_path / "Windows" / "Dogfood" / "Engine" / "CrashReportClient.exe"
    helper.parent.mkdir(parents=True)
    helper.write_bytes(b"helper")
    assert locate_artifact(tmp_path, "windows") == launcher


def test_locate_missing_artifact_is_a_ship_error(tmp_path: Path) -> None:
    with pytest.raises(ShipError) as caught:
        locate_artifact(tmp_path, "ios")
    assert caught.value.code == "ship.artifact_not_found"


def test_locate_two_artifacts_at_one_depth_is_ambiguous(tmp_path: Path) -> None:
    (tmp_path / "IOS").mkdir()
    (tmp_path / "IOS" / "A.ipa").write_bytes(b"a")
    (tmp_path / "IOS" / "B.ipa").write_bytes(b"b")
    with pytest.raises(ShipError) as caught:
        locate_artifact(tmp_path, "ios")
    assert caught.value.code == "ship.artifact_ambiguous"


def test_publish_replaces_an_earlier_app(tmp_path: Path) -> None:
    release = tmp_path / "release"
    stale = release / "macos" / "Old.app"
    stale.mkdir(parents=True)
    (stale / "stale.txt").write_text("old", encoding="utf-8")
    app = _app(tmp_path / "archive")
    published = publish_artifact(app, release, "macos")
    assert published == release / "macos" / "Dogfood.app"
    assert (published / "Contents" / "MacOS" / "Dogfood").read_bytes() == b"binary"
    assert not stale.exists()


def test_publish_windows_copies_the_folder_holding_the_exe(tmp_path: Path) -> None:
    exe = tmp_path / "archive" / "Windows" / "Dogfood.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"exe")
    (exe.parent / "Dogfood").mkdir()
    (exe.parent / "Dogfood" / "data.pak").write_bytes(b"pak")
    published = publish_artifact(exe, tmp_path / "release", "windows")
    assert published == tmp_path / "release" / "windows" / "Dogfood.exe"
    assert (tmp_path / "release" / "windows" / "Dogfood" / "data.pak").read_bytes() == b"pak"


def test_sha256_of_a_file_matches_its_bytes(tmp_path: Path) -> None:
    path = tmp_path / "Dogfood.aab"
    path.write_bytes(b"abc")
    assert artifact_sha256(path) == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_sha256_of_a_folder_depends_on_relative_paths_and_bytes(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    for root in (first, second):
        root.mkdir()
    (first / "a.bin").write_bytes(b"x")
    (second / "b.bin").write_bytes(b"x")
    assert artifact_sha256(first) != artifact_sha256(second)
    assert artifact_sha256(first) == artifact_sha256(first)
