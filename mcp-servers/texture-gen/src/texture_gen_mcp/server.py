"""texture-gen MCP server: start texture jobs, poll them, and report backend availability (#7).

Tools return structured results. A ``TextureGenError`` comes back as
``{"error": {"code", "message", "remediation"}}`` rather than an exception. Logs go to stderr only,
because stdout is the MCP channel.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from nmg_game_dev.texture import contact_sheet, generate, jobs
from nmg_game_dev.texture.errors import TextureGenError
from nmg_game_dev.texture.generate import TextureRequest, backend_status
from nmg_game_dev.texture.paths import output_root

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
    prompt: str | None = None,
    backend: str = "flux2-klein-4b",
    seeds: list[int] | None = None,
    resolution: int = 1024,
    name: str | None = None,
    maps: str | None = None,
    ao: bool = False,
    requests: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Start a background texture job and return its job_id at once. A job that starts while another
    runs waits in a queue and runs after it.

    Pass prompt with backend, seeds, resolution, name, maps, and ao for one texture. Or pass
    requests,
    a list of request objects with the same fields, for a batch that runs as one job and loads each
    model once. Pass one or the other, not both. backend is z-image-turbo, flux2-klein-4b, or both.
    Poll get_texture_job(job_id) for progress and the PNG paths. Outputs go to
    SourceArt/Textures/Generated/<name>/ in the project. maps is a material preset (fabric, wood,
    stone, plastic, metal); ao adds an AO map to it.
    """
    try:
        if (prompt is None) == (requests is None):
            raise TextureGenError(
                "texture.invalid_request",
                "Pass either prompt or requests, not both and not neither.",
                "Pass prompt for one texture, or requests (a list of request objects) for a batch.",
            )
        if requests is not None:
            job_id = jobs.start(generate.batch_from_items(requests))
        else:
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
    """Report each backend: available, not_installed, unsupported_platform, insufficient_memory, or
    dependencies_missing (the mflux or mlx module is not installed; run from the plugin root)."""
    try:
        return {"backends": backend_status()}
    except TextureGenError as error:
        return _error(error)


@mcp.tool()
def texture_contact_sheet() -> dict[str, Any]:
    """Rebuild the contact sheet at the output root from every texture set, with no texture model
    needed. Returns the page paths, the cell count, and any skipped albedos, or the error
    texture.no_texture_sets when the output root holds no texture sets."""
    try:
        sheet = contact_sheet.build(output_root(os.environ, Path.cwd()), require_sets=True)
    except TextureGenError as error:
        return _error(error)
    return sheet.as_json()


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    mcp.run()


if __name__ == "__main__":
    main()
