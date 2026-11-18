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

__all__ = [
    "GD_DIR",
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


class SubprocessGodotRunner:
    """Runs the real Godot binary headless, with the dummy audio driver."""

    def __init__(self, binary: Path) -> None:
        self.binary = binary

    def argv(self, args: Sequence[str], *, project: Path) -> list[str]:
        return [
            str(self.binary),
            "--headless",
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
                timeout=timeout,
                env=merged,
            )
        except subprocess.TimeoutExpired as error:
            return CommandResult(returncode=124, stderr=f"Godot timed out after {error.timeout}s")
        except OSError as error:
            return CommandResult(returncode=127, stderr=str(error))
        return CommandResult(returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)


def _error_lines(result: CommandResult) -> list[str]:
    lines = f"{result.stdout}\n{result.stderr}".splitlines()
    return [line.strip() for line in lines if line.strip().startswith("ERROR:")]


def import_project(
    runner: GodotRunner,
    project: Path,
    *,
    error_code: str = "import_godot.import_failed",
    timeout: float | None = None,
) -> CommandResult:
    """Run ``--import``; a non-zero exit or any ``ERROR:`` line raises ``error_code``."""
    result = runner.run(["--import"], project=project, timeout=timeout)
    errors = _error_lines(result)
    if result.returncode != 0 or errors:
        detail = errors[0] if errors else f"godot --import exited {result.returncode}"
        raise PipelineError(
            code=error_code,
            message=f"Godot import failed for {project}: {detail}",
            remediation=IMPORT_REMEDIATION,
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
    ``<project>/.godot/nmg_probes/`` beside a params JSON file whose absolute path follows ``--``.
    """
    source = Path(script)
    if not source.is_absolute():
        source = GD_DIR / source
    probe_dir = project / PROBE_DIR
    probe_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, probe_dir / source.name)
    params_path = probe_dir / f"{source.stem}.params.json"
    params_path.write_text(json.dumps(dict(params), sort_keys=True), encoding="utf-8")
    res_script = f"res://{PROBE_DIR.as_posix()}/{source.name}"
    result = runner.run(
        ["-s", res_script, "--", str(params_path.resolve())],
        project=project,
        timeout=timeout,
    )
    if result.returncode != 0:
        errors = _error_lines(result)
        detail = errors[0] if errors else f"exit code {result.returncode}"
        raise PipelineError(
            code=error_code,
            message=f"Godot probe {source.name} failed: {detail}",
            remediation="Read the Godot output, fix the reported problem, then rerun.",
            stage=error_code.split(".", 1)[0],
        )
    return parse_nmg_result(result.stdout, error_code=error_code)
