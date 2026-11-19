"""Run ``godot --headless`` through an injectable runner (#249 FR1).

``SubprocessGodotRunner`` runs the real binary; tests substitute
``tests/godot_fakes.FakeGodotRunner``.
``import_project`` runs the editor import pass, and ``run_probe`` runs one GDScript probe from
``godot/gd/`` and returns the JSON it prints on its ``NMG_RESULT`` line.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, Protocol

from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.process import CommandResult

from .result import parse_nmg_result

GD_DIR: Final = Path(__file__).resolve().parent / "gd"
PROBE_DIR: Final = Path(".godot") / "nmg_probes"
"""Probes are copied under the project's ``.godot/`` so ``-s`` loads them as ``res://`` scripts."""

IMPORT_REMEDIATION: Final = (
    "Open the project in Godot or read the import output, fix the reported resource, then rerun."
)
TIMEOUT_EXIT: Final = 124
"""``SubprocessGodotRunner`` returns this exit code when Godot ran past its timeout."""
DEFAULT_TIMEOUT_S: Final = 900.0
"""Every headless Godot run is bounded, so a stalled Godot fails instead of hanging a job."""
TIMEOUT_ENV: Final = "NMG_GODOT_TIMEOUT_S"
TIMEOUT_REMEDIATION: Final = (
    "Check that Godot starts headless on this host (run `godot --headless --version`; on macOS, "
    f"clear a quarantine on Godot.app), or raise {TIMEOUT_ENV}, then rerun."
)

__all__ = [
    "GD_DIR",
    "DEFAULT_TIMEOUT_S",
    "TIMEOUT_EXIT",
    "CommandResult",
    "GodotRunner",
    "SubprocessGodotRunner",
    "import_project",
    "run_probe",
]


class GodotRunner(Protocol):
    """Runs one headless Godot command against a project directory."""

    def run(
        self,
        args: Sequence[str],
        *,
        project: Path,
        timeout: float | None = None,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        """Run ``godot --headless --path <project> *args`` and return its outcome."""
        ...


def default_timeout(env: Mapping[str, str] | None = None) -> float:
    """Return ``NMG_GODOT_TIMEOUT_S`` when it is a positive number, else ``DEFAULT_TIMEOUT_S``."""
    raw = (os.environ if env is None else env).get(TIMEOUT_ENV, "")
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_TIMEOUT_S
    return value if value > 0 else DEFAULT_TIMEOUT_S


class SubprocessGodotRunner:
    """Runs the real Godot binary with the dummy audio driver, headless unless ``headless`` is off.

    A windowed run (``headless=False``, used by the game screenshot) omits ``--headless`` and keeps
    the rest of the argv. A run with no explicit ``timeout`` is bounded by ``default_timeout``
    (``NMG_GODOT_TIMEOUT_S``, else ``DEFAULT_TIMEOUT_S``); past it the process is killed and the
    result has exit code 124.
    """

    def __init__(
        self, binary: Path, *, timeout: float | None = None, headless: bool = True
    ) -> None:
        self.binary = binary
        self.timeout = default_timeout() if timeout is None else timeout
        self.headless = headless

    def argv(self, args: Sequence[str], *, project: Path) -> list[str]:
        return [
            str(self.binary),
            *(["--headless"] if self.headless else []),
            "--audio-driver",
            "Dummy",
            "--path",
            str(project),
            *args,
        ]

    def run(
        self,
        args: Sequence[str],
        *,
        project: Path,
        timeout: float | None = None,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        merged = None if env is None else {**os.environ, **env}
        try:
            proc = subprocess.run(
                self.argv(args, project=project),
                capture_output=True,
                text=True,
                check=False,
                timeout=self.timeout if timeout is None else timeout,
                env=merged,
            )
        except subprocess.TimeoutExpired as error:
            return CommandResult(
                returncode=TIMEOUT_EXIT,
                stderr=f"Godot did not finish within {error.timeout:g} s and was stopped",
            )
        except OSError as error:
            return CommandResult(returncode=127, stderr=str(error))
        return CommandResult(returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)


def _error_lines(result: CommandResult) -> list[str]:
    lines = f"{result.stdout}\n{result.stderr}".splitlines()
    return [line.strip() for line in lines if line.strip().startswith("ERROR:")]


def _failure(result: CommandResult, fallback: str, remediation: str) -> tuple[str, str]:
    """Return the detail and remediation for a failed run.

    The first ``ERROR:`` line wins. A timeout reports the runner's timeout text with
    ``TIMEOUT_REMEDIATION``; otherwise ``fallback`` names the exit code.
    """
    errors = _error_lines(result)
    if errors:
        return errors[0], remediation
    if result.returncode == TIMEOUT_EXIT:
        text = result.stderr.strip().splitlines()
        return (text[-1] if text else f"Godot timed out (exit {TIMEOUT_EXIT})"), TIMEOUT_REMEDIATION
    return fallback, remediation


def import_project(
    runner: GodotRunner,
    project: Path,
    *,
    error_code: str = "import_godot.import_failed",
    timeout: float | None = None,
) -> CommandResult:
    """Run ``--import``; a non-zero exit or any ``ERROR:`` line raises ``error_code``."""
    result = runner.run(["--import"], project=project, timeout=timeout)
    if result.returncode != 0 or _error_lines(result):
        detail, remediation = _failure(
            result, f"godot --import exited {result.returncode}", IMPORT_REMEDIATION
        )
        raise PipelineError(
            code=error_code,
            message=f"Godot import failed for {project}: {detail}",
            remediation=remediation,
            stage=error_code.split(".", 1)[0],
        )
    return result


def run_probe(
    runner: GodotRunner,
    project: Path,
    script: str | Path,
    params: Mapping[str, Any],
    *,
    error_code: str,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Run one GDScript probe and return its ``NMG_RESULT`` payload.

    ``script`` is a probe file name in ``godot/gd/`` or a path to a ``.gd`` file. It is copied to
    ``<project>/.godot/nmg_probes/`` beside a uniquely named temporary params JSON file whose
    absolute path follows ``--``; the params file is removed when the probe returns.
    """
    source = Path(script)
    if not source.is_absolute():
        source = GD_DIR / source
    probe_dir = project / PROBE_DIR
    probe_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, probe_dir / source.name)
    descriptor, temp = tempfile.mkstemp(
        prefix=f"{source.stem}.", suffix=".params.json", dir=probe_dir
    )
    params_path = Path(temp)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(dict(params), sort_keys=True))
        res_script = f"res://{PROBE_DIR.as_posix()}/{source.name}"
        result = runner.run(
            ["-s", res_script, "--", str(params_path.resolve())],
            project=project,
            timeout=timeout,
        )
    finally:
        params_path.unlink(missing_ok=True)
    if result.returncode != 0:
        detail, remediation = _failure(
            result,
            f"exit code {result.returncode}",
            "Read the Godot output, fix the reported problem, then rerun.",
        )
        raise PipelineError(
            code=error_code,
            message=f"Godot probe {source.name} failed: {detail}",
            remediation=remediation,
            stage=error_code.split(".", 1)[0],
        )
    return parse_nmg_result(result.stdout, error_code=error_code)
