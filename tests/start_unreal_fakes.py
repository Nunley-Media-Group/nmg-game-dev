"""Fakes for the start-unreal-mcp.sh plugin-build tests (#103).

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
SOURCE_AGE_SECONDS = 100

# Build.sh body that compiles nothing: the fake build exits 0 with no output.
BUILD_OK = "exit 0"


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

    @property
    def dylib(self) -> Path:
        return (
            self.project / "Plugins" / "Fake" / "Binaries" / "Mac" / f"UnrealEditor-{MODULE}.dylib"
        )


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


def make_sandbox(
    tmp_path: Path,
    *,
    dylib: str = "missing",
    build_sh: bool = True,
    build_body: str = BUILD_OK,
) -> Sandbox:
    """Build a project whose plugin Fake needs a build unless ``dylib`` is ``"current"``.

    ``dylib="current"`` writes the editor dylib with a newer mtime than the plugin sources, so the
    launcher must skip the build. ``build_sh=False`` leaves the engine without Build.sh.
    """
    project = tmp_path / "Game"
    uplugin = project / "Plugins" / "Fake" / "Fake.uplugin"
    source = project / "Plugins" / "Fake" / "Source" / "Fake.cpp"
    uproject = project / "Game.uproject"
    uproject.parent.mkdir(parents=True, exist_ok=True)
    uproject.write_text(
        json.dumps(
            {
                "FileVersion": 3,
                "EngineAssociation": "5.8",
                "Plugins": [{"Name": "Fake", "Enabled": True}],
            }
        ),
        encoding="utf-8",
    )
    uplugin.parent.mkdir(parents=True, exist_ok=True)
    uplugin.write_text(
        json.dumps({"FileVersion": 3, "Modules": [{"Name": MODULE, "Type": "Editor"}]}),
        encoding="utf-8",
    )
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("// fake\n", encoding="utf-8")

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

    old = time.time() - SOURCE_AGE_SECONDS
    os.utime(uplugin, (old, old))
    os.utime(source, (old, old))
    if dylib == "current":
        sandbox.dylib.parent.mkdir(parents=True, exist_ok=True)
        sandbox.dylib.write_bytes(b"")
        now = time.time()
        os.utime(sandbox.dylib, (now, now))
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


def wait_for_editor(events: Path, timeout: float = 5.0) -> list[list[str]]:
    """Wait for the detached fake editor to record its launch, then return every event."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        found = read_events(events)
        if any(event[0] == "editor" for event in found):
            return found
        time.sleep(0.05)
    raise AssertionError(f"fake UnrealEditor never recorded a launch in {events}")


def expected_build_argv(sandbox: Sandbox) -> list[str]:
    return [
        "build",
        "UnrealEditor",
        "Mac",
        "Development",
        f"-Project={sandbox.uproject}",
        "-TargetType=Editor",
        "-NoEngineChanges",
    ]
