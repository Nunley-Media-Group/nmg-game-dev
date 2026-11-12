"""Terrain requests route import_ue to import_terrain_variant, Desktop then Mobile (#154, AC4, FR8).

The real orchestrator, cache, gates, and envelope handling run. ``TerrainStepRunner`` is the
Blender fake from ``tests.finalize_fakes`` with the export writing a terrain ``nmg-variants.json``.
``FakeUnrealRunner`` is the Unreal MCP double. A spy stands in for ``import_terrain_variant`` in
the first tests. The last tests run the real terrain import code through the double, so they show
the UE Python that reaches the editor for each variant.

A validate failure stops the run before any Unreal call (AC6, FR8).
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest

from nmg_game_dev.pipeline import (
    FinalizeClients,
    FinalizeRequest,
    PipelineError,
    engine,
    finalize,
)
from nmg_game_dev.unreal import ue_samples
from tests.finalize_fakes import FakeStepRunner, FakeUnrealRunner

DESKTOP_DEST = "/Game/Environment/Hills/Desktop"
MOBILE_DEST = "/Game/Environment/Hills/Mobile"
LAYERS = ["Grass", "Rock"]
_HALF = 63.0
_SAMPLES = [[-_HALF, _HALF, 10.0], [_HALF, -_HALF, 40.0], [0.0, 0.0, 25.0]]


def _entry(heightmap_px: int, mobile: bool) -> dict[str, Any]:
    """One variant's terrain entry in nmg-variants.json."""
    return {
        "heightmap": f"{'Mobile' if mobile else 'Desktop'}/T_Hills_Height.png",
        "heightmap_px": heightmap_px,
        "spacing_m": 1.0 if not mobile else 2.0,
        "height_min_m": 10.0,
        "height_max_m": 40.0,
        "uv_tile_m": 8.0,
        "layers": list(LAYERS),
        "max_texture_px": 1024 if mobile else 2048,
        "texture_bytes": 1024,
        "samples": _SAMPLES,
    }


DESKTOP_ENTRY = _entry(127, mobile=False)
MOBILE_ENTRY = _entry(127, mobile=True)


