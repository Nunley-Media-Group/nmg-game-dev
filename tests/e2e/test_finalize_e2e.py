"""End-to-end finalize (#69, #249): fixture assets through headless Blender and headless Godot.

Runs only with ``pytest tests/e2e --runslow``.  It needs Blender (``BLENDER_BIN`` or
``BLENDER_APP``) and Godot 4 (``GODOT_BIN``, ``godot`` on PATH, or the macOS app).  Each test writes
a throwaway Godot project under ``tmp_path/game`` and finalizes into ``game/assets``, so nothing
outside the temporary directory changes.  The Crate fixture is a compliant standard_prop collection
saved to ``tests/e2e/fixtures/crate.blend``, or to the path in ``NMG_FINALIZE_E2E_BLEND``.  The
multi-part test builds its Gantry fixture headless from ``fixtures/build_multipart_fixture.py``
(#145), and the Mobile test builds a single-mesh Crate from ``fixtures/build_crate_fixture.py`` when
no Crate fixture is set up (#146).
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from nmg_game_dev.godot.binary import resolve_godot
from nmg_game_dev.godot.import_asset import import_variants
from nmg_game_dev.godot.runner import SubprocessGodotRunner
from nmg_game_dev.pipeline import STEP_ORDER, FinalizeRequest, finalize
from nmg_game_dev.pipeline.blender_proc import resolve_blender

pytestmark = pytest.mark.slow

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "crate.blend"
_GANTRY_BUILDER = Path(__file__).resolve().parent / "fixtures" / "build_multipart_fixture.py"
_CRATE_BUILDER = Path(__file__).resolve().parent / "fixtures" / "build_crate_fixture.py"


def _project(tmp_path: Path) -> Path:
    """Write a minimal Godot project and return its ``assets`` export root."""
    game = tmp_path / "game"
    game.mkdir(parents=True, exist_ok=True)
    (game / "project.godot").write_text(
        'config_version=5\n\n[application]\n\nconfig/name="E2E"\n', encoding="utf-8"
    )
    return game / "assets"


def _fixture_blend() -> Path:
    override = os.environ.get("NMG_FINALIZE_E2E_BLEND")
    blend = Path(override) if override else _FIXTURE
    if not blend.is_file():
        pytest.skip(
            f"The e2e fixture is missing: {blend}. Save a compliant Crate collection there."
        )
    return blend


def _build(builder: Path, blend: Path) -> Path:
    built = subprocess.run(
        [
            str(resolve_blender()),
            "--background",
            "--factory-startup",
            "--python",
            str(builder),
            "--",
            str(blend),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )
    assert built.returncode == 0, built.stderr[-2000:]
    return blend


def test_finalize_imports_both_variants_into_godot(tmp_path: Path) -> None:
    blend = _fixture_blend()
    request = FinalizeRequest(
        collection="Crate",
        category="Props",
        asset_class="standard_prop",
        export_root=_project(tmp_path),
        blend=blend,
    )

    result = finalize(request, cache_dir=tmp_path / "cache", job_dir=tmp_path / "job")

    assert [step.step for step in result.steps] == list(STEP_ORDER)
    assert result.desktop_resource_path == "res://assets/Props/Crate/Desktop/Crate.glb"
    assert result.mobile_resource_path == "res://assets/Props/Crate/Mobile/Crate.glb"
    for variant in ("Desktop", "Mobile"):
        folder = request.export_root / "Props" / "Crate" / variant
        assert (folder / "Crate.glb").is_file()
        assert (folder / "nmg-asset.json").is_file()


def test_finalize_multi_part_static_asset_keeps_every_part(tmp_path: Path) -> None:
    """AC7 (#145): a multi-part fixture lands in both variants with one mesh node per part.

    ``import_godot`` raises ``import_godot.mismatch`` on any name, triangle, slot, or bounds
    difference from ``nmg-asset.json``, so a finished import has passed those checks.
    """
    blend = _build(_GANTRY_BUILDER, tmp_path / "Gantry.blend")
    request = FinalizeRequest(
        collection="Gantry",
        category="Props",
        asset_class="standard_prop",
        export_root=_project(tmp_path),
        blend=blend,
    )

    result = finalize(request, cache_dir=tmp_path / "cache", job_dir=tmp_path / "job")

    assert result.desktop_resource_path == "res://assets/Props/Gantry/Desktop/Gantry.glb"
    imports = next(step for step in result.steps if step.step == "import_godot").outputs["imports"]
    for variant in ("Desktop", "Mobile"):
        assert len(imports[variant]["meshes"]) == 3


def _static_crate_blend(tmp_path: Path) -> Path:
    """The Crate for the Mobile test: crate.blend when it is set up, else a headless build."""
    override = os.environ.get("NMG_FINALIZE_E2E_BLEND")
    if override and Path(override).is_file():
        return Path(override)
    if _FIXTURE.is_file():
        return _FIXTURE
    return _build(_CRATE_BUILDER, tmp_path / "Crate.blend")


def test_finalize_mobile_is_one_glb_and_reimports_cleanly(tmp_path: Path) -> None:
    """#146 on Godot: the Mobile variant is one ``Crate.glb`` with no per-LOD files.

    Godot generates the LODs at import time, so the export writes none. A second import of the
    same variants passes the probe comparison again.
    """
    request = FinalizeRequest(
        collection="Crate",
        category="Props",
        asset_class="standard_prop",
        export_root=_project(tmp_path),
        blend=_static_crate_blend(tmp_path),
    )

    result = finalize(request, cache_dir=tmp_path / "cache", job_dir=tmp_path / "job")

    mobile = request.export_root / "Props" / "Crate" / "Mobile"
    assert result.mobile_resource_path == "res://assets/Props/Crate/Mobile/Crate.glb"
    assert not list(mobile.glob("*_LOD*"))
    sidecar = json.loads(
        (request.export_root / "Props" / "Crate" / "nmg-variants.json").read_text()
    )
    project = request.export_root.parent
    again = import_variants(
        SubprocessGodotRunner(resolve_godot()),
        project,
        name="Crate",
        variant_dirs={
            v: request.export_root / "Props" / "Crate" / v for v in ("Desktop", "Mobile")
        },
        sidecar=sidecar,
    )
    assert again["Mobile"]["resource_path"] == "res://assets/Props/Crate/Mobile/Crate.glb"
