"""Resolve ffmpeg and encode a stored WAV to Ogg Vorbis for music imports (#249 FR5).

Resolution order: ``FFMPEG_BIN`` (must be executable), then ``ffmpeg`` on ``PATH``. Otherwise
``audio.ffmpeg_not_found`` is raised, before the music import writes anything under ``game/``.
ffmpeg is never pinned. ``FfmpegRunner`` is the injectable seam; tests substitute a fake that
writes the output file itself.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Final, Protocol

from nmg_game_dev.audio.errors import AudioError
from nmg_game_dev.onboard.commands import CommandResult

NOT_FOUND_REMEDIATION: Final = "Install ffmpeg or set FFMPEG_BIN to its executable."
VORBIS_QUALITY: Final = "5"

Which = Callable[[str], str | None]

__all__ = [
    "NOT_FOUND_REMEDIATION",
    "FfmpegRunner",
    "SubprocessFfmpegRunner",
    "encode_ogg",
    "encode_ogg_args",
    "resolve_ffmpeg",
]


class FfmpegRunner(Protocol):
    """Runs one ffmpeg command line (the arguments after the executable)."""

    def run(self, args: Sequence[str]) -> CommandResult:
        """Run ``ffmpeg *args`` and return its outcome."""
        ...


class SubprocessFfmpegRunner:
    """Runs the real ffmpeg binary with stdin closed, so it never waits on a prompt."""

    def __init__(self, binary: Path) -> None:
        self.binary = binary

    def run(self, args: Sequence[str]) -> CommandResult:
        try:
            proc = subprocess.run(
                [str(self.binary), *args],
                capture_output=True,
                text=True,
                check=False,
                stdin=subprocess.DEVNULL,
            )
        except OSError as error:
            return CommandResult(returncode=127, stderr=str(error))
        return CommandResult(returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)


def _is_executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def resolve_ffmpeg(env: Mapping[str, str] | None = None, which: Which = shutil.which) -> Path:
    """Return the ffmpeg executable, or raise ``audio.ffmpeg_not_found`` with a remediation."""
    environ = os.environ if env is None else env
    tried: list[str] = []
    override = environ.get("FFMPEG_BIN", "")
    if override:
        if _is_executable(Path(override)):
            return Path(override)
        tried.append(f"FFMPEG_BIN={override}")
    on_path = which("ffmpeg")
    if on_path:
        return Path(on_path)
    tried.append("ffmpeg on PATH")
    raise AudioError(
        code="audio.ffmpeg_not_found",
        message=f"ffmpeg was not found. Tried: {', '.join(tried)}.",
        remediation=NOT_FOUND_REMEDIATION,
    )


def encode_ogg_args(wav: Path, out: Path) -> list[str]:
    """Return the ffmpeg arguments that encode ``wav`` to Ogg Vorbis at ``out``."""
    return ["-i", str(wav), "-c:a", "libvorbis", "-q:a", VORBIS_QUALITY, str(out)]


def encode_ogg(runner: FfmpegRunner, wav: Path, out: Path) -> None:
    """Encode ``wav`` to ``out``; raise ``audio.encode_failed`` when ffmpeg fails."""
    result = runner.run(encode_ogg_args(wav, out))
    if result.returncode != 0 or not out.is_file():
        lines = [line.strip() for line in result.stderr.splitlines() if line.strip()]
        detail = lines[-1] if lines else f"ffmpeg exited {result.returncode}"
        raise AudioError(
            code="audio.encode_failed",
            message=f"ffmpeg could not encode {wav.name} to Ogg Vorbis: {detail}",
            remediation="Check that your ffmpeg build includes libvorbis (`ffmpeg -encoders`), "
            "then import the sound again. The stored WAV is kept.",
        )