class TerrainStepRunner(FakeStepRunner):
    """The Blender fake, with an export that writes a terrain sidecar.

    Parameters:
        sidecar_entries: The ``desktop``/``mobile`` entries to write. Omit a key to leave it out.
    """

    def __init__(
        self,
        request: FinalizeRequest,
        *,
        sidecar_entries: dict[str, dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(request, **kwargs)
        self.sidecar_entries = (
            sidecar_entries
            if sidecar_entries is not None
            else {"desktop": DESKTOP_ENTRY, "mobile": MOBILE_ENTRY}
        )

    def _export_outputs(self, job_dir: Path) -> dict[str, Any]:
        outputs = super()._export_outputs(job_dir)
        sidecar = Path(str(outputs["sidecar"]))
        payload: dict[str, Any] = {"terrain": True, "class": "terrain", **self.sidecar_entries}
        sidecar.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        return outputs


class ImportTerrainSpy:
    """Stands in for ``engine.import_terrain_variant``. Records each call and replies ok."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self,
        client: Any,
        *,
        variant_dir: str,
        dest: str,
        name: str,
        sidecar_variant: dict[str, Any],
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "variant_dir": variant_dir,
                "dest": dest,
                "name": name,
                "sidecar_variant": sidecar_variant,
            }
        )
        return {"ok": True, "dest": dest, "name": name, "error": None}


@pytest.fixture()
def terrain_request(tmp_path: Path) -> FinalizeRequest:
    blend = tmp_path / "hills.blend"
    blend.write_bytes(b"authored")
    return FinalizeRequest(
        collection="Hills",
        category="Environment",
        asset_class="terrain",
        export_root=tmp_path / "export",
        blend=blend,
    )


def _finalize(
    request: FinalizeRequest,
    tmp_path: Path,
    runner: FakeStepRunner,
    unreal: FakeUnrealRunner,
) -> Any:
    return finalize(
        request,
        cache_dir=tmp_path / "cache",
        runner=runner,
        job_dir=tmp_path / "job",
        clients=FinalizeClients(unreal=unreal),
    )


def _ue_params(code: str) -> dict[str, Any]:
    """The PARAMS literal that the UE import code embeds, decoded."""
    line = next(line for line in code.splitlines() if line.startswith("PARAMS = json.loads("))
    decoded = ast.literal_eval(line[len("PARAMS = json.loads(") : -1])
    params: dict[str, Any] = json.loads(decoded)
    return params


def test_terrain_import_runs_desktop_then_mobile_through_import_terrain_variant(
    terrain_request: FinalizeRequest,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spy = ImportTerrainSpy()
    monkeypatch.setattr(engine, "import_terrain_variant", spy)

    def no_mesh_import(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("a terrain request must not run the mesh import")

    monkeypatch.setattr(engine, "import_variant", no_mesh_import)

    result = _finalize(
        terrain_request,
        tmp_path,
        TerrainStepRunner(terrain_request),
        FakeUnrealRunner(),
    )

    assert [call["dest"] for call in spy.calls] == [DESKTOP_DEST, MOBILE_DEST]
    assert [call["name"] for call in spy.calls] == ["Hills", "Hills"]
    assert spy.calls[0]["sidecar_variant"] == DESKTOP_ENTRY
    assert spy.calls[1]["sidecar_variant"] == MOBILE_ENTRY
    assert spy.calls[0]["variant_dir"].endswith("Environment/Hills/Desktop")
    assert spy.calls[1]["variant_dir"].endswith("Environment/Hills/Mobile")
    assert result.desktop_content_path == DESKTOP_DEST
    assert result.mobile_content_path == MOBILE_DEST


def test_terrain_import_sends_the_terrain_code_for_each_variant(
    terrain_request: FinalizeRequest,
    tmp_path: Path,
) -> None:
    unreal = FakeUnrealRunner()

    _finalize(terrain_request, tmp_path, TerrainStepRunner(terrain_request), unreal)

    assert len(unreal.codes) == 2
    first, second = (_ue_params(code) for code in unreal.codes)
    assert [first["variant"], second["variant"]] == ["desktop", "mobile"]
    assert [first["dest"], second["dest"]] == [DESKTOP_DEST, MOBILE_DEST]
    assert first["heightmap_px"] == 127
    assert first["samples_cm"] == ue_samples(_SAMPLES)
    assert "FbxImportUI" not in unreal.codes[0]
    assert "NmgLandscapeLibrary" in unreal.codes[0]


@pytest.mark.parametrize("failure", ["gate", "envelope"])
def test_a_validate_failure_never_reaches_unreal(
    terrain_request: FinalizeRequest,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    spy = ImportTerrainSpy()
    monkeypatch.setattr(engine, "import_terrain_variant", spy)
    unreal = FakeUnrealRunner()
    if failure == "gate":
        runner = TerrainStepRunner(terrain_request, failing_reports=frozenset({"validate"}))
        expected = "quality.contract_failed"
    else:
        runner = TerrainStepRunner(
            terrain_request,
            failures={"validate": ("layer_range", "a layer is outside 0-1", "Clamp the layer.")},
        )
        expected = "validate.layer_range"

    with pytest.raises(PipelineError) as raised:
        _finalize(terrain_request, tmp_path, runner, unreal)

    assert raised.value.code == expected
    assert unreal.codes == []
    assert spy.calls == []


def test_a_sidecar_missing_the_mobile_entry_fails_before_any_unreal_call(
    terrain_request: FinalizeRequest,
    tmp_path: Path,
) -> None:
    unreal = FakeUnrealRunner()
    runner = TerrainStepRunner(terrain_request, sidecar_entries={"desktop": DESKTOP_ENTRY})

    with pytest.raises(PipelineError) as raised:
        _finalize(terrain_request, tmp_path, runner, unreal)

    assert raised.value.code == "import_ue.failed"
    assert "mobile" in raised.value.message
    assert unreal.codes == []
