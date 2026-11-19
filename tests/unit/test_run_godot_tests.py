"""gate-godot-headless: scripts/run-godot-tests.sh against a fake Godot, curl, and unzip (#249).

The script resolves Godot from GODOT_BIN, then PATH, then a download of the latest stable release
into a cache folder. Every tool here is a fake on a sandbox PATH, so nothing touches the network or
runs a real Godot. Also checks the add-on version and the committed fixture files.
"""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import pytest

from nmg_game_dev.pipeline.errors import PipelineError
from tests.godot.make_crate_glb import build as build_crate_glb

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
SCRIPT: Final = REPO_ROOT / "scripts" / "run-godot-tests.sh"
FIXTURE: Final = REPO_ROOT / "tests" / "godot" / "fixture"
ADDON: Final = REPO_ROOT / "plugins" / "nmg-game-dev-godot-addon" / "addons" / "nmg_game_dev"
TAG: Final = "4.9-stable"

_FAKE_GODOT: Final = r"""
import json, os, sys
from pathlib import Path

args = sys.argv[1:]
project = Path(args[args.index("--path") + 1])
rest = args[args.index("--path") + 2:]
record = {"argv": args, "self": os.environ["FAKE_SELF"]}
if rest[:1] == ["-s"] and "--" in rest:
    record["params"] = json.loads(Path(rest[rest.index("--") + 1]).read_text())
    record["probe_exists"] = (project / rest[1].removeprefix("res://")).is_file()
with open(os.environ["FAKE_GODOT_LOG"], "a") as log:
    log.write(json.dumps(record) + "\n")
mode = os.environ.get("FAKE_GODOT_MODE", "")
if mode == "hang":
    import time
    time.sleep(30)
if rest == ["--import"]:
    if not (project / "project.godot").is_file() or not (
        project / "addons/nmg_game_dev/plugin.cfg"
    ).is_file() or not (project / "Beep.wav").is_file():
        print("ERROR: fixture, add-on, or Beep.wav was not copied")
        sys.exit(0)
    if mode == "import_error":
        print("ERROR: Failed loading resource: res://Crate.glb")
    sys.exit(1 if mode == "import_exit" else 0)
if rest[:2] == ["-s", "res://addons/nmg_game_dev/tests/run_tests.gd"]:
    if mode == "tests_fail":
        print("FAIL test_nmg_assets.gd::test_mobile_variant\n8 passed, 1 failed")
        sys.exit(1)
    if mode == "tests_script_error":
        print("SCRIPT ERROR: Invalid call\n9 passed, 0 failed")
        sys.exit(0)
    if mode == "tests_no_summary":
        sys.exit(0)
    required = ["test_nmg_assets.gd::test_desktop_variant",
                "test_nmg_assets.gd::test_mobile_variant",
                "test_nmg_assets.gd::test_malformed_path_is_unchanged_with_a_warning",
                "test_nmg_launch.gd::test_cmdline_options",
                "test_nmg_launch.gd::test_web_hash_options",
                "test_nmg_launch.gd::test_flag_reads_true",
                "test_nmg_launch.gd::test_absent_option_returns_default",
                "test_nmg_launch.gd::test_autoplay_emits_once",
                "test_nmg_launch.gd::test_save_dir_with_test_saves",
                "test_nmg_launch.gd::test_save_dir_default"]
    if mode == "tests_missing_routing":
        required = required[:2]
    if mode == "tests_missing_launch":
        required = required[:3]
    for name in required:
        print(f"PASS {name}")
    print(f"{len(required)} passed, 0 failed")
    sys.exit(0)
if rest[:1] == ["--check-only"]:
    if mode == "check_error" and rest[2].endswith("probe_audio.gd"):
        print("SCRIPT ERROR: Parse Error: Unexpected identifier")
        sys.exit(1)
    sys.exit(0)
if rest[:1] == ["-s"] and not rest[1].endswith("probe_asset.gd"):
    name = rest[1].rsplit("/", 1)[-1]
    params = record["params"]
    if name == "probe_anims.gd":
        result = json.loads((project / "expected-anims.json").read_text())["result"]
        if mode == "anims_mismatch":
            result["clips"]["Wave"]["frame_count"] = 25
    elif name == "probe_terrain.gd" and params["mode"] == "scene":
        result = json.loads((project / "expected-terrain.json").read_text())["result"]
    elif name == "probe_terrain.gd":
        result = {"meshes": {glb: ["Crate"] for glb in params["glbs"]}}
    else:
        result = {"class": "AudioStreamWAV", "loop_mode": 0}
        if mode == "smoke_shape":
            result = {"class": "AudioStreamOggVorbis", "loop": False}
    print("NMG_RESULT " + json.dumps(result))
    sys.exit(0)
if rest[:1] == ["-s"]:
    if mode == "probe_none":
        print("Godot Engine v4")
        sys.exit(0)
    if mode == "probe_exit":
        sys.exit(1)
    result = json.loads(Path(os.environ["FAKE_EXPECTED"]).read_text())
    if mode == "probe_mismatch":
        result["meshes"][0]["tris"] = 11
    if mode == "probe_near":
        result["meshes"][0]["bounds"]["max"][0] = 0.5004
    if mode == "probe_far":
        result["meshes"][0]["bounds"]["max"][0] = 0.502
    print("NMG_RESULT " + json.dumps(result))
    sys.exit(0)
print("ERROR: unexpected command " + " ".join(rest))
sys.exit(1)
"""

