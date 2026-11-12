"""plugin.session-smoke pages the whole /mcp list and judges servers from every row read (#193).

Each test runs the real provider through node with a fake ``herdr`` first on PATH. The fake
renders a 16-row /mcp list in a tab of configurable height, scrolls it to keep the selection
visible, moves the selection on up/down keys (wrapping at either end, as Claude Code does), and
logs the keys it receives. With ``name_width`` set it draws the narrow-pane list Claude Code
draws in a ~40-column Herdr tab: names cut to ``plugin:nmg-game…`` and ``enter`` opening a detail
view that names the server in full, which ``esc`` leaves with the first row selected. No Claude
Code, Blender, or Unreal process starts.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

from _scaffold_contract import REPO_ROOT

SMOKE_MODULE = REPO_ROOT / "steering" / "extensions" / "plugin-session-smoke.mjs"

# Fake herdr: answers each subcommand the provider calls and keeps the /mcp list state in a file.
_FAKE_HERDR = r"""
import json
import os
import sys
import textwrap
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HOME = Path(os.environ["FAKE_HERDR_DIR"])
STATE = HOME / "state.json"
KEYS = HOME / "keys.log"
TAB = "tab-1"
PANE = "pane-1"


def emit(result):
    print(json.dumps({"id": "fake", "result": result}))
    sys.exit(0)


def load():
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}


def save(state):
    STATE.write_text(json.dumps(state), encoding="utf-8")


def layout(top, height, count):
    above = top > 0
    room = height - (1 if above else 0)
    if top + room < count:
        room -= 1
    return above, min(count, top + room)


def scroll(selected, top, height, count):
    top = min(top, selected)
    while selected >= layout(top, height, count)[1]:
        top += 1
    return top


def narrow(row, width):
    # "plugin:nmg-game-dev:blender ✔ connected" -> "✔ plugin:nmg-game…   3 tools"
    name, status = row.split(" ", 1)
    icon = status.split()[0]
    shown = name if len(name) <= width else name[: width - 1] + "…"
    return f"{icon} {shown}" + ("   3 tools" if icon == "✔" else "")


def detail(row):
    name, status = row.split(" ", 1)
    # The real view capitalises the name and wraps it: "Plugin:nmg-game-dev:blender MCP" / "Server".
    title = textwrap.wrap(f"{name[:1].upper()}{name[1:]} MCP Server", width=34)
    return "\n".join([
        "Manage MCP servers",
        *title,
        "",
        f"Status:           {status}",
        "Config location:  Dynamically",
        "                  configured",
        "❯ 1. View tools",
        "↑/↓ to navigate · Enter to select",
        "· Esc to back",
    ]) + "\n"


def render(state):
    rows, top, height = state["rows"], state["top"], state["height"]
    if state.get("detail"):
        return detail(rows[state["selected"]])
    width = state.get("name_width")
    above, last = layout(top, height, len(rows))
    lines = [f"{len(rows)} servers"]
    lines += [f"↑ {top} more"] if above else []
    for index in range(top, last):
        mark = "❯ " if index == state["selected"] else "  "
        lines.append(mark + (narrow(rows[index], width) if width else rows[index]))
    below = len(rows) - last
    if below:
        lines.append(f"↓ {below} more")
    return "\n".join(lines) + "\n"


def press(state, key):
    count = len(state["rows"])
    if state.get("detail"):
        if key == "esc":
            state.update(detail=False, selected=0, top=0)
        return
    if key == "enter":
        state["detail"] = True
        return
    if key == "up":
        state["selected"] = (state["selected"] - 1) % count
    elif key == "down":
        state["selected"] = (state["selected"] + 1) % count
    else:
        return
    state["top"] = scroll(state["selected"], state["top"], state["height"], count)


args = sys.argv[1:]
if args[:2] == ["tab", "create"]:
    save({"label": args[args.index("--label") + 1]})
    emit({"tab": {"tab_id": TAB}})
if args[:2] == ["tab", "list"]:
    emit({"tabs": [{"tab_id": TAB, "label": load().get("label")}]})
if args[:2] == ["pane", "list"]:
    emit({"panes": [{"pane_id": PANE, "tab_id": TAB}]})
