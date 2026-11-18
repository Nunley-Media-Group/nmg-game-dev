# Headless terrain probe for import_godot (#249 FR4).
#
# Run as: godot --headless --path <project> -s <this script> -- <params.json>
# Params, one of:
#   {"mode": "meshes", "glbs": ["res://.../<Name>_Chunk_0_0.glb", ...]}
#     -> NMG_RESULT {"meshes": {"<glb>": ["<MeshInstance3D path relative to the chunk root>", ...]}}
#   {"mode": "scene", "scene": "res://.../<Variant>/<Name>.tscn"}
#     -> NMG_RESULT {"chunks", "height_min", "height_max", "mesh_height_min", "mesh_height_max"}
# chunks counts the root's instanced .glb children. height_min/height_max come from the
# HeightMapShape3D map_data scaled and offset by its CollisionShape3D. mesh_height_min/max is the
# union of the chunk meshes' AABB Y extents in the scene root's space, in metres.
extends SceneTree


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	if args.is_empty():
		push_error("probe_terrain.gd needs the params JSON path after --")
		quit(1)
		return
	var params: Variant = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	if not params is Dictionary:
		push_error("probe_terrain.gd could not read params from %s" % args[0])
		quit(1)
		return
	var settings := params as Dictionary
	var result: Dictionary
	if String(settings.get("mode", "scene")) == "meshes":
		result = _list_meshes(settings.get("glbs", []) as Array)
	else:
		result = _measure(String(settings["scene"]))
	if result.is_empty():
		quit(1)
		return
	print("NMG_RESULT " + JSON.stringify(result))
	quit(0)


func _list_meshes(glbs: Array) -> Dictionary:
	var meshes: Dictionary = {}
	for item: Variant in glbs:
		var path := String(item)
		var scene := load(path) as PackedScene
		if scene == null:
			push_error("probe_terrain.gd could not load %s" % path)
			return {}
		var root := scene.instantiate()
		var found: Array = []
		for child in root.get_children():
			_collect_mesh_paths(root, child, found)
		root.free()
		meshes[path] = found
	return {"meshes": meshes}


func _collect_mesh_paths(root: Node, node: Node, found: Array) -> void:
	if node is MeshInstance3D:
		found.append(String(root.get_path_to(node)))
	for child in node.get_children():
		_collect_mesh_paths(root, child, found)


func _measure(scene_path: String) -> Dictionary:
	var scene := load(scene_path) as PackedScene
	if scene == null:
		push_error("probe_terrain.gd could not load %s" % scene_path)
		return {}
	var root := scene.instantiate() as Node3D
	if root == null:
		push_error("probe_terrain.gd: %s has no Node3D root" % scene_path)
		return {}
	var chunks := 0
	var bounds: Array = [INF, -INF]
	var heights: Array = [INF, -INF]
	for child in root.get_children():
		if child.scene_file_path.ends_with(".glb"):
			chunks += 1
			_mesh_extent(child, (child as Node3D).transform, bounds)
		elif child is StaticBody3D:
			_height_extent(child as Node3D, (child as Node3D).transform, heights)
	root.free()
	if chunks == 0 or bounds[0] == INF or heights[0] == INF:
		push_error("probe_terrain.gd: %s has no chunk meshes or no HeightMapShape3D" % scene_path)
		return {}
	return {
		"chunks": chunks,
		"height_min": heights[0],
		"height_max": heights[1],
		"mesh_height_min": bounds[0],
		"mesh_height_max": bounds[1],
	}


func _mesh_extent(node: Node, xform: Transform3D, bounds: Array) -> void:
	if node is MeshInstance3D and (node as MeshInstance3D).mesh != null:
		var box: AABB = xform * (node as MeshInstance3D).mesh.get_aabb()
		bounds[0] = minf(float(bounds[0]), box.position.y)
		bounds[1] = maxf(float(bounds[1]), box.end.y)
	for child in node.get_children():
		var child_xform := xform
		if child is Node3D:
			child_xform = xform * (child as Node3D).transform
		_mesh_extent(child, child_xform, bounds)


func _height_extent(node: Node3D, xform: Transform3D, heights: Array) -> void:
	if node is CollisionShape3D and (node as CollisionShape3D).shape is HeightMapShape3D:
		var shape := (node as CollisionShape3D).shape as HeightMapShape3D
		for value in shape.map_data:
			var y := (xform * Vector3(0.0, value, 0.0)).y
			heights[0] = minf(float(heights[0]), y)
			heights[1] = maxf(float(heights[1]), y)
	for child in node.get_children():
		if child is Node3D:
			_height_extent(child as Node3D, xform * (child as Node3D).transform, heights)
