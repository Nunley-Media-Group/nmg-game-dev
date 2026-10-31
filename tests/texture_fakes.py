"""Shared fakes for the #7 texture tests: a fake worker process, synthetic images, and model
folders.

The fake worker is a real child process: it reads the batch file the package writes, logs when it
starts and exits, and writes synthetic PNGs. Tests therefore check real process timing, not mocks.
No test here loads an mflux model.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image as PILImage

from nmg_game_dev.texture.hardware import HardwareFacts

APPLE_SILICON_32GB = HardwareFacts(system="Darwin", machine="arm64", total_ram_gb=32.0)
APPLE_SILICON_16GB = HardwareFacts(system="Darwin", machine="arm64", total_ram_gb=16.0)
INTEL_LINUX = HardwareFacts(system="Linux", machine="x86_64", total_ram_gb=64.0)

FAKE_WORKER_SOURCE = """
import json, os, sys, time
from pathlib import Path

import numpy as np
from PIL import Image

log = Path(os.environ["FAKE_WORKER_LOG"])
batch = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if os.environ.get("FAKE_WORKER_FAIL") == "1":
    sys.stderr.write("simulated worker crash\\n")
    sys.exit(3)


def record(event):
    with log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"event": event, "backend": batch["backend"], "t": time.time(),
                                 "items": len(batch["items"])}) + "\\n")


record("start")
for item in batch["items"]:
    started = time.monotonic()
    rng = np.random.default_rng(item["seed"])
    size = item["resolution"]
    yy, xx = np.mgrid[0:size, 0:size]
    base = (xx + yy) / (2 * size) * 255.0
    noise = rng.integers(0, 40, size=(size, size, 3))
    rgb = np.clip(base[..., None] + noise, 0, 255).astype(np.uint8)
    path = Path(item["path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb).save(path)
    print(json.dumps({"index": item["index"], "path": item["path"],
                      "seconds": round(time.monotonic() - started, 3)}), flush=True)
record("exit")
"""


def write_fake_worker(directory: Path) -> Path:
    """Write the fake worker script into ``directory`` and return its path."""
    directory.mkdir(parents=True, exist_ok=True)
    script = directory / "fake_worker.py"
    script.write_text(FAKE_WORKER_SOURCE, encoding="utf-8")
    return script


def fake_spawn(
    worker: Path, log: Path, *, fail: bool = False
) -> Callable[[Path], subprocess.CompletedProcess[str]]:
    """A ``spawn`` for ``run_backend_batches`` that runs the fake worker as a child process."""
    env = {**os.environ, "FAKE_WORKER_LOG": str(log), "FAKE_WORKER_FAIL": "1" if fail else "0"}

    def spawn(batch_file: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(worker), str(batch_file)],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )

    return spawn


def read_log(log: Path) -> list[dict[str, Any]]:
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]


def make_models(root: Path, ids: tuple[str, ...] = ("z-image-turbo", "flux2-klein-4b")) -> Path:
    """Create ``<id>-q4`` folders with a weights file, as a successful ``mflux-save`` leaves
    them."""
    for backend_id in ids:
        folder = root / f"{backend_id}-q4"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "weights.safetensors").write_bytes(b"weights")
    return root


def synthetic_image(size: int = 256, seed: int = 0) -> np.ndarray:
    """A non-tiling test image: a diagonal gradient with seeded noise, as uint8 RGB."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:size, 0:size]
    base = (xx + yy) / (2 * size) * 255.0
    noise = rng.integers(0, 20, size=(size, size, 3))
    rgb: np.ndarray = np.clip(base[..., None] + noise, 0, 255).astype(np.uint8)
    return rgb


def save_png(array: np.ndarray, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    PILImage.fromarray(array).save(path)
    return path
