"""Injectable process, host, and disk seams for onboarding (#7 FR1, FR2).

Production code uses the defaults here (``subprocess``, ``shutil.which``, ``platform``,
``shutil.disk_usage``). Tests pass their own callables, so no real ``git``, ``mflux-save``, or
``uv`` runs and no real volume is probed.
"""

from __future__ import annotations

import os
import platform
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CommandResult:
    """The outcome of one external command."""

    returncode: int
    stdout: str = ""
    stderr: str = ""


Runner = Callable[[Sequence[str], Mapping[str, str] | None], CommandResult]
Which = Callable[[str], str | None]
FreeBytes = Callable[[Path], int]


@dataclass(frozen=True)
class HostFacts:
    """The host's OS name and CPU architecture, as ``platform`` reports them."""

    system: str
    machine: str


def default_run(argv: Sequence[str], env: Mapping[str, str] | None = None) -> CommandResult:
    """Run ``argv`` with ``env`` merged over the environment. A missing program returns code 127."""
    merged = None if env is None else {**os.environ, **env}
    try:
        proc = subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            check=False,
            env=merged,
        )
    except OSError as error:
        return CommandResult(returncode=127, stderr=str(error))
    return CommandResult(returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)


def default_host() -> HostFacts:
    return HostFacts(system=platform.system(), machine=platform.machine())
