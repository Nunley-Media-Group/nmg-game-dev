"""Generate seamless textures end to end (#7 FR15, FR16, AC17–AC20; #143 FR6–FR8).

``run`` validates one request, resolves and checks the backends (expanding ``both`` to the available
ones in registry order), runs one worker per backend, applies the seamless post-process to every
PNG, derives the optional maps, writes the ``both`` comparison sheet, records ``textures.json``
under ``<output_root>/<name>/``, and then refreshes the root contact sheet (#152).

``run_batch`` runs several requests as one job. Each backend's worker covers every image of every
request that uses it, so the model loads once for the whole batch (#143 FR6).

Every dependency is injected (``env``, ``facts``, ``spawn``, ``output_root``, ``deps_probe``), so
tests can run the whole flow with a fake worker and synthetic hardware facts.
"""

from __future__ import annotations

import json
import os
import random
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, fields, replace
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image as PILImage

from nmg_game_dev.texture.batch import Batch, ImageItem, Spawn, default_spawn, run_backend_batches
from nmg_game_dev.texture.contact_sheet import MANIFEST_NAME, ContactSheet
from nmg_game_dev.texture.contact_sheet import build as build_contact_sheet
from nmg_game_dev.texture.deps import DepsProbe, require_dependencies
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
    contact_sheet: ContactSheet = field(default_factory=ContactSheet)

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
            "contact_sheet": self.contact_sheet.as_json(),
        }


@dataclass(frozen=True)
class BatchResult:
    """What a batch run produced: one :class:`TextureResult` per request, in request order."""

    results: tuple[TextureResult, ...]

    def as_json(self) -> dict[str, Any]:
        return {"results": [result.as_json() for result in self.results]}


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


def _invalid_batch(failures: Sequence[str]) -> TextureGenError:
    return TextureGenError(
        "texture.invalid_request",
        "The batch is invalid, so nothing was generated or queued: " + "; ".join(failures),
        "Fix each listed request and submit the whole batch again.",
    )


def validate_batch(requests: Sequence[TextureRequest]) -> None:
    """Reject the whole batch with one ``texture.invalid_request`` that lists each bad index (#143
    FR8), and each output name that two or more requests share (#211 FR1)."""
    if not requests:
        raise TextureGenError(
            "texture.invalid_request",
            "The batch is empty.",
            "Pass at least one request in the batch.",
        )
    failures: list[str] = []
    indexes_by_name: dict[str, list[int]] = {}
    for index, request in enumerate(requests):
        try:
            validate_request(request)
        except TextureGenError as error:
            failures.append(f"request {index}: {error.message.rstrip('.')}")
        name = slugify(request.name or request.prompt)
        indexes_by_name.setdefault(name, []).append(index)
    for name, indexes in indexes_by_name.items():
        if len(indexes) > 1:
            listed = ", ".join(str(index) for index in indexes)
            failures.append(f"requests {listed}: output name {name!r} is used more than once")
    if failures:
        raise _invalid_batch(failures)


_REQUEST_FIELDS = frozenset(f.name for f in fields(TextureRequest))
_FIELD_TYPES: dict[str, tuple[type, ...]] = {
    "prompt": (str,),
    "backend": (str,),
    "name": (str,),
    "style_suffix": (str,),
    "resolution": (int,),
    "ao": (bool,),
    "seeds": (list,),
    "maps": (str, list),
}


def request_from_mapping(data: object) -> TextureRequest:
    """Build one request from a batch item: a JSON object with the request's fields (#143 FR7).

    Null and absent fields take their defaults. Raises ``ValueError`` with the reason when the item
    is not an object, names an unknown field, or has a field of the wrong type.
    """
    if not isinstance(data, Mapping):
        raise ValueError("it is not a JSON object")
    unknown = sorted(str(key) for key in data if key not in _REQUEST_FIELDS)
    if unknown:
        raise ValueError(f"unknown field {', '.join(unknown)}")
    kwargs: dict[str, Any] = {key: value for key, value in data.items() if value is not None}
    for key, expected in _FIELD_TYPES.items():
        if key in kwargs and not isinstance(kwargs[key], expected):
            raise ValueError(f"{key} must be {' or '.join(t.__name__ for t in expected)}")
    if "prompt" not in kwargs:
        raise ValueError("prompt is missing")
    if "seeds" in kwargs and not all(type(seed) is int for seed in kwargs["seeds"]):
        raise ValueError("seeds must be integers")
    maps = kwargs.get("maps")
    if isinstance(maps, list):
        numeric = all(isinstance(v, int | float) and not isinstance(v, bool) for v in maps)
        if len(maps) != 2 or not numeric:
            raise ValueError("maps must be a preset name or [roughness, metallic]")
        kwargs["maps"] = (float(maps[0]), float(maps[1]))
    return TextureRequest(**kwargs)


