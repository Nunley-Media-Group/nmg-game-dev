"""Sequential backend batches: one worker process per backend, never two at once (#7 FR14).

``run_backend_batches`` writes each batch file, runs the worker through the injected ``spawn``, and
waits for it to exit before the next backend starts. Tests inject a ``spawn`` that runs a fake
worker script and records timestamps.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nmg_game_dev.texture.errors import TextureGenError
from nmg_game_dev.texture.registry import BackendSpec

Spawn = Callable[[Path], "subprocess.CompletedProcess[str]"]
TAIL_LINES = 12


@dataclass(frozen=True)
class ImageItem:
    """One image to generate: its position in the batch, prompt, seed, size, and output path."""

    index: int
    prompt: str
    seed: int
    resolution: int
    path: Path


@dataclass(frozen=True)
class Batch:
    """All images for one backend, run in one worker process that loads the model once."""

    spec: BackendSpec
    weights: Path
    items: tuple[ImageItem, ...]
    batch_file: Path

    def as_json(self) -> dict[str, Any]:
        return {
            "backend": self.spec.id,
            "mflux_entry": self.spec.mflux_entry,
            "weights": str(self.weights),
            "steps": self.spec.default_steps,
            "items": [
                {
                    "index": item.index,
                    "prompt": item.prompt,
                    "seed": item.seed,
                    "resolution": item.resolution,
                    "path": str(item.path),
                }
                for item in self.items
            ],
        }


@dataclass(frozen=True)
class ImageTiming:
    """What the worker reported for one finished image."""

    index: int
    path: Path
    seconds: float


def default_spawn(batch_file: Path) -> subprocess.CompletedProcess[str]:
    """Run the real worker for ``batch_file`` in a child process and wait for it to exit."""
    return subprocess.run(
        [sys.executable, "-m", "nmg_game_dev.texture.worker", str(batch_file)],
        capture_output=True,
        text=True,
        check=False,
    )


def _parse_timings(stdout: str) -> list[ImageTiming]:
    timings: list[ImageTiming] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        record = json.loads(line)
        timings.append(
            ImageTiming(
                index=int(record["index"]),
                path=Path(str(record["path"])),
                seconds=float(record["seconds"]),
            )
        )
    return timings


def run_backend_batches(
    batches: Sequence[Batch],
    spawn: Spawn = default_spawn,
    on_batch_done: Callable[[Batch], None] | None = None,
) -> dict[str, list[ImageTiming]]:
    """Run each batch in order and return the per-image timings keyed by backend id.

    A non-zero worker exit raises ``texture.worker_failed`` with the tail of the worker's stderr.
    """
    results: dict[str, list[ImageTiming]] = {}
    for batch in batches:
        batch.batch_file.parent.mkdir(parents=True, exist_ok=True)
        batch.batch_file.write_text(json.dumps(batch.as_json(), indent=2), encoding="utf-8")
        proc = spawn(batch.batch_file)
        if proc.returncode != 0:
            tail = "\n".join((proc.stderr or "").strip().splitlines()[-TAIL_LINES:])
            raise TextureGenError(
                "texture.worker_failed",
                f"The {batch.spec.id} worker exited with code {proc.returncode}.",
                "Check that the models are installed and that the Blender reserve leaves enough "
                f"memory, then rerun. Worker stderr tail:\n{tail}",
            )
        results[batch.spec.id] = _parse_timings(proc.stdout or "")
        if on_batch_done is not None:
            on_batch_done(batch)
    return results
