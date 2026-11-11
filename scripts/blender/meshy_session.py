"""Live-session operations for Meshy: collection state, GLB import and export, and map wiring (#98).

The host sets two globals and then exec's this file through the Blender MCP execute_code tool, the
same contract as scripts/blender/finalize_session.py:

    NMG_OP = "collection_state" | "import_glb" | "export_glb" | "apply_maps"
    NMG_PAYLOAD = {...}

    collection_state: {"name"}                        -> {"ok", "state": missing|exists|no_mesh}
    import_glb:       {"name", "path", "pose"?,       -> {"ok", "collection", "mesh", "material",
                       "raise_arms"?}                      "merged_vertices", "origin_offset",
                                                          "arm_raise"}
    export_glb:       {"name", "path"}                -> {"ok", "path", "meshes"}
    apply_maps:       {"name", "maps": {kind: path}}  -> {"ok", "material", "maps"}

``<Name>`` is the collection, ``SM_<Name>`` its root mesh, and ``M_<Name>_Body`` its material.
``import_glb`` also welds the mesh, bakes its transform, moves its origin to the bottom center at
the world origin, and smooths its normals. ``merged_vertices`` counts the vertices the weld removed,
and ``origin_offset`` is the [x, y, z] translation it applied to the geometry, in meters.
When ``pose`` is ``a-pose`` and ``raise_arms`` is not false, ``import_glb`` also raises each arm
about its detected shoulder to a 48 degree drop, so ``rig_humanoid`` accepts it (#106, #135).
``arm_raise`` holds ``{"left", "right"}``, and each side reports ``detected``. A detected side also
reports ``shoulder`` and ``hand_tip`` as world-space [x, y, z] in meters after the raise,
``drop_before_deg``, ``drop_after_deg``, and ``rotation_deg`` (0 when that side is already
compliant). An undetected side reports ``detected`` false, ``reason`` ``no_armpit``, null points and
drops, and ``rotation_deg`` 0; it moves no vertex. ``arm_raise`` is ``null`` for any other pose, for
none, or when ``raise_arms`` is false.
Each run prints exactly one line, NMG_RESULT <json>. Failures come back as
{"ok": false, "error": {"code", "message", "remediation"}} and never raise into the session.
Nodes are created here, and every lookup goes by data type or by the datablock name this script set,
never by a localized node name.
"""

import json
import math

import bmesh
import bpy
from mathutils import Matrix, Vector

NOT_FOUND = "meshy.collection_not_found"
EXISTS = "meshy.collection_exists"
SESSION_FAILED = "meshy.session_failed"
WELD_DISTANCE = 1e-5
SMOOTH_ANGLE_DEG = 30
# A-pose arm raise (#106, #135). Each shoulder is found from the mesh's horizontal slices, the arm
# is tracked down from its armpit, and the arm rotates about its shoulder to a 48 degree drop.
# Lengths in the slice rules are fractions of the height H.
TARGET_DROP_DEG = 48.0
SLICE_STEP = 0.005
SLICE_GAP = 0.002
ARMPIT_RUN = 0.05
ARM_GROWTH = 2.0
BLEND_WIDTH = 0.04
ARM_SIDES = (("left", 1.0), ("right", -1.0))
NO_ARMPIT = "no_armpit"
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


def _drop_deg(pivot, point):
    """Return how many degrees the line from ``pivot`` to ``point`` falls below horizontal."""
    horizontal = math.hypot(point[0] - pivot[0], point[1] - pivot[1])
    return math.degrees(math.atan2(pivot[2] - point[2], horizontal))


def _raise_point(point, pivot, angle):
    """Rotate ``point`` about the Y axis through ``pivot`` by ``angle`` radians, right-hand rule."""
    dx = point[0] - pivot[0]
    dz = point[2] - pivot[2]
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    return (
        pivot[0] + cos_a * dx + sin_a * dz,
        point[1],
        pivot[2] - sin_a * dx + cos_a * dz,
    )


def _undetected():
    return {
        "detected": False,
        "reason": NO_ARMPIT,
        "shoulder": None,
        "hand_tip": None,
        "drop_before_deg": None,
        "drop_after_deg": None,
        "rotation_deg": 0.0,
    }


def _slice_z(z_top, step, index):
    """Return the height of slice ``index``, which sits half a step below its grid line."""
    return z_top - (index + 0.5) * step


class _Slices:
    """The mesh's horizontal silhouettes, one per slice from the top down, with their X intervals.

    ``intervals[index]`` is slice ``index``'s sorted, non-overlapping list of (low, high) X ranges.
    """

    def __init__(self, z_top, step, intervals):
        self.z_top = z_top
        self.step = step
        self.intervals = intervals

    def z(self, index):
        return _slice_z(self.z_top, self.step, index)

    def nearest(self, z):
        return round((self.z_top - z) / self.step - 0.5)


