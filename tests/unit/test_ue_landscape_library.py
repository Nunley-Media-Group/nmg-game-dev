"""Source guard for the UNmgLandscapeLibrary C++ editor helper (#154).

Covers AC4 and FR6 of specs/154-*/requirements.md on the C++ side. The helper compiles only under
UBT (gate-ue-compile), which these unit tests never run, so they read the header and Build.cs text
and check the declarations the generated UE Python calls.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EDITOR_MODULE = REPO_ROOT / "plugins" / "nmg-game-dev-ue-plugin" / "Source" / "NmgGameDevEditor"
HEADER_PATH = EDITOR_MODULE / "Public" / "NmgLandscapeLibrary.h"
BUILD_PATH = EDITOR_MODULE / "NmgGameDevEditor.Build.cs"

BLUEPRINT_STATICS = ("BuildLayeredMaterial", "CreateLayerInfo", "ImportLandscape", "SampleHeights")
REQUIRED_PRIVATE_DEPENDENCIES = ("Landscape", "ImageWrapper", "MaterialEditor")


def _blueprint_callable_static_pattern(name: str) -> re.Pattern[str]:
    """A UFUNCTION(BlueprintCallable ...) directly followed by a static declaration named `name`."""
    return re.compile(
        rf"UFUNCTION\(\s*BlueprintCallable\b[^)]*\)\s*static\s+[^;(]*?\b{name}\s*\(",
    )


def _private_dependencies(build_text: str) -> set[str]:
    match = re.search(
        r"PrivateDependencyModuleNames\.AddRange\(\s*new string\[\]\s*\{(.*?)\}\s*\);",
        build_text,
        re.DOTALL,
    )
    assert match is not None, "NmgGameDevEditor.Build.cs has no PrivateDependencyModuleNames list"
    return set(re.findall(r'"([A-Za-z0-9_]+)"', match.group(1)))


def test_header_declares_four_blueprint_callable_statics() -> None:
    text = HEADER_PATH.read_text(encoding="utf-8")

    assert "class NMGGAMEDEVEDITOR_API UNmgLandscapeLibrary" in text
    for name in BLUEPRINT_STATICS:
        assert _blueprint_callable_static_pattern(name).search(text), (
            f"NmgLandscapeLibrary.h does not declare {name} as a "
            "UFUNCTION(BlueprintCallable) static"
        )


def test_build_cs_lists_landscape_and_image_wrapper() -> None:
    dependencies = _private_dependencies(BUILD_PATH.read_text(encoding="utf-8"))

    for module in REQUIRED_PRIVATE_DEPENDENCIES:
        assert module in dependencies, f"NmgGameDevEditor.Build.cs does not list {module}"
