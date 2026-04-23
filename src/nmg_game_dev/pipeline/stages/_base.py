"""Base types shared across all pipeline stage modules.

Defines the ``Stage`` callable Protocol, ``StageContext``, ``StageArtifact``,
``McpClients`` DI container, and the minimum MCP client Protocol shims that
stages call into.  The shims are structural — any object that exposes the
required methods satisfies them, including the scripted fakes used in tests.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from ..prompt import Prompt

# Stages are a closed set. Using a Literal gives tests, BDD steps, and
# stage_overrides dict keys a single source of truth and catches typos at
# type-check time.
StageName = Literal["generate", "texture", "cleanup", "variants", "quality", "import_ue"]

# Minimal MCP client Protocol shims — only the surface that stage modules
# actually call. The real .mcp.json-wired clients and the test fakes both
# satisfy them structurally.


class BlenderMcp(Protocol):
    """Minimum surface of the Blender MCP client that stages call."""

    def run_script(self, script: str, **kwargs: object) -> dict[str, object]:
        """Execute a Python script inside Blender and return the result dict."""
        ...

    def ping(self) -> bool:
        """Return True when the Blender MCP socket is reachable."""
        ...


class UnrealMcp(Protocol):
    """Minimum surface of the VibeUE Unreal MCP client that stages call."""

    def import_asset(
        self,
        source_path: str,
        destination_path: str,
        **kwargs: object,
    ) -> dict[str, object]:
        """Import a source file into the UE content tree."""
        ...

    def ping(self) -> bool:
        """Return True when the UE MCP bridge is reachable."""
        ...


class MeshyMcp(Protocol):
    """Minimum surface of the Meshy MCP client that stages call."""

    def generate(self, prompt: str, **kwargs: object) -> dict[str, object]:
        """Trigger Meshy asset generation and return the result dict."""
        ...


@dataclass(frozen=True)
class McpClients:
    """Immutable container of pre-configured MCP client instances.

    ``meshy`` is optional because Blender-first runs do not require it.
    Pass ``meshy=None`` (the default) for Blender-source pipelines.
    """

    blender: BlenderMcp
    unreal: UnrealMcp
    meshy: MeshyMcp | None = None


_HASH_CHUNK_BYTES = 1 << 20  # 1 MiB — streams 4K textures / hero meshes without RAM spikes


@dataclass(frozen=True)
class StageArtifact:
    """The immutable output of a single pipeline stage.

    Attributes:
        stage: Name of the stage that produced this artifact.
        blob_path: Path to the primary produced file (mesh, texture, etc.).
            For cache-hit artifacts this points directly at the cache-resident
            blob — no copy is made until a downstream stage reads the file.
        sidecar: Optional JSON-serialisable metadata dict (budget summary,
            variant paths, manifest fields, etc.).  ``None`` when the stage
            produces no metadata.
    """

    stage: str
    blob_path: Path
    sidecar: dict[str, object] | None

    def content_hash(self) -> str:
        """Return SHA-256 hex digest over blob bytes + canonical sidecar JSON.

        The sidecar is serialised with ``sort_keys=True`` and a ``default=str``
        fallback so non-string values (e.g. ``Path``) round-trip
        deterministically.  Used as the ``upstream_hash`` component when
        computing the next stage's cache key.

        The digest is memoised on first call — StageArtifact is frozen, so the
        blob and sidecar can never change for a given instance. The orchestrator
        calls this once per artifact per run, but defensive memoisation keeps
        large-blob hashes bounded even if a caller reuses the object.
        """
        cached = getattr(self, "_hash_cache", None)
        if isinstance(cached, str):
            return cached
        h = hashlib.sha256()
        try:
            with self.blob_path.open("rb") as fh:
                for chunk in iter(lambda: fh.read(_HASH_CHUNK_BYTES), b""):
                    h.update(chunk)
        except OSError:
            # If the blob is missing (e.g. a sidecar-only artifact), hash only
            # the path string so the key remains stable.
            h.update(str(self.blob_path).encode())
        sidecar_json = json.dumps(
            self.sidecar if self.sidecar is not None else {},
            sort_keys=True,
            default=str,
        ).encode()
        h.update(sidecar_json)
        digest = h.hexdigest()
        # Frozen dataclass blocks setattr; go through object.__setattr__.
        object.__setattr__(self, "_hash_cache", digest)
        return digest


@dataclass(frozen=True)
class StageContext:
    """Immutable execution context passed into every stage callable.

    Attributes:
        prompt: The validated asset-generation prompt for this run.
        upstream_artifact: The artifact produced by the immediately preceding
            stage, or ``None`` for the first stage (generate).
        cache_dir: Resolved root of the content-addressed artifact cache.
        mcp_clients: Pre-configured MCP client container.
    """

    prompt: Prompt
    upstream_artifact: StageArtifact | None
    cache_dir: Path
    mcp_clients: McpClients


@runtime_checkable
class Stage(Protocol):
    """A callable that accepts a ``StageContext`` and returns a ``StageArtifact``.

    Stage modules expose plain module-level functions that satisfy this
    Protocol.  No inheritance required — structural subtyping is the contract.
    """

    def __call__(self, ctx: StageContext) -> StageArtifact: ...