def batch_from_items(items: object) -> tuple[TextureRequest, ...]:
    """Parse a batch: a JSON array of request objects. One malformed item rejects the whole
    batch."""
    if not isinstance(items, list):
        raise TextureGenError(
            "texture.invalid_request",
            "A batch must be a JSON array of request objects.",
            "Wrap the request objects in [ ... ], one object per request.",
        )
    requests: list[TextureRequest] = []
    failures: list[str] = []
    for index, item in enumerate(items):
        try:
            requests.append(request_from_mapping(item))
        except ValueError as error:
            failures.append(f"request {index}: {error}")
    if failures:
        raise _invalid_batch(failures)
    return tuple(requests)


def load_batch_file(path: Path) -> tuple[TextureRequest, ...]:
    """Read a batch file: a JSON array of request objects (#143 FR7)."""
    try:
        items: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise TextureGenError(
            "texture.invalid_request",
            f"Cannot read the batch file {path}: {error}",
            "Pass --batch FILE, where FILE holds a JSON array of request objects.",
        ) from error
    return batch_from_items(items)


def select_backends(
    backend: str,
    registry: Mapping[str, BackendSpec],
    models_root: Path | None,
    facts: HardwareFacts,
    reserve: float,
    deps_probe: DepsProbe | None = None,
) -> tuple[list[BackendSpec], list[dict[str, str]]]:
    """Return the backends to run and the ``both`` entries that were skipped and why."""
    if backend != BOTH:
        spec = resolve(backend, registry)
        require_available(spec, facts, models_root, reserve, deps_probe)
        return [spec], []
    candidates = list(registry.values())
    selected: list[BackendSpec] = []
    skipped: list[dict[str, str]] = []
    for spec in candidates:
        status = availability(spec, facts, models_root, reserve, deps_probe)
        if status == "available":
            selected.append(spec)
        else:
            skipped.append({"backend": spec.id, "availability": status})
    if not selected:
        require_available(candidates[0], facts, models_root, reserve, deps_probe)
    return selected, skipped


def backend_status(
    env: Mapping[str, str] | None = None,
    facts: HardwareFacts | None = None,
    registry: Mapping[str, BackendSpec] = REGISTRY,
    deps_probe: DepsProbe | None = None,
) -> dict[str, str]:
    """Availability per backend id, for the ``status`` command and the ``texture_backends`` tool."""
    env_map = os.environ if env is None else env
    host = probe() if facts is None else facts
    root = models_dir(env_map)
    reserve = reserve_gb(env_map)
    return {
        spec.id: availability(spec, host, root, reserve, deps_probe) for spec in registry.values()
    }


def plan_total(request: TextureRequest, selected: list[BackendSpec]) -> int:
    """How many images the run will produce."""
    return len(request.seeds) * len(selected)


def _full_prompt(request: TextureRequest) -> str:
    suffix = request.style_suffix.strip()
    prompt = request.prompt.strip()
    return f"{prompt}, {suffix}" if suffix else prompt


@dataclass(frozen=True)
class _Plan:
    """One request's share of a run: its folder, display name, and the backends that will run."""

    request: TextureRequest
    name: str
    out_dir: Path
    selected: tuple[BackendSpec, ...]
    skipped: tuple[dict[str, str], ...]


