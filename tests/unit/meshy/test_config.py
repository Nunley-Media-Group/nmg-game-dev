"""Key resolution, .env parsing, and the project root (#98 FR2, AC8, AC9)."""

from __future__ import annotations

from pathlib import Path

import pytest

from nmg_game_dev.meshy import config
from nmg_game_dev.meshy.errors import MeshyError


def test_environment_key_wins_over_dotenv(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("MESHY_API_KEY=key-from-dotenv\n", encoding="utf-8")
    assert config.api_key({"MESHY_API_KEY": "key-from-env"}, tmp_path) == "key-from-env"


def test_dotenv_key_used_when_environment_is_unset(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("MESHY_API_KEY=key-from-dotenv\n", encoding="utf-8")
    assert config.api_key({}, tmp_path) == "key-from-dotenv"


@pytest.mark.parametrize("env", [{}, {"MESHY_API_KEY": ""}, {"MESHY_API_KEY": "   "}])
def test_missing_key_fails_fast_with_remediation(tmp_path: Path, env: dict[str, str]) -> None:
    with pytest.raises(MeshyError) as info:
        config.api_key(env, tmp_path)
    assert info.value.code == "meshy.api_key_missing"
    assert "MESHY_API_KEY" in info.value.remediation
    assert ".env" in info.value.remediation


def test_empty_dotenv_value_counts_as_missing(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("MESHY_API_KEY=\n", encoding="utf-8")
    with pytest.raises(MeshyError) as info:
        config.api_key({}, tmp_path)
    assert info.value.code == "meshy.api_key_missing"


def test_project_dir_selects_the_dotenv_location(tmp_path: Path) -> None:
    project = tmp_path / "game"
    project.mkdir()
    (project / ".env").write_text("MESHY_API_KEY=from-project\n", encoding="utf-8")
    other = tmp_path / "elsewhere"
    other.mkdir()
    assert config.api_key({"CLAUDE_PROJECT_DIR": str(project)}, other) == "from-project"
    assert config.project_root({"CLAUDE_PROJECT_DIR": str(project)}, other) == project
    assert config.project_root({}, other) == other


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("MESHY_API_KEY=plain\n", "plain"),
        ("export MESHY_API_KEY=exported\n", "exported"),
        ('MESHY_API_KEY="quoted"\n', "quoted"),
        ("MESHY_API_KEY='single'\n", "single"),
        ("  MESHY_API_KEY =  spaced  \n", "spaced"),
        ("# MESHY_API_KEY=commented\nMESHY_API_KEY=real\n", "real"),
        ("\n\nOTHER=1\nMESHY_API_KEY=last\n", "last"),
        ("MESHY_API_KEY=\"mismatched'\n", "\"mismatched'"),
    ],
)
def test_dotenv_parsing(tmp_path: Path, text: str, expected: str) -> None:
    path = tmp_path / ".env"
    path.write_text(text, encoding="utf-8")
    assert config.read_dotenv(path)["MESHY_API_KEY"] == expected


def test_missing_dotenv_has_no_values(tmp_path: Path) -> None:
    assert config.read_dotenv(tmp_path / "absent.env") == {}


def test_redact_replaces_every_occurrence() -> None:
    assert config.redact("key abc and abc", "abc") == "key *** and ***"
    assert config.redact("unchanged", "") == "unchanged"