_FAKE_CURL: Final = r"""
import json, os, sys
from pathlib import Path

args = sys.argv[1:]
with open(os.environ["FAKE_CURL_LOG"], "a") as log:
    log.write(json.dumps(args) + "\n")
if os.environ.get("FAKE_CURL_OFFLINE"):
    sys.stderr.write("curl: (6) Could not resolve host\n")
    sys.exit(6)
if "-o" in args:
    out = Path(args[args.index("-o") + 1])
    if out.name == "SHA512-SUMS.txt":
        import hashlib
        tag = os.environ.get("FAKE_TAG", "4.9-stable")
        digest = hashlib.sha512(b"PK fake zip").hexdigest()
        if os.environ.get("FAKE_BAD_SUM"):
            digest = "0" * 128
        suffixes = ("macos.universal", "linux.x86_64")
        lines = [f"{digest}  Godot_v{tag}_{suffix}.zip" for suffix in suffixes]
        out.write_text("\n".join(lines) + "\n")
    else:
        out.write_bytes(b"PK fake zip")
    sys.exit(0)
print(json.dumps({"tag_name": os.environ.get("FAKE_TAG", "4.9-stable")}))
"""

_FAKE_UNZIP: Final = r"""
import os, shutil, stat, sys
from pathlib import Path

args = sys.argv[1:]
dest = Path(args[args.index("-d") + 1])
zip_name = Path(args[args.index("-d") - 1]).name
tag = zip_name.removeprefix("Godot_v").split("_")[0]
if os.environ.get("FAKE_OS", "Darwin") == "Darwin":
    binary = dest / "Godot.app" / "Contents" / "MacOS" / "Godot"
else:
    binary = dest / f"Godot_v{tag}_linux.x86_64"
binary.parent.mkdir(parents=True, exist_ok=True)
shutil.copyfile(os.environ["FAKE_GODOT_SOURCE"], binary)
binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
"""


