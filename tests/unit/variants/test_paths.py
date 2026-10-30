"""Unit tests for the split-variant path helpers and the cross-reference guard."""

from __future__ import annotations

from pathlib import Path

import pytest

from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.variants import assert_no_cross_reference, desktop_path, mobile_path


class TestDesktopPath:
    def test_path_is_content_category_name_desktop(self) -> None:
        root = Path("/project")
        assert desktop_path(root, "Props", "TestCrate") == (
            root / "Content" / "Props" / "TestCrate" / "Desktop"
        )

    def test_path_ends_with_desktop(self) -> None:
        assert desktop_path(Path("/root"), "Props", "TestCrate").name == "Desktop"

    def test_path_contains_category_and_name(self) -> None:
        parts = desktop_path(Path("/root"), "Props", "TestCrate").parts
        assert "Props" in parts
        assert "TestCrate" in parts


class TestMobilePath:
    def test_path_is_content_category_name_mobile(self) -> None:
        root = Path("/project")
        assert mobile_path(root, "Props", "TestCrate") == (
            root / "Content" / "Props" / "TestCrate" / "Mobile"
        )

    def test_desktop_and_mobile_are_siblings(self) -> None:
        root = Path("/project")
        desktop = desktop_path(root, "Props", "TestCrate")
        mobile = mobile_path(root, "Props", "TestCrate")
        assert desktop.parent == mobile.parent
        assert desktop != mobile


class TestCrossReferenceGuard:
    def test_none_sidecar_is_not_checked(self) -> None:
        assert_no_cross_reference(None)

    def test_non_string_variant_is_not_checked(self) -> None:
        assert_no_cross_reference({"variant": 3, "path": "/Mobile/x.fbx"})

    def test_desktop_sidecar_with_desktop_path_passes(self) -> None:
        assert_no_cross_reference(
            {
                "variant": "desktop",
                "desktop_path": "/Content/Props/TestCrate/Desktop/SM_TestCrate.fbx",
            }
        )

    def test_mobile_sidecar_with_mobile_path_passes(self) -> None:
        assert_no_cross_reference(
            {
                "variant": "mobile",
                "mobile_path": "/Content/Props/TestCrate/Mobile/SM_TestCrate.fbx",
            }
        )

    def test_mobile_sidecar_referencing_desktop_raises(self) -> None:
        with pytest.raises(PipelineError) as info:
            assert_no_cross_reference(
                {
                    "variant": "mobile",
                    "desktop_path": "/Content/Props/TestCrate/Desktop/SM_TestCrate.fbx",
                }
            )
        assert info.value.code == "variants.cross_reference"
        assert "Desktop" in info.value.message

    def test_desktop_sidecar_referencing_mobile_raises(self) -> None:
        with pytest.raises(PipelineError) as info:
            assert_no_cross_reference(
                {
                    "variant": "desktop",
                    "mobile_path": "/Content/Props/TestCrate/Mobile/SM_TestCrate.fbx",
                }
            )
        assert info.value.code == "variants.cross_reference"
        assert info.value.stage == "variants"
