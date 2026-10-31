"""Generate seamless textures end to end (#7 FR15, FR16, AC17–AC20).

``run`` validates the request, resolves and checks the backends (expanding ``both`` to the available
ones in registry order), runs one worker per backend, applies the seamless post-process to every
PNG, derives the optional maps, writes the ``both`` comparison sheet, and records ``textures.json``
under ``<output_root>/<name>/``.

Every dependency is injected (``env``, ``facts``, ``spawn``, ``output_root``), so tests can run the
whole flow with a fake worker and synthetic hardware facts.
"""

from __future__ import annotations

import json
import os
import random
import shutil
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image as PILImage

from nmg_game_dev.texture.batch import Batch, ImageItem, Spawn, default_spawn, run_backend_batches
from nmg_game_dev.texture.errors import TextureGenError
from nmg_game_dev.texture.hardware import (
    HardwareFacts,
    availability,
    probe,
    require_available,
    reserve_gb,
)
from nmg_game_dev.texture.maps import MapSet, derive, resolve_material
from nmg_game_dev.texture.paths import models_dir, output_root, slugify, weights_dir
from nmg_game_dev.texture.registry import REGISTRY, BackendSpec, resolve
from nmg_game_dev.texture.seamless import make_seamless
from nmg_game_dev.texture.sheet import compare

STYLE_SUFFIX = (
    "seamless tileable texture, flat top-down orthographic photo scan, uniform even diffuse "
    "lighting, no shadows, no perspective, fills the entire frame edge to edge, photorealistic, "
    "PBR albedo, no objects, no text, no watermark"
)
BOTH = "both"
DEFAULT_BACKEND = "flux2-klein-4b"
MIN_RESOLUTION = 256
MAX_RESOLUTION = 2048
MANIFEST_NAME = "textures.json"
BATCH_DIR_NAME = ".batch"


def _random_seed() -> list[int]:
    return [random.randrange(2**31)]


@dataclass(frozen=True)
class TextureRequest:
    """One generation request. ``seeds`` defaults to a single random seed."""

    prompt: str
    backend: str = DEFAULT_BACKEND
    seeds: list[int] = field(default_factory=_random_seed)
    resolution: int = 1024
    name: str | None = None
    maps: str | tuple[float, float] | None = None
    ao: bool = False
    style_suffix: str = STYLE_SUFFIX


@dataclass(frozen=True)
class ImageRecord:
    """One finished albedo, its timing, and the maps derived from it."""

    backend: str
    repo: str
    revision: str
    seed: int
    steps: int
    resolution: int
    seconds: float
    path: Path
    maps: dict[str, str]

    def as_json(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "repo": self.repo,
            "revision": self.revision,
            "seed": self.seed,
            "steps": self.steps,
            "resolution": self.resolution,
            "seconds": self.seconds,
            "path": str(self.path),
            "maps": dict(self.maps),
        }


@dataclass(frozen=True)
class TextureResult:
    """What a finished run produced, and what it skipped."""

    name: str
    prompt: str
    style_suffix: str
    output_dir: Path
    images: tuple[ImageRecord, ...]
    skipped: tuple[dict[str, str], ...]
    manifest: Path
    compare: Path | None

    def as_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "prompt": self.prompt,
            "style_suffix": self.style_suffix,
            "output_dir": str(self.output_dir),
            "images": [record.as_json() for record in self.images],
            "skipped": [dict(entry) for entry in self.skipped],
            "manifest": str(self.manifest),
            "compare": str(self.compare) if self.compare is not None else None,
        }


def validate_request(request: TextureRequest) -> None:
    """Raise ``texture.invalid_request`` for an empty prompt, a bad size, or no seeds."""
    if not request.prompt.strip():
        raise TextureGenError(
            "texture.invalid_request",
            "The prompt is empty.",
            "Pass a non-empty --prompt describing the material.",
        )
    size = request.resolution
    if not (MIN_RESOLUTION <= size <= MAX_RESOLUTION and size & (size - 1) == 0):
        raise TextureGenError(
            "texture.invalid_request",
            f"Resolution {size} is not a power of two from {MIN_RESOLUTION} to {MAX_RESOLUTION}.",
            f"Use a resolution such as {MIN_RESOLUTION}, 512, 1024, or {MAX_RESOLUTION}.",
        )
    if not request.seeds:
        raise TextureGenError(
            "texture.invalid_request",
            "No seeds were given.",
            "Pass at least one seed, or omit --seed to use a random one.",
        )
    if request.maps is not None:
        resolve_material(request.maps)
    if request.ao and request.maps is None:
        raise TextureGenError(
            "texture.invalid_request",
            "AO is derived with the other maps, but no material was given.",
            "Pass --maps with a preset (or --roughness and --metallic) along with --ao.",
        )


def select_backends(
    backend: str,
    registry: Mapping[str, BackendSpec],
    models_root: Path | None,
    facts: HardwareFacts,
    reserve: float,
) -> tuple[list[BackendSpec], list[dict[str, str]]]:
    """Return the backends to run and the ``both`` entries that were skipped and why."""
    if backend != BOTH:
        spec = resolve(backend, registry)
        require_available(spec, facts, models_root, reserve)
        return [spec], []
    candidates = list(registry.values())
    selected: list[BackendSpec] = []
    skipped: list[dict[str, str]] = []
    for spec in candidates:
        status = availability(spec, facts, models_root, reserve)
        if status == "available":
            selected.append(spec)
        else:
            skipped.append({"backend": spec.id, "availability": status})
    if not selected:
        require_available(candidates[0], facts, models_root, reserve)
    return selected, skipped


