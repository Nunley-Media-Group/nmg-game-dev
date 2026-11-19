extends "res://addons/nmg_game_dev/tests/nmg_test_case.gd"
## NmgAssets variant routing: Desktop, Mobile, and every malformed shape.

const NmgAssetsScript: GDScript = preload("res://addons/nmg_game_dev/nmg_assets.gd")
const CRATE: String = "res://assets/Props/Crate/Crate.glb"


func _resolve(path: String, mobile: bool) -> String:
	var assets: Node = NmgAssetsScript.new()
	var resolved: String = assets.resolve_variant_path_for(path, mobile)
	assets.free()
	return resolved


## Resolve a malformed path and check it comes back unchanged with exactly one NmgAssets warning.
func _check_unchanged_with_warning(path: String, mobile: bool, label: String) -> void:
	take_warnings()
	check_eq(_resolve(path, mobile), path, label)
	var warnings: PackedStringArray = take_warnings()
	check_eq(warnings.size(), 1, "%s: warnings logged" % label)
	if warnings.size() == 1:
		check(
			warnings[0].contains("NmgAssets:") and warnings[0].contains("unchanged"),
			"%s: warning text %s" % [label, warnings[0]],
		)


func test_desktop_variant() -> void:
	take_warnings()
	check_eq(_resolve(CRATE, false), "res://assets/Props/Crate/Desktop/Crate.glb", "desktop")
	check_eq(take_warnings().size(), 0, "desktop: no warning")


func test_mobile_variant() -> void:
	take_warnings()
	check_eq(_resolve(CRATE, true), "res://assets/Props/Crate/Mobile/Crate.glb", "mobile")
	check_eq(take_warnings().size(), 0, "mobile: no warning")


func test_malformed_path_is_unchanged_with_a_warning() -> void:
	_check_unchanged_with_warning("res://assets/Props/Crate/Barrel.glb", true, "malformed")


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
	_check_unchanged_with_warning("", true, "empty")


func test_path_with_desktop_folder_is_unchanged() -> void:
	var path: String = "res://assets/Props/Crate/Desktop/Crate.glb"
	_check_unchanged_with_warning(path, true, "already Desktop")


func test_path_with_mobile_folder_is_unchanged() -> void:
	var path: String = "res://assets/Props/Crate/Mobile/Crate.glb"
	_check_unchanged_with_warning(path, false, "already Mobile")


func test_path_without_parent_folder_is_unchanged() -> void:
	_check_unchanged_with_warning("Crate.glb", false, "bare file")
	_check_unchanged_with_warning("res://Crate.glb", false, "file at res root")


func test_stem_not_matching_folder_is_unchanged() -> void:
	var path: String = "res://assets/Props/Crate/Barrel.glb"
	_check_unchanged_with_warning(path, true, "stem differs from folder")