def _generate(
    requests: Sequence[TextureRequest],
    *,
    registry: Mapping[str, BackendSpec],
    env_map: Mapping[str, str],
    host: HardwareFacts,
    spawn: Spawn,
    base: Path,
    on_progress: Callable[[int, int], None] | None,
    deps_probe: DepsProbe | None,
) -> tuple[TextureResult, ...]:
    """Run ``requests`` as one job: one worker per backend covers every image, then each request is
    finished."""
    root = models_dir(env_map)
    reserve = reserve_gb(env_map)
    plans: list[_Plan] = []
    for request in requests:
        selected, skipped = select_backends(
            request.backend, registry, root, host, reserve, deps_probe
        )
        name = slugify(request.name or request.prompt)
        plans.append(_Plan(request, name, base / name, tuple(selected), tuple(skipped)))
    require_dependencies(deps_probe)
    for plan in plans:
        plan.out_dir.mkdir(parents=True, exist_ok=True)

    # Images grouped by backend in first-use order. ``owners`` maps each image's batch-wide index
    # back
    # to the request that asked for it, so timings land on the right request.
    specs: dict[str, BackendSpec] = {}
    images: dict[str, list[ImageItem]] = {}
    owners: dict[int, tuple[int, ImageItem]] = {}
    for position, plan in enumerate(plans):
        full_prompt = _full_prompt(plan.request)
        for spec in plan.selected:
            specs.setdefault(spec.id, spec)
            for seed in plan.request.seeds:
                item = ImageItem(
                    index=len(owners),
                    prompt=full_prompt,
                    seed=seed,
                    resolution=plan.request.resolution,
                    path=plan.out_dir / f"{spec.id}_{seed}_{plan.request.resolution}.png",
                )
                owners[item.index] = (position, item)
                images.setdefault(spec.id, []).append(item)

    total = len(owners)
    completed = 0
    if on_progress is not None:
        on_progress(0, total)

    def batch_done(batch: Batch) -> None:
        nonlocal completed
        completed += len(batch.items)
        if on_progress is not None:
            on_progress(completed, total)

    with tempfile.TemporaryDirectory(prefix="nmg-texture-batch-") as scratch:
        batches = [
            Batch(
                spec=spec,
                weights=weights_dir(spec, root) if root is not None else Path(),
                items=tuple(images[spec.id]),
                batch_file=Path(scratch) / f"{spec.id}.json",
            )
            for spec in specs.values()
        ]
        timings = run_backend_batches(batches, spawn=spawn, on_batch_done=batch_done)

    records: list[list[ImageRecord]] = [[] for _ in plans]
    materials = [
        resolve_material(plan.request.maps) if plan.request.maps is not None else None
        for plan in plans
    ]
    for batch in batches:
        for timing in timings.get(batch.spec.id, []):
            position, item = owners[timing.index]
            _make_seamless_png(item.path)
            map_set: MapSet | None = None
            material = materials[position]
            if material is not None:
                map_set = derive(
                    item.path,
                    material[0],
                    material[1],
                    ao=plans[position].request.ao,
                )
            records[position].append(
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

    results: list[TextureResult] = []
    for plan, plan_records in zip(plans, records, strict=True):
        compare_path: Path | None = None
        if plan.request.backend == BOTH and len(plan_records) >= 2:
            compare_path = compare(
                [record.path for record in plan_records],
                [f"{r.backend} seed {r.seed} - {r.seconds:g}s" for r in plan_records],
                plan.out_dir / f"{plan.name}_compare.png",
            )
        result = TextureResult(
            name=plan.name,
            prompt=plan.request.prompt,
            style_suffix=plan.request.style_suffix,
            output_dir=plan.out_dir,
            images=tuple(plan_records),
            skipped=plan.skipped,
            manifest=plan.out_dir / MANIFEST_NAME,
            compare=compare_path,
        )
        result.manifest.write_text(
            json.dumps(_manifest(result), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        results.append(result)

    # The contact sheet is refreshed once after every manifest is written; each result carries it.
    sheet = _refresh_contact_sheet(base)
    return tuple(replace(result, contact_sheet=sheet) for result in results)


def run(
    request: TextureRequest,
    *,
    registry: Mapping[str, BackendSpec] = REGISTRY,
    env: Mapping[str, str] | None = None,
    facts: HardwareFacts | None = None,
    spawn: Spawn | None = None,
    cwd: Path | None = None,
    output_root_override: Path | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    deps_probe: DepsProbe | None = None,
) -> TextureResult:
    """Generate the textures for ``request`` and return what was written."""
    env_map = os.environ if env is None else env
    host = probe() if facts is None else facts
    validate_request(request)
    results = _generate(
        [request],
        registry=registry,
        env_map=env_map,
        host=host,
        spawn=default_spawn if spawn is None else spawn,
        base=output_root_override or output_root(env_map, cwd or Path.cwd()),
        on_progress=on_progress,
        deps_probe=deps_probe,
    )
    return results[0]


def run_batch(
    requests: Sequence[TextureRequest],
    *,
    registry: Mapping[str, BackendSpec] = REGISTRY,
    env: Mapping[str, str] | None = None,
    facts: HardwareFacts | None = None,
    spawn: Spawn | None = None,
    cwd: Path | None = None,
    output_root_override: Path | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    deps_probe: DepsProbe | None = None,
) -> BatchResult:
    """Generate every request in one job, loading each backend's model once for all of them (#143
    FR6)."""
    env_map = os.environ if env is None else env
    host = probe() if facts is None else facts
    validate_batch(requests)
    results = _generate(
        requests,
        registry=registry,
        env_map=env_map,
        host=host,
        spawn=default_spawn if spawn is None else spawn,
        base=output_root_override or output_root(env_map, cwd or Path.cwd()),
        on_progress=on_progress,
        deps_probe=deps_probe,
    )
    return BatchResult(results=results)


def _refresh_contact_sheet(base: Path) -> ContactSheet:
    """Rebuild the root contact sheet after the manifest is written. An OSError is reported in
    ``skipped`` instead of failing the run (#152 AC6)."""
    try:
        return build_contact_sheet(base, require_sets=False)
    except OSError as error:
        return ContactSheet(
            skipped=({"path": str(base), "reason": f"{type(error).__name__}: {error}"},),
        )


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
