"""Headless Blender runner for finalize steps (#69).

Every Blender step runs in its own ``blender --background`` process, so a crash loses only that step
and never touches the open session.  The process writes ``<job_dir>/<step>.json``, the envelope that
``steps.envelope_outputs`` reads, and for mutating steps ``<job_dir>/<step>.blend``.  It prints
``NMG_PROGRESS {json}`` lines, which are forwarded to the caller.  Its full output goes to
``<job_dir>/blender-<step>.log``.  A process that exits without writing its envelope is a crash.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Final, Protocol

from .errors import PipelineError

ProgressCallback = Callable[[dict[str, Any]], None]

REPO_ROOT: Final = Path(__file__).resolve().parents[3]
ENTRY_SCRIPT: Final = REPO_ROOT / "scripts" / "blender" / "finalize_entry.py"
DEFAULT_BLENDER_APP: Final = Path("/Applications/Blender.app")
_BINARY_RELATIVE: Final = Path("Contents") / "MacOS" / "Blender"
_PROGRESS_PREFIX: Final = "NMG_PROGRESS "


class StepRunner(Protocol):
    """Runs Blender steps and content hashing.  Tests substitute an in-process fake."""

    def run_step(
        self,
        step: str,
        *,
        job_dir: Path,
        in_blend: Path | None,
        inputs: Mapping[str, Any] | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """Run one step and return its envelope."""
        ...

    def hash(self, *, job_dir: Path, in_blend: Path) -> str:
        """Return ``finalize_core.content_hash`` for the collection in ``in_blend``."""
        ...


def resolve_blender() -> Path:
    """Return the Blender executable.

    Resolution order: ``BLENDER_BIN``, then ``BLENDER_APP/Contents/MacOS/Blender``, then the
    documented ``/Applications/Blender.app`` default.  Raises ``finalize.blender_not_found``.
    """
    tried: list[str] = []
    override = os.environ.get("BLENDER_BIN", "")
    if override:
        if _is_executable(Path(override)):
            return Path(override)
        tried.append(f"BLENDER_BIN={override}")

    candidates: list[Path] = []
    app = os.environ.get("BLENDER_APP", "")
    if app:
        candidates.append(Path(app) / _BINARY_RELATIVE)
    candidates.append(DEFAULT_BLENDER_APP / _BINARY_RELATIVE)
    for candidate in candidates:
        if _is_executable(candidate):
            return candidate
        tried.append(str(candidate))

    raise PipelineError(
        code="finalize.blender_not_found",
        message=f"Blender was not found. Tried: {', '.join(tried)}.",
        remediation="Set BLENDER_BIN to the Blender executable, or BLENDER_APP to the Blender.app "
        "bundle, then rerun.",
        stage="finalize",
    )


class SubprocessStepRunner:
    """Runs each step in a headless Blender process.

    Parameters:
        blender: Explicit executable.  ``None`` resolves it from the environment on first use.
    """

    def __init__(self, blender: Path | None = None) -> None:
        self._blender = blender

    def _binary(self) -> Path:
        if self._blender is None:
            self._blender = resolve_blender()
        return self._blender

    def run_step(
        self,
        step: str,
        *,
        job_dir: Path,
        in_blend: Path | None,
        inputs: Mapping[str, Any] | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """Run ``step`` headless and return its envelope.  Raises ``finalize.job_crashed``."""
        envelope_path = job_dir / f"{step}.json"
        envelope_path.unlink(missing_ok=True)

        args = [step, "--job-dir", str(job_dir)]
        if inputs is not None:
            inputs_path = job_dir / f"{step}.inputs.json"
            inputs_path.write_text(json.dumps(inputs, indent=2, sort_keys=True), encoding="utf-8")
            args += ["--inputs", str(inputs_path)]

        command = [str(self._binary()), "--background"]
        if step == "reimport":
            command.append("--factory-startup")
        if in_blend is not None:
            command.append(str(in_blend))
        command += ["--python", str(ENTRY_SCRIPT), "--", *args]

        log_path = job_dir / f"blender-{step}.log"
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            assert process.stdout is not None
            for line in process.stdout:
                log.write(line)
                event = _progress_event(line)
                if event is not None and on_progress is not None:
                    on_progress(event)
            exit_code = process.wait()

        if not envelope_path.is_file():
            raise PipelineError(
                code="finalize.job_crashed",
                message=f"The Blender {step} step exited with code {exit_code} before writing "
                "its result",
                remediation=f"Read {log_path} for the Blender output, then rerun the step.",
                stage=step,
            )
        loaded: dict[str, Any] = json.loads(envelope_path.read_text(encoding="utf-8"))
        return loaded

    def hash(self, *, job_dir: Path, in_blend: Path) -> str:
        """Return the collection content hash for ``in_blend``, computed headless."""
        hash_path = job_dir / "hash.json"
        hash_path.unlink(missing_ok=True)
        command = [
            str(self._binary()),
            "--background",
            str(in_blend),
            "--python",
            str(ENTRY_SCRIPT),
            "--",
            "hash",
            "--job-dir",
            str(job_dir),
        ]
        log_path = job_dir / "blender-hash.log"
        with log_path.open("w", encoding="utf-8") as log:
            exit_code = subprocess.run(
                command, stdout=log, stderr=subprocess.STDOUT, check=False
            ).returncode
        if not hash_path.is_file():
            raise PipelineError(
                code="finalize.job_crashed",
                message=f"The Blender hash pass exited with code {exit_code} before writing "
                "its result",
                remediation=f"Read {log_path} for the Blender output, then rerun.",
                stage="finalize",
            )
        data = json.loads(hash_path.read_text(encoding="utf-8"))
        error = data.get("error") if isinstance(data, dict) else None
        if isinstance(error, dict):
            raise PipelineError(
                code=str(error.get("code", "finalize.hash_failed")),
                message=str(error.get("message", "The content hash failed")),
                remediation=str(error.get("remediation", f"Read {log_path} and rerun.")),
                stage="finalize",
            )
        value = data.get("hash") if isinstance(data, dict) else None
        if not isinstance(value, str) or not value:
            raise PipelineError(
                code="finalize.bad_envelope",
                message="The Blender hash pass wrote no hash",
                remediation=f"Read {log_path} and rerun.",
                stage="finalize",
            )
        return value


def _progress_event(line: str) -> dict[str, Any] | None:
    if not line.startswith(_PROGRESS_PREFIX):
        return None
    try:
        event = json.loads(line[len(_PROGRESS_PREFIX) :])
    except json.JSONDecodeError:
        return None
    return event if isinstance(event, dict) else None


def _is_executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)
