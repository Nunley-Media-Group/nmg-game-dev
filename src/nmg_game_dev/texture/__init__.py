"""Local texture generation for NMG games (#7).

Two pinned models (Z-Image Turbo and FLUX.2 klein 4B) generate seamless albedo through mflux. The
seamless post-process and derived PBR maps run in this process. ``generate`` is the synchronous
entry; ``jobs`` is the detached one the ``texture-gen`` MCP server polls.
"""

from __future__ import annotations

from nmg_game_dev.texture.errors import TextureGenError
from nmg_game_dev.texture.generate import TextureRequest, TextureResult
from nmg_game_dev.texture.generate import run as generate_textures
from nmg_game_dev.texture.registry import REGISTRY, BackendSpec

__all__ = [
    "REGISTRY",
    "BackendSpec",
    "TextureGenError",
    "TextureRequest",
    "TextureResult",
    "generate_textures",
]