def _triangles(points, mesh):
    """Return the mesh's faces as world-space fan triangles."""
    triangles = []
    for poly in mesh.polygons:
        indices = poly.vertices
        first = points[indices[0]]
        for index in range(1, len(indices) - 1):
            triangles.append((first, points[indices[index]], points[indices[index + 1]]))
    return triangles


def _chords(triangles, z):
    """Return each triangle's X range where the plane at height ``z`` cuts it.

    A triangle counts for the planes with its lowest z <= ``z`` < its highest z, so each cut has
    exactly two edge crossings and no vertex on the plane is counted twice.
    """
    chords = []
    for tri in triangles:
        crossings = []
        for start, end in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            if min(start[2], end[2]) <= z < max(start[2], end[2]):
                t = (z - start[2]) / (end[2] - start[2])
                crossings.append(start[0] + t * (end[0] - start[0]))
        if len(crossings) == 2:
            chords.append((min(crossings), max(crossings)))
    return chords


def _union(chords, gap):
    """Return the sorted intervals of ``chords``, merging ranges that overlap or sit within gap."""
    merged = []
    for low, high in sorted(chords):
        if merged and low - merged[-1][1] < gap:
            merged[-1] = (merged[-1][0], max(merged[-1][1], high))
        else:
            merged.append((low, high))
    return merged


def _slice_mesh(points, mesh, height):
    """Slice the mesh from its top down to its bottom in steps of SLICE_STEP·H."""
    zs = [point[2] for point in points]
    z_top = max(zs)
    step = SLICE_STEP * height
    count = max(0, math.floor((z_top - min(zs)) / step - 0.5) + 1)
    buckets = [[] for _ in range(count)]
    for tri in _triangles(points, mesh):
        low = min(tri[0][2], tri[1][2], tri[2][2])
        high = max(tri[0][2], tri[1][2], tri[2][2])
        if high <= low:
            continue
        first = max(0, math.floor((z_top - high) / step - 0.5) + 1)
        last = min(count - 1, math.floor((z_top - low) / step - 0.5))
        for index in range(first, last + 1):
            buckets[index].append(tri)
    intervals = []
    for index, bucket in enumerate(buckets):
        z = _slice_z(z_top, step, index)
        intervals.append(_union(_chords(bucket, z), SLICE_GAP * height))
    return _Slices(z_top, step, intervals)


def _containing(intervals, x_c):
    """Return the interval that holds the midline ``x_c``, or None."""
    return next((interval for interval in intervals if interval[0] <= x_c <= interval[1]), None)


def _outermost(intervals, x_c, sign):
    """Return the interval on side ``sign`` that does not hold ``x_c`` and lies farthest out."""
    if sign > 0:
        sides = [interval for interval in intervals if interval[0] > x_c]
        return max(sides, key=lambda interval: interval[1], default=None)
    sides = [interval for interval in intervals if interval[1] < x_c]
    return min(sides, key=lambda interval: interval[0], default=None)


def _find_armpit(intervals, x_c, sign, run):
    """Return the index of the highest slice where the torso and a separate arm both exist.

    The torso and the arm must stay separate for ``run`` slices below that slice. Returns None when
    no such slice exists on side ``sign``.
    """
    present = [
        _containing(slice_intervals, x_c) is not None
        and _outermost(slice_intervals, x_c, sign) is not None
        for slice_intervals in intervals
    ]
    for index in range(len(intervals) - run):
        if all(present[index : index + run + 1]):
            return index
    return None


def _track_arm(intervals, x_c, sign, armpit):
    """Walk the arm down from the armpit slice; return its (slice, low, high) list and drift.

    Each slice's arm interval must be the one that overlaps the previous arm interval, carried along
    the arm's drift from the slice before. Tracking stops when no interval overlaps, when more than
    one overlaps, or when the overlapping interval is wider than ARM_GROWTH times the previous one.
    The drift is the change in the arm's midpoint over the last slice. A tapering arm narrows below
    the drift per slice near its tip, so the carried overlap is what lets tracking reach the tip.
    """
    first = _outermost(intervals[armpit], x_c, sign)
    tracked = [(armpit, first[0], first[1])]
    drift = 0.0
    for index in range(armpit + 1, len(intervals)):
        _, prev_low, prev_high = tracked[-1]
        found = [
            (low, high)
            for low, high in intervals[index]
            if not (low <= x_c <= high) and low <= prev_high + drift and high >= prev_low + drift
        ]
        if len(found) != 1:
            break
        low, high = found[0]
        if high - low > ARM_GROWTH * (prev_high - prev_low):
            break
        drift = (low + high) / 2 - (prev_low + prev_high) / 2
        tracked.append((index, low, high))
    return tracked, drift


