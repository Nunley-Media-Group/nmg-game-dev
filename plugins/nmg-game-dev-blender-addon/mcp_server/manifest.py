"""Integration seam into ahujasid/blender-mcp — NOT a separate MCP server; binds no port.

The directory name mcp_server/ is historical. v1 responsibility is discovery:
enumerate registered nmggamedev.* operators into a structured manifest for
pipeline code and docs generators. Invocation itself goes through the host's
execute_blender_code tool (``bpy.ops.nmggamedev.<op>()``).
"""

from __future__ import annotations


def list_nmg_tools() -> list[dict[str, str]]:
    """Return {idname, label, description} for every registered nmggamedev.* operator.

    Enumerates bpy.types at call time so this module stays importable outside
    Blender (useful for docs generation).
    """
    import bpy  # noqa: PLC0415 — deferred so module is importable without bpy

    tools: list[dict[str, str]] = []
    for name in dir(bpy.types):
        cls = getattr(bpy.types, name, None)
        idname = getattr(cls, "bl_idname", None) if cls is not None else None
        if not isinstance(idname, str) or not idname.startswith("nmggamedev."):
            continue
        tools.append(
            {
                "idname": idname,
                "label": getattr(cls, "bl_label", ""),
                "description": getattr(cls, "bl_description", ""),
            }
        )
    return tools