if args[:2] == ["agent", "start"]:
    emit({})
if args[:2] == ["agent", "prompt"]:
    state = load()
    state.update(json.loads((HOME / "config.json").read_text(encoding="utf-8")))
    save(state)
    emit({})
if args[:2] == ["pane", "read"]:
    state = load()
    sys.stdout.write(render(state) if "rows" in state else "")
    sys.exit(0)
if args[:2] == ["pane", "send-keys"]:
    state = load()
    if state.get("refuse_keys"):
        sys.stderr.write("fake herdr: pane is not accepting keys\n")
        sys.exit(1)
    for key in args[3:]:
        with KEYS.open("a", encoding="utf-8") as log:
            log.write(key + "\n")
        press(state, key)
    save(state)
    emit({})
if args[:2] == ["tab", "close"]:
    emit({})
sys.stderr.write(f"fake herdr: unhandled {args}\n")
sys.exit(2)
"""

# Runs the provider with near-zero timings. argv: module URL, project root.
_DRIVER = """
const { createSmoke } = await import(process.argv[1]);
const smoke = createSmoke({ pollMs: 1, keySettleMs: 1, mcpPolls: 2 });
const result = await smoke({
  projectRoot: process.argv[2],
  config: { expectConnected: ["blender"] },
  identity: { label: "plugin-session-smoke-test" },
});
process.stdout.write(JSON.stringify(result));
"""


def _mcp_rows(blender_at: int | None, blender_status: str = "✔ connected") -> list[str]:
    rows = [f"plugin:nmg-game-dev:server-{index:02d} ✔ connected" for index in range(16)]
    if blender_at is not None:
        rows[blender_at] = f"plugin:nmg-game-dev:blender {blender_status}"
    return rows


def _smoke(
    tmp_path: Path,
    rows: list[str],
    *,
    height: int,
    top: int = 0,
    selected: int = 0,
    **screen: Any,
) -> tuple[dict[str, Any], list[str]]:
    home = tmp_path / "herdr"
    home.mkdir()
    config = {"rows": rows, "height": height, "top": top, "selected": selected, **screen}
    (home / "config.json").write_text(json.dumps(config), encoding="utf-8")
    fake = tmp_path / "fake_herdr.py"
    fake.write_text(_FAKE_HERDR, encoding="utf-8")
    shim_dir = tmp_path / "bin"
    shim_dir.mkdir()
    shim = shim_dir / "herdr"
    shim.write_text(
        f'#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(fake))} "$@"\n',
        encoding="utf-8",
    )
    shim.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{shim_dir}{os.pathsep}{os.environ['PATH']}",
        "FAKE_HERDR_DIR": str(home),
    }

    completed = subprocess.run(
        ["node", "--input-type=module", "-e", _DRIVER, SMOKE_MODULE.as_uri(), str(tmp_path)],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    result: dict[str, Any] = json.loads(completed.stdout)
    keys_log = home / "keys.log"
    keys = keys_log.read_text(encoding="utf-8").splitlines() if keys_log.exists() else []
    return result, keys


def test_a_connected_server_below_the_fold_is_found(tmp_path: Path) -> None:
    # AC1: a 6-row tab shows the top of a 16-row list; blender is row 13 (index 12).
    result, keys = _smoke(tmp_path, _mcp_rows(blender_at=12), height=6)

    assert result["status"] == "passed", result
    assert "nmg-game-dev:blender connected" in result["summary"]
    assert "down" in keys


def test_a_connected_server_above_a_bottom_scrolled_window_is_found(tmp_path: Path) -> None:
    # AC1: the window starts scrolled to the bottom; blender is row 2 (index 1), above it.
    result, keys = _smoke(tmp_path, _mcp_rows(blender_at=1), height=6, top=11, selected=15)

    assert result["status"] == "passed", result
    assert "nmg-game-dev:blender connected" in result["summary"]
    assert "up" in keys


def test_a_server_missing_from_the_full_list_fails_and_is_named(tmp_path: Path) -> None:
    # AC2: no blender row anywhere in the list.
    result, _ = _smoke(tmp_path, _mcp_rows(blender_at=None), height=6)

    assert result["status"] == "failed", result
    assert "nmg-game-dev:blender missing" in result["summary"]


def test_a_failed_server_below_the_fold_fails_and_is_named(tmp_path: Path) -> None:
    # AC2: blender is below the fold and marked failed.
    rows = _mcp_rows(blender_at=12, blender_status="✘ failed")
    result, _ = _smoke(tmp_path, rows, height=6)

    assert result["status"] == "failed", result
    assert "nmg-game-dev:blender failed" in result["summary"]


def test_the_mcp_artifact_holds_every_row_read_after_paging(tmp_path: Path) -> None:
    # AC3: the 16 rows are only all visible after paging through a 6-row tab.
    rows = _mcp_rows(blender_at=12)
    result, _ = _smoke(tmp_path, rows, height=6)

    artifacts = [entry["artifact"] for entry in result["evidence"] if entry["kind"] == "artifact"]
    assert len(artifacts) == 1, result["evidence"]
    for row in rows:
        assert row in artifacts[0]


def test_a_window_tall_enough_for_the_whole_list_sends_no_keys(tmp_path: Path) -> None:
    # FR2: no More marker on screen, so the pass reads once and sends nothing.
    result, keys = _smoke(tmp_path, _mcp_rows(blender_at=12), height=20)

    assert result["status"] == "passed", result
    assert "nmg-game-dev:blender connected" in result["summary"]
    assert keys == []


# The ~40-column Herdr pane of the real gate run: every plugin name is cut to "plugin:nmg-game…".
_NARROW = 16


def _mcp_artifact(result: dict[str, Any]) -> str:
    artifacts = [entry["artifact"] for entry in result["evidence"] if entry["kind"] == "artifact"]
    assert len(artifacts) == 1, result["evidence"]
    return str(artifacts[0])


def test_a_connected_server_with_a_truncated_name_is_found_in_its_detail_view(
    tmp_path: Path,
) -> None:
    # AC1: a short, narrow tab; blender's row reads "✔ plugin:nmg-game…   3 tools" below the fold.
    result, keys = _smoke(tmp_path, _mcp_rows(blender_at=12), height=6, name_width=_NARROW)

    assert result["status"] == "passed", result
    assert "nmg-game-dev:blender connected" in result["summary"]
    assert "enter" in keys
    assert "esc" in keys
    # AC3: the evidence holds the detail view that named the server.
    assert "Plugin:nmg-game-dev:blender MCP" in _mcp_artifact(result)


def test_a_failed_server_with_a_truncated_name_fails_and_is_named(tmp_path: Path) -> None:
    # AC2: the failed status is read from blender's detail view.
    rows = _mcp_rows(blender_at=12, blender_status="✘ failed")
    result, _ = _smoke(tmp_path, rows, height=6, name_width=_NARROW)

    assert result["status"] == "failed", result
    assert "nmg-game-dev:blender failed" in result["summary"]


def test_a_missing_server_among_truncated_names_is_walked_once(tmp_path: Path) -> None:
    # AC2: no blender row. The first open also finds the walk's place in the list (esc selects
    # the first row), so that row is opened twice and every other row once; an unchanged list is
    # not walked again on the second poll.
    rows = _mcp_rows(blender_at=None)
    result, keys = _smoke(tmp_path, rows, height=6, name_width=_NARROW)

    assert result["status"] == "failed", result
    assert "nmg-game-dev:blender missing" in result["summary"]
    assert keys.count("enter") == len(rows) + 1
    assert keys.count("enter") == keys.count("esc")


def test_refused_keys_are_recorded_as_paging_stopped_early(tmp_path: Path) -> None:
    # AC3: the evidence says why rows below the fold were never read.
    result, keys = _smoke(tmp_path, _mcp_rows(blender_at=12), height=6, refuse_keys=True)

    assert result["status"] == "failed", result
    assert "nmg-game-dev:blender missing" in result["summary"]
    assert keys == []
    refused = [entry for entry in result["evidence"] if "paging stopped early" in entry["summary"]]
    assert refused, result["evidence"]
    assert "not accepting keys" in refused[0]["stderr"]
