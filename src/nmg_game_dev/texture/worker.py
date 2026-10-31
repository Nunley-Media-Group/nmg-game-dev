"""Worker process: load one backend once, generate a batch, write raw PNGs, exit (#7 FR14, AC16).

Run as ``python -m nmg_game_dev.texture.worker <batch.json>``. The batch file names the mflux entry
point, the saved weights directory, the step count, and one item per image. The worker prints one
JSON line per finished image on stdout and sends diagnostics to stderr.

This is the only module in the package that imports mflux or mlx. Importing it on a host without the
``texture-ai`` extra fails here and nowhere else.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any


def _load_model(entry: str, weights: Path) -> Any:
    import mlx.core as mx
    from mflux.models.common.config.model_config import ModelConfig

    if entry == "ZImage":
        from mflux.models.z_image.variants.z_image import ZImage

        return ZImage(
            quantize=4,
            model_path=str(weights),
            model_config=ModelConfig.z_image_turbo(),
            compute_precision=mx.float16,
        )
    if entry == "Flux2Klein":
        from mflux.models.flux2.variants.txt2img.flux2_klein import Flux2Klein

        return Flux2Klein(
            quantize=4,
            model_path=str(weights),
            model_config=ModelConfig.flux2_klein_4b(),
            compute_precision=mx.float16,
        )
    raise ValueError(f"unknown mflux entry {entry!r}")


def run_batch(batch: dict[str, Any]) -> None:
    """Load the backend once, then generate and save every item, printing one JSON line each."""
    model = _load_model(str(batch["mflux_entry"]), Path(str(batch["weights"])))
    steps = int(batch["steps"])
    for item in batch["items"]:
        started = time.monotonic()
        image = model.generate_image(
            seed=int(item["seed"]),
            prompt=str(item["prompt"]),
            num_inference_steps=steps,
            height=int(item["resolution"]),
            width=int(item["resolution"]),
        )
        path = Path(str(item["path"]))
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path=path, overwrite=True)
        seconds = round(time.monotonic() - started, 2)
        print(
            json.dumps({"index": item["index"], "path": str(path), "seconds": seconds}),
            flush=True,
        )


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: python -m nmg_game_dev.texture.worker <batch.json>", file=sys.stderr)
        return 2
    batch: dict[str, Any] = json.loads(Path(args[0]).read_text(encoding="utf-8"))
    run_batch(batch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
