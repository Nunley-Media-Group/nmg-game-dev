"""Live-session operations for Meshy: collection state, GLB import and export, and map wiring (#98).

The host sets two globals and then exec's this file through the Blender MCP execute_code tool, the
same contract as scripts/blender/finalize_session.py:

    NMG_OP = "collection_state" | "import_glb" | "export_glb" | "apply_maps"
    NMG_PAYLOAD = {...}

    collection_state: {"name"}                        -> {"ok", "state": missing|exists|no_mesh}
    import_glb:       {"name", "path"}                -> {"ok", "collection", "mesh", "material",
                                                          "merged_vertices", "origin_offset"}
    export_glb:       {"name", "path"}                -> {"ok", "path", "meshes"}
    apply_maps:       {"name", "maps": {kind: path}}  -> {"ok", "material", "maps"}

``<Name>`` is the collection, ``SM_<Name>`` its root mesh, and ``M_<Name>_Body`` its material.
``import_glb`` also welds the mesh, bakes its transform, moves its origin to the bottom center at
the world origin, and smooths its normals. ``merged_vertices`` counts the vertices the weld removed,
and ``origin_offset`` is the [x, y, z] translation it applied to the geometry, in meters.
Each run prints exactly one line, NMG_RESULT <json>. Failures come back as
{"ok": false, "error": {"code", "message", "remediation"}} and never raise into the session.
Nodes are created here, and every lookup goes by data type or by the datablock name this script set,
never by a localized node name.
"""

import json
import math

import bmesh
import bpy
from mathutils import Matrix

NOT_FOUND = "meshy.collection_not_found"
EXISTS = "meshy.collection_exists"
SESSION_FAILED = "meshy.session_failed"
WELD_DISTANCE = 1e-5
SMOOTH_ANGLE_DEG = 30
MAP_INPUTS = {
    "base_color": ("Base Color", "sRGB"),
    "roughness": ("Roughness", "Non-Color"),
    "metallic": ("Metallic", "Non-Color"),
}


def _fail(code, message, remediation):
    return {
        "ok": False,
        "error": {"code": code, "message": message, "remediation": remediation},
    }


def _mesh_name(name):
    return f"SM_{name}"


def _material_name(name):
    return f"M_{name}_Body"


def _mesh_object(name):
    """Return (collection, SM object); either is None when it is missing."""
    collection = bpy.data.collections.get(name)
    if collection is None:
        return None, None
    obj = collection.objects.get(_mesh_name(name))
    if obj is None or obj.type != "MESH":
        return collection, None
    return collection, obj


def _collection_state(payload):
    name = payload["name"]
    collection, obj = _mesh_object(name)
    if collection is None:
        state = "missing"
    elif obj is None:
        state = "no_mesh"
    else:
        state = "exists"
    return {"ok": True, "state": state}


class _NormalizeStepError(Exception):
    """A normalization step failed; the message names the step."""


def _weld(mesh):
    """Merge vertices within WELD_DISTANCE, recalculate face normals, and return the merge count."""
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        before = len(bm.verts)
        bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=WELD_DISTANCE)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        merged = before - len(bm.verts)
        bm.to_mesh(mesh)
    finally:
        bm.free()
    return merged


def _recenter(mesh):
    """Translate the geometry so its bottom center is at the origin, and return the translation."""
    if not mesh.vertices:
        raise _NormalizeStepError("Recentering the mesh failed: it has no vertices.")
    xs = [vertex.co.x for vertex in mesh.vertices]
    ys = [vertex.co.y for vertex in mesh.vertices]
    zs = [vertex.co.z for vertex in mesh.vertices]
    offset = (-(min(xs) + max(xs)) / 2, -(min(ys) + max(ys)) / 2, -min(zs))
    mesh.transform(Matrix.Translation(offset))
    return offset


def _fix_normals(obj):
    """Clear custom split normals, then smooth by angle, keeping edges sharper than the angle."""
    if obj.data.has_custom_normals:
        try:
            with bpy.context.temp_override(object=obj, active_object=obj):
                bpy.ops.mesh.customdata_custom_splitnormals_clear()
        except RuntimeError as error:
            raise _NormalizeStepError(f"Clearing the custom normals failed: {error}.") from error
    try:
        with bpy.context.temp_override(
            selected_editable_objects=[obj], active_object=obj, object=obj
        ):
            bpy.ops.object.shade_smooth_by_angle(
                angle=math.radians(SMOOTH_ANGLE_DEG), keep_sharp_edges=True
            )
    except RuntimeError as error:
        raise _NormalizeStepError(
            f"Smoothing by {SMOOTH_ANGLE_DEG} degrees failed: {error}."
        ) from error


def _normalize(obj):
    """Bake the transform, weld, recenter to the bottom center, and fix the normals of ``obj``.

    Returns the numbers the import result reports. Raises _NormalizeStepError on a failed step.
    """
    mesh = obj.data
    mesh.transform(obj.matrix_world)
    obj.matrix_world = Matrix.Identity(4)
    merged = _weld(mesh)
    offset = _recenter(mesh)
    _fix_normals(obj)
    return {"merged_vertices": merged, "origin_offset": [round(value, 6) for value in offset]}


