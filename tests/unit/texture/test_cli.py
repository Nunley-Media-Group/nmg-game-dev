"""The CLI: generate prints JSON, status prints availability, and failures print ERROR and
Remediation (#7 AC20). seamless makes a PNG tile and reports the seam check (#147 FR7)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image as PILImage

from nmg_game_dev.texture import generate, hardware
from nmg_game_dev.texture.__main__ import main
from nmg_game_dev.texture.seamless import is_seamless
from tests.texture_fakes import APPLE_SILICON_32GB, save_png, synthetic_image


def _set_with_albedo(root: Path, name: str) -> None:
    """A texture set holding one albedo and its manifest (#152)."""
    albedo = save_png(synthetic_image(256), root / name / "z-image-turbo_1_256.png")
    manifest = {
        "name": name,
        "images": [{"backend": "z-image-turbo", "seed": 1, "path": str(albedo)}],
    }
    (root / name / "textures.json").write_text(json.dumps(manifest), encoding="utf-8")


@pytest.fixture
def apple(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(generate, "probe", lambda: APPLE_SILICON_32GB)
    monkeypatch.delenv("TEXTURE_GEN_MODELS_DIR", raising=False)


def _pixels(path: Path) -> np.ndarray:
    with PILImage.open(path) as opened:
        return np.asarray(opened.convert("RGB"))


def test_status_prints_availability_for_both_backends(
    monkeypatch: pytest.MonkeyPatch, apple: None, models: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("TEXTURE_GEN_MODELS_DIR", str(models))
    assert main(["status"]) == 0
    table = json.loads(capsys.readouterr().out)
    assert table == {"z-image-turbo": "available", "flux2-klein-4b": "available"}


def test_generate_without_models_exits_one_with_remediation(
    apple: None, capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NMG_GAME_DEV_TEXTURE_DIR", str(tmp_path / "out"))
    code = main(["generate", "--prompt", "burlap", "--backend", "z-image-turbo", "--seed", "1"])
    assert code == 1
    err = capsys.readouterr().err
    assert "ERROR [texture.model_not_installed]" in err
    assert "Remediation:" in err and "/onboard-consumer" in err


def test_half_a_map_request_is_refused(apple: None, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["generate", "--prompt", "x", "--roughness", "0.5"]) == 1
    assert "ERROR [texture.invalid_request]" in capsys.readouterr().err


def test_generate_requires_a_prompt() -> None:
    with pytest.raises(SystemExit) as caught:
        main(["generate"])
    assert caught.value.code == 2


def test_seamless_rewrites_the_png_in_place_and_reports_the_check(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = save_png(synthetic_image(256), tmp_path / "albedo.png")
    assert not is_seamless(_pixels(source))
    assert main(["seamless", str(source)]) == 0
    assert json.loads(capsys.readouterr().out) == {"path": str(source), "seamless": True}
    assert is_seamless(_pixels(source))


def test_seamless_with_out_writes_a_new_png_and_leaves_the_input(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = save_png(synthetic_image(256), tmp_path / "albedo.png")
    before = source.read_bytes()
    target = tmp_path / "nested" / "tile.png"
    assert main(["seamless", str(source), "--out", str(target)]) == 0
    assert json.loads(capsys.readouterr().out) == {"path": str(target), "seamless": True}
    assert source.read_bytes() == before
    assert is_seamless(_pixels(target))


def test_seamless_missing_input_exits_one_with_remediation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["seamless", str(tmp_path / "missing.png")]) == 1
    err = capsys.readouterr().err
    assert "ERROR [texture.input_missing]" in err
    assert "Remediation: Pass the path of an existing PNG texture." in err


def test_sheet_rebuilds_the_root_and_prints_its_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "root"
    _set_with_albedo(root, "rusted-steel")
    assert main(["sheet", "--root", str(root)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert set(printed) == {"pages", "cells", "skipped"}
    assert printed["cells"] == 1 and printed["skipped"] == []
    assert printed["pages"] == [str(root / "contact_sheet_001.png")]
    assert (root / "contact_sheet_001.png").is_file()


def test_sheet_defaults_to_the_output_root_from_the_environment(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "generated"
    _set_with_albedo(root, "oak")
    monkeypatch.setenv("NMG_GAME_DEV_TEXTURE_DIR", str(root))
    assert main(["sheet"]) == 0
    assert json.loads(capsys.readouterr().out)["cells"] == 1


def test_sheet_on_an_empty_root_exits_one_with_the_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["sheet", "--root", str(tmp_path / "empty")]) == 1
    err = capsys.readouterr().err
    assert "ERROR [texture.no_texture_sets]" in err
    assert "Remediation:" in err


def test_sheet_needs_no_backend_or_hardware_probe(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse() -> None:
        raise AssertionError("the sheet command must not probe the host")

    monkeypatch.setattr(generate, "probe", refuse)
    monkeypatch.setattr(hardware, "probe", refuse)
    monkeypatch.delenv("TEXTURE_GEN_MODELS_DIR", raising=False)
    root = tmp_path / "root"
    _set_with_albedo(root, "steel")
    assert main(["sheet", "--root", str(root)]) == 0
    assert json.loads(capsys.readouterr().out)["cells"] == 1
