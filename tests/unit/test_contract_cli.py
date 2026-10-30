"""Unit tests for the contract CLI and Blender resolution (#30, AC7).

Blender is replaced by a stub on BLENDER_BIN. The stub logs its argv, then copies a fixed
payload to the --report path, so exit codes and argument passing are checked without launching
Blender. The stub is a shell script because a Python shebang cannot hold the repo venv path,
which contains a space.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from nmg_game_dev.contract import blender as blender_module
from nmg_game_dev.contract import main, resolve_blender

REPO_ROOT = Path(__file__).resolve().parents[2]

_STUB = r"""#!/bin/sh
printf '%s\n' "$@" > "$STUB_ARGV_LOG"
if [ -n "$STUB_SKIP_REPORT" ]; then
  echo "stub: simulated Blender failure" >&2
  exit 3
fi
report=""
prev=""
for arg in "$@"; do
  if [ "$prev" = "--report" ]; then
    report="$arg"
  fi
  prev="$arg"
done
mkdir -p "$(dirname "$report")"
cp "$STUB_PAYLOAD" "$report"
"""

_TRANSFORM = {
    "rule": "transform.root_applied",
    "target": "SM_Crate",
    "message": "Root rotation is (0, 0, 90) degrees.",
    "remediation": "Apply rotation and scale to SM_Crate (Ctrl+A) before export.",
}
_PIVOT = {
    "rule": "pivot.bottom_center",
    "target": "SM_Crate",
    "message": "Origin is 0.4 m above the bottom center.",
    "remediation": "Move the origin to the bottom center at world origin.",
}


def _report_body(kind: str, passed: bool, findings: list[dict[str, str]] | None = None) -> str:
    return json.dumps(
        {
            "kind": kind,
            "asset": "Crate",
            "class": "standard_prop",
            "passed": passed,
            "findings": findings or [],
            "snapshot": {},
        }
    )


def _set_payload(tmp_path: Path, body: str) -> None:
    (tmp_path / "payload.json").write_text(body, encoding="utf-8")


def _argv(tmp_path: Path) -> list[str]:
    return (tmp_path / "argv.txt").read_text(encoding="utf-8").splitlines()


def _make_executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(0o755)
    return path


@pytest.fixture()
def entry_script(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    entry = tmp_path / "contract_entry.py"
    entry.write_text("# stands in for scripts/blender/contract_entry.py\n", encoding="utf-8")
    monkeypatch.setattr(blender_module, "ENTRY_SCRIPT", entry)
    return entry


@pytest.fixture()
def blender_stub(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    entry_script: Path,  # noqa: ARG001 — ENTRY_SCRIPT must be patched first
) -> Path:
    stub = _make_executable(tmp_path / "bin" / "Blender")
    stub.write_text(_STUB, encoding="utf-8")
    stub.chmod(0o755)
    monkeypatch.setenv("BLENDER_BIN", str(stub))
    monkeypatch.delenv("BLENDER_APP", raising=False)
    monkeypatch.delenv("STUB_SKIP_REPORT", raising=False)
    monkeypatch.setenv("STUB_ARGV_LOG", str(tmp_path / "argv.txt"))
    monkeypatch.setenv("STUB_PAYLOAD", str(tmp_path / "payload.json"))
    return stub


def test_validate_pass_exits_zero(
    tmp_path: Path,
    blender_stub: Path,  # noqa: ARG001
    entry_script: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_payload(tmp_path, _report_body("contract", passed=True))
    blend = tmp_path / "Crate.blend"
    report = tmp_path / "out" / "nmg-report.json"

    code = main(
        [
            "validate",
            "--blend",
            str(blend),
            "--collection",
            "Crate",
            "--class",
            "standard_prop",
            "--report",
            str(report),
        ]
    )

    assert code == 0
    assert capsys.readouterr().out == "contract: PASS\n"
    assert report.is_file()
    argv = _argv(tmp_path)
    assert argv[:4] == ["--background", "--python", str(entry_script), "--"]
    assert argv[4:] == [
        "validate",
        "--blend",
        str(blend),
        "--collection",
        "Crate",
        "--class",
        "standard_prop",
        "--report",
        str(report),
    ]


def test_validate_fail_exits_one_with_findings(
    tmp_path: Path,
    blender_stub: Path,  # noqa: ARG001
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_payload(tmp_path, _report_body("contract", False, [_TRANSFORM, _PIVOT]))
    report = tmp_path / "nmg-report.json"

    code = main(
        [
            "validate",
            "--blend",
            str(tmp_path / "Crate.blend"),
            "--collection",
            "Crate",
            "--class",
            "standard_prop",
            "--report",
            str(report),
        ]
    )

    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == (
        "contract: FAIL (2 findings): transform.root_applied, pivot.bottom_center\n"
    )
    assert "Apply rotation and scale to SM_Crate (Ctrl+A) before export." in captured.err


def test_validate_forwards_budgets_without_factory_startup(
    tmp_path: Path,
    blender_stub: Path,  # noqa: ARG001
) -> None:
    _set_payload(tmp_path, _report_body("contract", passed=True))
    budgets = tmp_path / "nmg-budgets.json"

    code = main(
        [
            "validate",
            "--blend",
            "Crate.blend",
            "--collection",
            "Crate",
            "--class",
            "hero_prop",
            "--report",
            str(tmp_path / "r.json"),
            "--budgets",
            str(budgets),
        ]
    )

    argv = _argv(tmp_path)
    assert code == 0
    assert "--factory-startup" not in argv
    assert argv[argv.index("--budgets") + 1] == str(budgets)


def test_reimport_runs_with_factory_startup(
    tmp_path: Path,
    blender_stub: Path,  # noqa: ARG001
    entry_script: Path,
) -> None:
    _set_payload(tmp_path, _report_body("reimport", passed=True))
    variant_dir = tmp_path / "Props" / "Crate" / "Desktop"
    pre_report = tmp_path / "pre.json"
    report = tmp_path / "reimport.json"

    code = main(
        [
            "reimport",
            "--variant-dir",
            str(variant_dir),
            "--pre-report",
            str(pre_report),
            "--report",
            str(report),
        ]
    )

    argv = _argv(tmp_path)
    assert code == 0
    assert argv[:5] == ["--background", "--factory-startup", "--python", str(entry_script), "--"]
    assert argv[5:] == [
        "reimport",
        "--variant-dir",
        str(variant_dir),
        "--pre-report",
        str(pre_report),
        "--report",
        str(report),
    ]


def test_reimport_fail_exits_one(
    tmp_path: Path,
    blender_stub: Path,  # noqa: ARG001
    capsys: pytest.CaptureFixture[str],
) -> None:
    finding = {
        "rule": "reimport.texture_missing",
        "target": "T_Crate_Body_BC.png",
        "message": "Not found beside SM_Crate.fbx.",
        "remediation": "Re-export the Desktop variant.",
    }
    _set_payload(tmp_path, _report_body("reimport", False, [finding]))

    code = main(
        [
            "reimport",
            "--variant-dir",
            str(tmp_path),
            "--pre-report",
            str(tmp_path / "pre.json"),
            "--report",
            str(tmp_path / "r.json"),
        ]
    )

    assert code == 1
    assert "contract: FAIL (1 findings): reimport.texture_missing" in capsys.readouterr().out


def test_missing_blender_exits_two_with_remediation(
    tmp_path: Path,
    entry_script: Path,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("BLENDER_BIN", raising=False)
    empty_app = tmp_path / "Empty.app"
    empty_app.mkdir()
    monkeypatch.setenv("BLENDER_APP", str(empty_app))
    missing_default = tmp_path / "Missing.app"
    monkeypatch.setattr(blender_module, "DEFAULT_BLENDER_APP", missing_default)
    report = tmp_path / "r.json"

    code = main(
        [
            "validate",
            "--blend",
            "Crate.blend",
            "--collection",
            "Crate",
            "--class",
            "standard_prop",
            "--report",
            str(report),
        ]
    )

    err = capsys.readouterr().err
    assert code == 2
    assert "contract.blender_not_found" in err
    assert "BLENDER_BIN" in err
    assert str(missing_default / "Contents" / "MacOS" / "Blender") in err
    assert not report.exists()


def test_missing_report_exits_two_with_blender_output(
    tmp_path: Path,
    blender_stub: Path,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("STUB_SKIP_REPORT", "1")

    code = main(
        [
            "validate",
            "--blend",
            "Crate.blend",
            "--collection",
            "Crate",
            "--class",
            "standard_prop",
            "--report",
            str(tmp_path / "r.json"),
        ]
    )

    err = capsys.readouterr().err
    assert code == 2
    assert "contract.no_report" in err
    assert "exited with code 3" in err
    assert "simulated Blender failure" in err


def test_stale_report_is_removed_before_blender_runs(
    tmp_path: Path,
    blender_stub: Path,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = tmp_path / "r.json"
    report.write_text(_report_body("contract", passed=True), encoding="utf-8")
    monkeypatch.setenv("STUB_SKIP_REPORT", "1")

    code = main(
        [
            "validate",
            "--blend",
            "Crate.blend",
            "--collection",
            "Crate",
            "--class",
            "standard_prop",
            "--report",
            str(report),
        ]
    )

    assert code == 2
    assert not report.exists()


def test_unreadable_report_exits_two(
    tmp_path: Path,
    blender_stub: Path,  # noqa: ARG001
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_payload(tmp_path, "{not json")

    code = main(
        [
            "validate",
            "--blend",
            "Crate.blend",
            "--collection",
            "Crate",
            "--class",
            "standard_prop",
            "--report",
            str(tmp_path / "r.json"),
        ]
    )

    assert code == 2
    assert "quality.report_unreadable" in capsys.readouterr().err


def test_missing_entry_script_exits_two(
    tmp_path: Path,
    blender_stub: Path,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(blender_module, "ENTRY_SCRIPT", tmp_path / "absent.py")

    code = main(
        [
            "validate",
            "--blend",
            "Crate.blend",
            "--collection",
            "Crate",
            "--class",
            "standard_prop",
            "--report",
            str(tmp_path / "r.json"),
        ]
    )

    assert code == 2
    assert "contract.entry_missing" in capsys.readouterr().err
    assert not (tmp_path / "argv.txt").exists()


def test_render_reports_written_file_count(
    tmp_path: Path,
    blender_stub: Path,  # noqa: ARG001
    capsys: pytest.CaptureFixture[str],
) -> None:
    views = ("front", "back", "side", "three_quarter")
    files = [f"{variant}/Crate_{view}.png" for variant in ("desktop", "mobile") for view in views]
    _set_payload(tmp_path, json.dumps({"kind": "render", "files": files}))
    blend = tmp_path / "Crate.blend"
    out = tmp_path / "review"

    code = main(
        ["render", "--blend", str(blend), "--collection", "Crate", "--out", str(out)],
    )

    argv = _argv(tmp_path)
    assert code == 0
    assert capsys.readouterr().out == f"render: wrote 8 file(s) to {out}\n"
    assert "--factory-startup" not in argv
    assert argv[4:] == [
        "render",
        "--blend",
        str(blend),
        "--collection",
        "Crate",
        "--out",
        str(out),
        "--resolution",
        "1024",
        "--report",
        str(out / "render-report.json"),
    ]


def test_render_forwards_optional_inputs(
    tmp_path: Path,
    blender_stub: Path,  # noqa: ARG001
) -> None:
    _set_payload(tmp_path, json.dumps({"kind": "render", "files": ["desktop/Crate_proof.png"]}))
    out = tmp_path / "review"

    code = main(
        [
            "render",
            "--blend",
            "Crate.blend",
            "--collection",
            "Crate",
            "--out",
            str(out),
            "--proof-variant-dir",
            str(tmp_path / "Desktop"),
            "--pre-bake",
            str(tmp_path / "prebake.png"),
            "--resolution",
            "128",
        ]
    )

    argv = _argv(tmp_path)
    assert code == 0
    assert argv[argv.index("--proof-variant-dir") + 1] == str(tmp_path / "Desktop")
    assert argv[argv.index("--pre-bake") + 1] == str(tmp_path / "prebake.png")
    assert argv[argv.index("--resolution") + 1] == "128"


def test_render_missing_report_exits_two(
    tmp_path: Path,
    blender_stub: Path,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STUB_SKIP_REPORT", "1")

    code = main(
        ["render", "--blend", "Crate.blend", "--collection", "Crate", "--out", str(tmp_path)],
    )

    assert code == 2


def test_resolve_blender_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bin_override = _make_executable(tmp_path / "override" / "Blender")
    app_bundle = tmp_path / "Applied.app"
    app_binary = _make_executable(app_bundle / "Contents" / "MacOS" / "Blender")
    default_bundle = tmp_path / "Default.app"
    default_binary = _make_executable(default_bundle / "Contents" / "MacOS" / "Blender")
    not_executable = tmp_path / "plain.txt"
    not_executable.write_text("not a program", encoding="utf-8")
    monkeypatch.setattr(blender_module, "DEFAULT_BLENDER_APP", default_bundle)

    monkeypatch.setenv("BLENDER_BIN", str(bin_override))
    monkeypatch.setenv("BLENDER_APP", str(app_bundle))
    assert resolve_blender() == bin_override

    monkeypatch.setenv("BLENDER_BIN", str(not_executable))
    assert resolve_blender() == app_binary

    monkeypatch.delenv("BLENDER_BIN")
    assert resolve_blender() == app_binary

    monkeypatch.delenv("BLENDER_APP")
    assert resolve_blender() == default_binary


def test_module_entry_point_prints_help() -> None:
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")}

    completed = subprocess.run(
        [sys.executable, "-m", "nmg_game_dev.contract", "validate", "--help"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    assert completed.returncode == 0
    assert "--class" in completed.stdout