def _import_glb(payload):
    name = payload["name"]
    if bpy.data.collections.get(name) is not None:
        return _fail(
            EXISTS,
            f"The open file already has a collection named {name!r}.",
            f"Pick another name, or delete the {name} collection in Blender, then retry.",
        )
    existing = set(bpy.data.objects.keys())
    bpy.ops.import_scene.gltf(filepath=payload["path"])
    imported = [bpy.data.objects[key] for key in bpy.data.objects.keys() if key not in existing]

    meshes = [obj for obj in imported if obj.type == "MESH"]
    if not meshes:
        for obj in imported:
            bpy.data.objects.remove(obj, do_unlink=True)
        return _fail(
            SESSION_FAILED,
            "The GLB holds no mesh objects.",
            "Export the model with at least one mesh, then retry.",
        )

    collection = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(collection)
    for obj in imported:
        for owner in list(obj.users_collection):
            owner.objects.unlink(obj)
        collection.objects.link(obj)

    for obj in meshes:
        world = obj.matrix_world.copy()
        obj.parent = None
        obj.matrix_world = world
    for obj in imported:
        if obj.type != "MESH":
            bpy.data.objects.remove(obj, do_unlink=True)

    target = meshes[0]
    if len(meshes) > 1:
        with bpy.context.temp_override(active_object=target, selected_editable_objects=meshes):
            bpy.ops.object.join()

    target.name = _mesh_name(name)
    target.data.name = _mesh_name(name)
    material = target.data.materials[0] if len(target.data.materials) else None
    if material is None:
        material = bpy.data.materials.new(_material_name(name))
        if len(target.data.materials):
            target.data.materials[0] = material
        else:
            target.data.materials.append(material)
    material.name = _material_name(name)
    try:
        normalized = _normalize(target)
    except _NormalizeStepError as error:
        return _fail(
            SESSION_FAILED,
            f"{error} The {name} collection stays in the open file.",
            f"Delete the {name} collection in Blender, then retry.",
        )
    return {
        "ok": True,
        "collection": collection.name,
        "mesh": target.name,
        "material": material.name,
        **normalized,
    }


def _export_glb(payload):
    name = payload["name"]
    collection, obj = _mesh_object(name)
    if obj is None:
        return _fail(
            NOT_FOUND,
            f"No collection {name!r} with mesh {_mesh_name(name)!r} is in the open file.",
            "Retexture needs the collection that generate_model or an import created. "
            "Check the name.",
        )
    meshes = [item for item in collection.all_objects if item.type == "MESH"]
    view_layer = bpy.context.view_layer
    previous_selection = list(bpy.context.selected_objects)
    previous_active = view_layer.objects.active
    for item in view_layer.objects:
        item.select_set(False)
    for item in meshes:
        item.select_set(True)
    view_layer.objects.active = obj
    try:
        bpy.ops.export_scene.gltf(
            filepath=payload["path"],
            export_format="GLB",
            use_selection=True,
        )
    finally:
        for item in view_layer.objects:
            item.select_set(False)
        for item in previous_selection:
            if item.name in view_layer.objects:
                item.select_set(True)
        view_layer.objects.active = previous_active
    return {"ok": True, "path": payload["path"], "meshes": len(meshes)}


def _image_node(tree, path, colorspace):
    image = bpy.data.images.load(path, check_existing=True)
    image.colorspace_settings.name = colorspace
    node = tree.nodes.new("ShaderNodeTexImage")
    node.image = image
    return node


def _apply_maps(payload):
    name = payload["name"]
    maps = payload["maps"]
    collection, obj = _mesh_object(name)
    if obj is None:
        return _fail(
            NOT_FOUND,
            f"No collection {name!r} with mesh {_mesh_name(name)!r} is in the open file.",
            "Retexture needs the collection that generate_model or an import created.",
        )
    unknown = sorted(set(maps) - {"base_color", "normal", "roughness", "metallic"})
    if unknown:
        return _fail(
            SESSION_FAILED,
            f"Unknown map kinds: {unknown}.",
            "Use base_color, normal, roughness, or metallic.",
        )

    material = bpy.data.materials.get(_material_name(name))
    if material is None:
        material = bpy.data.materials.new(_material_name(name))
    if material.node_tree is None:
        material.use_nodes = True
    tree = material.node_tree
    tree.nodes.clear()
    bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
    output = tree.nodes.new("ShaderNodeOutputMaterial")
    tree.links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])

    for kind, path in sorted(maps.items()):
        if kind == "normal":
            texture = _image_node(tree, path, "Non-Color")
            normal_map = tree.nodes.new("ShaderNodeNormalMap")
            tree.links.new(texture.outputs["Color"], normal_map.inputs["Color"])
            tree.links.new(normal_map.outputs["Normal"], bsdf.inputs["Normal"])
        else:
            socket, colorspace = MAP_INPUTS[kind]
            texture = _image_node(tree, path, colorspace)
            tree.links.new(texture.outputs["Color"], bsdf.inputs[socket])

    obj.data.materials.clear()
    obj.data.materials.append(material)
    return {"ok": True, "material": material.name, "maps": sorted(maps)}


_OPERATIONS = {
    "collection_state": _collection_state,
    "import_glb": _import_glb,
    "export_glb": _export_glb,
    "apply_maps": _apply_maps,
}


def _dispatch(op, payload):
    handler = _OPERATIONS.get(op)
    if handler is None:
        return _fail(
            SESSION_FAILED,
            f"Unknown session operation {op!r}.",
            "Use collection_state, import_glb, export_glb, or apply_maps.",
        )
    return handler(payload)


try:
    _nmg_result = _dispatch(NMG_OP, NMG_PAYLOAD)  # noqa: F821 - set by the host before exec
except Exception as _error:  # noqa: BLE001 - report every failure as a result line
    _nmg_result = _fail(
        SESSION_FAILED,
        str(_error),
        "Check the Blender console for the traceback, then rerun.",
    )

print("NMG_RESULT " + json.dumps(_nmg_result, sort_keys=True, default=str), flush=True)
