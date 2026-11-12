"""Shared fakes for the #7 texture tests: a fake worker process, synthetic images, and model
folders. The #147 seam fixtures (periodic and non-periodic noise, the seam corpus) and the
file-path loader for the bpy-free bake_core modules live here too.

The fake worker is a real child process: it reads the batch file the package writes, logs when it
starts and exits, and writes synthetic PNGs. Tests therefore check real process timing, not mocks.
No test here loads an mflux model.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
from PIL import Image as PILImage

from nmg_game_dev.texture.hardware import HardwareFacts
from nmg_game_dev.texture.seamless import make_seamless

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


def periodic_noise(size: int, seed: int, cutoff: float, channels: int = 3) -> np.ndarray:
    """Exactly periodic band-limited noise (#147): seeded white noise low-pass filtered in the
    Fourier domain at ``cutoff`` cycles per pixel, scaled to 0 to 1 as float64 (H x W x C).
    Opposite edges are neighbours on the period, so the wrap matches the interior."""
    rng = np.random.default_rng(seed)
    white = rng.standard_normal((size, size, channels))
    freq = np.fft.fftfreq(size)
    radius = np.hypot(freq[:, None], freq[None, :])
    spectrum = np.fft.fft2(white, axes=(0, 1)) * (radius <= cutoff)[..., None]
    field = np.fft.ifft2(spectrum, axes=(0, 1)).real
    low, high = float(field.min()), float(field.max())
    scaled: np.ndarray = (field - low) / (high - low)
    return scaled


def periodic_crop(size: int, seed: int, cutoff: float, channels: int = 3) -> np.ndarray:
    """A size x size crop of a 2 x size periodic field (#147): the first and last columns and rows
    are not neighbours, so the wrap is a real discontinuity on the same texture statistics."""
    return periodic_noise(2 * size, seed, cutoff, channels)[:size, :size]


def smooth_ramp(size: int = 256) -> np.ndarray:
    """A smooth 0 to 0.03 vertical ramp (#147 AC3): its wrap step is under 0.04 but far above the
    interior step."""
    ramp = np.linspace(0.0, 0.03, size)[:, None, None]
    return np.broadcast_to(ramp, (size, size, 3)).copy()


def near_flat_u8(size: int = 256, seed: int = 0) -> np.ndarray:
    """An 8-bit texture whose pixels vary by one quantization level around 128 (#147 AC4)."""
    rng = np.random.default_rng(seed)
    return (128 + rng.integers(-1, 2, size=(size, size, 3))).astype(np.uint8)


def white_noise_u8(size: int = 256, seed: int = 0) -> np.ndarray:
    """Uniform 8-bit RGB noise: the input make_seamless must make tile (#147 AC5)."""
    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, size=(size, size, 3), dtype=np.uint8)


def seam_corpus() -> list[tuple[str, np.ndarray]]:
    """Every image class the #147 spec names, as float and 8-bit, RGB and single-channel (AC6)."""
    floats: dict[str, np.ndarray] = {
        "periodic": periodic_noise(256, seed=0, cutoff=0.25),
        "crop": periodic_crop(256, seed=0, cutoff=0.08),
        "seamless-crop": make_seamless(periodic_crop(256, seed=0, cutoff=0.08)),
        "ramp": smooth_ramp(),
        "constant": np.full((256, 256, 3), 0.5),
    }
    corpus: list[tuple[str, np.ndarray]] = []
    for name, img in floats.items():
        as_u8 = np.rint(img * 255.0).astype(np.uint8)
        corpus.extend(
            [
                (f"{name}-float-rgb", img),
                (f"{name}-float-gray", img[..., 0]),
                (f"{name}-u8-rgb", as_u8),
                (f"{name}-u8-gray", as_u8[..., 0]),
            ]
        )
    eight_bit: dict[str, np.ndarray] = {
        "near-flat": near_flat_u8(),
        "synthetic": synthetic_image(256),
        "seamless-synthetic": make_seamless(synthetic_image(256)),
        "white-noise": white_noise_u8(),
        "seamless-white-noise": make_seamless(white_noise_u8()),
    }
    for name, img in eight_bit.items():
        corpus.extend([(f"{name}-u8-rgb", img), (f"{name}-u8-gray", img[..., 0])])
    return corpus


def load_bake_core(filename: str) -> ModuleType:
    """Load one bake_core module by file path (#147). The add-on package imports bpy, so only the
    numpy-only, bpy-free modules (seam_metric, errors) can run under plain CPython."""
    path = Path(__file__).resolve().parents[1] / "plugins/nmg-game-dev-blender-addon/bake_core"
    stem = Path(filename).stem
    name = f"nmg_bake_core_{stem}_under_test"
    spec = importlib.util.spec_from_file_location(name, path / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # A dataclass resolves its module through sys.modules while the module executes.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
