"""Exit codes and printed lines of the design sync and scaffold commands (#112, #249).

Every test passes ``--project`` as ``tmp_path``, so no test touches the real repo.
"""

from __future__ import annotations

import io
import subprocess
import sys
from pathlib import Path

import pytest

from nmg_game_dev.design.__main__ import main
from nmg_game_dev.design.paths import backlog_path

REGION_FILE = "game/levels/OldTown/OldTown.tscn"

REGION = """\
---
type: region
name: Old Town
---
"""

PROP = """\
---
type: prop
name: Crate
asset_class: standard_prop
category: Props
---
"""


def _cli(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(argv, stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


def _write(root: Path, relative: str, text: str) -> None:
    path = root / "docs" / "design" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _sync(root: Path) -> None:
    code, _out, err = _cli(["sync", "--project", str(root)])
    assert code == 0, err


def test_sync_on_a_fresh_project_prints_planned_lines_and_exits_0(tmp_path: Path) -> None:
    _write(tmp_path, "regions/old-town.md", REGION)
    _write(tmp_path, "props/crate.md", PROP)

    code, out, err = _cli(["sync", "--project", str(tmp_path)])

    assert code == 0
    assert err == ""
    assert out.splitlines() == [
        "planned prop Crate: docs/design/props/crate.md",
        "planned region OldTown: docs/design/regions/old-town.md",
    ]
    assert backlog_path(tmp_path).is_file()


def test_sync_with_design_errors_prints_every_error_and_keeps_the_backlog(tmp_path: Path) -> None:
    _write(tmp_path, "regions/old-town.md", REGION)
    _sync(tmp_path)
    before = backlog_path(tmp_path).read_bytes()
    _write(tmp_path, "props/bad-type.md", "---\ntype: spaceship\nname: Ship\n---\n")
    _write(tmp_path, "regions/no-frontmatter.md", "# Old Town\n")

    code, out, _err = _cli(["sync", "--project", str(tmp_path)])

    assert code == 1
    lines = out.splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("error design.unknown_type docs/design/props/bad-type.md: type — ")
    assert lines[1].startswith(
        "error design.frontmatter_missing docs/design/regions/no-frontmatter.md: frontmatter — "
    )
    assert backlog_path(tmp_path).read_bytes() == before


def test_sync_without_a_design_directory_exits_1_with_dir_missing(tmp_path: Path) -> None:
    code, out, _err = _cli(["sync", "--project", str(tmp_path)])

    assert code == 1
    assert out.startswith("error design.dir_missing docs/design: directory — ")
    assert not backlog_path(tmp_path).exists()


def _godot_project(root: Path) -> None:
    (root / "game").mkdir(parents=True, exist_ok=True)
    (root / "game" / "project.godot").write_text("config_version=5\n", encoding="utf-8")


def test_scaffold_exits_0_when_every_item_scaffolds(tmp_path: Path) -> None:
    _write(tmp_path, "regions/old-town.md", REGION)
    _sync(tmp_path)
    _godot_project(tmp_path)

    code, out, err = _cli(["scaffold", "--project", str(tmp_path)])

    assert code == 0
    assert out == f"created region OldTown: {REGION_FILE}\n"
    assert err == ""
    assert (tmp_path / REGION_FILE).is_file()


def test_scaffold_exits_1_when_an_item_fails(tmp_path: Path) -> None:
    _write(tmp_path, "regions/old-town.md", REGION)
    _sync(tmp_path)
    _godot_project(tmp_path)
    (tmp_path / "game" / "levels").write_text("not a folder", encoding="utf-8")

    code, out, _err = _cli(["scaffold", "--project", str(tmp_path)])

    assert code == 1
    assert out.startswith(f"error design.scaffold_failed OldTown: {REGION_FILE}: ")


def test_scaffold_exits_1_when_the_godot_project_is_missing(tmp_path: Path) -> None:
    _write(tmp_path, "regions/old-town.md", REGION)
    _sync(tmp_path)

    code, out, err = _cli(["scaffold", "--project", str(tmp_path)])

    assert code == 1
    assert out == ""
    assert "ERROR [design.godot_project_missing] " in err
    assert "Remediation: Run /onboard-consumer" in err
    assert not (tmp_path / "game").exists()


def test_scaffold_exits_1_with_a_message_when_the_backlog_is_missing(tmp_path: Path) -> None:
    _write(tmp_path, "regions/old-town.md", REGION)
    _godot_project(tmp_path)

    code, _out, err = _cli(["scaffold", "--project", str(tmp_path)])

    assert code == 1
    assert "does not exist" in err
    assert "python -m nmg_game_dev.design sync" in err
    assert sorted(p.name for p in (tmp_path / "game").iterdir()) == ["project.godot"]


def test_scaffold_has_no_url_option(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as caught:
        _cli(["scaffold", "--project", str(tmp_path), "--url", "http://127.0.0.1:1/mcp"])
    assert caught.value.code == 2


def test_the_module_runs_as_a_script(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "nmg_game_dev.design", "scaffold", "--help"],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert "--project" in result.stdout
    assert "--url" not in result.stdout
