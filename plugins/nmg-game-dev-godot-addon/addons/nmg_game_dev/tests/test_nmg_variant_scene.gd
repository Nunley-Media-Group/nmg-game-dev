extends "res://addons/nmg_game_dev/tests/nmg_test_case.gd"
## NmgVariantScene: the variant-neutral loader /design puts in a region for its terrain.
##
## Variant scenes are written under user:// for each test and removed afterwards, so the tests do
## not depend on what the host project's res://assets/ holds.

const VariantSceneScript: GDScript = preload("res://addons/nmg_game_dev/nmg_variant_scene.gd")
const VALLEY: String = "res://assets/Terrain/Valley/Valley.tscn"
const ROOT: String = "user://nmg_variant_scene_test"
const PROBE: String = ROOT + "/Probe/Probe.tscn"


func _node(path: String) -> Node3D:
	var node: Node3D = VariantSceneScript.new()
	node.set("scene_path", path)
	return node


## Save a one-node scene named variant_name at the Desktop or Mobile variant of PROBE.
func _write_variant(mobile: bool, variant_name: String) -> void:
	var root: Node3D = Node3D.new()
	root.name = variant_name
	var packed: PackedScene = PackedScene.new()
	packed.pack(root)
	root.free()
	var path: String = _variant_path_for(mobile)
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	check_eq(ResourceSaver.save(packed, path), OK, "save %s" % path)


func _variant_path_for(mobile: bool) -> String:
	return "%s/Probe/%s/Probe.tscn" % [ROOT, "Mobile" if mobile else "Desktop"]


func _remove_variants() -> void:
	for mobile: bool in [false, true]:
		var path: String = _variant_path_for(mobile)
		DirAccess.remove_absolute(path)
		DirAccess.remove_absolute(path.get_base_dir())
	DirAccess.remove_absolute(ROOT + "/Probe")
	DirAccess.remove_absolute(ROOT)


func test_variant_path_routes_desktop_and_mobile() -> void:
	var node: Node3D = _node(VALLEY)
	check_eq(
		node.call("variant_path", false),
		"res://assets/Terrain/Valley/Desktop/Valley.tscn",
		"desktop"
	)
	check_eq(
		node.call("variant_path", true),
		"res://assets/Terrain/Valley/Mobile/Valley.tscn",
		"mobile"
	)
	node.free()


func test_a_missing_variant_instances_nothing_with_a_warning() -> void:
	_remove_variants()
	var node: Node3D = _node(PROBE)
	take_warnings()
	check_eq(node.call("instance_variant", true), null, "no child")
	check_eq(node.get_child_count(), 0, "child count")
	var warnings: PackedStringArray = take_warnings()
	check_eq(warnings.size(), 1, "warnings logged")
	if warnings.size() == 1:
		check(warnings[0].contains("NmgVariantScene:"), "warning text %s" % warnings[0])
	node.free()


func test_an_existing_variant_is_instanced_as_an_unowned_child() -> void:
	_write_variant(false, "DesktopProbe")
	_write_variant(true, "MobileProbe")
	for mobile: bool in [false, true]:
		var node: Node3D = _node(PROBE)
		var child: Node = node.call("instance_variant", mobile)
		check(child != null, "instanced (mobile=%s)" % mobile)
		check_eq(node.get_child_count(), 1, "child count (mobile=%s)" % mobile)
		if child != null:
			check_eq(String(child.name), "MobileProbe" if mobile else "DesktopProbe", "variant")
			check_eq(child.owner, null, "unowned, so never saved")
		node.free()
	_remove_variants()


func test_the_editor_preview_shows_the_desktop_variant_once() -> void:
	_write_variant(false, "DesktopProbe")
	var node: Node3D = _node(PROBE)
	node.call("preview")
	var child: Node = node.call("preview")
	check_eq(node.get_child_count(), 1, "a second preview replaces the first")
	if child != null:
		check_eq(String(child.name), "DesktopProbe", "preview variant")
		check_eq(child.owner, null, "the preview is never saved")
	node.set("scene_path", "")
	check_eq(node.call("preview"), null, "no preview without a scene_path")
	check_eq(node.get_child_count(), 0, "an empty scene_path clears the preview")
	node.free()
	_remove_variants()
