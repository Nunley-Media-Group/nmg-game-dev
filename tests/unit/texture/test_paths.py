"""Output and model paths, the mflux-save command, and prompt slugs (#7 FR13, AC20)."""

from __future__ import annotations

from pathlib import Path

from nmg_game_dev.texture.paths import (
    install_command,
    models_dir,
    output_root,
    slugify,
    weights_dir,
)
from nmg_game_dev.texture.registry import REGISTRY


def test_output_root_defaults_under_the_project(tmp_path: Path) -> None:
    project = tmp_path / "project"
    root = output_root({"CLAUDE_PROJECT_DIR": str(project)}, tmp_path / "cwd")
    assert root == project / "SourceArt" / "Textures" / "Generated"


def test_output_root_falls_back_to_cwd_and_honors_the_override(tmp_path: Path) -> None:
    assert output_root({}, tmp_path) == tmp_path / "SourceArt" / "Textures" / "Generated"
    assert output_root({"NMG_GAME_DEV_TEXTURE_DIR": "/vol/tex"}, tmp_path) == Path("/vol/tex")


def test_models_dir_and_weights_dir(tmp_path: Path) -> None:
    assert models_dir({}) is None
    assert models_dir({"TEXTURE_GEN_MODELS_DIR": str(tmp_path)}) == tmp_path
    assert weights_dir(REGISTRY["z-image-turbo"], tmp_path) == tmp_path / "z-image-turbo-q4"


def test_install_command_is_the_exact_save_line(tmp_path: Path) -> None:
    assert install_command("z-image-turbo", tmp_path) == (
        f"mflux-save --model z-image-turbo --quantize 4 --path {tmp_path / 'z-image-turbo-q4'}"
    )


def test_slugify_is_kebab_case_and_capped() -> None:
    assert slugify("Burlap Weave, 2x!") == "burlap-weave-2x"
    assert len(slugify("word " * 40)) <= 48
    assert slugify("!!!") == "texture"
