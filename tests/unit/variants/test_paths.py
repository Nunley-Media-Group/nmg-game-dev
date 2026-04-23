"""Unit tests for variants path helpers and cross-reference guard (T016)."""

from __future__ import annotations

from pathlib import Path

import pytest

from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.pipeline.prompt import Prompt
from nmg_game_dev.pipeline.stages._base import StageArtifact
from nmg_game_dev.variants import assert_no_cross_reference, desktop_path, mobile_path


@pytest.fixture()
def standard_prompt() -> Prompt:
    return Prompt(category="Props", name="TestCrate", tier="standard", description="a wooden crate")


@pytest.fixture()
def hero_prompt() -> Prompt:
    return Prompt(
        category="Guards", name="Patrol", tier="hero", description="futuristic patrol guard"
    )


class TestDesktopPath:
    def test_standard_tier(self, standard_prompt: Prompt) -> None:
        root = Path("/project")
        p = desktop_path(root, standard_prompt)
        assert p == Path("/project/Content/Props/TestCrate/Desktop")

    def test_hero_tier(self, hero_prompt: Prompt) -> None:
        root = Path("/project")
        p = desktop_path(root, hero_prompt)
        assert p == Path("/project/Content/Guards/Patrol/Desktop")

    def test_path_ends_with_desktop(self, standard_prompt: Prompt) -> None:
        p = desktop_path(Path("/root"), standard_prompt)
        assert p.name == "Desktop"

    def test_path_contains_category_and_name(self, standard_prompt: Prompt) -> None:
        p = desktop_path(Path("/root"), standard_prompt)
        parts = p.parts
        assert "Props" in parts
        assert "TestCrate" in parts
        assert "Desktop" in parts


class TestMobilePath:
    def test_standard_tier(self, standard_prompt: Prompt) -> None:
        root = Path("/project")
        p = mobile_path(root, standard_prompt)
        assert p == Path("/project/Content/Props/TestCrate/Mobile")

    def test_hero_tier(self, hero_prompt: Prompt) -> None:
        root = Path("/project")
        p = mobile_path(root, hero_prompt)
        assert p == Path("/project/Content/Guards/Patrol/Mobile")

    def test_path_ends_with_mobile(self, standard_prompt: Prompt) -> None:
        p = mobile_path(Path("/root"), standard_prompt)
        assert p.name == "Mobile"

    def test_desktop_and_mobile_differ_only_in_variant_segment(
        self, standard_prompt: Prompt
    ) -> None:
        root = Path("/root")
        dp = desktop_path(root, standard_prompt)
        mp = mobile_path(root, standard_prompt)
        assert dp.parent == mp.parent
        assert dp.name != mp.name


class TestAssertNoCrossReference:
    def _artifact(self, stage: str, blob: Path, sidecar: dict[str, object] | None) -> StageArtifact:
        return StageArtifact(stage=stage, blob_path=blob, sidecar=sidecar)

    def test_no_sidecar_passes(self, tmp_path: Path) -> None:
        a = self._artifact("variants", tmp_path / "file.fbx", None)
        assert_no_cross_reference(a)  # should not raise

    def test_desktop_sidecar_with_desktop_path_passes(self, tmp_path: Path) -> None:
        sidecar: dict[str, object] = {
            "variant": "desktop",
            "desktop_path": "/Content/Props/TestCrate/Desktop/SM_TestCrate.fbx",
        }
        a = self._artifact("variants", tmp_path / "file.fbx", sidecar)
        assert_no_cross_reference(a)

    def test_mobile_sidecar_with_mobile_path_passes(self, tmp_path: Path) -> None:
        sidecar: dict[str, object] = {
            "variant": "mobile",
            "mobile_path": "/Content/Props/TestCrate/Mobile/SM_TestCrate.fbx",
        }
        a = self._artifact("variants", tmp_path / "file.fbx", sidecar)
        assert_no_cross_reference(a)

    def test_mobile_artifact_references_desktop_path_raises(self, tmp_path: Path) -> None:
        sidecar: dict[str, object] = {
            "variant": "mobile",
            "some_ref": "/Content/Props/TestCrate/Desktop/SM_TestCrate.fbx",
        }
        a = self._artifact("variants", tmp_path / "file.fbx", sidecar)
        with pytest.raises(PipelineError) as exc_info:
            assert_no_cross_reference(a)
        assert exc_info.value.code == "variants.cross_reference"

    def test_desktop_artifact_references_mobile_path_raises(self, tmp_path: Path) -> None:
        sidecar: dict[str, object] = {
            "variant": "desktop",
            "some_ref": "/Content/Props/TestCrate/Mobile/SM_TestCrate.fbx",
        }
        a = self._artifact("variants", tmp_path / "file.fbx", sidecar)
        with pytest.raises(PipelineError) as exc_info:
            assert_no_cross_reference(a)
        assert exc_info.value.code == "variants.cross_reference"

    def test_non_string_sidecar_variant_skipped(self, tmp_path: Path) -> None:
        sidecar: dict[str, object] = {"variant": 42}
        a = self._artifact("variants", tmp_path / "file.fbx", sidecar)
        assert_no_cross_reference(a)  # non-string variant: skip guard

    def test_remediation_mentions_content_paths(self, tmp_path: Path) -> None:
        sidecar: dict[str, object] = {
            "variant": "mobile",
            "path": "/Content/Props/Crate/Desktop/mesh.fbx",
        }
        a = self._artifact("variants", tmp_path / "file.fbx", sidecar)
        with pytest.raises(PipelineError) as exc_info:
            assert_no_cross_reference(a)
        assert "Desktop" in exc_info.value.remediation or "Mobile" in exc_info.value.remediation
