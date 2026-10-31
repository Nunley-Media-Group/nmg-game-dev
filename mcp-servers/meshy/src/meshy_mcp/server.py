"""meshy MCP server: start Meshy generate and retexture jobs, and poll them (#98).

Tools return structured results. A ``PipelineError`` (including ``MeshyError``) comes back as
``{"error": {"code", "message", "remediation"}}`` rather than an exception. Logs go to stderr only,
because stdout is the MCP channel. The key is never returned or logged.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

from nmg_game_dev.meshy import jobs
from nmg_game_dev.meshy.request import GenerateRequest, RetextureRequest
from nmg_game_dev.pipeline.errors import PipelineError

log = logging.getLogger("meshy")
mcp = FastMCP("meshy")


def _error(error: PipelineError) -> dict[str, Any]:
    return {
        "error": {
            "code": error.code,
            "message": error.message,
            "remediation": error.remediation,
        }
    }


@mcp.tool()
def generate_model(
    name: str,
    prompt: str | None = None,
    image_paths: list[str] | None = None,
    texture: bool = True,
    pose: str | None = None,
) -> dict[str, Any]:
    """Start a background Meshy generate job and return its job_id at once.

    Give a prompt, one to four reference images, or both. Prompt only: Meshy shapes the model from
    the text. With images, the images shape the model and the prompt steers only the texture.
    texture=False returns the untextured mesh, with no prompt and images together. pose is a-pose
    or t-pose and applies to characters and creatures with limbs only; set it only for those,
    never for props. Poll get_meshy_job(job_id) until it succeeds; the result names the GLB and
    the collection <name> it was imported into.
    """
    request = GenerateRequest(
        name=name,
        prompt=prompt,
        image_paths=tuple(image_paths or ()),
        texture=texture,
        pose=pose,
    )
    try:
        job_id = jobs.start_generate(request)
    except PipelineError as error:
        log.warning("generate_model refused: %s", error.code)
        return _error(error)
    return {"job_id": job_id}


@mcp.tool()
def retexture_model(
    name: str,
    prompt: str | None = None,
    image_path: str | None = None,
) -> dict[str, Any]:
    """Start a background Meshy retexture job for an authored collection and return its job_id.

    The collection <name> must already be in the Blender session with mesh SM_<name>. Give exactly
    one of prompt (a text style) and image_path (a style image). The job exports the collection,
    downloads the base color, normal, roughness, and metallic maps, and wires them into the
    collection's material. Poll get_meshy_job(job_id) for the map paths.
    """
    request = RetextureRequest(name=name, prompt=prompt, image_path=image_path)
    try:
        job_id = jobs.start_retexture(request)
    except PipelineError as error:
        log.warning("retexture_model refused: %s", error.code)
        return _error(error)
    return {"job_id": job_id}


@mcp.tool()
def get_meshy_job(job_id: str) -> dict[str, Any]:
    """Return a Meshy job's state: queued, running (stage and progress), succeeded, or failed.

    A succeeded generate job's result has the GLB path and loaded_into_session. A succeeded
    retexture job's result has the map paths and applied_to_session. Warnings name what was kept
    when the Blender session was unreachable.
    """
    try:
        return jobs.status(job_id)
    except PipelineError as error:
        return _error(error)


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    mcp.run()


if __name__ == "__main__":
    main()