def _write_tool(path: Path, body: str) -> Path:
    """Write ``path`` as a sh wrapper running ``body`` with this Python (paths may hold spaces)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    source = path.parent / f".{path.name}.py"
    source.write_text(body, encoding="utf-8")
    path.write_text(
        f"#!/bin/sh\nFAKE_SELF=\"$0\" exec '{sys.executable}' '{source}' \"$@\"\n",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


@dataclass
class Gate:
    """A sandbox with fake tools; ``run`` executes the real gate script under it."""

    root: Path
    tools: Path
    path_godot: Path
    cache: Path
    env: dict[str, str]

    def run(self, **extra: str) -> subprocess.CompletedProcess[str]:
        env = {**self.env, **extra}
        return subprocess.run(
            [str(SCRIPT)],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def with_path_godot(self) -> dict[str, str]:
        return {"PATH": os.pathsep.join([str(self.path_godot.parent), self.env["PATH"]])}

    def godot_calls(self) -> list[dict[str, Any]]:
        log = Path(self.env["FAKE_GODOT_LOG"])
        if not log.is_file():
            return []
        return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]

    def curl_calls(self) -> list[list[str]]:
        log = Path(self.env["FAKE_CURL_LOG"])
        if not log.is_file():
            return []
        return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


@pytest.fixture
def gate(tmp_path: Path) -> Gate:
    tools = tmp_path / "tools"
    godot_source = _write_tool(tmp_path / "fake-godot-source" / "godot", _FAKE_GODOT)
    path_godot = _write_tool(tmp_path / "path-bin" / "godot", _FAKE_GODOT)
    _write_tool(tools / "curl", _FAKE_CURL)
    _write_tool(tools / "unzip", _FAKE_UNZIP)
    uname = tools / "uname"
    uname.write_text('#!/bin/sh\necho "${FAKE_OS:-Darwin}"\n', encoding="utf-8")
    uname.chmod(0o755)
    env = {
        "PATH": os.pathsep.join(
            [str(tools), str(Path(sys.executable).parent), "/usr/bin", "/bin", "/usr/sbin", "/sbin"]
        ),
        "HOME": str(tmp_path),
        "LANG": "C",
        "GODOT_CACHE_DIR": str(tmp_path / "cache"),
        "FAKE_GODOT_LOG": str(tmp_path / "godot.jsonl"),
        "FAKE_CURL_LOG": str(tmp_path / "curl.jsonl"),
        "FAKE_GODOT_SOURCE": str(godot_source),
        "FAKE_EXPECTED": str(FIXTURE / "expected-probe.json"),
    }
    return Gate(
        root=tmp_path, tools=tools, path_godot=path_godot, cache=tmp_path / "cache", env=env
    )


# Resolution order -------------------------------------------------------------------------------


def test_godot_bin_wins_over_path_and_download(gate: Gate) -> None:
    explicit = _write_tool(gate.root / "explicit" / "Godot", _FAKE_GODOT)
    result = gate.run(GODOT_BIN=str(explicit), **gate.with_path_godot())
    assert result.returncode == 0, result.stderr
    calls = gate.godot_calls()
    assert {call["self"] for call in calls} == {str(explicit)}
    assert gate.curl_calls() == []
    assert "gate-godot-headless: import, add-on tests, and probes passed" in result.stdout


def test_godot_bin_that_is_not_executable_exits_2(gate: Gate) -> None:
    missing = gate.root / "no-such-godot"
    result = gate.run(GODOT_BIN=str(missing), **gate.with_path_godot())
    assert result.returncode == 2
    assert "GODOT_BIN is not an executable file" in result.stderr
    assert "Remediation:" in result.stderr
    assert gate.godot_calls() == []


def test_godot_on_path_is_used_without_downloading(gate: Gate) -> None:
    result = gate.run(**gate.with_path_godot())
    assert result.returncode == 0, result.stderr
    assert {call["self"] for call in gate.godot_calls()} == {str(gate.path_godot)}
    assert gate.curl_calls() == []


def test_download_fetches_the_latest_macos_release_into_the_cache(gate: Gate) -> None:
    result = gate.run()
    assert result.returncode == 0, result.stderr
    binary = gate.cache / TAG / "Godot.app" / "Contents" / "MacOS" / "Godot"
    assert binary.is_file()
    curl = gate.curl_calls()
    assert "https://api.github.com/repos/godotengine/godot/releases/latest" in curl[0]
    assert (
        f"https://github.com/godotengine/godot/releases/download/{TAG}/"
        f"Godot_v{TAG}_macos.universal.zip"
    ) in curl[1]
    assert (
        f"https://github.com/godotengine/godot/releases/download/{TAG}/SHA512-SUMS.txt" in (curl[2])
    )
    assert {call["self"] for call in gate.godot_calls()} == {str(binary)}
    assert not list((gate.cache / TAG).glob("*.zip"))


def test_download_uses_the_linux_asset_on_linux(gate: Gate) -> None:
    result = gate.run(FAKE_OS="Linux")
    assert result.returncode == 0, result.stderr
    assert (gate.cache / TAG / f"Godot_v{TAG}_linux.x86_64").is_file()
    assert any(f"Godot_v{TAG}_linux.x86_64.zip" in arg for arg in gate.curl_calls()[1])


def test_a_cached_release_is_reused(gate: Gate) -> None:
    assert gate.run().returncode == 0
    first_downloads = len(gate.curl_calls())
    result = gate.run()
    assert result.returncode == 0, result.stderr
    later = gate.curl_calls()[first_downloads:]
    assert len(later) == 1
    assert "-o" not in later[0]


def test_offline_with_a_cached_release_uses_the_newest_copy(gate: Gate) -> None:
    assert gate.run().returncode == 0
    result = gate.run(FAKE_CURL_OFFLINE="1")
    assert result.returncode == 0, result.stderr
    assert "could not query the latest Godot release" in result.stderr


def test_offline_without_a_cache_exits_3(gate: Gate) -> None:
    result = gate.run(FAKE_CURL_OFFLINE="1")
    assert result.returncode == 3
    assert "could not query the latest Godot release" in result.stderr
    assert "Remediation:" in result.stderr
    assert gate.godot_calls() == []


def test_a_download_that_fails_its_checksum_exits_3_and_caches_nothing(gate: Gate) -> None:
    result = gate.run(FAKE_BAD_SUM="1")
    assert result.returncode == 3
    assert "does not match its SHA-512" in result.stderr
    assert gate.godot_calls() == []
    assert not (gate.cache / TAG).exists()
    assert [path.name for path in gate.cache.iterdir()] == []


def test_a_release_tag_that_is_not_a_stable_version_exits_3(gate: Gate) -> None:
    result = gate.run(FAKE_TAG="../../escape")
    assert result.returncode == 3
    assert "is not a stable version" in result.stderr
    assert gate.godot_calls() == []


def test_unsupported_os_exits_3(gate: Gate) -> None:
    result = gate.run(FAKE_OS="FreeBSD")
    assert result.returncode == 3
    assert "no Godot download for FreeBSD" in result.stderr


# Steps ------------------------------------------------------------------------------------------


def test_steps_run_import_then_addon_tests_then_probe(gate: Gate) -> None:
    result = gate.run(**gate.with_path_godot())
    assert result.returncode == 0, result.stderr
    calls = gate.godot_calls()
    commands = [call["argv"][call["argv"].index("--path") + 2 :] for call in calls]
    assert commands[0] == ["--import"]
    assert commands[1] == ["-s", "res://addons/nmg_game_dev/tests/run_tests.gd"]
    assert commands[2][:3] == ["-s", "res://.godot/nmg_probes/probe_asset.gd", "--"]
    assert calls[2]["params"] == {"glb": "res://Crate.glb"}
    assert calls[2]["probe_exists"] is True
    # Every probe script parses, then the anims, terrain, and audio probes smoke-run.
    probes = sorted(path.name for path in (REPO_ROOT / "src/nmg_game_dev/godot/gd").glob("*.gd"))
    checked = [command for command in commands if command[:1] == ["--check-only"]]
    assert checked == [["--check-only", "-s", f"res://.godot/nmg_probes/{name}"] for name in probes]
    smoke = [
        (call["argv"][call["argv"].index("-s") + 1].rsplit("/", 1)[-1], call["params"])
        for call in calls[3 + len(probes) :]
    ]
    expected_anims = json.loads((FIXTURE / "expected-anims.json").read_text(encoding="utf-8"))
    expected_terrain = json.loads((FIXTURE / "expected-terrain.json").read_text(encoding="utf-8"))
    assert smoke == [
        ("probe_anims.gd", expected_anims["params"]),
        ("probe_terrain.gd", expected_terrain["params"]),
        ("probe_terrain.gd", {"mode": "meshes", "glbs": ["res://Crate.glb"]}),
        ("probe_audio.gd", {"stream": "res://Beep.wav"}),
    ]
    for call in calls:
        assert call["argv"][:3] == ["--headless", "--audio-driver", "Dummy"]
    projects = {call["argv"][call["argv"].index("--path") + 1] for call in calls}
    (project,) = projects
    assert not Path(project).exists(), "the temp project should be removed"


@pytest.mark.parametrize("mode", ["import_error", "import_exit"])
def test_import_failure_exits_4(gate: Gate, mode: str) -> None:
    result = gate.run(FAKE_GODOT_MODE=mode, **gate.with_path_godot())
    assert result.returncode == 4
    assert "fixture import failed" in result.stderr
    assert len(gate.godot_calls()) == 1


@pytest.mark.parametrize(
    "mode",
    [
        "tests_fail",
        "tests_script_error",
        "tests_no_summary",
        "tests_missing_routing",
        "tests_missing_launch",
    ],
)
def test_addon_test_failure_exits_5(gate: Gate, mode: str) -> None:
    result = gate.run(FAKE_GODOT_MODE=mode, **gate.with_path_godot())
    assert result.returncode == 5
    assert "add-on tests failed" in result.stderr
    assert len(gate.godot_calls()) == 2


@pytest.mark.parametrize("mode", ["probe_none", "probe_exit"])
def test_probe_without_a_result_exits_6(gate: Gate, mode: str) -> None:
    result = gate.run(FAKE_GODOT_MODE=mode, **gate.with_path_godot())
    assert result.returncode == 6
    assert "NMG_RESULT" in result.stderr


@pytest.mark.parametrize("mode", ["probe_mismatch", "probe_far"])
def test_probe_mismatch_exits_7(gate: Gate, mode: str) -> None:
    result = gate.run(FAKE_GODOT_MODE=mode, **gate.with_path_godot())
    assert result.returncode == 7
    assert "differs from tests/godot/fixture/expected-probe.json" in result.stderr


def test_a_probe_that_fails_check_only_exits_8(gate: Gate) -> None:
    result = gate.run(FAKE_GODOT_MODE="check_error", **gate.with_path_godot())
    assert result.returncode == 8
    assert "probe_audio.gd failed --check-only" in result.stderr
    assert "Remediation:" in result.stderr


def test_a_smoke_probe_with_the_wrong_result_shape_exits_9(gate: Gate) -> None:
    result = gate.run(FAKE_GODOT_MODE="smoke_shape", **gate.with_path_godot())
    assert result.returncode == 9
    assert "probe_audio.gd smoke run failed" in result.stderr


def test_a_probe_result_that_differs_from_its_expected_file_exits_9(gate: Gate) -> None:
    result = gate.run(FAKE_GODOT_MODE="anims_mismatch", **gate.with_path_godot())
    assert result.returncode == 9
    assert "probe_anims.gd result differs from tests/godot/fixture/expected-anims.json" in (
        result.stderr
    )
    assert "result.clips.Wave.frame_count: 25 != 15" in result.stderr


def test_a_stalled_godot_fails_with_exit_10_after_the_timeout(gate: Gate) -> None:
    result = gate.run(FAKE_GODOT_MODE="hang", GODOT_GATE_TIMEOUT="1", **gate.with_path_godot())
    assert result.returncode == 10
    assert "the fixture import did not finish within 1 s" in result.stderr
    assert "quarantined" in result.stderr


def test_probe_floats_within_tolerance_pass(gate: Gate) -> None:
    result = gate.run(FAKE_GODOT_MODE="probe_near", **gate.with_path_godot())
    assert result.returncode == 0, result.stderr


# Add-on and fixture -----------------------------------------------------------------------------


def _config_value(text: str, key: str) -> str:
    match = re.search(rf'^{re.escape(key)}="([^"]*)"$', text, re.MULTILINE)
    assert match is not None, f"{key} missing"
    return match.group(1)


def test_plugin_cfg_version_matches_the_repo_version() -> None:
    text = (ADDON / "plugin.cfg").read_text(encoding="utf-8")
    version = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert _config_value(text, "version") == version
    assert _config_value(text, "name") == "nmg-game-dev"
    assert _config_value(text, "script") == "plugin.gd"


def test_addon_ships_the_designed_files() -> None:
    for rel in (
        "plugin.gd",
        "nmg_assets.gd",
        "nmg_launch.gd",
        "nmg_mission_definition.gd",
        "nmg_variant_scene.gd",
        "terrain/nmg_terrain.gdshader",
        "tests/run_tests.gd",
        "tests/nmg_log_capture.gd",
        "tests/test_nmg_assets.gd",
        "tests/test_nmg_launch.gd",
        "tests/test_mission_definition.gd",
        "tests/test_nmg_variant_scene.gd",
    ):
        assert (ADDON / rel).is_file(), rel
    plugin = (ADDON / "plugin.gd").read_text(encoding="utf-8")
    assert plugin.startswith("@tool\nextends EditorPlugin")
    assert "add_autoload_singleton(AUTOLOAD_NAME, AUTOLOAD_PATH)" in plugin
    assert "remove_autoload_singleton(AUTOLOAD_NAME)" in plugin
    assert "add_autoload_singleton(LAUNCH_AUTOLOAD_NAME, LAUNCH_AUTOLOAD_PATH)" in plugin
    assert "remove_autoload_singleton(LAUNCH_AUTOLOAD_NAME)" in plugin
    mission = (ADDON / "nmg_mission_definition.gd").read_text(encoding="utf-8")
    assert "class_name NmgMissionDefinition\nextends Resource" in mission
    for field in (
        "mission_name: String",
        "act: int",
        "region: StringName",
        "depends_on: Array[StringName]",
        "design_doc_path: String",
    ):
        assert f"@export var {field}" in mission


def test_gdscript_is_indented_with_tabs() -> None:
    for path in [*ADDON.rglob("*.gd"), *ADDON.rglob("*.gdshader")]:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            assert not line.startswith(" "), f"{path.name}:{number} is indented with spaces"


def test_probe_fixtures_are_the_generator_output() -> None:
    from tests.godot.make_probe_fixtures import files  # noqa: PLC0415

    stale = [str(path) for path, data in files().items() if path.read_bytes() != data]
    assert stale == [], "run uv run python -m tests.godot.make_probe_fixtures"


def test_probe_fixture_expectations_satisfy_the_python_readers(tmp_path: Path) -> None:
    """The results the gate requires from real Godot are the ones import_anims and import_godot
    accept: the slid clip measures frame_end - frame_start, and the terrain matches its sidecar."""
    from nmg_game_dev.godot.anims import ClipPlan, verify_clips  # noqa: PLC0415
    from nmg_game_dev.godot.terrain import check_probe  # noqa: PLC0415
    from tests.godot.make_probe_fixtures import TERRAIN_VARIANT  # noqa: PLC0415

    anims = json.loads((FIXTURE / "expected-anims.json").read_text(encoding="utf-8"))["result"]
    # Walk is authored from frame 0 to 24; Wave from frame 10 to 25 and exported slid to zero.
    plans = [
        ClipPlan("Walk", tmp_path / "A_Rig_Walk.glb", 24.0, 24 - 0),
        ClipPlan("Wave", tmp_path / "A_Rig_Wave.glb", 30.0, 25 - 10),
    ]
    assert verify_clips(plans, anims["clips"]) == {
        "Walk": ["Hip", "Spine"],
        "Wave": ["Hip", "Spine"],
    }
    # Left unslid, the same clip measures frame_end, so import_anims would reject it.
    unslid = [ClipPlan("WaveUnslid", tmp_path / "A_Rig_WaveUnslid.glb", 30.0, 25 - 10)]
    with pytest.raises(PipelineError) as caught:
        verify_clips(unslid, anims["clips"])
    assert caught.value.code == "import_anims.clip_mismatch"
    terrain = json.loads((FIXTURE / "expected-terrain.json").read_text(encoding="utf-8"))["result"]
    check_probe("Desktop", TERRAIN_VARIANT, terrain)


def test_crate_glb_is_the_generator_output() -> None:
    assert (FIXTURE / "Crate.glb").read_bytes() == build_crate_glb()


def test_crate_glb_holds_one_crate_cube() -> None:
    data = (FIXTURE / "Crate.glb").read_bytes()
    assert data[:4] == b"glTF"
    length = int.from_bytes(data[12:16], "little")
    doc = json.loads(data[20 : 20 + length])
    assert [node["name"] for node in doc["nodes"]] == ["Crate"]
    (primitive,) = doc["meshes"][0]["primitives"]
    assert primitive["material"] == 0
    assert len(doc["materials"]) == 1
    indices = doc["accessors"][primitive["indices"]]
    assert indices["count"] // 3 == 12
    position = doc["accessors"][primitive["attributes"]["POSITION"]]
    assert position["min"] == [-0.5, -0.5, -0.5]
    assert position["max"] == [0.5, 0.5, 0.5]


def test_expected_probe_matches_the_crate() -> None:
    expected = json.loads((FIXTURE / "expected-probe.json").read_text(encoding="utf-8"))
    assert expected == {
        "meshes": [
            {
                "name": "Crate",
                "tris": 12,
                "material_slots": 1,
                "bounds": {"min": [-0.5, -0.5, -0.5], "max": [0.5, 0.5, 0.5]},
            }
        ]
    }


def test_fixture_project_uses_the_compatibility_renderer_and_the_addon() -> None:
    text = (FIXTURE / "project.godot").read_text(encoding="utf-8")
    assert "config_version=5" in text
    assert 'renderer/rendering_method="gl_compatibility"' in text
    assert 'NmgAssets="*res://addons/nmg_game_dev/nmg_assets.gd"' in text
    assert 'NmgLaunch="*res://addons/nmg_game_dev/nmg_launch.gd"' in text
    assert 'enabled=PackedStringArray("res://addons/nmg_game_dev/plugin.cfg")' in text


def test_fixture_export_presets_match_the_rendered_presets() -> None:
    from nmg_game_dev.godot.presets import render_export_presets

    text = (FIXTURE / "export_presets.cfg").read_text(encoding="utf-8")
    assert text == render_export_presets("Fixture")


def test_cache_folder_is_git_ignored() -> None:
    lines = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".cache/godot/" in lines


def test_gate_is_registered_in_the_manifest() -> None:
    manifest = json.loads((REPO_ROOT / "steering" / "manifest.json").read_text(encoding="utf-8"))
    validations = {item["id"]: item for item in manifest["validations"]}
    gate = validations["gate-godot-headless"]
    assert gate["provider"] == "builtin.command"
    assert gate["config"]["program"] == "scripts/run-godot-tests.sh"
    assert gate["config"]["env"] == ["GODOT_BIN"]
    assert gate["when"]["include"] == [
        "plugins/nmg-game-dev-godot-addon/**",
        "src/nmg_game_dev/godot/**",
        "tests/godot/**",
        "scripts/run-godot-tests.sh",
    ]
    assert "gate-ue-compile" not in validations
    assert all(ext["id"] != "project.ue-compile" for ext in manifest["extensions"])
