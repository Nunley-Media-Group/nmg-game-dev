"""Export paths and artifact hashing (#6, FR9, AC1, AC5; #249 FR9)."""

from __future__ import annotations

from pathlib import Path

from nmg_game_dev.ship.artifacts import artifact_sha256, export_path, release_artifact


def test_export_paths_follow_the_release_layout(tmp_path: Path) -> None:
    release = tmp_path / "release"
    assert export_path(release, "macos", "Dogfood") == release / "macos" / "Dogfood.app"
    assert export_path(release, "ios", "Dogfood") == release / "ios" / "Dogfood.ipa"
    assert export_path(release, "android", "Dogfood") == release / "android" / "Dogfood.aab"
    assert export_path(release, "windows", "Dogfood") == release / "windows" / "Dogfood.exe"
    assert export_path(release, "web", "Dogfood") == release / "web" / "index.html"


def test_the_web_release_artifact_is_its_folder(tmp_path: Path) -> None:
    release = tmp_path / "release"
    assert release_artifact(release, "web", "Dogfood") == release / "web"
    assert release_artifact(release, "ios", "Dogfood") == release / "ios" / "Dogfood.ipa"


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
    before = artifact_sha256(first)
    assert artifact_sha256(first) == before
    (first / "a.bin").write_bytes(b"y")
    assert artifact_sha256(first) != before