def backend_status(
    env: Mapping[str, str] | None = None,
    facts: HardwareFacts | None = None,
    registry: Mapping[str, BackendSpec] = REGISTRY,
) -> dict[str, str]:
    """Availability per backend id, for the ``status`` command and the ``texture_backends`` tool."""
    env_map = os.environ if env is None else env
    host = probe() if facts is None else facts
    root = models_dir(env_map)
    reserve = reserve_gb(env_map)
    return {spec.id: availability(spec, host, root, reserve) for spec in registry.values()}


def plan_total(request: TextureRequest, selected: list[BackendSpec]) -> int:
    """How many images the run will produce."""
    return len(request.seeds) * len(selected)


def _full_prompt(request: TextureRequest) -> str:
    suffix = request.style_suffix.strip()
    prompt = request.prompt.strip()
    return f"{prompt}, {suffix}" if suffix else prompt


def run(
    request: TextureRequest,
    *,
    registry: Mapping[str, BackendSpec] = REGISTRY,
    env: Mapping[str, str] | None = None,
    facts: HardwareFacts | None = None,
    spawn: Spawn = default_spawn,
    cwd: Path | None = None,
    output_root_override: Path | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> TextureResult:
    """Generate the textures for ``request`` and return what was written."""
    env_map = os.environ if env is None else env
    host = probe() if facts is None else facts
    validate_request(request)
    root = models_dir(env_map)
    selected, skipped = select_backends(request.backend, registry, root, host, reserve_gb(env_map))
    total = plan_total(request, selected)
    name = slugify(request.name or request.prompt)
    base = output_root_override or output_root(env_map, cwd or Path.cwd())
    out_dir = base / name
    out_dir.mkdir(parents=True, exist_ok=True)
    full_prompt = _full_prompt(request)

    batches: list[Batch] = []
    for spec in selected:
        items = tuple(
            ImageItem(
                index=index,
                prompt=full_prompt,
                seed=seed,
                resolution=request.resolution,
                path=out_dir / f"{spec.id}_{seed}_{request.resolution}.png",
            )
            for index, seed in enumerate(request.seeds)
        )
        batches.append(
            Batch(
                spec=spec,
                weights=weights_dir(spec, root) if root is not None else Path(),
                items=items,
                batch_file=out_dir / BATCH_DIR_NAME / f"{spec.id}.json",
            )
        )

    completed = 0
    if on_progress is not None:
        on_progress(0, total)

    def batch_done(batch: Batch) -> None:
        nonlocal completed
        completed += len(batch.items)
        if on_progress is not None:
            on_progress(completed, total)

    timings = run_backend_batches(batches, spawn=spawn, on_batch_done=batch_done)
    shutil.rmtree(out_dir / BATCH_DIR_NAME, ignore_errors=True)

    records: list[ImageRecord] = []
    roughness_metallic = resolve_material(request.maps) if request.maps is not None else None
    for batch in batches:
        for timing in timings.get(batch.spec.id, []):
            item = batch.items[timing.index]
            _make_seamless_png(item.path)
            map_set: MapSet | None = None
            if roughness_metallic is not None:
                map_set = derive(
                    item.path,
                    roughness_metallic[0],
                    roughness_metallic[1],
                    ao=request.ao,
                )
            records.append(
                ImageRecord(
                    backend=batch.spec.id,
                    repo=batch.spec.repo,
                    revision=batch.spec.revision,
                    seed=item.seed,
                    steps=batch.spec.default_steps,
                    resolution=item.resolution,
                    seconds=timing.seconds,
                    path=item.path,
                    maps=map_set.as_dict() if map_set is not None else {},
                )
            )

    compare_path: Path | None = None
    if request.backend == BOTH and len(records) >= 2:
        compare_path = compare(
            [record.path for record in records],
            [f"{r.backend} seed {r.seed} - {r.seconds:g}s" for r in records],
            out_dir / f"{name}_compare.png",
        )

    result = TextureResult(
        name=name,
        prompt=request.prompt,
        style_suffix=request.style_suffix,
        output_dir=out_dir,
        images=tuple(records),
        skipped=tuple(skipped),
        manifest=out_dir / MANIFEST_NAME,
        compare=compare_path,
    )
    result.manifest.write_text(
        json.dumps(_manifest(result), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def _make_seamless_png(path: Path) -> None:
    image = np.asarray(PILImage.open(path).convert("RGB"))
    PILImage.fromarray(make_seamless(image)).save(path)


def _manifest(result: TextureResult) -> dict[str, Any]:
    return {
        "name": result.name,
        "prompt": result.prompt,
        "style_suffix": result.style_suffix,
        "images": [record.as_json() for record in result.images],
        "skipped": [dict(entry) for entry in result.skipped],
    }


def request_as_json(request: TextureRequest) -> dict[str, Any]:
    """The request as plain JSON, for the job's ``request.json``."""
    data = asdict(request)
    if isinstance(request.maps, tuple):
        data["maps"] = list(request.maps)
    return data


def request_from_json(data: Mapping[str, Any]) -> TextureRequest:
    """Rebuild a :class:`TextureRequest` from :func:`request_as_json` output."""
    maps_raw = data.get("maps")
    maps: str | tuple[float, float] | None
    if isinstance(maps_raw, list):
        maps = (float(maps_raw[0]), float(maps_raw[1]))
    else:
        maps = maps_raw
    return TextureRequest(
        prompt=str(data["prompt"]),
        backend=str(data["backend"]),
        seeds=[int(seed) for seed in data["seeds"]],
        resolution=int(data["resolution"]),
        name=data.get("name"),
        maps=maps,
        ao=bool(data["ao"]),
        style_suffix=str(data["style_suffix"]),
    )
