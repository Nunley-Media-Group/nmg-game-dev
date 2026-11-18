extends "res://addons/nmg_game_dev/tests/nmg_test_case.gd"
## NmgAssets variant routing: Desktop, Mobile, and every malformed shape.

const NmgAssetsScript: GDScript = preload("res://addons/nmg_game_dev/nmg_assets.gd")
const CRATE: String = "res://assets/Props/Crate/Crate.glb"


func _resolve(path: String, mobile: bool) -> String:
	var assets: Node = NmgAssetsScript.new()
	var resolved: String = assets.resolve_variant_path_for(path, mobile)
	assets.free()
	return resolved


func test_desktop_variant() -> void:
	check_eq(_resolve(CRATE, false), "res://assets/Props/Crate/Desktop/Crate.glb", "desktop")


func test_mobile_variant() -> void:
	check_eq(_resolve(CRATE, true), "res://assets/Props/Crate/Mobile/Crate.glb", "mobile")


func test_resolve_variant_path_matches_the_running_platform() -> void:
	var assets: Node = NmgAssetsScript.new()
	var mobile: bool = OS.has_feature("mobile") or OS.has_feature("web")
	check_eq(assets.resolve_variant_path(CRATE), _resolve(CRATE, mobile), "running platform")
	assets.free()


func test_other_extensions_route_too() -> void:
	check_eq(
		_resolve("res://assets/Terrain/Hills/Hills.tscn", true),
		"res://assets/Terrain/Hills/Mobile/Hills.tscn",
		"terrain scene",
	)


func test_empty_path_is_unchanged() -> void:
	check_eq(_resolve("", true), "", "empty")


func test_path_with_desktop_folder_is_unchanged() -> void:
	var path: String = "res://assets/Props/Crate/Desktop/Crate.glb"
	check_eq(_resolve(path, true), path, "already Desktop")


func test_path_with_mobile_folder_is_unchanged() -> void:
	var path: String = "res://assets/Props/Crate/Mobile/Crate.glb"
	check_eq(_resolve(path, false), path, "already Mobile")


func test_path_without_parent_folder_is_unchanged() -> void:
	check_eq(_resolve("Crate.glb", false), "Crate.glb", "bare file")
	check_eq(_resolve("res://Crate.glb", false), "res://Crate.glb", "file at res root")


func test_stem_not_matching_folder_is_unchanged() -> void:
	var path: String = "res://assets/Props/Crate/Barrel.glb"
	check_eq(_resolve(path, true), path, "stem differs from folder")
