# Headless animation-clip probe for import_anims (#249 FR3).
#
# Run as: godot --headless --path <project> -s <this script> -- <params.json>
# Params:
#   {"clips": [{"name": "Walk", "path": "res://.../Animations/A_<Name>_Walk.glb", "fps": 30.0}],
#    "skeletons": ["res://.../Desktop/<Name>.glb", ...]}
# Prints exactly one line:
#   NMG_RESULT {"clips": {"Walk": {"animation", "frame_count", "bones"}},
#               "skeletons": {"<glb>": {"found", "bones"}}}
# Each clip loads as the AnimationLibrary the animation_library importer produced. animation is its
# first animation's name, frame_count is round(length * fps), and bones lists the bone names its
# tracks drive (the subname after ":" in each track path). A clip that does not load is omitted.
# Each skeleton entry reports whether the scene loaded and the bone names of its Skeleton3D nodes.
extends SceneTree


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	if args.is_empty():
		push_error("probe_anims.gd needs the params JSON path after --")
		quit(1)
		return
	var params: Variant = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	if not params is Dictionary:
		push_error("probe_anims.gd could not read params from %s" % args[0])
		quit(1)
		return
	var settings := params as Dictionary
	var clips: Dictionary = {}
	for item: Variant in settings.get("clips", []) as Array:
		var clip := item as Dictionary
		var measured := _measure_clip(String(clip["path"]), float(clip.get("fps", 30.0)))
		if not measured.is_empty():
			clips[String(clip["name"])] = measured
	var skeletons: Dictionary = {}
	for item: Variant in settings.get("skeletons", []) as Array:
		skeletons[String(item)] = _skeleton_bones(String(item))
	print("NMG_RESULT " + JSON.stringify({"clips": clips, "skeletons": skeletons}))
	quit(0)


func _measure_clip(path: String, fps: float) -> Dictionary:
	if not ResourceLoader.exists(path):
		return {}
	var library := load(path) as AnimationLibrary
	if library == null:
		return {}
	var names := library.get_animation_list()
	if names.is_empty():
		return {}
	var animation := library.get_animation(names[0])
	var bones: Array = []
	for track in animation.get_track_count():
		var subname := String(animation.track_get_path(track).get_concatenated_subnames())
		if not subname.is_empty() and not bones.has(subname):
			bones.append(subname)
	bones.sort()
	return {
		"animation": String(names[0]),
		"frame_count": roundi(animation.length * fps),
		"bones": bones,
	}


func _skeleton_bones(path: String) -> Dictionary:
	if not ResourceLoader.exists(path):
		return {"found": false, "bones": []}
	var scene := load(path) as PackedScene
	if scene == null:
		return {"found": false, "bones": []}
	var root := scene.instantiate()
	var bones: Array = []
	_collect_bones(root, bones)
	root.free()
	bones.sort()
	return {"found": true, "bones": bones}


func _collect_bones(node: Node, bones: Array) -> void:
	if node is Skeleton3D:
		var skeleton := node as Skeleton3D
		for index in skeleton.get_bone_count():
			var bone := skeleton.get_bone_name(index)
			if not bones.has(bone):
				bones.append(bone)
	for child in node.get_children():
		_collect_bones(child, bones)
