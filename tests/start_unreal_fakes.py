"""Fakes for the start-unreal-mcp.sh plugin-build tests (#103, #150).

Each sandbox is a temporary consumer project with one source-only plugin, ``Plugins/Fake``, plus a
fake ``UE_ROOT``. The fake UnrealEditor and Build.sh append one tab-separated line per invocation to
a shared event log, so a test can check what ran, with which argv, and in what order. The fake
editor exits at once, and the launcher only checks the port, so nothing real is built or started.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = REPO_ROOT / "scripts" / "start-unreal-mcp.sh"
BUILD_LOG = Path("/tmp/unreal-mcp-build.log")
MODULE = "FakeEditor"
SECOND_MODULE = "FakeExtras"

# Ages in seconds before the test runs. A "current" binary is newer than the first module's sources,
# a "stale" one older. The second module's sources are newer than the first module's binary, and its
# binary is newer than its sources (#150 AC4).
SOURCE_AGE_SECONDS = 100
CURRENT_BINARY_AGE_SECONDS = 50
STALE_BINARY_AGE_SECONDS = 200
SECOND_SOURCE_AGE_SECONDS = 20
SECOND_BINARY_AGE_SECONDS = 10
ENGINE_INI_AGE_SECONDS = 0

# Build.sh body that compiles nothing: the fake build exits 0 with no output.
BUILD_OK = "exit 0"
# Build.sh bodies that fail as UnrealBuildTool does on UE 5.8 with an invalid action graph (#150): a
# Result line with no error: line, optionally after UBT's planning message.
BUILD_ACTION_GRAPH_INVALID = 'printf "Result: Failed (ActionGraphInvalid)\\n"\nexit 9'
BUILD_ACTION_GRAPH_REASON = (
    'printf "Action graph is invalid; unable to continue\\n"\n'
    'printf "Result: Failed (ActionGraphInvalid)\\n"\nexit 9'
)


@dataclass
class Sandbox:
    """Paths of one temporary project and fake engine install."""

    project: Path
    uproject: Path
    ue_root: Path
    events: Path

    @property
    def build_sh(self) -> Path:
        return self.ue_root / "Engine" / "Build" / "BatchFiles" / "Mac" / "Build.sh"

    def module_dylib(self, module: str) -> Path:
        """The UE 5.8 editor dylib of ``module`` in the Fake plugin."""
        return (
            self.project
            / "Plugins"
            / "Fake"
            / "Binaries"
            / "Mac"
            / f"libUnrealEditor-{module}.dylib"
        )

    @property
    def dylib(self) -> Path:
        return self.module_dylib(MODULE)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
    return port


def _executable(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)


def _record(tag: str) -> str:
    """Shell line that appends ``tag`` and the argv, tab-separated, to $FAKE_UE_EVENTS."""
    return f"{{ printf '{tag}'; printf '\\t%s' \"$@\"; printf '\\n'; }} >>\"$FAKE_UE_EVENTS\"\n"


def write_build_sh(sandbox: Sandbox, body: str = BUILD_OK) -> None:
    """(Re)write the fake Build.sh with ``body`` after its argv record."""
    _executable(sandbox.build_sh, "#!/usr/bin/env bash\n" + _record("build") + body + "\n")


def _write_text(path: Path, text: str = "// fake\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _age(path: Path, seconds: float) -> None:
    """Set ``path``'s mtime to ``seconds`` before now."""
    when = time.time() - seconds
    os.utime(path, (when, when))


def _age_tree(root: Path, seconds: float) -> None:
    """Age ``root``, its directories and its files alike.

    The launcher's ``find -newer`` also sees directory mtimes, so a directory created just now would
    otherwise look newer than every binary.
    """
    _age(root, seconds)
    for path in root.rglob("*"):
        _age(path, seconds)


