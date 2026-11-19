# Headless import probe for one finalized variant (#249 FR1).
#
# Run as: godot --headless --path <project> -s <this script> -- <params.json>
# Params: {"glb": "res://assets/<Category>/<Name>/<Variant>/<Name>.glb"}
# Prints exactly one line:
#   NMG_RESULT {"meshes": [{"name", "tris", "material_slots", "bounds": {"min", "max"}}]}
# tris is the sum over surfaces of index count / 3 (vertex count / 3 without indices). bounds is
# each mesh's AABB transformed into the scene root's space, in metres.
extends SceneTree


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	if args.is_empty():
		push_error("probe_asset.gd needs the params JSON path after --")
		quit(1)
		return
	var params: Variant = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	if not params is Dictionary:
		push_error("probe_asset.gd could not read params from %s" % args[0])
		quit(1)
		return
	var scene := load(String(params["glb"])) as PackedScene
	if scene == null:
		push_error("probe_asset.gd could not load %s" % params["glb"])
		quit(1)
		return
	var root := scene.instantiate()
	var meshes: Array = []
	for child in root.get_children():
		_walk(child, Transform3D.IDENTITY, meshes)
	root.free()
	print("NMG_RESULT " + JSON.stringify({"meshes": meshes}))
	quit(0)


func _walk(node: Node, parent_xform: Transform3D, meshes: Array) -> void:
	var xform := parent_xform
	if node is Node3D:
		xform = parent_xform * (node as Node3D).transform
	if node is MeshInstance3D and (node as MeshInstance3D).mesh != null:
		var mesh := (node as MeshInstance3D).mesh
		var box: AABB = xform * mesh.get_aabb()
		meshes.append({
			"name": String(node.name),
			"tris": _triangles(mesh),
			"material_slots": mesh.get_surface_count(),
			"bounds": {
				"min": [box.position.x, box.position.y, box.position.z],
				"max": [box.end.x, box.end.y, box.end.z],
			},
		})
	for child in node.get_children():
		_walk(child, xform, meshes)


func _triangles(mesh: Mesh) -> int:
	var total := 0
	for surface in mesh.get_surface_count():
		var arrays := mesh.surface_get_arrays(surface)
		var indices: Variant = arrays[Mesh.ARRAY_INDEX]
		if indices != null and (indices as PackedInt32Array).size() > 0:
			total += (indices as PackedInt32Array).size() / 3
		else:
			total += (arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array).size() / 3
	return total
