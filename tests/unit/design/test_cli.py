"""Exit codes and printed lines of the design sync and scaffold commands (AC1-AC3, AC5, AC6).

Every test passes ``--project`` as ``tmp_path``, and scaffold tests pass a fake editor, so no test
touches the real repo or a live Unreal editor.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

from nmg_game_dev.design.__main__ import main
from nmg_game_dev.design.paths import backlog_path
from nmg_game_dev.pipeline.errors import PipelineError

UNREACHABLE = "mcp.unreal.unreachable"
REGION_PATH = "/Game/Levels/OldTown/L_OldTown"

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


class FakeEditor:
    """Stands in for the Unreal MCP client: answers every call with one fixed ``NMG_RESULT``."""

    def __init__(
        self,
        result: dict[str, Any] | None = None,
        raises: PipelineError | None = None,
    ) -> None:
        self.calls = 0
        self._result = result or {"ok": True, "created": True, "path": REGION_PATH, "error": None}
        self._raises = raises

    def execute_python_code(self, code: str) -> str:
        self.calls += 1
        if self._raises is not None:
            raise self._raises
        return f"NMG_RESULT {json.dumps(self._result)}\n"


def _cli(argv: list[str], editor: FakeEditor | None = None) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(argv, client=editor, stdout=out, stderr=err)
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


def test_scaffold_exits_0_when_every_item_scaffolds(tmp_path: Path) -> None:
    _write(tmp_path, "regions/old-town.md", REGION)
    _sync(tmp_path)
    editor = FakeEditor()

    code, out, err = _cli(["scaffold", "--project", str(tmp_path)], editor)

    assert code == 0
    assert out == f"created region OldTown: {REGION_PATH}\n"
    assert err == ""
    assert editor.calls == 1


def test_scaffold_exits_1_when_an_item_fails(tmp_path: Path) -> None:
    _write(tmp_path, "regions/old-town.md", REGION)
    _sync(tmp_path)
    failed = {"ok": False, "created": False, "path": REGION_PATH, "error": "RuntimeError: boom"}

    code, out, _err = _cli(["scaffold", "--project", str(tmp_path)], FakeEditor(result=failed))

    assert code == 1
    assert out == "error design.scaffold_failed OldTown: RuntimeError: boom\n"


def test_scaffold_exits_2_when_the_editor_is_unreachable(tmp_path: Path) -> None:
    _write(tmp_path, "regions/old-town.md", REGION)
    _sync(tmp_path)
    unreachable = PipelineError(
        UNREACHABLE,
        "Unreal MCP is unreachable at http://127.0.0.1:55557/mcp",
        "Start the Unreal editor, then rerun scaffold",
        "unreal_mcp",
    )

    code, out, err = _cli(["scaffold", "--project", str(tmp_path)], FakeEditor(raises=unreachable))

    assert code == 2
    assert out == ""
    assert "ERROR [mcp.unreal.unreachable] Unreal MCP is unreachable" in err
    assert "Remediation: Start the Unreal editor, then rerun scaffold" in err


def test_scaffold_exits_1_with_a_message_when_the_backlog_is_missing(tmp_path: Path) -> None:
    _write(tmp_path, "regions/old-town.md", REGION)
    editor = FakeEditor()

    code, _out, err = _cli(["scaffold", "--project", str(tmp_path)], editor)

    assert code == 1
    assert "does not exist" in err
    assert "python -m nmg_game_dev.design sync" in err
    assert editor.calls == 0
