"""Regression tests for two design-CLI faults found in review of #112.

A design file saved with a UTF-8 byte-order mark must still parse.  A corrupt backlog must make
``scaffold`` report an error and exit 1, not crash with a traceback.
"""

from __future__ import annotations

import io
from pathlib import Path

from nmg_game_dev.design.__main__ import main
from nmg_game_dev.design.model import Entry
from nmg_game_dev.design.parse import parse_file
from nmg_game_dev.design.paths import backlog_path


class _NeverCalled:
    """Fails the test if scaffold reaches the Unreal editor."""

    def execute_python_code(self, code: str) -> str:
        raise AssertionError("no Unreal call is expected when the backlog is unreadable")


def test_a_utf8_byte_order_mark_before_the_frontmatter_is_accepted(tmp_path: Path) -> None:
    path = tmp_path / "docs" / "design" / "props" / "crate.md"
    path.parent.mkdir(parents=True)
    text = "---\ntype: prop\nname: Crate\ncategory: Props\nasset_class: standard_prop\n---\n"
    path.write_bytes("﻿".encode() + text.encode("utf-8"))

    result = parse_file(path, tmp_path)

    assert isinstance(result, Entry)
    assert result.asset_name == "Crate"


def test_scaffold_reports_an_unreadable_backlog_and_exits_1(tmp_path: Path) -> None:
    (tmp_path / "docs" / "design").mkdir(parents=True)
    backlog_path(tmp_path).write_text("not json", encoding="utf-8")
    out, err = io.StringIO(), io.StringIO()

    code = main(
        ["scaffold", "--project", str(tmp_path)],
        client=_NeverCalled(),
        stdout=out,
        stderr=err,
    )

    assert code == 1
    assert err.getvalue().startswith("ERROR: ")
    assert out.getvalue() == ""
