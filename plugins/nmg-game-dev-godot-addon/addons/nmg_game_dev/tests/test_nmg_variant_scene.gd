extends "res://addons/nmg_game_dev/tests/nmg_test_case.gd"
## NmgVariantScene: the variant-neutral loader /design puts in a region for its terrain.

const VariantSceneScript: GDScript = preload("res://addons/nmg_game_dev/nmg_variant_scene.gd")
const VALLEY: String = "res://assets/Terrain/Valley/Valley.tscn"


func _node(path: String) -> Node3D:
	var node: Node3D = VariantSceneScript.new()
	node.set("scene_path", path)
	return node


func test_variant_path_routes_desktop_and_mobile() -> void:
	var node: Node3D = _node(VALLEY)
	check_eq(node.call("variant_path", false), "res://assets/Terrain/Valley/Desktop/Valley.tscn", "desktop")
	check_eq(node.call("variant_path", true), "res://assets/Terrain/Valley/Mobile/Valley.tscn", "mobile")
	node.free()


func test_a_missing_variant_instances_nothing_with_a_warning() -> void:
	var node: Node3D = _node(VALLEY)
	take_warnings()
	check_eq(node.call("instance_variant", true), null, "no child")
	check_eq(node.get_child_count(), 0, "child count")
	var warnings: PackedStringArray = take_warnings()
	check_eq(warnings.size(), 1, "warnings logged")
	if warnings.size() == 1:
		check(warnings[0].contains("NmgVariantScene:"), "warning text %s" % warnings[0])
	node.free()
