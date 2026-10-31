"""The closed registry of texture backends (#7 AC12, AC13).

Exactly two pinned models ship: Z-Image Turbo and FLUX.2 klein 4B. The registry is a read-only
mapping built once at import, and nothing in the package offers a way to add to it. ``resolve``
enforces the allowlist for both backend ids and explicit model repositories.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from nmg_game_dev.texture.errors import TextureGenError


@dataclass(frozen=True)
class BackendSpec:
    """One pinned texture model: where it comes from, how it runs, and what it needs."""

    id: str
    repo: str
    revision: str
    license: str
    quantization: int
    default_steps: int
    peak_memory_gb: float
    mflux_entry: str


_SPECS: tuple[BackendSpec, ...] = (
    BackendSpec(
        id="z-image-turbo",
        repo="Tongyi-MAI/Z-Image-Turbo",
        revision="f332072aa78be7aecdf3ee76d5c247082da564a6",
        license="apache-2.0",
        quantization=4,
        default_steps=9,
        peak_memory_gb=14.6,
        mflux_entry="ZImage",
    ),
    BackendSpec(
        id="flux2-klein-4b",
        repo="black-forest-labs/FLUX.2-klein-4B",
        revision="e7b7dc27f91deacad38e78976d1f2b499d76a294",
        license="apache-2.0",
        quantization=4,
        default_steps=4,
        peak_memory_gb=12.9,
        mflux_entry="Flux2Klein",
    ),
)

REGISTRY: Mapping[str, BackendSpec] = MappingProxyType({spec.id: spec for spec in _SPECS})


def _allowed_text() -> str:
    return "; ".join(f"{spec.id} ({spec.repo})" for spec in REGISTRY.values())


def resolve(
    backend: str, registry: Mapping[str, BackendSpec] = REGISTRY, model_ref: str | None = None
) -> BackendSpec:
    """Return the pinned spec for ``backend`` (a registry id or a model repo).

    Raises ``texture.model_not_allowed`` when ``backend`` or ``model_ref`` names a repo outside the
    allowlist, and ``texture.unknown_backend`` when ``backend`` is neither a registry id nor a repo.
    """
    allowed = f"Allowed backends: {_allowed_text()}."
    remediation = f'{allowed} Pass one of those backend ids or repos, or use backend "both".'
    spec = registry.get(backend)
    if spec is None:
        by_repo = next((s for s in registry.values() if s.repo == backend), None)
        if by_repo is not None:
            spec = by_repo
        elif "/" in backend:
            raise TextureGenError(
                "texture.model_not_allowed",
                f"Model repo {backend!r} is not one of the pinned texture models.",
                remediation,
            )
        else:
            raise TextureGenError(
                "texture.unknown_backend",
                f"Unknown texture backend {backend!r}.",
                remediation,
            )
    if model_ref is not None and model_ref != spec.repo:
        raise TextureGenError(
            "texture.model_not_allowed",
            f"Model {model_ref!r} is not the pinned repo for backend {spec.id!r}.",
            remediation,
        )
    return spec
