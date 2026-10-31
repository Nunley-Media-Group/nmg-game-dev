"""texture-gen MCP server: start texture jobs, poll them, and report backend availability (#7).

Tools return structured results. A ``TextureGenError`` comes back as
``{"error": {"code", "message", "remediation"}}`` rather than an exception. Logs go to stderr only,
because stdout is the MCP channel.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

from nmg_game_dev.texture import jobs
from nmg_game_dev.texture.errors import TextureGenError
from nmg_game_dev.texture.generate import TextureRequest, backend_status

log = logging.getLogger("texture-gen")
mcp = FastMCP("texture-gen")


def _error(error: TextureGenError) -> dict[str, Any]:
    return {
        "error": {
            "code": error.code,
            "message": error.message,
            "remediation": error.remediation,
        }
    }


@mcp.tool()
def generate_textures(
    prompt: str,
    backend: str = "flux2-klein-4b",
    seeds: list[int] | None = None,
    resolution: int = 1024,
    name: str | None = None,
    maps: str | None = None,
    ao: bool = False,
) -> dict[str, Any]:
    """Start a background texture job and return its job_id at once.

    backend is z-image-turbo, flux2-klein-4b, or both. Poll get_texture_job(job_id) for progress
    and the PNG paths. Outputs go to SourceArt/Textures/Generated/<name>/ in the project.
    maps is a material preset (fabric, wood, stone, plastic, metal); ao adds an AO map to it.
    """
    kwargs: dict[str, Any] = {
        "prompt": prompt,
        "backend": backend,
        "resolution": resolution,
        "name": name,
        "maps": maps,
        "ao": ao,
    }
    if seeds:
        kwargs["seeds"] = list(seeds)
    try:
        job_id = jobs.start(TextureRequest(**kwargs))
    except TextureGenError as error:
        log.warning("generate_textures refused: %s", error.code)
        return _error(error)
    return {"job_id": job_id}


@mcp.tool()
def get_texture_job(job_id: str) -> dict[str, Any]:
    """Return a texture job's state: queued, running (completed/total), succeeded, or failed."""
    try:
        return jobs.status(job_id)
    except TextureGenError as error:
        return _error(error)


@mcp.tool()
def texture_backends() -> dict[str, Any]:
    """Report each backend: available, not_installed, unsupported_platform, or
    insufficient_memory."""
    try:
        return {"backends": backend_status()}
    except TextureGenError as error:
        return _error(error)


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    mcp.run()


if __name__ == "__main__":
    main()
