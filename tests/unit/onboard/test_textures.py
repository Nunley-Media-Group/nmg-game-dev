"""Texture model install and volume listing for onboarding (#7 FR7, AC4, AC5, AC6)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from nmg_game_dev.onboard.commands import CommandResult
from nmg_game_dev.onboard.errors import OnboardError
from nmg_game_dev.onboard.textures import (
    REQUIRED_FREE_BYTES,
    TEXTURE_MODELS,
    install_command,
    install_models,
    missing_models,
)
from nmg_game_dev.onboard.volumes import list_volumes
from tests.onboard_fakes import GIB, FakeRunner, all_tools_present, mflux_missing


def test_model_ids_and_order_come_from_the_registry() -> None:
    assert TEXTURE_MODELS == (
        ("z-image-turbo", "Tongyi-MAI/Z-Image-Turbo"),
        ("flux2-klein-4b", "black-forest-labs/FLUX.2-klein-4B"),
    )
    assert REQUIRED_FREE_BYTES == 60 * GIB


def test_install_command_is_the_exact_mflux_save_line(tmp_path: Path) -> None:
    assert install_command("flux2-klein-4b", tmp_path) == (
        f"mflux-save --model flux2-klein-4b --quantize 4 --path {tmp_path / 'flux2-klein-4b-q4'}"
    )


def test_missing_models_lists_absent_or_empty_folders(tmp_path: Path) -> None:
    assert missing_models(tmp_path) == ["z-image-turbo", "flux2-klein-4b"]
    (tmp_path / "z-image-turbo-q4").mkdir()
    assert missing_models(tmp_path) == ["z-image-turbo", "flux2-klein-4b"]
    (tmp_path / "z-image-turbo-q4" / "w.bin").write_bytes(b"x")
    assert missing_models(tmp_path) == ["flux2-klein-4b"]


def test_install_models_saves_each_missing_model_in_order(tmp_path: Path) -> None:
    runner = FakeRunner()
    result = install_models(tmp_path, run=runner, which=all_tools_present)
    assert result.status == "installed"
    saves = [c[c.index("--model") + 1] for c in runner.calls if c[:1] == ["mflux-save"]]
    assert saves == ["z-image-turbo", "flux2-klein-4b"]
    assert all(
        e == {"HF_HOME": str(tmp_path / "hf-cache")}
        for c, e in zip(runner.calls, runner.envs, strict=True)
        if c[:1] == ["mflux-save"]
    )


def test_install_models_is_a_no_op_when_all_present(tmp_path: Path) -> None:
    for model in ("z-image-turbo", "flux2-klein-4b"):
        (tmp_path / f"{model}-q4").mkdir()
        (tmp_path / f"{model}-q4" / "w.bin").write_bytes(b"x")
    runner = FakeRunner()
    assert install_models(tmp_path, run=runner, which=mflux_missing).status == "unchanged"
    assert runner.calls == []


def test_mflux_install_failure_names_the_error(tmp_path: Path) -> None:
    class Refusing(FakeRunner):
        def __call__(
            self, argv: Sequence[str], env: Mapping[str, str] | None = None
        ) -> CommandResult:
            if list(argv[:3]) == ["uv", "tool", "install"]:
                self.calls.append(list(argv))
                return CommandResult(returncode=2)
            return super().__call__(argv, env)

    with pytest.raises(OnboardError) as caught:
        install_models(tmp_path, run=Refusing(), which=mflux_missing)
    assert caught.value.code == "onboard.mflux_install_failed"


def test_model_save_failure_names_the_model(tmp_path: Path) -> None:
    with pytest.raises(OnboardError) as caught:
        install_models(tmp_path, run=FakeRunner(fail="mflux-save"), which=all_tools_present)
    assert caught.value.code == "onboard.model_install_failed"
    assert "z-image-turbo" in caught.value.message


def test_list_volumes_reports_free_space_and_fit(tmp_path: Path) -> None:
    big = tmp_path / "big"
    small = tmp_path / "small"
    big.mkdir()
    small.mkdir()
    free = {big: 200 * GIB, small: 10 * GIB}
    rows = list_volumes(free_bytes=lambda p: free[p], mounts=lambda: [big, small, big])
    assert rows == [
        {"mount": str(big), "free_bytes": 200 * GIB, "fits_models": True},
        {"mount": str(small), "free_bytes": 10 * GIB, "fits_models": False},
    ]