def make_sandbox(
    tmp_path: Path,
    *,
    dylib: str = "missing",
    build_sh: bool = True,
    build_body: str = BUILD_OK,
    code_project: bool = False,
    second_module: bool = False,
    engine_ini_newer: bool = False,
) -> Sandbox:
    """Build a project whose plugin Fake has one editor module, ``MODULE``.

    ``dylib`` sets that module's binary: ``"missing"`` writes none, ``"current"`` writes a binary
    newer than its sources (the launcher must skip the build), and ``"stale"`` writes one older than
    them. ``build_sh=False`` leaves the engine without Build.sh. ``code_project=True`` adds the
    project's own ``<Project>Editor.Target.cs``. ``second_module=True`` adds ``SECOND_MODULE`` with
    its own ``<Module>.Build.cs``, a current binary, and sources newer than ``MODULE``'s binary. The
    engine ``Config/DefaultEngine.ini`` is written newer than every binary when
    ``engine_ini_newer=True``.
    """
    project = tmp_path / "Game"
    plugin = project / "Plugins" / "Fake"
    uplugin = plugin / "Fake.uplugin"
    source = plugin / "Source" / "Fake.cpp"
    uproject = project / "Game.uproject"
    modules = [{"Name": MODULE, "Type": "Editor"}]
    if second_module:
        modules.append({"Name": SECOND_MODULE, "Type": "Editor"})
    _write_text(
        uproject,
        json.dumps(
            {
                "FileVersion": 3,
                "EngineAssociation": "5.8",
                "Plugins": [{"Name": "Fake", "Enabled": True}],
            }
        ),
    )
    _write_text(uplugin, json.dumps({"FileVersion": 3, "Modules": modules}))
    _write_text(source)
    if code_project:
        _write_text(project / "Source" / f"{uproject.stem}Editor.Target.cs")
    if second_module:
        for module in (MODULE, SECOND_MODULE):
            _write_text(plugin / "Source" / module / f"{module}.Build.cs")
            _write_text(plugin / "Source" / module / f"{module}.cpp")
    _age_tree(plugin / "Source", SOURCE_AGE_SECONDS)
    _age(uplugin, SOURCE_AGE_SECONDS)
    if second_module:
        _age_tree(plugin / "Source" / SECOND_MODULE, SECOND_SOURCE_AGE_SECONDS)

    sandbox = Sandbox(
        project=project,
        uproject=uproject,
        ue_root=tmp_path / "UE_5.8",
        events=tmp_path / "events.txt",
    )
    editor = (
        sandbox.ue_root / "Engine" / "Binaries" / "Mac" / "UnrealEditor.app" / "Contents" / "MacOS"
    )
    _executable(editor / "UnrealEditor", "#!/usr/bin/env bash\n" + _record("editor") + "exit 0\n")
    if build_sh:
        write_build_sh(sandbox, build_body)

    if second_module:
        _write_text(sandbox.module_dylib(SECOND_MODULE), "")
        _age(sandbox.module_dylib(SECOND_MODULE), SECOND_BINARY_AGE_SECONDS)
    if dylib != "missing":
        _write_text(sandbox.dylib, "")
        _age(
            sandbox.dylib,
            STALE_BINARY_AGE_SECONDS if dylib == "stale" else CURRENT_BINARY_AGE_SECONDS,
        )
    if engine_ini_newer:
        ini = project / "Config" / "DefaultEngine.ini"
        _write_text(ini, "[/Script/EngineSettings.GameMapsSettings]\n")
        _age(ini, ENGINE_INI_AGE_SECONDS)
    return sandbox


def run_launcher(sandbox: Sandbox, port: int | None = None) -> subprocess.CompletedProcess[str]:
    """Run the launcher against the sandbox, returning as soon as it exits."""
    env = {
        **os.environ,
        "UE_ROOT": str(sandbox.ue_root),
        "UE_PROJECT": str(sandbox.uproject),
        "UE_MCP_PORT": str(port if port is not None else free_port()),
        "FAKE_UE_EVENTS": str(sandbox.events),
    }
    return subprocess.run(
        ["bash", str(LAUNCHER)], capture_output=True, text=True, env=env, timeout=30, check=False
    )


def read_events(events: Path) -> list[list[str]]:
    """Each fake invocation so far, as ``[tag, *argv]``."""
    if not events.is_file():
        return []
    return [line.split("\t") for line in events.read_text(encoding="utf-8").splitlines() if line]


def wait_for_editor(events: Path, timeout: float = 15.0) -> list[list[str]]:
    """Wait for the detached fake editor to record its launch, then return every event.

    The deadline only bounds this positive wait, so a slow loaded machine can start the detached
    fake late without failing the test. Negative checks never wait.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        found = read_events(events)
        if any(event[0] == "editor" for event in found):
            return found
        time.sleep(0.05)
    raise AssertionError(f"fake UnrealEditor never recorded a launch in {events}")


def expected_build_argv(sandbox: Sandbox) -> list[str]:
    """The single-target Build.sh argv: no positional target name (#150 FR1)."""
    return [
        "build",
        "Mac",
        "Development",
        f"-Project={sandbox.uproject}",
        "-TargetType=Editor",
        "-NoEngineChanges",
    ]