def _raise_side(points, slices, x_c, sign, height):
    """Detect and raise one arm; return its report and the moved vertices (index to new point).

    The arm is the vertices below the armpit whose X lies in the tracked interval of their nearest
    slice, plus the shoulder cap: the vertices at or above the armpit, outboard of the torso's edge,
    within the armpit interval's width of the shoulder. The shoulder is where the line fitted
    through the tracked midpoints meets the torso's edge. The hand tip is the arm vertex farthest
    from it.
    """
    run = round(ARMPIT_RUN / SLICE_STEP)
    armpit = _find_armpit(slices.intervals, x_c, sign, run)
    if armpit is None:
        return _undetected(), {}
    torso = _containing(slices.intervals[armpit], x_c)
    x_edge = torso[1] if sign > 0 else torso[0]
    tracked, drift = _track_arm(slices.intervals, x_c, sign, armpit)
    armpit_z = slices.z(armpit)
    last = armpit + len(tracked) - 1
    tolerance = SLICE_GAP * height + abs(drift)
    below = []
    for index, point in enumerate(points):
        if not (slices.z(last) - slices.step <= point[2] < armpit_z):
            continue
        _, low, high = tracked[min(max(slices.nearest(point[2]), armpit), last) - armpit]
        if low - tolerance <= point[0] <= high + tolerance:
            below.append(index)

    count = len(tracked)
    samples = [(slices.z(index), (low + high) / 2) for index, low, high in tracked]
    mean_z = sum(z for z, _ in samples) / count
    mean_x = sum(x for _, x in samples) / count
    spread = sum((z - mean_z) ** 2 for z, _ in samples)
    slope = sum((z - mean_z) * (x - mean_x) for z, x in samples) / spread if spread > 0 else 0.0
    intercept = mean_x - slope * mean_z
    if abs(slope) < 1e-6:
        shoulder_z = armpit_z
    else:
        shoulder_z = (x_edge - intercept) / slope
    ys = [points[index][1] for index in below]
    shoulder_y = (min(ys) + max(ys)) / 2 if ys else 0.0
    shoulder = (x_edge, shoulder_y, shoulder_z)

    reach = tracked[0][2] - tracked[0][1]
    cap = [
        index
        for index, point in enumerate(points)
        if point[2] >= armpit_z
        and sign * (point[0] - x_edge) > 0
        and math.dist(point, shoulder) <= reach
    ]
    selected = below + cap
    if not selected:
        return _undetected(), {}
    tip = max(selected, key=lambda index: math.dist(points[index], shoulder))
    length = math.dist(points[tip], shoulder)
    selected = [index for index in selected if math.dist(points[index], shoulder) <= length]

    drop = _drop_deg(shoulder, points[tip])
    excess = drop - TARGET_DROP_DEG
    blend = BLEND_WIDTH * height
    moved = {}
    if excess > 0:
        for index in selected:
            weight = min(1.0, sign * (points[index][0] - x_edge) / blend)
            if weight > 0:
                angle = math.radians(-sign * weight * excess)
                moved[index] = _raise_point(points[index], shoulder, angle)
    tip_after = moved.get(tip, points[tip])
    report = {
        "detected": True,
        "shoulder": [round(value, 6) for value in shoulder],
        "hand_tip": [round(value, 6) for value in tip_after],
        "drop_before_deg": round(drop, 2),
        "drop_after_deg": round(_drop_deg(shoulder, tip_after), 2),
        "rotation_deg": round(excess, 2) if excess > 0 else 0.0,
    }
    return report, moved


def _raise_arms(obj):
    """Raise each arm of the A-pose ``obj`` about its detected shoulder to a 48 degree drop (#135).

    Each side's shoulder is found from the mesh's horizontal slices, not from fixed proportions, and
    only the arm is moved: the vertices of the arm's tracked slices below the armpit and of its cap.
    No vertex farther from the shoulder than the arm's length moves. A side with no armpit moves no
    vertex and reports ``detected`` false. A side at or under the target keeps every vertex. This is
    vertex math only: no modifier and no armature, so counts, connectivity, and winding are kept.
    Returns each side's report, in degrees and meters.
    """
    mesh = obj.data
    to_world = obj.matrix_world
    to_local = to_world.inverted()
    points = [tuple(to_world @ vertex.co) for vertex in mesh.vertices]
    xs = [point[0] for point in points]
    zs = [point[2] for point in points]
    height = max(zs) - min(zs)
    if not points or height <= 0:
        return {"left": _undetected(), "right": _undetected()}
    x_c = (min(xs) + max(xs)) / 2
    slices = _slice_mesh(points, mesh, height)
    report = {}
    moved = {}
    for side, sign in ARM_SIDES:
        report[side], side_moved = _raise_side(points, slices, x_c, sign, height)
        moved.update(side_moved)
    for index, point in moved.items():
        mesh.vertices[index].co = to_local @ Vector(point)
    if moved:
        mesh.update()
    return report


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
    raise_arms = payload.get("pose") == "a-pose" and payload.get("raise_arms", True)
    arm_raise = _raise_arms(target) if raise_arms else None
    return {
        "ok": True,
        "collection": collection.name,
        "mesh": target.name,
        "material": material.name,
        **normalized,
        "arm_raise": arm_raise,
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
